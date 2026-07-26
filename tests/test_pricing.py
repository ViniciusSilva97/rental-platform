from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.forms.models import inlineformset_factory

from apps.catalog.admin import PricingPolicyInlineFormSet
from apps.catalog.models import Category, ToolModel
from apps.organizations.models import Organization
from apps.pricing.models import BillingUnit, PricingPolicy
from apps.pricing.services import (
    PricingUnavailable,
    calculate_charge,
    select_effective_policy,
)


def create_tool_model(*, organization, name="Furadeira"):
    category = Category.objects.create(organization=organization, name=f"{name}s")
    return ToolModel.objects.create(
        organization=organization,
        category=category,
        name=name,
    )


@pytest.mark.django_db
def test_pricing_policy_accepts_optional_hour_day_and_month_rates():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)

    policy = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 7, 1),
        hourly_rate=Decimal("12.50"),
        daily_rate=Decimal("45.00"),
        monthly_rate=Decimal("780.00"),
    )

    assert policy.fixed_month_days == 30
    assert str(policy) == "Furadeira — 01/07/2026"


@pytest.mark.django_db
def test_pricing_policy_requires_at_least_one_rate():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)

    with pytest.raises(ValidationError) as error:
        PricingPolicy.objects.create(
            organization=organization,
            tool_model=tool_model,
            effective_from=date(2026, 7, 1),
        )

    assert "hourly_rate" in error.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["hourly_rate", "daily_rate", "monthly_rate"])
def test_pricing_policy_rejects_negative_rates(field):
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)
    values = {"daily_rate": Decimal("45.00"), field: Decimal("-0.01")}

    with pytest.raises(ValidationError):
        PricingPolicy.objects.create(
            organization=organization,
            tool_model=tool_model,
            effective_from=date(2026, 7, 1),
            **values,
        )


@pytest.mark.django_db
def test_pricing_policy_rejects_tool_model_from_another_organization():
    organization_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    organization_b = Organization.objects.create(name="Locadora B", slug="locadora-b")
    tool_model_a = create_tool_model(organization=organization_a)

    with pytest.raises(ValidationError) as error:
        PricingPolicy.objects.create(
            organization=organization_b,
            tool_model=tool_model_a,
            effective_from=date(2026, 7, 1),
            daily_rate=Decimal("45.00"),
        )

    assert "tool_model" in error.value.message_dict


@pytest.mark.django_db
def test_calendar_month_does_not_keep_fixed_days():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)

    policy = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 7, 1),
        monthly_rate=Decimal("780.00"),
        month_definition=PricingPolicy.MonthDefinition.CALENDAR_MONTH,
        fixed_month_days=30,
    )

    assert policy.fixed_month_days is None


@pytest.mark.django_db
def test_fixed_month_requires_valid_number_of_days():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)

    with pytest.raises(ValidationError) as error:
        PricingPolicy.objects.create(
            organization=organization,
            tool_model=tool_model,
            effective_from=date(2026, 7, 1),
            monthly_rate=Decimal("780.00"),
            fixed_month_days=0,
        )

    assert "fixed_month_days" in error.value.message_dict


@pytest.mark.django_db
def test_tool_model_has_only_one_policy_version_per_date():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)
    policy_data = {
        "organization": organization,
        "tool_model": tool_model,
        "effective_from": date(2026, 7, 1),
        "daily_rate": Decimal("45.00"),
    }
    PricingPolicy.objects.create(**policy_data)

    with pytest.raises(ValidationError):
        PricingPolicy.objects.create(**policy_data)


@pytest.mark.django_db
def test_select_effective_policy_uses_latest_active_version_in_force():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)
    old_policy = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 1, 1),
        daily_rate=Decimal("40.00"),
    )
    current_policy = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 7, 1),
        daily_rate=Decimal("45.00"),
    )
    PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 8, 1),
        daily_rate=Decimal("50.00"),
    )

    assert (
        select_effective_policy(tool_model=tool_model, on_date=date(2026, 7, 26))
        == current_policy
    )

    current_policy.active = False
    current_policy.save()
    assert (
        select_effective_policy(tool_model=tool_model, on_date=date(2026, 7, 26))
        == old_policy
    )


