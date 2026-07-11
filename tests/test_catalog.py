from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import Category, ToolModel, ToolUnit
from apps.organizations.models import Organization


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

