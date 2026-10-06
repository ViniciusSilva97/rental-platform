from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import ToolUnit
from apps.offerings.models import Offering, OfferingStock
from apps.organizations.models import Membership
from apps.reservations.models import (
    Reservation,
    ReservationAllocation,
    ReservationOffering,
)

from .models import Contract, ContractItem, ContractOffering


def _validate_organization(organization):
    if not organization or not organization.active:
        raise ValidationError("A organização atual precisa estar ativa.")


def _locked_contract(*, organization, contract):
    try:
        return (
            Contract.objects.select_for_update()
            .select_related("reservation")
            .get(pk=contract.pk, organization=organization)
        )
    except Contract.DoesNotExist as error:
        raise ValidationError("Selecione um contrato da organização atual.") from error


def _validate_operator(*, organization, user):
    if not user or not user.is_authenticated:
        raise ValidationError("Um usuário autenticado deve registrar a operação.")
    if not Membership.objects.filter(
        organization=organization,
        user=user,
        active=True,
    ).exists():
        raise ValidationError("O usuário não possui acesso ativo à organização atual.")


def create_contract(*, organization, reservation):
    _validate_organization(organization)
    try:
        with transaction.atomic():
            try:
                locked_reservation = (
                    Reservation.objects.select_for_update()
                    .select_related(
                        "quotation__customer",
                        "establishment",
                    )
                    .get(pk=reservation.pk, organization=organization)
                )
            except Reservation.DoesNotExist as error:
                raise ValidationError(
                    "Selecione uma reserva da organização atual."
                ) from error

            if locked_reservation.status != Reservation.Status.CONFIRMED:
                raise ValidationError("Somente uma reserva confirmada pode gerar contrato.")
            if Contract.objects.filter(reservation=locked_reservation).exists():
                raise ValidationError("Esta reserva já possui um contrato.")

            allocations = list(
                ReservationAllocation.objects.select_for_update()
                .select_related("tool_unit__tool_model")
                .filter(
                    organization=organization,
                    reservation=locked_reservation,
                )
            )
            if not allocations:
                raise ValidationError("A reserva precisa possuir equipamentos alocados.")
            if any(allocation.released_at is not None for allocation in allocations):
                raise ValidationError("A reserva possui uma alocação já liberada.")

            quotation = locked_reservation.quotation
            customer = quotation.customer
            contract = Contract(
                organization=organization,
                reservation=locked_reservation,
                customer=customer,
                establishment=locked_reservation.establishment,
                starts_at=locked_reservation.starts_at,
                ends_at=locked_reservation.ends_at,
                total_amount_snapshot=quotation.total_amount,
                customer_name_snapshot=customer.name,
                customer_document_snapshot=customer.document,
            )
            contract.save()

            reserved_options = list(
                ReservationOffering.objects.select_for_update()
                .select_related("quotation_item_offering")
                .filter(organization=organization, reservation=locked_reservation)
            )
            contract_options = {}
            for reserved in reserved_options:
                quoted = reserved.quotation_item_offering
                snapshot = ContractOffering(
                    organization=organization,
                    contract=contract,
                    reservation_offering=reserved,
                    offering_name=reserved.offering_name,
                    kind=reserved.kind,
                    quantity=reserved.quantity,
                    price_effect=quoted.price_effect,
                    line_total_snapshot=quoted.line_total,
                    requires_preparation=quoted.requires_preparation,
                )
                snapshot.save()
                contract_options[quoted.pk] = snapshot

            items = []
            for allocation in allocations:
                contract_offering = contract_options.get(
                    allocation.quotation_item_offering_id
                )
                item = ContractItem(
                    organization=organization,
                    contract=contract,
                    contract_offering=contract_offering,
                    reservation_allocation=allocation,
                    tool_unit=allocation.tool_unit,
                    asset_code_snapshot=allocation.tool_unit.asset_code,
                    tool_name_snapshot=(
                        f"{contract_offering.offering_name} "
                        f"({allocation.tool_unit.tool_model})"
                        if contract_offering
                        else str(allocation.tool_unit.tool_model)
                    ),
                )
                item.save()
                items.append(item)
            return contract, tuple(items)
    except IntegrityError as error:
        raise ValidationError(
            "O contrato já foi criado por outra operação. Atualize a página."
        ) from error


