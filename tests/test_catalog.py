from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import Category, ToolModel, ToolUnit
from apps.organizations.models import Establishment, Organization


@pytest.mark.django_db
def test_tool_unit_starts_available():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    category = Category.objects.create(organization=organization, name="Furadeiras")
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name="Furadeira de impacto",
        brand="Bosch",
        model_number="GSB 13 RE",
        daily_rate=Decimal("35.00"),
    )

    unit = ToolUnit.objects.create(
        organization=organization,
        tool_model=tool_model,
        asset_code="FUR-001",
    )

    assert unit.status == ToolUnit.Status.AVAILABLE
    assert str(unit) == "FUR-001 — Bosch Furadeira de impacto GSB 13 RE"


@pytest.mark.django_db(transaction=True)
def test_asset_code_is_unique_inside_organization():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    category = Category.objects.create(organization=organization, name="Furadeiras")
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name="Furadeira",
        daily_rate=Decimal("20.00"),
    )
    ToolUnit.objects.create(
        organization=organization, tool_model=tool_model, asset_code="FUR-001"
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ToolUnit.objects.create(
            organization=organization, tool_model=tool_model, asset_code="FUR-001"
        )


@pytest.mark.django_db
def test_tool_unit_can_be_assigned_to_establishment():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    establishment = Establishment.objects.create(organization=organization, name="Matriz")
    category = Category.objects.create(organization=organization, name="Furadeiras")
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name="Furadeira",
        daily_rate=Decimal("20.00"),
    )

    unit = ToolUnit.objects.create(
        organization=organization,
        establishment=establishment,
        tool_model=tool_model,
        asset_code="FUR-001",
    )

    assert unit.establishment == establishment


@pytest.mark.django_db
def test_tool_model_rejects_category_from_another_organization():
    organization_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    organization_b = Organization.objects.create(name="Locadora B", slug="locadora-b")
    category = Category.objects.create(organization=organization_a, name="Furadeiras")

    with pytest.raises(ValidationError):
        ToolModel.objects.create(
            organization=organization_b,
            category=category,
            name="Furadeira",
            daily_rate=Decimal("20.00"),
        )


@pytest.mark.django_db
def test_tool_unit_rejects_model_from_another_organization():
    organization_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    organization_b = Organization.objects.create(name="Locadora B", slug="locadora-b")
    category_a = Category.objects.create(organization=organization_a, name="Furadeiras")
    tool_model_a = ToolModel.objects.create(
        organization=organization_a,
        category=category_a,
        name="Furadeira",
        daily_rate=Decimal("20.00"),
    )

    with pytest.raises(ValidationError):
        ToolUnit.objects.create(
            organization=organization_b,
            tool_model=tool_model_a,
            asset_code="FUR-001",
        )


@pytest.mark.django_db
def test_tool_unit_rejects_establishment_from_another_organization():
    organization_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    organization_b = Organization.objects.create(name="Locadora B", slug="locadora-b")
    establishment_b = Establishment.objects.create(organization=organization_b, name="Matriz B")
    category = Category.objects.create(organization=organization_a, name="Furadeiras")
    tool_model = ToolModel.objects.create(
        organization=organization_a,
        category=category,
        name="Furadeira",
        daily_rate=Decimal("20.00"),
    )

    with pytest.raises(ValidationError):
        ToolUnit.objects.create(
            organization=organization_a,
            establishment=establishment_b,
            tool_model=tool_model,
            asset_code="FUR-001",
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "daily_rate,deposit_amount",
    [
        (Decimal("-0.01"), Decimal("0.00")),
        (Decimal("20.00"), Decimal("-0.01")),
    ],
)
def test_tool_model_rejects_negative_money_values(daily_rate, deposit_amount):
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    category = Category.objects.create(organization=organization, name="Furadeiras")

    with pytest.raises(ValidationError):
        ToolModel.objects.create(
            organization=organization,
            category=category,
            name="Furadeira",
            daily_rate=daily_rate,
            deposit_amount=deposit_amount,
        )
