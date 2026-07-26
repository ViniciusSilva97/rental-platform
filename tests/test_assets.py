from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.forms.models import inlineformset_factory

from apps.assets.models import AssetProfile
from apps.catalog.admin import AssetProfileInlineFormSet
from apps.catalog.models import Category, ToolModel, ToolUnit
from apps.organizations.models import Establishment, Organization


def create_tool_unit(*, organization, asset_code="FUR-001"):
    establishment = Establishment.objects.create(
        organization=organization,
        name=f"Matriz {asset_code}",
    )
    category = Category.objects.create(
        organization=organization,
        name=f"Categoria {asset_code}",
    )
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name=f"Furadeira {asset_code}",
    )
    return ToolUnit.objects.create(
        organization=organization,
        establishment=establishment,
        tool_model=tool_model,
        asset_code=asset_code,
    )


@pytest.mark.django_db
def test_asset_profile_records_depreciation_base_without_calculating_depreciation():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_unit = create_tool_unit(organization=organization)

    profile = AssetProfile.objects.create(
        organization=organization,
        tool_unit=tool_unit,
        acquisition_date=date(2026, 1, 10),
        placed_in_service_date=date(2026, 1, 15),
        acquisition_cost=Decimal("5000.00"),
        residual_value=Decimal("500.00"),
        useful_life_months=60,
        supplier_name="Fornecedor Exemplo",
        invoice_number="NF-123",
    )

    assert profile.depreciable_amount == Decimal("4500.00")
    assert str(profile) == "FUR-001 — perfil patrimonial"


@pytest.mark.django_db
def test_asset_profile_rejects_tool_unit_from_another_organization():
    organization_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    organization_b = Organization.objects.create(name="Locadora B", slug="locadora-b")
    tool_unit_a = create_tool_unit(organization=organization_a)

    with pytest.raises(ValidationError) as error:
        AssetProfile.objects.create(
            organization=organization_b,
            tool_unit=tool_unit_a,
            acquisition_date=date(2026, 1, 10),
            placed_in_service_date=date(2026, 1, 15),
            acquisition_cost=Decimal("5000.00"),
            residual_value=Decimal("500.00"),
            useful_life_months=60,
        )

    assert "tool_unit" in error.value.message_dict


@pytest.mark.django_db
def test_asset_profile_rejects_residual_value_above_cost():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_unit = create_tool_unit(organization=organization)

    with pytest.raises(ValidationError) as error:
        AssetProfile.objects.create(
            organization=organization,
            tool_unit=tool_unit,
            acquisition_date=date(2026, 1, 10),
            placed_in_service_date=date(2026, 1, 15),
            acquisition_cost=Decimal("5000.00"),
            residual_value=Decimal("5000.01"),
            useful_life_months=60,
        )

    assert "residual_value" in error.value.message_dict


@pytest.mark.django_db
def test_asset_profile_rejects_service_date_before_acquisition():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_unit = create_tool_unit(organization=organization)

    with pytest.raises(ValidationError) as error:
        AssetProfile.objects.create(
            organization=organization,
            tool_unit=tool_unit,
            acquisition_date=date(2026, 1, 10),
            placed_in_service_date=date(2026, 1, 9),
            acquisition_cost=Decimal("5000.00"),
            residual_value=Decimal("500.00"),
            useful_life_months=60,
        )

    assert "placed_in_service_date" in error.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize(
    "acquisition_cost,residual_value,useful_life_months",
    [
        (Decimal("-0.01"), Decimal("0.00"), 60),
        (Decimal("5000.00"), Decimal("-0.01"), 60),
        (Decimal("5000.00"), Decimal("500.00"), 0),
    ],
)
def test_asset_profile_rejects_invalid_financial_base(
    acquisition_cost,
    residual_value,
    useful_life_months,
):
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_unit = create_tool_unit(organization=organization)

    with pytest.raises(ValidationError):
        AssetProfile.objects.create(
            organization=organization,
            tool_unit=tool_unit,
            acquisition_date=date(2026, 1, 10),
            placed_in_service_date=date(2026, 1, 15),
            acquisition_cost=acquisition_cost,
            residual_value=residual_value,
            useful_life_months=useful_life_months,
        )


@pytest.mark.django_db
def test_tool_unit_has_only_one_asset_profile():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_unit = create_tool_unit(organization=organization)
    profile_data = {
        "organization": organization,
        "tool_unit": tool_unit,
        "acquisition_date": date(2026, 1, 10),
        "placed_in_service_date": date(2026, 1, 15),
        "acquisition_cost": Decimal("5000.00"),
        "residual_value": Decimal("500.00"),
        "useful_life_months": 60,
    }
    AssetProfile.objects.create(**profile_data)

    with pytest.raises(ValidationError):
        AssetProfile.objects.create(**profile_data)


@pytest.mark.django_db(transaction=True)
def test_asset_constraints_protect_bulk_writes():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_unit = create_tool_unit(organization=organization)

    with pytest.raises(IntegrityError), transaction.atomic():
        AssetProfile.objects.bulk_create(
            [
                AssetProfile(
                    organization=organization,
                    tool_unit=tool_unit,
                    acquisition_date=date(2026, 1, 10),
                    placed_in_service_date=date(2026, 1, 15),
                    acquisition_cost=Decimal("5000.00"),
                    residual_value=Decimal("5000.01"),
                    useful_life_months=60,
                )
            ]
        )


@pytest.mark.django_db
def test_asset_inline_preserves_unsaved_tool_unit_parent_and_organization():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    establishment = Establishment.objects.create(organization=organization, name="Matriz")
    category = Category.objects.create(organization=organization, name="Furadeiras")
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name="Furadeira",
    )
    tool_unit = ToolUnit(
        organization=organization,
        establishment=establishment,
        tool_model=tool_model,
        asset_code="FUR-001",
    )
    profile_formset = inlineformset_factory(
        ToolUnit,
        AssetProfile,
        formset=AssetProfileInlineFormSet,
        fields=(
            "acquisition_date",
            "placed_in_service_date",
            "acquisition_cost",
            "residual_value",
            "useful_life_months",
            "supplier_name",
            "invoice_number",
            "notes",
        ),
        extra=1,
    )
    formset = profile_formset(
        data={
            "asset_profile-TOTAL_FORMS": "1",
            "asset_profile-INITIAL_FORMS": "0",
            "asset_profile-MIN_NUM_FORMS": "0",
            "asset_profile-MAX_NUM_FORMS": "1",
            "asset_profile-0-acquisition_date": "2026-01-10",
            "asset_profile-0-placed_in_service_date": "2026-01-15",
            "asset_profile-0-acquisition_cost": "5000.00",
            "asset_profile-0-residual_value": "500.00",
            "asset_profile-0-useful_life_months": "60",
            "asset_profile-0-supplier_name": "Fornecedor Exemplo",
            "asset_profile-0-invoice_number": "NF-123",
            "asset_profile-0-notes": "",
        },
        instance=tool_unit,
        prefix="asset_profile",
    )

    assert formset.is_valid(), formset.errors
    tool_unit.save()
    profile = formset.save()[0]

    assert profile.organization == organization
    assert profile.tool_unit == tool_unit
