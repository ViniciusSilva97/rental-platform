from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ToolModel
from apps.customers.models import Customer
from apps.pricing.models import BillingUnit, PricingPolicy
from apps.pricing.services import calculate_billable_quantity, calculate_charge

from .models import Quotation, QuotationItem

_QUANTITY_PRECISION = Decimal("0.000001")
_CENT = Decimal("0.01")
_MICROSECONDS_PER_HOUR = Decimal(3_600_000_000)
_HOURS_PER_DAY = Decimal(24)


@dataclass(frozen=True)
class QuotationLineInput:
    tool_model: ToolModel
    equipment_quantity: int
    billing_unit: str


@dataclass(frozen=True)
class PeriodCalculation:
    period_quantity: Decimal
    billed_quantity: Decimal


def _normalized_datetime(value: datetime) -> datetime:
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _duration_hours(starts_at: datetime, ends_at: datetime) -> Decimal:
    delta = ends_at - starts_at
    total_microseconds = Decimal(
        (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    )
    return total_microseconds / _MICROSECONDS_PER_HOUR


def _add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month = value.replace(year=year + 1, month=1, day=1)
    else:
        next_month = value.replace(year=year, month=month + 1, day=1)
    last_day = (next_month - timedelta(days=1)).day
    return value.replace(year=year, month=month, day=min(value.day, last_day))


def _calendar_month_quantity(starts_at: datetime, ends_at: datetime) -> Decimal:
    whole_months = (ends_at.year - starts_at.year) * 12 + ends_at.month - starts_at.month
    whole_months = max(whole_months, 0)
    while _add_calendar_months(starts_at, whole_months) > ends_at:
        whole_months -= 1
    while _add_calendar_months(starts_at, whole_months + 1) <= ends_at:
        whole_months += 1

    anchor = _add_calendar_months(starts_at, whole_months)
    if anchor == ends_at:
        return Decimal(whole_months)

    next_anchor = _add_calendar_months(starts_at, whole_months + 1)
    remaining_hours = _duration_hours(anchor, ends_at)
    calendar_month_hours = _duration_hours(anchor, next_anchor)
    return Decimal(whole_months) + remaining_hours / calendar_month_hours


def calculate_period(
    *,
    policy: PricingPolicy,
    unit: str,
    starts_at: datetime,
    ends_at: datetime,
) -> PeriodCalculation:
    """Convert an exclusive [start, end) interval into the selected billing unit."""
    normalized_start = _normalized_datetime(starts_at)
    normalized_end = _normalized_datetime(ends_at)
    if normalized_end <= normalized_start:
        raise ValueError("O fim da locação deve ser posterior ao início.")

    normalized_unit = (unit or "").upper()
    hours = _duration_hours(normalized_start, normalized_end)
    if normalized_unit == BillingUnit.HOUR:
        quantity = hours
    elif normalized_unit == BillingUnit.DAY:
        quantity = hours / _HOURS_PER_DAY
    elif normalized_unit == BillingUnit.MONTH:
        if policy.month_definition == PricingPolicy.MonthDefinition.CALENDAR_MONTH:
            quantity = _calendar_month_quantity(normalized_start, normalized_end)
        else:
            quantity = hours / (_HOURS_PER_DAY * Decimal(policy.fixed_month_days))
    else:
        raise ValueError("A unidade de cobrança deve ser hora, dia ou mês.")

    period_quantity = quantity.quantize(_QUANTITY_PRECISION, rounding=ROUND_HALF_UP)
    billed_quantity = calculate_billable_quantity(
        policy=policy,
        quantity=period_quantity,
    ).quantize(_QUANTITY_PRECISION)
    return PeriodCalculation(
        period_quantity=period_quantity,
        billed_quantity=billed_quantity,
    )


def _select_policy_for_snapshot(*, tool_model: ToolModel, on_date):
    return (
        PricingPolicy.objects.select_for_update()
        .filter(
            organization_id=tool_model.organization_id,
            tool_model=tool_model,
            active=True,
            effective_from__lte=on_date,
        )
        .order_by("-effective_from", "-created_at")
        .first()
    )


def _unit_rate(policy: PricingPolicy, unit: str) -> Decimal | None:
    return {
        BillingUnit.HOUR: policy.hourly_rate,
        BillingUnit.DAY: policy.daily_rate,
        BillingUnit.MONTH: policy.monthly_rate,
    }.get(unit)


@transaction.atomic
def save_draft_quotation(
    *,
    organization,
    customer: Customer,
    starts_at: datetime,
    ends_at: datetime,
    lines: tuple[QuotationLineInput, ...],
    quotation: Quotation | None = None,
) -> Quotation:
    """Create or replace a draft and atomically persist reproducible price snapshots."""
    if not organization.active:
        raise ValidationError("A locadora ativa é obrigatória para criar um orçamento.")
    if not lines:
        raise ValidationError("Adicione ao menos um item ao orçamento.")

    normalized_start = _normalized_datetime(starts_at)
    normalized_end = _normalized_datetime(ends_at)
    if normalized_end <= normalized_start:
        raise ValidationError({"ends_at": "O fim deve ser posterior ao início."})

    try:
        scoped_customer = Customer.objects.get(
            pk=customer.pk,
            organization=organization,
            active=True,
        )
    except Customer.DoesNotExist as error:
        raise ValidationError(
            {"customer": "Selecione um cliente ativo da locadora atual."}
        ) from error

    if quotation is None:
        scoped_quotation = Quotation(
            organization=organization,
            customer=scoped_customer,
            starts_at=normalized_start,
            ends_at=normalized_end,
        )
    else:
        try:
            scoped_quotation = Quotation.objects.select_for_update().get(
                pk=quotation.pk,
                organization=organization,
            )
        except Quotation.DoesNotExist as error:
            raise ValidationError("O orçamento não pertence à locadora ativa.") from error
        if scoped_quotation.status != Quotation.Status.DRAFT:
            raise ValidationError("Somente orçamentos em rascunho podem ser recalculados.")
        scoped_quotation.customer = scoped_customer
        scoped_quotation.starts_at = normalized_start
        scoped_quotation.ends_at = normalized_end

    scoped_quotation.total_amount = Decimal("0.00")
    scoped_quotation.save()

    effective_date = timezone.localtime(normalized_start).date()
    prepared_items = []
    seen_lines = set()
    total_amount = Decimal("0.00")
    for index, line in enumerate(lines, start=1):
        normalized_unit = (line.billing_unit or "").upper()
        if normalized_unit not in BillingUnit.values:
            raise ValidationError(f"O item {index} possui uma unidade de cobrança inválida.")
        if not isinstance(line.equipment_quantity, int) or line.equipment_quantity < 1:
            raise ValidationError(f"O item {index} precisa de ao menos um equipamento.")

        try:
            tool_model = ToolModel.objects.get(
                pk=line.tool_model.pk,
                organization=organization,
                active=True,
            )
        except ToolModel.DoesNotExist as error:
            raise ValidationError(
                f"O modelo do item {index} não pertence à locadora ativa."
            ) from error

        line_key = (tool_model.pk, normalized_unit)
        if line_key in seen_lines:
            raise ValidationError(
                f"O modelo {tool_model} foi repetido com a mesma unidade de cobrança."
            )
        seen_lines.add(line_key)

        policy = _select_policy_for_snapshot(
            tool_model=tool_model,
            on_date=effective_date,
        )
        if policy is None:
            raise ValidationError(
                f"Não existe preço ativo e vigente para {tool_model} no início da locação."
            )
        rate = _unit_rate(policy, normalized_unit)
        if rate is None:
            raise ValidationError(
                f"{tool_model} não possui valor por "
                f"{BillingUnit(normalized_unit).label.lower()}."
            )

        period = calculate_period(
            policy=policy,
            unit=normalized_unit,
            starts_at=normalized_start,
            ends_at=normalized_end,
        )
        period_charge = calculate_charge(
            policy=policy,
            unit=normalized_unit,
            quantity=period.period_quantity,
        )
        line_total = (period_charge * line.equipment_quantity).quantize(
            _CENT,
            rounding=ROUND_HALF_UP,
        )
        item = QuotationItem(
            organization=organization,
            quotation=scoped_quotation,
            tool_model=tool_model,
            pricing_policy=policy,
            equipment_quantity=line.equipment_quantity,
            billing_unit=normalized_unit,
            period_quantity=period.period_quantity,
            billed_quantity=period.billed_quantity,
            unit_rate=rate,
            line_total=line_total,
            policy_effective_from=policy.effective_from,
            partial_unit_rounding=policy.partial_unit_rounding,
            month_definition=policy.month_definition,
            fixed_month_days=policy.fixed_month_days,
        )
        item.full_clean(validate_unique=False, validate_constraints=False)
        prepared_items.append(item)
        total_amount += line_total

    scoped_quotation.items.all().delete()
    QuotationItem.objects.bulk_create(prepared_items)
    scoped_quotation.total_amount = total_amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    scoped_quotation.save(
        update_fields=[
            "customer",
            "starts_at",
            "ends_at",
            "total_amount",
            "updated_at",
        ]
    )
    return scoped_quotation


@transaction.atomic
def recalculate_draft_quotation(*, organization, quotation: Quotation) -> Quotation:
    try:
        scoped_quotation = (
            Quotation.objects.select_for_update()
            .prefetch_related("items__tool_model")
            .get(pk=quotation.pk, organization=organization)
        )
    except Quotation.DoesNotExist as error:
        raise ValidationError("O orçamento não pertence à locadora ativa.") from error
    if scoped_quotation.status != Quotation.Status.DRAFT:
        raise ValidationError("Somente orçamentos em rascunho podem ser recalculados.")
    lines = tuple(
        QuotationLineInput(
            tool_model=item.tool_model,
            equipment_quantity=item.equipment_quantity,
            billing_unit=item.billing_unit,
        )
        for item in scoped_quotation.items.all()
    )
    return save_draft_quotation(
        organization=organization,
        customer=scoped_quotation.customer,
        starts_at=scoped_quotation.starts_at,
        ends_at=scoped_quotation.ends_at,
        lines=lines,
        quotation=scoped_quotation,
    )


@transaction.atomic
def transition_quotation(*, organization, quotation: Quotation, target_status: str) -> Quotation:
    try:
        scoped_quotation = (
            Quotation.objects.select_for_update()
            .get(
                pk=quotation.pk,
                organization=organization,
            )
        )
    except Quotation.DoesNotExist as error:
        raise ValidationError("O orçamento não pertence à locadora ativa.") from error

    transitions = {
        Quotation.Status.DRAFT: {Quotation.Status.SENT, Quotation.Status.CANCELLED},
        Quotation.Status.SENT: {Quotation.Status.EXPIRED, Quotation.Status.CANCELLED},
        Quotation.Status.EXPIRED: set(),
        Quotation.Status.CANCELLED: set(),
    }
    if target_status not in transitions[scoped_quotation.status]:
        target_label = (
            Quotation.Status(target_status).label
            if target_status in Quotation.Status.values
            else target_status
        )
        raise ValidationError(
            "Não é permitido alterar o orçamento de "
            f"{scoped_quotation.get_status_display()} para "
            f"{target_label}."
        )

    if target_status == Quotation.Status.SENT:
        from apps.reservations.services import available_establishments_for_quotation

        establishments = available_establishments_for_quotation(
            organization=organization,
            quotation=scoped_quotation,
        )
        if not establishments.exists():
            raise ValidationError(
                "Não é possível enviar este orçamento: nenhum estabelecimento ativo "
                "possui todos os equipamentos solicitados disponíveis nesse período."
            )

    if scoped_quotation.status == Quotation.Status.SENT:
        try:
            reservation = scoped_quotation.reservation
        except ObjectDoesNotExist:
            reservation = None
        if reservation is not None and reservation.cancelled_at is None:
            raise ValidationError(
                "Cancele primeiro a reserva confirmada antes de encerrar o orçamento."
            )

    now = timezone.now()
    scoped_quotation.status = target_status
    update_fields = ["status", "updated_at"]
    if target_status == Quotation.Status.SENT:
        scoped_quotation.sent_at = now
        update_fields.append("sent_at")
    elif target_status == Quotation.Status.EXPIRED:
        scoped_quotation.expired_at = now
        update_fields.append("expired_at")
    elif target_status == Quotation.Status.CANCELLED:
        scoped_quotation.cancelled_at = now
        update_fields.append("cancelled_at")
    scoped_quotation.save(update_fields=update_fields)
    return scoped_quotation