def check_out_contract(*, organization, contract, user):
    _validate_organization(organization)
    _validate_operator(organization=organization, user=user)
    with transaction.atomic():
        locked = _locked_contract(organization=organization, contract=contract)
        if locked.status != Contract.Status.PREPARED:
            raise ValidationError("Somente um contrato preparado pode registrar retirada.")
        if locked.reservation.status != Reservation.Status.CONFIRMED:
            raise ValidationError("A reserva precisa continuar confirmada.")

        items = list(
            ContractItem.objects.select_for_update()
            .select_related("reservation_allocation", "tool_unit")
            .filter(organization=organization, contract=locked)
        )
        if not items:
            raise ValidationError("O contrato precisa possuir equipamentos.")
        if any(item.checked_out_at is not None for item in items):
            raise ValidationError("A retirada deste contrato já foi registrada.")
        if any(item.reservation_allocation.released_at is not None for item in items):
            raise ValidationError("Uma alocação do contrato já foi liberada.")

        unit_ids = [item.tool_unit_id for item in items]
        units = {
            unit.pk: unit
            for unit in ToolUnit.objects.select_for_update().filter(
                organization=organization,
                pk__in=unit_ids,
            )
        }
        if len(units) != len(unit_ids):
            raise ValidationError("Um equipamento não pertence mais à organização atual.")
        invalid = [
            unit.asset_code
            for unit in units.values()
            if unit.status != ToolUnit.Status.AVAILABLE
        ]
        if invalid:
            raise ValidationError(
                "Os equipamentos precisam estar aptos para retirada: " + ", ".join(invalid)
            )

        options = list(
            ContractOffering.objects.select_for_update()
            .select_related(
                "reservation_offering__quotation_item_offering__offering"
            )
            .filter(organization=organization, contract=locked)
        )

        checked_out_at = timezone.now()
        for option in options:
            if option.kind != Offering.Kind.CONSUMABLE:
                continue
            reserved = option.reservation_offering
            if reserved.consumed_at or reserved.released_at:
                raise ValidationError(
                    f"O estado de {option.offering_name} não permite a retirada."
                )
            try:
                stock = OfferingStock.objects.select_for_update().get(
                    organization=organization,
                    establishment=locked.establishment,
                    offering=reserved.quotation_item_offering.offering,
                )
            except OfferingStock.DoesNotExist as error:
                raise ValidationError(
                    f"O estoque de {option.offering_name} não foi encontrado."
                ) from error
            if (
                stock.on_hand_quantity < option.quantity
                or stock.reserved_quantity < option.quantity
            ):
                raise ValidationError(
                    f"O saldo reservado de {option.offering_name} está inconsistente."
                )
            stock.on_hand_quantity -= option.quantity
            stock.reserved_quantity -= option.quantity
            stock.save(
                update_fields=["on_hand_quantity", "reserved_quantity", "updated_at"]
            )
            reserved.consumed_at = checked_out_at
            reserved.save(update_fields=["consumed_at", "updated_at"])

        for item in items:
            item.checked_out_at = checked_out_at
            item.checked_out_by = user
            item.save(update_fields=["checked_out_at", "checked_out_by", "updated_at"])
            unit = units[item.tool_unit_id]
            unit.status = ToolUnit.Status.RENTED
            unit.save(update_fields=["status", "updated_at"])

        locked.status = Contract.Status.ACTIVE
        locked.activated_at = checked_out_at
        locked.save(update_fields=["status", "activated_at", "updated_at"])
        return locked


def return_contract_item(*, organization, contract, contract_item, condition, notes, user):
    _validate_organization(organization)
    _validate_operator(organization=organization, user=user)
    valid_conditions = set(ContractItem.ReturnCondition.values)
    if condition not in valid_conditions:
        raise ValidationError("Selecione uma condição de devolução válida.")

    with transaction.atomic():
        locked_contract = _locked_contract(organization=organization, contract=contract)
        if locked_contract.status != Contract.Status.ACTIVE:
            raise ValidationError("Somente um contrato em andamento aceita devoluções.")

        try:
            item = (
                ContractItem.objects.select_for_update()
                .select_related("reservation_allocation", "tool_unit")
                .get(
                    pk=contract_item.pk,
                    organization=organization,
                    contract=locked_contract,
                )
            )
        except ContractItem.DoesNotExist as error:
            raise ValidationError("Selecione um equipamento deste contrato.") from error
        if item.checked_out_at is None:
            raise ValidationError("O equipamento ainda não foi retirado.")
        if item.returned_at is not None:
            raise ValidationError("A devolução deste equipamento já foi registrada.")

        try:
            unit = ToolUnit.objects.select_for_update().get(
                pk=item.tool_unit_id,
                organization=organization,
            )
        except ToolUnit.DoesNotExist as error:
            raise ValidationError("O equipamento não pertence à organização atual.") from error
        try:
            allocation = ReservationAllocation.objects.select_for_update().get(
                pk=item.reservation_allocation_id,
                organization=organization,
                reservation=locked_contract.reservation,
            )
        except ReservationAllocation.DoesNotExist as error:
            raise ValidationError("A alocação do equipamento não é válida.") from error

        returned_at = timezone.now()
        item.returned_at = returned_at
        item.returned_by = user
        item.return_condition = condition
        item.return_notes = (notes or "").strip()
        item.save(
            update_fields=[
                "returned_at",
                "returned_by",
                "return_condition",
                "return_notes",
                "updated_at",
            ]
        )
        unit.status = condition
        unit.save(update_fields=["status", "updated_at"])
        allocation.released_at = returned_at
        allocation.save(update_fields=["released_at", "updated_at"])

        has_pending_items = ContractItem.objects.filter(
            organization=organization,
            contract=locked_contract,
            returned_at__isnull=True,
        ).exists()
        if not has_pending_items:
            locked_contract.status = Contract.Status.COMPLETED
            locked_contract.completed_at = returned_at
            locked_contract.save(
                update_fields=["status", "completed_at", "updated_at"]
            )
        return item, locked_contract
