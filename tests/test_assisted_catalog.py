from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection
from django.urls import reverse

from apps.assets.models import AssetProfile
from apps.catalog.forms import AssistedToolRegistrationForm
from apps.catalog.models import AssetCodeSequence, Category, ToolModel, ToolUnit
from apps.catalog.services import (
    AssetConfiguration,
    PricingConfiguration,
    create_tool_batch,
)
from apps.organizations.models import Establishment, Membership, Organization
from apps.pricing.models import PricingPolicy

User = get_user_model()


def create_organization(name="Locadora Exemplo", slug="locadora-exemplo"):
    organization = Organization.objects.create(name=name, slug=slug)
    establishment = Establishment.objects.create(
        organization=organization,
        name="Matriz",
        kind=Establishment.Kind.HEADQUARTERS,
    )
    return organization, establishment


def create_user_with_membership(organization, username="vinicius"):
    user = User.objects.create_user(username=username, password="test-password-123")
    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.Role.OWNER,
    )
    return user


def create_batch(*, organization, establishment, category=None, model_name="Furadeira"):
    return create_tool_batch(
        organization=organization,
        category=category,
        new_category_name="Furadeiras" if category is None else "",
        establishment=establishment,
        model_name=model_name,
        quantity=1,
        serial_numbers=("",),
    )


