from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Category, ToolModel
from apps.customers.models import Customer
from apps.organizations.models import Membership, Organization
from apps.pricing.models import BillingUnit, PricingPolicy
from apps.quotations.admin import (
    QuotationAdmin,
    QuotationItemAdmin,
    QuotationItemInline,
)
from apps.quotations.models import Quotation, QuotationItem
from apps.quotations.services import (
    QuotationLineInput,
    calculate_period,
    recalculate_draft_quotation,
    save_draft_quotation,
    transition_quotation,
)


def aware(year, month, day, hour=0, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute))


def create_domain(suffix="a", **policy_values):
    organization = Organization.objects.create(
        name=f"Locadora {suffix.upper()}",
        slug=f"locadora-{suffix}",
    )
    customer = Customer.objects.create(
        organization=organization,
        kind=Customer.Kind.INDIVIDUAL,
        name=f"Cliente {suffix.upper()}",
        document="529.982.247-25",
    )
    category = Category.objects.create(
        organization=organization,
        name=f"Furadeiras {suffix}",
    )
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name=f"Furadeira {suffix}",
    )
    defaults = {
        "effective_from": date(2026, 1, 1),
        "daily_rate": Decimal("60.00"),
    }
    defaults.update(policy_values)
    policy = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        **defaults,
    )
    return organization, customer, tool_model, policy


def create_quote(
    *,
    organization,
    customer,
    tool_model,
    starts_at=None,
    ends_at=None,
    equipment_quantity=2,
    billing_unit=BillingUnit.DAY,
):
    return save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=starts_at or aware(2026, 8, 13, 8),
        ends_at=ends_at or aware(2026, 8, 16, 8),
        lines=(
            QuotationLineInput(
                tool_model=tool_model,
                equipment_quantity=equipment_quantity,
                billing_unit=billing_unit,
            ),
        ),
    )


def create_user(organization, suffix="a"):
    user = User.objects.create_user(
        username=f"usuario-{suffix}",
        email=f"usuario-{suffix}@example.com",
        password="test-password-123",
    )
    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.Role.OWNER,
    )
    return user


def quotation_post_data(customer, tool_model, **overrides):
    data = {
        "customer": str(customer.pk),
        "starts_at": "2026-08-13T08:00",
        "ends_at": "2026-08-16T08:00",
        "items-TOTAL_FORMS": "1",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "1",
        "items-MAX_NUM_FORMS": "20",
        "items-0-tool_model": str(tool_model.pk),
        "items-0-equipment_quantity": "2",
        "items-0-billing_unit": BillingUnit.DAY,
    }
    data.update(overrides)
    return data


def policy_for_period(**values):
    defaults = {
        "daily_rate": Decimal("60.00"),
        "partial_unit_rounding": PricingPolicy.PartialUnitRounding.UP,
        "month_definition": PricingPolicy.MonthDefinition.FIXED_DAYS,
        "fixed_month_days": 30,
    }
    defaults.update(values)
    return PricingPolicy(**defaults)


def test_period_converts_hours_and_applies_rounding_rule():
    policy = policy_for_period(hourly_rate=Decimal("10.00"))

    result = calculate_period(
        policy=policy,
        unit=BillingUnit.HOUR,
        starts_at=aware(2026, 8, 13, 8),
        ends_at=aware(2026, 8, 13, 9, 30),
    )

    assert result.period_quantity == Decimal("1.500000")
    assert result.billed_quantity == Decimal("2.000000")


def test_period_can_preserve_proportional_day_fraction():
    policy = policy_for_period(
        partial_unit_rounding=PricingPolicy.PartialUnitRounding.PROPORTIONAL
    )

    result = calculate_period(
        policy=policy,
        unit=BillingUnit.DAY,
        starts_at=aware(2026, 8, 13, 8),
        ends_at=aware(2026, 8, 14, 20),
    )

    assert result.period_quantity == Decimal("1.500000")
    assert result.billed_quantity == Decimal("1.500000")


