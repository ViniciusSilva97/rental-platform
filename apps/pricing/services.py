from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

from django.utils import timezone

from .models import BillingUnit, PricingPolicy

_CENT = Decimal("0.01")
_WHOLE_UNIT = Decimal("1")


class PricingUnavailable(ValueError):
    """Raised when a requested unit has no configured rate."""


def select_effective_policy(*, tool_model, on_date: date | None = None):
    """Return the latest active policy in force on a date."""
    reference_date = on_date or timezone.localdate()
    return (
        PricingPolicy.objects.filter(
            organization_id=tool_model.organization_id,
            tool_model=tool_model,
            active=True,
            effective_from__lte=reference_date,
        )
        .order_by("-effective_from", "-created_at")
        .first()
    )


def calculate_charge(
    *,
    policy: PricingPolicy,
    unit: str,
    quantity: Decimal,
) -> Decimal:
    """Calculate a deterministic charge for a quantity already expressed in a unit."""
    if isinstance(quantity, float):
        raise ValueError("Use Decimal em vez de float para quantidades financeiras.")

    try:
        normalized_quantity = Decimal(quantity)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("A quantidade deve ser um número decimal.") from error

    if normalized_quantity <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")

    rates = {
        BillingUnit.HOUR: policy.hourly_rate,
        BillingUnit.DAY: policy.daily_rate,
        BillingUnit.MONTH: policy.monthly_rate,
    }
    normalized_unit = (unit or "").upper()
    if normalized_unit not in rates:
        valid_units = ", ".join(BillingUnit.values)
        raise ValueError(f"A unidade deve ser {valid_units}.")

    rate = rates[normalized_unit]
    if rate is None:
        raise PricingUnavailable(f"Não existe valor configurado para {normalized_unit}.")

    billable_quantity = calculate_billable_quantity(
        policy=policy,
        quantity=normalized_quantity,
    )

    return (rate * billable_quantity).quantize(_CENT, rounding=ROUND_HALF_UP)


def calculate_billable_quantity(
    *,
    policy: PricingPolicy,
    quantity: Decimal,
) -> Decimal:
    """Apply only the policy rounding rule to a positive Decimal quantity."""
    if isinstance(quantity, float):
        raise ValueError("Use Decimal em vez de float para quantidades financeiras.")

    try:
        normalized_quantity = Decimal(quantity)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("A quantidade deve ser um número decimal.") from error

    if normalized_quantity <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")

    if policy.partial_unit_rounding == PricingPolicy.PartialUnitRounding.UP:
        return normalized_quantity.quantize(_WHOLE_UNIT, rounding=ROUND_CEILING)
    return normalized_quantity