def valid_form_data(establishment, **overrides):
    data = {
        "new_category_name": "Furadeiras",
        "model_name": "Furadeira",
        "brand": "",
        "model_number": "",
        "description": "",
        "deposit_amount": "0.00",
        "quantity": "1",
        "establishment": str(establishment.pk),
        "serial_numbers": "",
        "effective_from": "2026-08-10",
        "hourly_rate": "",
        "daily_rate": "",
        "monthly_rate": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_assisted_batch_creates_five_available_units_with_pricing_and_assets():
    organization, establishment = create_organization()

    result = create_tool_batch(
        organization=organization,
        category=None,
        new_category_name="Furadeiras",
        establishment=establishment,
        model_name="Furadeira de impacto",
        brand="Marca Exemplo",
        model_number="FI-900",
        deposit_amount=Decimal("200.00"),
        quantity=5,
        serial_numbers=("SER-1", "SER-2", "", "SER-4", "SER-5"),
        pricing=PricingConfiguration(
            effective_from=date(2026, 8, 10),
            hourly_rate=Decimal("15.00"),
            daily_rate=Decimal("60.00"),
            monthly_rate=Decimal("900.00"),
        ),
        asset=AssetConfiguration(
            acquisition_date=date(2026, 8, 1),
            placed_in_service_date=date(2026, 8, 10),
            acquisition_cost=Decimal("1200.00"),
            residual_value=Decimal("120.00"),
            useful_life_months=60,
            supplier_name="Fornecedor Exemplo",
            invoice_number="NF-123",
        ),
    )

    assert result.category.name == "Furadeiras"
    assert result.tool_model.organization == organization
    assert [unit.asset_code for unit in result.units] == [
        "EQ-000001",
        "EQ-000002",
        "EQ-000003",
        "EQ-000004",
        "EQ-000005",
    ]
    assert [unit.serial_number for unit in result.units] == [
        "SER-1",
        "SER-2",
        "",
        "SER-4",
        "SER-5",
    ]
    assert all(unit.status == ToolUnit.Status.AVAILABLE for unit in result.units)
    assert result.pricing_policy.daily_rate == Decimal("60.00")
    assert len(result.asset_profiles) == 5
    assert all(
        profile.acquisition_cost == Decimal("1200.00")
        for profile in result.asset_profiles
    )
    assert ToolUnit.objects.count() == 5
    assert AssetProfile.objects.count() == 5
    assert PricingPolicy.objects.count() == 1
    sequence = AssetCodeSequence.objects.get(organization=organization)
    assert sequence.next_value == 6
    assert str(sequence) == "Locadora Exemplo — próximo EQ-000006"


@pytest.mark.django_db
def test_assisted_batch_works_without_pricing_or_asset_profile():
    organization, establishment = create_organization()

    result = create_batch(organization=organization, establishment=establishment)

    assert result.pricing_policy is None
    assert result.asset_profiles == ()
    assert ToolUnit.objects.count() == 1
    assert not PricingPolicy.objects.exists()
    assert not AssetProfile.objects.exists()


@pytest.mark.django_db
def test_repeated_batches_never_reuse_asset_codes():
    organization, establishment = create_organization()
    category = Category.objects.create(organization=organization, name="Ferramentas")

    first = create_tool_batch(
        organization=organization,
        category=category,
        new_category_name="",
        establishment=establishment,
        model_name="Furadeira",
        quantity=3,
        serial_numbers=("", "", ""),
    )
    second = create_tool_batch(
        organization=organization,
        category=category,
        new_category_name="",
        establishment=establishment,
        model_name="Serra circular",
        quantity=2,
        serial_numbers=("", ""),
    )

    assert [unit.asset_code for unit in first.units] == [
        "EQ-000001",
        "EQ-000002",
        "EQ-000003",
    ]
    assert [unit.asset_code for unit in second.units] == ["EQ-000004", "EQ-000005"]
    assert ToolUnit.objects.values("asset_code").distinct().count() == 5


@pytest.mark.django_db
def test_invalid_asset_data_rolls_back_entire_new_batch_and_sequence():
    organization, establishment = create_organization()

    with pytest.raises(ValidationError):
        create_tool_batch(
            organization=organization,
            category=None,
            new_category_name="Furadeiras",
            establishment=establishment,
            model_name="Furadeira",
            quantity=2,
            serial_numbers=("SER-1", "SER-2"),
            asset=AssetConfiguration(
                acquisition_date=date(2026, 8, 1),
                placed_in_service_date=date(2026, 8, 10),
                acquisition_cost=Decimal("100.00"),
                residual_value=Decimal("101.00"),
                useful_life_months=60,
            ),
        )

    assert not Category.objects.exists()
    assert not ToolModel.objects.exists()
    assert not ToolUnit.objects.exists()
    assert not AssetProfile.objects.exists()
    assert not AssetCodeSequence.objects.exists()


@pytest.mark.django_db
def test_service_rejects_category_and_establishment_from_other_tenant():
    organization_a, establishment_a = create_organization()
    organization_b, establishment_b = create_organization("Locadora B", "locadora-b")
    category_b = Category.objects.create(organization=organization_b, name="Furadeiras")

    with pytest.raises(ValidationError) as category_error:
        create_tool_batch(
            organization=organization_a,
            category=category_b,
            new_category_name="",
            establishment=establishment_a,
            model_name="Furadeira",
            quantity=1,
            serial_numbers=("",),
        )
    assert "category" in category_error.value.message_dict

    category_a = Category.objects.create(organization=organization_a, name="Furadeiras")
    with pytest.raises(ValidationError) as establishment_error:
        create_tool_batch(
            organization=organization_a,
            category=category_a,
            new_category_name="",
            establishment=establishment_b,
            model_name="Furadeira",
            quantity=1,
            serial_numbers=("",),
        )
    assert "establishment" in establishment_error.value.message_dict
    assert not ToolModel.objects.exists()


@pytest.mark.django_db
def test_service_rejects_inactive_organization_and_missing_category():
    organization, establishment = create_organization()
    organization.active = False
    organization.save()

    with pytest.raises(ValidationError) as organization_error:
        create_batch(organization=organization, establishment=establishment)
    assert "A locadora ativa" in organization_error.value.messages[0]

    organization.active = True
    organization.save()
    with pytest.raises(ValidationError) as category_error:
        create_tool_batch(
            organization=organization,
            category=None,
            new_category_name="",
            establishment=establishment,
            model_name="Furadeira",
            quantity=1,
            serial_numbers=("",),
        )
    assert "new_category_name" in category_error.value.message_dict


@pytest.mark.django_db
def test_new_category_reactivates_existing_inactive_category():
    organization, establishment = create_organization()
    category = Category.objects.create(
        organization=organization,
        name="Furadeiras",
        active=False,
    )

    result = create_batch(organization=organization, establishment=establishment)

    category.refresh_from_db()
    assert category.active is True
    assert result.category == category


@pytest.mark.django_db
@pytest.mark.parametrize(
    "quantity,serial_numbers,field",
    [
        (0, (), "quantity"),
        (101, tuple("" for _ in range(101)), "quantity"),
        (2, ("SER-1",), "serial_numbers"),
        (2, ("SER-1", "SER-1"), "serial_numbers"),
        (1, ("X" * 101,), "serial_numbers"),
    ],
)
def test_service_validates_batch_size_and_serial_numbers(quantity, serial_numbers, field):
    organization, establishment = create_organization()

    with pytest.raises(ValidationError) as error:
        create_tool_batch(
            organization=organization,
            category=None,
            new_category_name="Furadeiras",
            establishment=establishment,
            model_name="Furadeira",
            quantity=quantity,
            serial_numbers=serial_numbers,
        )

    assert field in error.value.message_dict
    assert not ToolUnit.objects.exists()


@pytest.mark.django_db
def test_form_only_offers_active_tenant_categories_and_establishments():
    organization_a, establishment_a = create_organization()
    organization_b, establishment_b = create_organization("Locadora B", "locadora-b")
    category_a = Category.objects.create(organization=organization_a, name="Furadeiras")
    category_b = Category.objects.create(organization=organization_b, name="Serras")

    form = AssistedToolRegistrationForm(organization=organization_a)

    assert list(form.fields["category"].queryset) == [category_a]
    assert list(form.fields["establishment"].queryset) == [establishment_a]
    assert str(form.fields["establishment"].initial.pk) == str(establishment_a.pk)
    assert category_b not in form.fields["category"].queryset
    assert establishment_b not in form.fields["establishment"].queryset


@pytest.mark.django_db
def test_form_uses_headquarters_as_default_when_tenant_has_branches():
    organization, headquarters = create_organization()
    Establishment.objects.create(
        organization=organization,
        name="Filial Centro",
        kind=Establishment.Kind.BRANCH,
    )

    form = AssistedToolRegistrationForm(organization=organization)

    assert form.fields["establishment"].initial == headquarters


@pytest.mark.django_db
def test_form_requires_explicit_confirmation_for_common_asset_data():
    organization, establishment = create_organization()
    data = {
        "new_category_name": "Furadeiras",
        "model_name": "Furadeira",
        "deposit_amount": "0.00",
        "quantity": "1",
        "establishment": str(establishment.pk),
        "acquisition_date": "2026-08-01",
        "placed_in_service_date": "2026-08-10",
        "acquisition_cost": "1200.00",
        "residual_value": "120.00",
        "useful_life_months": "60",
    }

    form = AssistedToolRegistrationForm(data=data, organization=organization)

    assert not form.is_valid()
    assert "confirm_asset_data" in form.errors


@pytest.mark.django_db
def test_form_rejects_ambiguous_category_duplicate_model_and_extra_serials():
    organization, establishment = create_organization()
    category = Category.objects.create(organization=organization, name="Furadeiras")
    ToolModel.objects.create(
        organization=organization,
        category=category,
        name="Furadeira",
    )
    form = AssistedToolRegistrationForm(
        data=valid_form_data(
            establishment,
            category=str(category.pk),
            new_category_name="Outra categoria",
            serial_numbers="SER-1\nSER-2",
        ),
        organization=organization,
    )

    assert not form.is_valid()
    assert "new_category_name" in form.errors
    assert "model_name" in form.errors
    assert "serial_numbers" in form.errors


@pytest.mark.django_db
def test_form_requires_category_price_date_and_complete_valid_asset_data():
    organization, establishment = create_organization()
    form = AssistedToolRegistrationForm(
        data=valid_form_data(
            establishment,
            new_category_name="",
            effective_from="",
            daily_rate="60.00",
            confirm_asset_data="on",
            acquisition_date="2026-08-10",
            placed_in_service_date="2026-08-01",
            acquisition_cost="100.00",
            residual_value="101.00",
            useful_life_months="",
        ),
        organization=organization,
    )

    assert not form.is_valid()
    assert "new_category_name" in form.errors
    assert "effective_from" in form.errors
    assert "useful_life_months" in form.errors
    assert "residual_value" in form.errors
    assert "placed_in_service_date" in form.errors


@pytest.mark.django_db
def test_form_save_creates_confirmed_pricing_and_asset_profile():
    organization, establishment = create_organization()
    form = AssistedToolRegistrationForm(
        data=valid_form_data(
            establishment,
            daily_rate="60.00",
            confirm_asset_data="on",
            acquisition_date="2026-08-01",
            placed_in_service_date="2026-08-10",
            acquisition_cost="1200.00",
            residual_value="120.00",
            useful_life_months="60",
            supplier_name="Fornecedor",
            invoice_number="NF-123",
        ),
        organization=organization,
    )

    assert form.is_valid(), form.errors
    result = form.save()

    assert result.pricing_policy.daily_rate == Decimal("60.00")
    assert result.asset_profiles[0].supplier_name == "Fornecedor"


@pytest.mark.django_db
def test_assisted_registration_view_creates_batch_without_exposing_organization(client):
    organization, establishment = create_organization()
    user = create_user_with_membership(organization)
    client.force_login(user)

    response = client.post(
        reverse("catalog:assisted-registration"),
        data={
            "new_category_name": "Furadeiras",
            "model_name": "Furadeira de impacto",
            "brand": "Marca Exemplo",
            "model_number": "FI-900",
            "description": "Uso profissional",
            "deposit_amount": "200.00",
            "quantity": "2",
            "establishment": str(establishment.pk),
            "serial_numbers": "SER-1\nSER-2",
            "effective_from": "2026-08-10",
            "daily_rate": "60.00",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("catalog:equipment-list")
    assert list(ToolUnit.objects.values_list("asset_code", flat=True)) == [
        "EQ-000001",
        "EQ-000002",
    ]
    assert ToolUnit.objects.filter(organization=organization).count() == 2

    listing = client.get(reverse("catalog:equipment-list"))
    content = listing.content.decode()
    assert listing.status_code == 200
    assert "EQ-000001" in content
    assert "Furadeira de impacto" in content


@pytest.mark.django_db
def test_manipulated_form_cannot_use_another_tenants_relationships(client):
    organization_a, _ = create_organization()
    organization_b, establishment_b = create_organization("Locadora B", "locadora-b")
    category_b = Category.objects.create(organization=organization_b, name="Furadeiras")
    user = create_user_with_membership(organization_a)
    client.force_login(user)

    response = client.post(
        reverse("catalog:assisted-registration"),
        data={
            "category": str(category_b.pk),
            "model_name": "Furadeira",
            "deposit_amount": "0.00",
            "quantity": "1",
            "establishment": str(establishment_b.pk),
        },
    )

    assert response.status_code == 200
    assert "Faça uma escolha válida" in response.content.decode()
    assert not ToolModel.objects.exists()
    assert not ToolUnit.objects.exists()


@pytest.mark.django_db
def test_equipment_list_never_displays_other_tenants_units(client):
    organization_a, establishment_a = create_organization()
    organization_b, establishment_b = create_organization("Locadora B", "locadora-b")
    create_batch(
        organization=organization_a,
        establishment=establishment_a,
        model_name="Furadeira A",
    )
    create_batch(
        organization=organization_b,
        establishment=establishment_b,
        model_name="Furadeira B",
    )
    user = create_user_with_membership(organization_a)
    client.force_login(user)

    response = client.get(reverse("catalog:equipment-list"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Furadeira A" in content
    assert "Furadeira B" not in content


@pytest.mark.django_db
def test_assisted_views_require_active_organization(client):
    user = User.objects.create_user(username="sem-locadora", password="test-password-123")
    client.force_login(user)

    response = client.get(reverse("catalog:assisted-registration"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:home")

    listing = client.get(reverse("catalog:equipment-list"))
    assert listing.status_code == 302
    assert listing.url == reverse("workspace:home")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "service_error,expected_message",
    [
        (
            ValidationError({"category": "Categoria alterada durante o cadastro."}),
            "Categoria alterada",
        ),
        (ValidationError("Falha geral de validação."), "Falha geral"),
        (IntegrityError("conflito concorrente"), "entrou em conflito"),
    ],
)
def test_view_reports_service_conflicts_without_partial_success(
    client,
    service_error,
    expected_message,
):
    organization, establishment = create_organization()
    user = create_user_with_membership(organization)
    client.force_login(user)

    with patch(
        "apps.catalog.views.AssistedToolRegistrationForm.save",
        side_effect=service_error,
    ):
        response = client.post(
            reverse("catalog:assisted-registration"),
            data=valid_form_data(establishment),
        )

    assert response.status_code == 200
    assert expected_message in response.content.decode()
    assert not ToolUnit.objects.exists()


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="PostgreSQL is required to verify row-lock concurrency.",
)
@pytest.mark.django_db(transaction=True)
def test_concurrent_batches_allocate_distinct_code_ranges():
    organization, establishment = create_organization()
    category = Category.objects.create(organization=organization, name="Ferramentas")
    barrier = Barrier(2)

    def register(index):
        close_old_connections()
        try:
            barrier.wait()
            result = create_tool_batch(
                organization=organization,
                category=category,
                new_category_name="",
                establishment=establishment,
                model_name=f"Modelo {index}",
                quantity=5,
                serial_numbers=("", "", "", "", ""),
            )
            return [unit.asset_code for unit in result.units]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        batches = list(executor.map(register, (1, 2)))

    codes = [code for batch in batches for code in batch]
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert set(codes) == {f"EQ-{value:06d}" for value in range(1, 11)}
    assert AssetCodeSequence.objects.get(organization=organization).next_value == 11