def test_period_converts_fixed_month_days():
    policy = policy_for_period(
        monthly_rate=Decimal("900.00"),
        partial_unit_rounding=PricingPolicy.PartialUnitRounding.PROPORTIONAL,
    )

    result = calculate_period(
        policy=policy,
        unit=BillingUnit.MONTH,
        starts_at=aware(2026, 1, 1),
        ends_at=aware(2026, 2, 15),
    )

    assert result.period_quantity == Decimal("1.500000")


def test_period_treats_matching_calendar_dates_as_whole_month():
    policy = policy_for_period(
        monthly_rate=Decimal("900.00"),
        month_definition=PricingPolicy.MonthDefinition.CALENDAR_MONTH,
        fixed_month_days=None,
        partial_unit_rounding=PricingPolicy.PartialUnitRounding.PROPORTIONAL,
    )

    result = calculate_period(
        policy=policy,
        unit=BillingUnit.MONTH,
        starts_at=aware(2026, 1, 31, 10),
        ends_at=aware(2026, 2, 28, 10),
    )

    assert result.period_quantity == Decimal("1.000000")
    assert result.billed_quantity == Decimal("1.000000")


def test_calendar_month_handles_december_and_partial_months():
    policy = policy_for_period(
        monthly_rate=Decimal("900.00"),
        month_definition=PricingPolicy.MonthDefinition.CALENDAR_MONTH,
        fixed_month_days=None,
        partial_unit_rounding=PricingPolicy.PartialUnitRounding.PROPORTIONAL,
    )

    result = calculate_period(
        policy=policy,
        unit=BillingUnit.MONTH,
        starts_at=datetime(2026, 12, 31, 10),
        ends_at=datetime(2027, 2, 14, 10),
    )

    assert Decimal("1") < result.period_quantity < Decimal("2")
    assert result.billed_quantity == result.period_quantity


@pytest.mark.parametrize(
    "unit,starts_at,ends_at",
    [
        ("WEEK", aware(2026, 1, 1), aware(2026, 1, 2)),
        (BillingUnit.DAY, aware(2026, 1, 2), aware(2026, 1, 1)),
        (BillingUnit.DAY, aware(2026, 1, 1), aware(2026, 1, 1)),
    ],
)
def test_period_rejects_invalid_unit_or_interval(unit, starts_at, ends_at):
    with pytest.raises(ValueError):
        calculate_period(
            policy=policy_for_period(),
            unit=unit,
            starts_at=starts_at,
            ends_at=ends_at,
        )


@pytest.mark.parametrize("quantity", [1.5, "inválida", Decimal("0")])
def test_billable_quantity_rejects_invalid_values(quantity):
    from apps.pricing.services import calculate_billable_quantity

    with pytest.raises(ValueError):
        calculate_billable_quantity(policy=policy_for_period(), quantity=quantity)


@pytest.mark.django_db
def test_draft_saves_price_quantity_total_and_memory_snapshot():
    organization, customer, tool_model, policy = create_domain()

    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )

    item = quotation.items.get()
    assert quotation.status == Quotation.Status.DRAFT
    assert quotation.total_amount == Decimal("360.00")
    assert item.pricing_policy == policy
    assert item.period_quantity == Decimal("3.000000")
    assert item.billed_quantity == Decimal("3.000000")
    assert item.unit_rate == Decimal("60.00")
    assert item.line_total == Decimal("360.00")
    assert item.policy_effective_from == policy.effective_from
    assert "2 equipamento(s) × 3 dia(s) × R$ 60,00 = R$ 360,00" == (
        item.calculation_summary
    )