@pytest.mark.django_db
def test_select_effective_policy_returns_none_without_version_in_force():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)
    PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 8, 1),
        daily_rate=Decimal("45.00"),
    )

    assert (
        select_effective_policy(tool_model=tool_model, on_date=date(2026, 7, 26))
        is None
    )


def test_calculate_charge_rounds_started_unit_up():
    policy = PricingPolicy(
        daily_rate=Decimal("45.00"),
        partial_unit_rounding=PricingPolicy.PartialUnitRounding.UP,
    )

    assert (
        calculate_charge(
            policy=policy,
            unit=BillingUnit.DAY,
            quantity=Decimal("1.1"),
        )
        == Decimal("90.00")
    )


def test_calculate_charge_can_be_proportional():
    policy = PricingPolicy(
        daily_rate=Decimal("45.00"),
        partial_unit_rounding=PricingPolicy.PartialUnitRounding.PROPORTIONAL,
    )

    assert (
        calculate_charge(
            policy=policy,
            unit="day",
            quantity=Decimal("1.5"),
        )
        == Decimal("67.50")
    )


def test_calculate_charge_rejects_unavailable_rate():
    policy = PricingPolicy(daily_rate=Decimal("45.00"))

    with pytest.raises(PricingUnavailable):
        calculate_charge(
            policy=policy,
            unit="HOUR",
            quantity=Decimal("1"),
        )


def test_calculate_charge_rejects_unknown_unit():
    policy = PricingPolicy(daily_rate=Decimal("45.00"))

    with pytest.raises(ValueError):
        calculate_charge(
            policy=policy,
            unit="WEEK",
            quantity=Decimal("1"),
        )


@pytest.mark.parametrize(
    "quantity",
    [Decimal("0"), Decimal("-1"), "não numérico", 1.5],
)
def test_calculate_charge_rejects_invalid_quantity(quantity):
    policy = PricingPolicy(daily_rate=Decimal("45.00"))

    with pytest.raises(ValueError):
        calculate_charge(policy=policy, unit="DAY", quantity=quantity)


@pytest.mark.django_db
def test_pricing_inline_inherits_tool_model_organization():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    tool_model = create_tool_model(organization=organization)
    policy_formset = inlineformset_factory(
        ToolModel,
        PricingPolicy,
        formset=PricingPolicyInlineFormSet,
        fields=(
            "effective_from",
            "hourly_rate",
            "daily_rate",
            "monthly_rate",
            "partial_unit_rounding",
            "month_definition",
            "fixed_month_days",
            "active",
        ),
        extra=1,
    )
    formset = policy_formset(
        data={
            "pricing_policies-TOTAL_FORMS": "1",
            "pricing_policies-INITIAL_FORMS": "0",
            "pricing_policies-MIN_NUM_FORMS": "0",
            "pricing_policies-MAX_NUM_FORMS": "1000",
            "pricing_policies-0-effective_from": "2026-07-01",
            "pricing_policies-0-hourly_rate": "",
            "pricing_policies-0-daily_rate": "45.00",
            "pricing_policies-0-monthly_rate": "780.00",
            "pricing_policies-0-partial_unit_rounding": (
                PricingPolicy.PartialUnitRounding.UP
            ),
            "pricing_policies-0-month_definition": (
                PricingPolicy.MonthDefinition.FIXED_DAYS
            ),
            "pricing_policies-0-fixed_month_days": "30",
            "pricing_policies-0-active": "on",
        },
        instance=tool_model,
        prefix="pricing_policies",
    )

    assert formset.is_valid(), formset.errors
    policy = formset.save()[0]
    assert policy.organization == organization
