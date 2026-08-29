from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.utils import timezone

from apps.catalog.models import ToolUnit
from apps.offerings.models import Offering, OfferingStock
from apps.organizations.models import Establishment
from apps.quotations.models import Quotation

from .models import Reservation, ReservationAllocation, ReservationOffering


class ReservationUnavailable(ValidationError):
    """The requested physical units cannot be allocated safely."""


def _validate_period(starts_at, ends_at):
    if not starts_at or not ends_at or ends_at <= starts_at:
        raise ValidationError("O fim da reserva deve ser posterior ao início.")


def available_units(*, organization, establishment, tool_model, starts_at, ends_at):
    _validate_period(starts_at, ends_at)
    if not organization.active:
        raise ValidationError("A organização atual precisa estar ativa.")
    if establishment.organization_id != organization.id:
        raise ValidationError("O estabelecimento deve pertencer à organização atual.")
    if not establishment.active:
        raise ValidationError("O estabelecimento precisa estar ativo.")
    if tool_model.organization_id != organization.id:
        raise ValidationError("O modelo deve pertencer à organização atual.")
    if not tool_model.active:
        raise ValidationError("O modelo precisa estar ativo.")

    conflicts = ReservationAllocation.objects.filter(
        organization=organization,
        tool_unit_id=OuterRef("pk"),
        released_at__isnull=True,
        starts_at__lt=ends_at,
        ends_at__gt=starts_at,
    )
    return (
        ToolUnit.objects.filter(
            organization=organization,
            establishment=establishment,
            tool_model=tool_model,
            status=ToolUnit.Status.AVAILABLE,
        )
        .annotate(has_reservation_conflict=Exists(conflicts))
        .filter(has_reservation_conflict=False)
        .select_related("tool_model", "establishment")
        .order_by("asset_code")
    )


def available_establishments_for_quotation(*, organization, quotation):
    _validate_period(quotation.starts_at, quotation.ends_at)
    if not organization.active:
        raise ValidationError("A organização atual precisa estar ativa.")
    if quotation.organization_id != organization.id:
        raise ValidationError("O orçamento deve pertencer à organização atual.")

    requirements = {}
    consumable_requirements = {}
    for item in quotation.items.select_related("tool_model").prefetch_related(
        "offerings__offering", "offerings__inventory_tool_model"
    ):
        if not item.tool_model.active:
            return Establishment.objects.none()
        requirement = requirements.setdefault(
            item.tool_model_id,
            {"tool_model": item.tool_model, "quantity": 0},
        )
        requirement["quantity"] += item.equipment_quantity
        for option in item.offerings.all():
            if option.inventory_tool_model_id:
                physical = requirements.setdefault(
                    option.inventory_tool_model_id,
                    {"tool_model": option.inventory_tool_model, "quantity": 0},
                )
                physical["quantity"] += option.quantity
            if option.kind == Offering.Kind.CONSUMABLE:
                consumable_requirements[option.offering_id] = (
                    consumable_requirements.get(option.offering_id, 0) + option.quantity
                )

    establishments = Establishment.objects.filter(
        organization=organization,
        active=True,
    )
    if not requirements:
        return establishments.none()

    available_establishment_ids = []
    for establishment in establishments:
        units_available = all(
            available_units(
                organization=organization,
                establishment=establishment,
                tool_model=requirement["tool_model"],
                starts_at=quotation.starts_at,
                ends_at=quotation.ends_at,
            ).count()
            >= requirement["quantity"]
            for requirement in requirements.values()
        )
        consumables_available = all(
            OfferingStock.objects.filter(
                organization=organization,
                establishment=establishment,
                offering_id=offering_id,
                on_hand_quantity__gte=models.F("reserved_quantity") + quantity,
            ).exists()
            for offering_id, quantity in consumable_requirements.items()
        )
        if units_available and consumables_available:
            available_establishment_ids.append(establishment.pk)

    return establishments.filter(pk__in=available_establishment_ids)