@pytest.mark.django_db
def test_existing_snapshot_survives_price_change_until_draft_is_recalculated():
    organization, customer, tool_model, policy = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    original_item_id = quotation.items.get().pk

    policy.daily_rate = Decimal("100.00")
    policy.save()

    quotation.refresh_from_db()
    stored_item = quotation.items.get()
    assert stored_item.pk == original_item_id
    assert stored_item.unit_rate == Decimal("60.00")
    assert quotation.total_amount == Decimal("360.00")

    recalculate_draft_quotation(organization=organization, quotation=quotation)
    quotation.refresh_from_db()
    recalculated_item = quotation.items.get()
    assert recalculated_item.pk != original_item_id
    assert recalculated_item.unit_rate == Decimal("100.00")
    assert quotation.total_amount == Decimal("600.00")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "month_definition,fixed_month_days,starts_at,ends_at,expected_quantity,expected_total",
    [
        (
            PricingPolicy.MonthDefinition.FIXED_DAYS,
            30,
            aware(2026, 1, 1),
            aware(2026, 2, 15),
            Decimal("1.500000"),
            Decimal("1350.00"),
        ),
        (
            PricingPolicy.MonthDefinition.CALENDAR_MONTH,
            None,
            aware(2026, 1, 31, 10),
            aware(2026, 2, 28, 10),
            Decimal("1.000000"),
            Decimal("900.00"),
        ),
    ],
)
def test_monthly_snapshots_follow_fixed_and_calendar_month_policies(
    month_definition,
    fixed_month_days,
    starts_at,
    ends_at,
    expected_quantity,
    expected_total,
):
    organization, customer, tool_model, _ = create_domain(
        daily_rate=None,
        monthly_rate=Decimal("900.00"),
        month_definition=month_definition,
        fixed_month_days=fixed_month_days,
        partial_unit_rounding=PricingPolicy.PartialUnitRounding.PROPORTIONAL,
    )

    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        starts_at=starts_at,
        ends_at=ends_at,
        equipment_quantity=1,
        billing_unit=BillingUnit.MONTH,
    )

    item = quotation.items.get()
    assert item.period_quantity == expected_quantity
    assert item.billed_quantity == expected_quantity
    assert item.line_total == expected_total
    assert quotation.total_amount == expected_total


@pytest.mark.django_db
def test_service_selects_latest_active_policy_already_in_force():
    organization, customer, tool_model, old_policy = create_domain(daily_rate=Decimal("40.00"))
    current = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 8, 1),
        daily_rate=Decimal("70.00"),
    )
    PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 8, 14),
        daily_rate=Decimal("90.00"),
    )
    inactive = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 8, 12),
        daily_rate=Decimal("80.00"),
        active=False,
    )

    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )

    item = quotation.items.get()
    assert item.pricing_policy == current
    assert item.pricing_policy not in {old_policy, inactive}
    assert item.unit_rate == Decimal("70.00")


@pytest.mark.django_db
def test_service_rejects_missing_rate_future_policy_and_invalid_period():
    organization, customer, tool_model, policy = create_domain(
        daily_rate=None,
        hourly_rate=Decimal("10.00"),
    )

    with pytest.raises(ValidationError, match="não possui valor por dia"):
        create_quote(
            organization=organization,
            customer=customer,
            tool_model=tool_model,
        )

    policy.effective_from = date(2026, 9, 1)
    policy.save()
    with pytest.raises(ValidationError, match="Não existe preço ativo"):
        create_quote(
            organization=organization,
            customer=customer,
            tool_model=tool_model,
            billing_unit=BillingUnit.HOUR,
        )

    with pytest.raises(ValidationError):
        create_quote(
            organization=organization,
            customer=customer,
            tool_model=tool_model,
            starts_at=aware(2026, 8, 16),
            ends_at=aware(2026, 8, 15),
        )


