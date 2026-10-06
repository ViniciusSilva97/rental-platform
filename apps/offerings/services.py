from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.pricing.models import BillingUnit
from apps.quotations.models import Quotation, QuotationItem, QuotationItemOffering

from .models import OfferingCompatibility, OfferingPricingPolicy

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class OfferingSelectionInput:
    offering: object
    quantity: int


def select_effective_offering_policy(*, offering, on_date):
    return (
        OfferingPricingPolicy.objects.select_for_update()
        .filter(
            organization_id=offering.organization_id,
            offering=offering,
            active=True,
            effective_from__lte=on_date,
        )
        .order_by("-effective_from", "-created_at")
        .first()
    )


def _policy_rate(*, policy, quotation_item):
    if policy.billing_method == OfferingPricingPolicy.BillingMethod.FLAT:
        return policy.flat_amount, Decimal("1")
    rate = {
        BillingUnit.HOUR: policy.hourly_rate,
        BillingUnit.DAY: policy.daily_rate,
        BillingUnit.MONTH: policy.monthly_rate,
    }.get(quotation_item.billing_unit)
    if rate is None:
        raise ValidationError(
            f"{policy.offering.name} não possui valor por "
            f"{quotation_item.get_billing_unit_display().lower()}."
        )
    return rate, quotation_item.billed_quantity


def recalculate_quotation_total(quotation):
    base = sum(quotation.items.values_list("line_total", flat=True), Decimal("0.00"))
    additions = Decimal("0.00")
    discounts = Decimal("0.00")
    for selection in QuotationItemOffering.objects.filter(quotation=quotation):
        if selection.price_effect == QuotationItemOffering.PriceEffect.DISCOUNT:
            discounts += selection.line_total
        else:
            additions += selection.line_total
    total = (base + additions - discounts).quantize(_CENT, rounding=ROUND_HALF_UP)
    if total < 0:
        raise ValidationError("Os descontos não podem tornar o orçamento negativo.")
    quotation.total_amount = total
    quotation.save(update_fields=["total_amount", "updated_at"])
    return quotation


@transaction.atomic
def save_quotation_item_offerings(*, organization, quotation_item, selections):
    if not organization or not organization.active:
        raise ValidationError("A organização atual precisa estar ativa.")
    try:
        item = (
            QuotationItem.objects.select_for_update()
            .select_related("quotation", "tool_model")
            .get(pk=quotation_item.pk, organization=organization)
        )
    except QuotationItem.DoesNotExist as error:
        raise ValidationError("Selecione um item da organização atual.") from error
    if item.quotation.status != Quotation.Status.DRAFT:
        raise ValidationError("Somente rascunhos podem alterar adicionais.")

    effective_date = timezone.localtime(item.quotation.starts_at).date()
    prepared = []
    seen = set()
    for index, selection in enumerate(selections, start=1):
        if not isinstance(selection.quantity, int) or selection.quantity < 1:
            raise ValidationError(f"O adicional {index} precisa de quantidade positiva.")
        try:
            compatibility = OfferingCompatibility.objects.select_related("offering").get(
                organization=organization,
                offering=selection.offering,
                tool_model=item.tool_model,
                offering__active=True,
                active=True,
            )
        except OfferingCompatibility.DoesNotExist as error:
            raise ValidationError(
                f"O adicional selecionado não é compatível com {item.tool_model}."
            ) from error
        offering = compatibility.offering
        if offering.pk in seen:
            raise ValidationError(f"O adicional {offering.name} foi repetido.")
        seen.add(offering.pk)
        maximum = compatibility.max_quantity_per_equipment * item.equipment_quantity
        if selection.quantity > maximum:
            raise ValidationError(
                f"{offering.name} aceita no máximo {maximum} unidade(s) neste item."
            )
        policy = select_effective_offering_policy(offering=offering, on_date=effective_date)
        if policy is None:
            raise ValidationError(f"Não existe preço ativo e vigente para {offering.name}.")
        unit_rate, billed_quantity = _policy_rate(policy=policy, quotation_item=item)
        line_total = (unit_rate * billed_quantity * selection.quantity).quantize(
            _CENT, rounding=ROUND_HALF_UP
        )
        snapshot = QuotationItemOffering(
            organization=organization,
            quotation=item.quotation,
            quotation_item=item,
            offering=offering,
            pricing_policy=policy,
            offering_name=offering.name,
            kind=offering.kind,
            price_effect=(
                QuotationItemOffering.PriceEffect.DISCOUNT
                if offering.is_discount
                else QuotationItemOffering.PriceEffect.ADDITION
            ),
            quantity=selection.quantity,
            billing_method=policy.billing_method,
            billing_unit=(
                item.billing_unit
                if policy.billing_method == OfferingPricingPolicy.BillingMethod.PER_PERIOD
                else ""
            ),
            billed_quantity=billed_quantity,
            unit_rate=unit_rate,
            line_total=line_total,
            policy_effective_from=policy.effective_from,
            inventory_tool_model=offering.inventory_tool_model,
            requires_preparation=offering.requires_preparation,
        )
        snapshot.full_clean(validate_unique=False, validate_constraints=False)
        prepared.append(snapshot)

    item.offerings.all().delete()
    QuotationItemOffering.objects.bulk_create(prepared)
    recalculate_quotation_total(item.quotation)
    return tuple(prepared)