def units_with_reservation_schedule(*, organization, queryset, at=None):
    reference_time = at or timezone.now()
    active_allocations = (
        ReservationAllocation.objects.filter(
            organization=organization,
            released_at__isnull=True,
            ends_at__gt=reference_time,
        )
        .select_related("reservation")
        .order_by("starts_at")
    )
    units = list(
        queryset.filter(organization=organization).prefetch_related(
            Prefetch(
                "reservation_allocations",
                queryset=active_allocations,
                to_attr="active_reservation_schedule",
            )
        )
    )
    for unit in units:
        unit.current_reservation_allocation = None
        unit.next_reservation_allocation = None
        for allocation in unit.active_reservation_schedule:
            if allocation.starts_at <= reference_time < allocation.ends_at:
                unit.current_reservation_allocation = allocation
            elif (
                allocation.starts_at > reference_time
                and unit.next_reservation_allocation is None
            ):
                unit.next_reservation_allocation = allocation
    return units


def _locked_available_units(*, organization, establishment, tool_model, starts_at, ends_at):
    units = available_units(
        organization=organization,
        establishment=establishment,
        tool_model=tool_model,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    if connection.features.has_select_for_update:
        units = units.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked
        )
    return units


def _confirm_reservation(*, organization, quotation, establishment):
    try:
        locked_quotation = (
            Quotation.objects.select_for_update()
            .prefetch_related(
                "items__tool_model",
                "items__offerings__offering",
                "items__offerings__inventory_tool_model",
            )
            .get(pk=quotation.pk, organization=organization)
        )
    except Quotation.DoesNotExist as error:
        raise ValidationError("Selecione um orçamento da organização atual.") from error

    if locked_quotation.status != Quotation.Status.SENT:
        raise ValidationError("Somente um orçamento enviado pode gerar uma reserva.")
    if Reservation.objects.filter(quotation=locked_quotation).exists():
        raise ValidationError("Este orçamento já possui uma reserva.")

    try:
        locked_establishment = Establishment.objects.select_for_update().get(
            pk=establishment.pk,
            organization=organization,
            active=True,
        )
    except Establishment.DoesNotExist as error:
        raise ValidationError("Selecione um estabelecimento ativo da organização atual.") from error

    items = list(locked_quotation.items.all())
    if not items:
        raise ValidationError("O orçamento precisa possuir ao menos um item.")

    selected_by_item = []
    already_selected = set()
    for item in items:
        candidates = _locked_available_units(
            organization=organization,
            establishment=locked_establishment,
            tool_model=item.tool_model,
            starts_at=locked_quotation.starts_at,
            ends_at=locked_quotation.ends_at,
        ).exclude(pk__in=already_selected)
        selected = list(candidates[: item.equipment_quantity])
        if len(selected) != item.equipment_quantity:
            raise ReservationUnavailable(
                f"Não há {item.equipment_quantity} equipamento(s) disponível(is) de "
                f"{item.tool_model} no período informado."
            )
        already_selected.update(unit.pk for unit in selected)
        selected_by_item.append((item, selected))
        for option in item.offerings.all():
            if not option.inventory_tool_model_id:
                continue
            candidates = _locked_available_units(
                organization=organization,
                establishment=locked_establishment,
                tool_model=option.inventory_tool_model,
                starts_at=locked_quotation.starts_at,
                ends_at=locked_quotation.ends_at,
            ).exclude(pk__in=already_selected)
            selected = list(candidates[: option.quantity])
            if len(selected) != option.quantity:
                raise ReservationUnavailable(
                    f"Não há {option.quantity} unidade(s) disponível(is) de "
                    f"{option.offering_name}."
                )
            already_selected.update(unit.pk for unit in selected)
            selected_by_item.append((item, selected, option))

    confirmed_at = timezone.now()
    reservation = Reservation(
        organization=organization,
        quotation=locked_quotation,
        establishment=locked_establishment,
        starts_at=locked_quotation.starts_at,
        ends_at=locked_quotation.ends_at,
        status=Reservation.Status.CONFIRMED,
        confirmed_at=confirmed_at,
    )
    reservation.save()

    for item in items:
        for option in item.offerings.all():
            if option.kind == Offering.Kind.CONSUMABLE:
                try:
                    stock = OfferingStock.objects.select_for_update().get(
                        organization=organization,
                        establishment=locked_establishment,
                        offering=option.offering,
                    )
                except OfferingStock.DoesNotExist as error:
                    raise ReservationUnavailable(
                        f"Não existe estoque de {option.offering_name} neste estabelecimento."
                    ) from error
                if stock.available_quantity < option.quantity:
                    raise ReservationUnavailable(
                        f"O saldo de {option.offering_name} ficou insuficiente."
                    )
                stock.reserved_quantity += option.quantity
                stock.save(update_fields=["reserved_quantity", "updated_at"])
            ReservationOffering.objects.create(
                organization=organization,
                reservation=reservation,
                quotation_item_offering=option,
                offering_name=option.offering_name,
                kind=option.kind,
                quantity=option.quantity,
                reserved_at=confirmed_at,
            )

    allocations = []
    for selected_group in selected_by_item:
        item, selected, *option_group = selected_group
        option = option_group[0] if option_group else None
        for unit in selected:
            allocation = ReservationAllocation(
                organization=organization,
                reservation=reservation,
                quotation_item=item,
                quotation_item_offering=option,
                tool_unit=unit,
                starts_at=reservation.starts_at,
                ends_at=reservation.ends_at,
            )
            allocation.save()
            allocations.append(allocation)

    return reservation, tuple(allocations)