@pytest.mark.django_db
def test_service_rejects_cross_tenant_customer_tool_and_quotation():
    organization_a, customer_a, tool_a, _ = create_domain("a")
    organization_b, customer_b, tool_b, _ = create_domain("b")

    with pytest.raises(ValidationError, match="cliente ativo"):
        create_quote(
            organization=organization_a,
            customer=customer_b,
            tool_model=tool_a,
        )
    with pytest.raises(ValidationError, match="não pertence"):
        create_quote(
            organization=organization_a,
            customer=customer_a,
            tool_model=tool_b,
        )

    quotation_b = create_quote(
        organization=organization_b,
        customer=customer_b,
        tool_model=tool_b,
    )
    with pytest.raises(ValidationError, match="não pertence"):
        save_draft_quotation(
            organization=organization_a,
            customer=customer_a,
            starts_at=aware(2026, 8, 13),
            ends_at=aware(2026, 8, 14),
            lines=(QuotationLineInput(tool_a, 1, BillingUnit.DAY),),
            quotation=quotation_b,
        )


@pytest.mark.django_db
def test_service_rejects_empty_and_duplicate_lines():
    organization, customer, tool_model, _ = create_domain()
    with pytest.raises(ValidationError, match="ao menos um item"):
        save_draft_quotation(
            organization=organization,
            customer=customer,
            starts_at=aware(2026, 8, 13),
            ends_at=aware(2026, 8, 14),
            lines=(),
        )

    duplicate = QuotationLineInput(tool_model, 1, BillingUnit.DAY)
    with pytest.raises(ValidationError, match="repetido"):
        save_draft_quotation(
            organization=organization,
            customer=customer,
            starts_at=aware(2026, 8, 13),
            ends_at=aware(2026, 8, 14),
            lines=(duplicate, duplicate),
        )
    assert not Quotation.objects.exists()


@pytest.mark.django_db
def test_service_rejects_inactive_organization_invalid_unit_and_quantity():
    organization, customer, tool_model, _ = create_domain()
    organization.active = False
    organization.save()
    with pytest.raises(ValidationError, match="locadora ativa"):
        create_quote(
            organization=organization,
            customer=customer,
            tool_model=tool_model,
        )

    organization.active = True
    organization.save()
    for line, message in (
        (QuotationLineInput(tool_model, 1, "WEEK"), "unidade"),
        (QuotationLineInput(tool_model, 0, BillingUnit.DAY), "ao menos um"),
    ):
        with pytest.raises(ValidationError, match=message):
            save_draft_quotation(
                organization=organization,
                customer=customer,
                starts_at=aware(2026, 8, 13),
                ends_at=aware(2026, 8, 14),
                lines=(line,),
            )


@pytest.mark.django_db
def test_state_transitions_preserve_snapshot_and_block_recalculation():
    organization, customer, tool_model, policy = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    item_id = quotation.items.get().pk

    sent = transition_quotation(
        organization=organization,
        quotation=quotation,
        target_status=Quotation.Status.SENT,
    )
    assert sent.status == Quotation.Status.SENT
    assert sent.sent_at is not None

    policy.daily_rate = Decimal("120.00")
    policy.save()
    with pytest.raises(ValidationError, match="Somente orçamentos em rascunho"):
        recalculate_draft_quotation(organization=organization, quotation=sent)

    expired = transition_quotation(
        organization=organization,
        quotation=sent,
        target_status=Quotation.Status.EXPIRED,
    )
    assert expired.expired_at is not None
    assert expired.items.get().pk == item_id
    assert expired.total_amount == Decimal("360.00")

    with pytest.raises(ValidationError, match="Não é permitido"):
        transition_quotation(
            organization=organization,
            quotation=expired,
            target_status=Quotation.Status.CANCELLED,
        )


@pytest.mark.django_db
def test_draft_and_sent_quotations_can_be_cancelled():
    organization, customer, tool_model, _ = create_domain()
    draft = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    cancelled = transition_quotation(
        organization=organization,
        quotation=draft,
        target_status=Quotation.Status.CANCELLED,
    )
    assert cancelled.cancelled_at is not None

    second = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    sent = transition_quotation(
        organization=organization,
        quotation=second,
        target_status=Quotation.Status.SENT,
    )
    cancelled_sent = transition_quotation(
        organization=organization,
        quotation=sent,
        target_status=Quotation.Status.CANCELLED,
    )
    assert cancelled_sent.status == Quotation.Status.CANCELLED


