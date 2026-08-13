from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.assets.models import AssetProfile
from apps.organizations.models import Establishment, Organization
from apps.pricing.models import PricingPolicy

from .models import AssetCodeSequence, Category, ToolModel, ToolUnit

MAX_BATCH_SIZE = 100
ASSET_CODE_PREFIX = "EQ"


@dataclass(frozen=True)
class PricingConfiguration:
    effective_from: date
    hourly_rate: Decimal | None = None
    daily_rate: Decimal | None = None
    monthly_rate: Decimal | None = None


@dataclass(frozen=True)
class AssetConfiguration:
    acquisition_date: date
    placed_in_service_date: date
    acquisition_cost: Decimal
    residual_value: Decimal
    useful_life_months: int
    supplier_name: str = ""
    invoice_number: str = ""


@dataclass(frozen=True)
class ToolBatchResult:
    category: Category
    tool_model: ToolModel
    units: tuple[ToolUnit, ...]
    pricing_policy: PricingPolicy | None
    asset_profiles: tuple[AssetProfile, ...]


def _normalize_serial_numbers(values: Sequence[str], quantity: int) -> tuple[str, ...]:
    serial_numbers = tuple((value or "").strip() for value in values)
    if len(serial_numbers) != quantity:
        raise ValidationError(
            {"serial_numbers": "A lista de números de série deve acompanhar a quantidade."}
        )
    if any(len(value) > 100 for value in serial_numbers):
        raise ValidationError(
            {"serial_numbers": "Cada número de série pode ter no máximo 100 caracteres."}
        )
    non_empty = [value for value in serial_numbers if value]
    if len(non_empty) != len(set(non_empty)):
        raise ValidationError(
            {"serial_numbers": "Não repita o mesmo número de série dentro do lote."}
        )
    return serial_numbers


def _allocate_asset_codes(organization: Organization, quantity: int) -> tuple[str, ...]:
    sequence, _ = AssetCodeSequence.objects.get_or_create(organization=organization)
    first_value = sequence.next_value
    sequence.next_value += quantity
    sequence.save(update_fields=["next_value", "updated_at"])
    return tuple(
        f"{ASSET_CODE_PREFIX}-{value:06d}"
        for value in range(first_value, first_value + quantity)
    )


@transaction.atomic
def create_tool_batch(
    *,
    organization: Organization,
    category: Category | None,
    new_category_name: str,
    establishment: Establishment,
    model_name: str,
    brand: str = "",
    model_number: str = "",
    description: str = "",
    deposit_amount: Decimal = Decimal("0.00"),
    quantity: int,
    serial_numbers: Sequence[str],
    pricing: PricingConfiguration | None = None,
    asset: AssetConfiguration | None = None,
) -> ToolBatchResult:
    if not 1 <= quantity <= MAX_BATCH_SIZE:
        raise ValidationError(
            {"quantity": f"Informe uma quantidade entre 1 e {MAX_BATCH_SIZE}."}
        )

    try:
        locked_organization = Organization.objects.select_for_update().get(
            pk=organization.pk,
            active=True,
        )
    except Organization.DoesNotExist as error:
        raise ValidationError("A locadora ativa não está mais disponível.") from error
    serials = _normalize_serial_numbers(serial_numbers, quantity)

    if category is not None:
        try:
            selected_category = Category.objects.get(
                pk=category.pk,
                organization=locked_organization,
                active=True,
            )
        except Category.DoesNotExist as error:
            raise ValidationError(
                {"category": "A categoria não pertence à locadora ativa."}
            ) from error
    else:
        category_name = new_category_name.strip()
        if not category_name:
            raise ValidationError(
                {"new_category_name": "Escolha uma categoria ou informe uma nova."}
            )
        selected_category, _ = Category.objects.get_or_create(
            organization=locked_organization,
            name=category_name,
        )
        if not selected_category.active:
            selected_category.active = True
            selected_category.save(update_fields=["active", "updated_at"])

    try:
        selected_establishment = Establishment.objects.get(
            pk=establishment.pk,
            organization=locked_organization,
            active=True,
        )
    except Establishment.DoesNotExist as error:
        raise ValidationError(
            {"establishment": "A unidade/filial não pertence à locadora ativa."}
        ) from error
    tool_model = ToolModel.objects.create(
        organization=locked_organization,
        category=selected_category,
        name=model_name.strip(),
        brand=brand.strip(),
        model_number=model_number.strip(),
        description=description.strip(),
        deposit_amount=deposit_amount,
    )

    pricing_policy = None
    if pricing is not None:
        pricing_policy = PricingPolicy.objects.create(
            organization=locked_organization,
            tool_model=tool_model,
            effective_from=pricing.effective_from,
            hourly_rate=pricing.hourly_rate,
            daily_rate=pricing.daily_rate,
            monthly_rate=pricing.monthly_rate,
        )

    codes = _allocate_asset_codes(locked_organization, quantity)
    units = tuple(
        ToolUnit.objects.create(
            organization=locked_organization,
            tool_model=tool_model,
            establishment=selected_establishment,
            asset_code=code,
            serial_number=serial_number,
            status=ToolUnit.Status.AVAILABLE,
        )
        for code, serial_number in zip(codes, serials, strict=True)
    )

    profiles: tuple[AssetProfile, ...] = ()
    if asset is not None:
        profiles = tuple(
            AssetProfile.objects.create(
                organization=locked_organization,
                tool_unit=unit,
                acquisition_date=asset.acquisition_date,
                placed_in_service_date=asset.placed_in_service_date,
                acquisition_cost=asset.acquisition_cost,
                residual_value=asset.residual_value,
                useful_life_months=asset.useful_life_months,
                supplier_name=asset.supplier_name.strip(),
                invoice_number=asset.invoice_number.strip(),
            )
            for unit in units
        )

    return ToolBatchResult(
        category=selected_category,
        tool_model=tool_model,
        units=units,
        pricing_policy=pricing_policy,
        asset_profiles=profiles,
    )