def confirm_reservation(*, organization, quotation, establishment):
    try:
        with transaction.atomic():
            return _confirm_reservation(
                organization=organization,
                quotation=quotation,
                establishment=establishment,
            )
    except IntegrityError as error:
        raise ReservationUnavailable(
            "A disponibilidade mudou durante a confirmação. Consulte novamente e repita."
        ) from error


def cancel_reservation(*, organization, reservation):
    with transaction.atomic():
        try:
            locked = Reservation.objects.select_for_update().get(
                pk=reservation.pk,
                organization=organization,
            )
        except Reservation.DoesNotExist as error:
            raise ValidationError("Selecione uma reserva da organização atual.") from error

        if locked.status != Reservation.Status.CONFIRMED:
            raise ValidationError("Somente uma reserva confirmada pode ser cancelada.")
        if hasattr(locked, "contract"):
            raise ValidationError(
                "A reserva possui contrato e não pode mais ser cancelada."
            )

        cancelled_at = timezone.now()
        locked.status = Reservation.Status.CANCELLED
        locked.cancelled_at = cancelled_at
        locked.save(update_fields=["status", "cancelled_at", "updated_at"])
        locked.allocations.filter(released_at__isnull=True).update(
            released_at=cancelled_at,
            updated_at=cancelled_at,
        )
        consumables = locked.offerings.select_for_update().filter(
            kind=Offering.Kind.CONSUMABLE,
            consumed_at__isnull=True,
            released_at__isnull=True,
        )
        for reserved in consumables:
            stock = OfferingStock.objects.select_for_update().get(
                organization=organization,
                establishment=locked.establishment,
                offering=reserved.quotation_item_offering.offering,
            )
            if stock.reserved_quantity < reserved.quantity:
                raise ValidationError("O saldo reservado de consumível está inconsistente.")
            stock.reserved_quantity -= reserved.quantity
            stock.save(update_fields=["reserved_quantity", "updated_at"])
            reserved.released_at = cancelled_at
            reserved.save(update_fields=["released_at", "updated_at"])
        return locked