@pytest.mark.django_db
def test_models_reject_cross_tenant_relationships():
    organization_a, customer_a, tool_a, policy_a = create_domain("a")
    organization_b, customer_b, _, _ = create_domain("b")

    with pytest.raises(ValidationError) as quotation_error:
        Quotation.objects.create(
            organization=organization_a,
            customer=customer_b,
            starts_at=aware(2026, 8, 13),
            ends_at=aware(2026, 8, 14),
        )
    assert "customer" in quotation_error.value.message_dict

    quotation = Quotation.objects.create(
        organization=organization_a,
        customer=customer_a,
        starts_at=aware(2026, 8, 13),
        ends_at=aware(2026, 8, 14),
    )
    with pytest.raises(ValidationError) as item_error:
        QuotationItem.objects.create(
            organization=organization_b,
            quotation=quotation,
            tool_model=tool_a,
            pricing_policy=policy_a,
            equipment_quantity=1,
            billing_unit=BillingUnit.DAY,
            period_quantity=Decimal("1.000000"),
            billed_quantity=Decimal("1.000000"),
            unit_rate=Decimal("60.00"),
            line_total=Decimal("60.00"),
            policy_effective_from=policy_a.effective_from,
            partial_unit_rounding=policy_a.partial_unit_rounding,
            month_definition=policy_a.month_definition,
            fixed_month_days=policy_a.fixed_month_days,
        )
    assert "quotation" in item_error.value.message_dict


@pytest.mark.django_db
def test_models_reject_invalid_period_and_policy_from_another_model():
    organization, customer, tool_model, policy = create_domain()
    with pytest.raises(ValidationError) as period_error:
        Quotation.objects.create(
            organization=organization,
            customer=customer,
            starts_at=aware(2026, 8, 14),
            ends_at=aware(2026, 8, 13),
        )
    assert "ends_at" in period_error.value.message_dict

    other_category = Category.objects.create(organization=organization, name="Serras")
    other_model = ToolModel.objects.create(
        organization=organization,
        category=other_category,
        name="Serra",
    )
    quotation = Quotation.objects.create(
        organization=organization,
        customer=customer,
        starts_at=aware(2026, 8, 13),
        ends_at=aware(2026, 8, 14),
    )
    with pytest.raises(ValidationError) as policy_error:
        QuotationItem.objects.create(
            organization=organization,
            quotation=quotation,
            tool_model=other_model,
            pricing_policy=policy,
            equipment_quantity=1,
            billing_unit=BillingUnit.DAY,
            period_quantity=Decimal("1.000000"),
            billed_quantity=Decimal("1.000000"),
            unit_rate=Decimal("60.00"),
            line_total=Decimal("60.00"),
            policy_effective_from=policy.effective_from,
            partial_unit_rounding=policy.partial_unit_rounding,
            month_definition=policy.month_definition,
            fixed_month_days=policy.fixed_month_days,
        )
    assert "pricing_policy" in policy_error.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"billing_unit": "WEEK"},
        {"partial_unit_rounding": "INVALID"},
        {"month_definition": "FIXED_DAYS", "fixed_month_days": None},
    ],
)
def test_database_protects_snapshot_enumerations_and_month_definition(changes):
    organization, customer, tool_model, _ = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        QuotationItem.objects.filter(quotation=quotation).update(**changes)


@pytest.mark.django_db
def test_database_rejects_invalid_quotation_status():
    organization, customer, tool_model, _ = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Quotation.objects.filter(pk=quotation.pk).update(status="INVALID")


