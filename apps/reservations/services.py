from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.catalog.models import ToolUnit
from apps.organizations.models import Establishment
from apps.quotations.models import Quotation

from .models import Reservation, ReservationAllocation


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
    for item in quotation.items.select_related("tool_model"):
        if not item.tool_model.active:
            return Establishment.objects.none()
        requirement = requirements.setdefault(
            item.tool_model_id,
            {"tool_model": item.tool_model, "quantity": 0},
        )
        requirement["quantity"] += item.equipment_quantity

    establishments = Establishment.objects.filter(
        organization=organization,
        active=True,
    )
    if not requirements:
        return establishments.none()

    available_establishment_ids = []
    for establishment in establishments:
        if all(
            available_units(
                organization=organization,
                establishment=establishment,
                tool_model=requirement["tool_model"],
                starts_at=quotation.starts_at,
                ends_at=quotation.ends_at,
            ).count()
            >= requirement["quantity"]
            for requirement in requirements.values()
        ):
            available_establishment_ids.append(establishment.pk)

    return establishments.filter(pk__in=available_establishment_ids)


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
            .prefetch_related("items__tool_model")
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

    allocations = []
    for item, selected in selected_by_item:
        for unit in selected:
            allocation = ReservationAllocation(
                organization=organization,
                reservation=reservation,
                quotation_item=item,
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

        cancelled_at = timezone.now()
        locked.status = Reservation.Status.CANCELLED
        locked.cancelled_at = cancelled_at
        locked.save(update_fields=["status", "cancelled_at", "updated_at"])
        locked.allocations.filter(released_at__isnull=True).update(
            released_at=cancelled_at,
            updated_at=cancelled_at,
        )
        return locked