def test_quotation_admin_disables_creation_and_deletion():
    site = AdminSite()
    quotation_admin = QuotationAdmin(Quotation, site)
    item_admin = QuotationItemAdmin(QuotationItem, site)
    item_inline = QuotationItemInline(Quotation, site)

    assert not quotation_admin.has_add_permission(None)
    assert not quotation_admin.has_delete_permission(None)
    assert not item_admin.has_add_permission(None)
    assert not item_admin.has_delete_permission(None)
    assert not item_inline.has_add_permission(None)
    assert item_inline.can_delete is False


@pytest.mark.django_db
def test_create_view_saves_multiple_snapshotted_items(client):
    organization, customer, tool_model, _ = create_domain()
    second_category = Category.objects.create(organization=organization, name="Serras")
    second_model = ToolModel.objects.create(
        organization=organization,
        category=second_category,
        name="Serra circular",
    )
    PricingPolicy.objects.create(
        organization=organization,
        tool_model=second_model,
        effective_from=date(2026, 1, 1),
        daily_rate=Decimal("40.00"),
    )
    user = create_user(organization)
    client.force_login(user)
    data = quotation_post_data(
        customer,
        tool_model,
        **{
            "items-TOTAL_FORMS": "2",
            "items-1-tool_model": str(second_model.pk),
            "items-1-equipment_quantity": "1",
            "items-1-billing_unit": BillingUnit.DAY,
        },
    )

    response = client.post(reverse("quotations:create"), data=data)

    quotation = Quotation.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("quotations:detail", args=[quotation.pk])
    assert quotation.items.count() == 2
    assert quotation.total_amount == Decimal("480.00")
    detail = client.get(response.url)
    assert detail.status_code == 200
    assert "Memória de cálculo" in detail.content.decode()
    assert "R$ 480,00" in detail.content.decode()
    assert "Adicionar outra ferramenta" in client.get(reverse("quotations:create")).content.decode()


@pytest.mark.django_db
def test_item_rows_only_grow_when_requested(client):
    organization, customer, tool_model, _ = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    user = create_user(organization)
    client.force_login(user)

    create_response = client.get(reverse("quotations:create"))
    edit_response = client.get(reverse("quotations:edit", args=[quotation.pk]))

    assert len(create_response.context["formset"].forms) == 1
    assert len(edit_response.context["formset"].forms) == 1
    assert "Item 2" not in create_response.content.decode()
    assert "Item 2" not in edit_response.content.decode()


@pytest.mark.django_db
def test_forms_and_views_never_expose_another_tenant(client):
    organization_a, customer_a, tool_a, _ = create_domain("a")
    organization_b, customer_b, tool_b, _ = create_domain("b")
    quotation_b = create_quote(
        organization=organization_b,
        customer=customer_b,
        tool_model=tool_b,
    )
    user = create_user(organization_a)
    client.force_login(user)

    response = client.get(reverse("quotations:create"))
    form = response.context["form"]
    item_form = response.context["formset"].forms[0]
    assert list(form.fields["customer"].queryset) == [customer_a]
    assert list(item_form.fields["tool_model"].queryset) == [tool_a]
    assert customer_b not in form.fields["customer"].queryset
    assert tool_b not in item_form.fields["tool_model"].queryset
    assert client.get(reverse("quotations:detail", args=[quotation_b.pk])).status_code == 404

    manipulated = client.post(
        reverse("quotations:create"),
        data=quotation_post_data(customer_b, tool_b),
    )
    assert manipulated.status_code == 200
    assert "Faça uma escolha válida" in manipulated.content.decode()
    assert Quotation.objects.count() == 1


@pytest.mark.django_db
def test_operational_actions_follow_draft_sent_expired_flow(client):
    organization, customer, tool_model, _ = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    user = create_user(organization)
    client.force_login(user)

    edit = client.get(reverse("quotations:edit", args=[quotation.pk]))
    assert edit.status_code == 200

    sent = client.post(
        reverse("quotations:transition", args=[quotation.pk, Quotation.Status.SENT])
    )
    assert sent.status_code == 302
    quotation.refresh_from_db()
    assert quotation.status == Quotation.Status.SENT

    blocked_edit = client.get(reverse("quotations:edit", args=[quotation.pk]))
    assert blocked_edit.status_code == 302
    blocked_recalculation = client.post(reverse("quotations:recalculate", args=[quotation.pk]))
    assert blocked_recalculation.status_code == 302

    expired = client.post(
        reverse("quotations:transition", args=[quotation.pk, Quotation.Status.EXPIRED])
    )
    assert expired.status_code == 302
    quotation.refresh_from_db()
    assert quotation.status == Quotation.Status.EXPIRED


@pytest.mark.django_db
def test_list_edit_and_recalculate_views_update_only_the_active_tenant(client):
    organization, customer, tool_model, policy = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    user = create_user(organization)
    client.force_login(user)

    listing = client.get(reverse("quotations:list"))
    assert listing.status_code == 200
    assert quotation.display_code in listing.content.decode()

    edited = client.post(
        reverse("quotations:edit", args=[quotation.pk]),
        data=quotation_post_data(
            customer,
            tool_model,
            **{"items-0-equipment_quantity": "1"},
        ),
    )
    assert edited.status_code == 302
    quotation.refresh_from_db()
    assert quotation.total_amount == Decimal("180.00")

    policy.daily_rate = Decimal("80.00")
    policy.save()
    recalculated = client.post(reverse("quotations:recalculate", args=[quotation.pk]))
    assert recalculated.status_code == 302
    quotation.refresh_from_db()
    assert quotation.total_amount == Decimal("240.00")


@pytest.mark.django_db
def test_create_view_reports_domain_value_and_integrity_errors(client):
    organization, customer, tool_model, policy = create_domain()
    user = create_user(organization)
    client.force_login(user)

    policy.active = False
    policy.save()
    domain_error = client.post(
        reverse("quotations:create"),
        data=quotation_post_data(customer, tool_model),
    )
    assert domain_error.status_code == 200
    assert "Não existe preço ativo" in domain_error.content.decode()

    with patch(
        "apps.quotations.views.save_draft_quotation",
        side_effect=ValueError("Falha de cálculo controlada."),
    ):
        value_error = client.post(
            reverse("quotations:create"),
            data=quotation_post_data(customer, tool_model),
        )
    assert "Falha de cálculo controlada" in value_error.content.decode()

    with patch(
        "apps.quotations.views.save_draft_quotation",
        side_effect=IntegrityError("conflito"),
    ):
        integrity_error = client.post(
            reverse("quotations:create"),
            data=quotation_post_data(customer, tool_model),
        )
    assert "entrou em conflito" in integrity_error.content.decode()


@pytest.mark.django_db
def test_transition_view_rejects_unknown_or_forbidden_state(client):
    organization, customer, tool_model, _ = create_domain()
    quotation = create_quote(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    user = create_user(organization)
    client.force_login(user)

    unknown = client.post(reverse("quotations:transition", args=[quotation.pk, "UNKNOWN"]))
    assert unknown.status_code == 404

    forbidden = client.post(
        reverse("quotations:transition", args=[quotation.pk, Quotation.Status.EXPIRED])
    )
    assert forbidden.status_code == 302
    quotation.refresh_from_db()
    assert quotation.status == Quotation.Status.DRAFT


@pytest.mark.django_db
def test_quotation_views_require_authentication_and_active_organization(client):
    assert client.get(reverse("quotations:list")).status_code == 302

    user = User.objects.create_user(
        username="sem-locadora",
        email="sem-locadora@example.com",
        password="test-password-123",
    )
    client.force_login(user)
    response = client.get(reverse("quotations:list"))
    assert response.status_code == 302
    assert response.url == reverse("workspace:home")
