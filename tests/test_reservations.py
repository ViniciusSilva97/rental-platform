from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, ToolModel, ToolUnit
from apps.customers.models import Customer
from apps.organizations.models import Establishment, Membership, Organization
from apps.pricing.models import BillingUnit, PricingPolicy
from apps.quotations.models import Quotation
from apps.quotations.services import (
    QuotationLineInput,
    save_draft_quotation,
    transition_quotation,
)
from apps.reservations.admin import (
    ReservationAdmin,
    ReservationAllocationAdmin,
    ReservationAllocationInline,
)
from apps.reservations.models import Reservation, ReservationAllocation
from apps.reservations.services import (
    ReservationUnavailable,
    available_establishments_for_quotation,
    available_units,
    cancel_reservation,
    confirm_reservation,
)

User = get_user_model()


def aware(year, month, day, hour=0, minute=0):
    return timezone.make_aware(datetime(year, month, day, hour, minute))


def create_domain(suffix="a", unit_count=2):
    organization = Organization.objects.create(
        name=f"Locadora {suffix.upper()}",
        slug=f"locadora-{suffix}",
    )
    establishment = Establishment.objects.create(
        organization=organization,
        name=f"Matriz {suffix.upper()}",
        kind=Establishment.Kind.HEADQUARTERS,
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
    PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 1, 1),
        daily_rate=Decimal("60.00"),
    )
    units = tuple(
        ToolUnit.objects.create(
            organization=organization,
            establishment=establishment,
            tool_model=tool_model,
            asset_code=f"EQ-{suffix.upper()}-{index:03d}",
        )
        for index in range(1, unit_count + 1)
    )
    return organization, establishment, customer, tool_model, units


def create_sent_quotation(
    *,
    organization,
    customer,
    tool_model,
    starts_at=None,
    ends_at=None,
    quantity=1,
):
    quotation = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=starts_at or aware(2026, 9, 1, 8),
        ends_at=ends_at or aware(2026, 9, 3, 8),
        lines=(
            QuotationLineInput(
                tool_model=tool_model,
                equipment_quantity=quantity,
                billing_unit=BillingUnit.DAY,
            ),
        ),
    )
    return transition_quotation(
        organization=organization,
        quotation=quotation,
        target_status=Quotation.Status.SENT,
    )


def create_user(organization, suffix="a"):
    user = User.objects.create_user(
        username=f"usuario-reserva-{suffix}",
        email=f"reserva-{suffix}@example.com",
        password="test-password-123",
    )
    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.Role.OWNER,
    )
    return user


@pytest.mark.django_db
def test_availability_uses_half_open_interval_and_filters_operational_status():
    organization, establishment, customer, tool_model, units = create_domain(unit_count=2)
    first_quote = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        starts_at=aware(2026, 9, 1, 8),
        ends_at=aware(2026, 9, 1, 10),
    )
    confirm_reservation(
        organization=organization,
        quotation=first_quote,
        establishment=establishment,
    )
    units[1].status = ToolUnit.Status.MAINTENANCE
    units[1].save(update_fields=["status", "updated_at"])

    overlapping = available_units(
        organization=organization,
        establishment=establishment,
        tool_model=tool_model,
        starts_at=aware(2026, 9, 1, 9),
        ends_at=aware(2026, 9, 1, 11),
    )
    adjacent = available_units(
        organization=organization,
        establishment=establishment,
        tool_model=tool_model,
        starts_at=aware(2026, 9, 1, 10),
        ends_at=aware(2026, 9, 1, 12),
    )

    assert list(overlapping) == []
    assert list(adjacent) == [units[0]]


@pytest.mark.django_db
def test_confirm_reservation_allocates_specific_units_and_preserves_quotation():
    organization, establishment, customer, tool_model, units = create_domain(unit_count=3)
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        quantity=2,
    )
    original_total = quotation.total_amount

    reservation, allocations = confirm_reservation(
        organization=organization,
        quotation=quotation,
        establishment=establishment,
    )

    quotation.refresh_from_db()
    assert reservation.status == Reservation.Status.CONFIRMED
    assert reservation.starts_at == quotation.starts_at
    assert reservation.ends_at == quotation.ends_at
    assert [allocation.tool_unit for allocation in allocations] == list(units[:2])
    assert all(allocation.quotation_item.quotation == quotation for allocation in allocations)
    assert quotation.status == Quotation.Status.SENT
    assert quotation.total_amount == original_total
    assert all(unit.status == ToolUnit.Status.AVAILABLE for unit in units)


@pytest.mark.django_db
def test_confirmation_rolls_back_when_quantity_is_unavailable():
    organization, establishment, customer, tool_model, units = create_domain(unit_count=2)
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        quantity=2,
    )
    units[1].status = ToolUnit.Status.MAINTENANCE
    units[1].save(update_fields=["status", "updated_at"])

    with pytest.raises(ReservationUnavailable, match="Não há 2 equipamento"):
        confirm_reservation(
            organization=organization,
            quotation=quotation,
            establishment=establishment,
        )

    assert not Reservation.objects.exists()
    assert not ReservationAllocation.objects.exists()


@pytest.mark.django_db
def test_sending_requires_one_establishment_with_the_complete_availability():
    organization, establishment, customer, tool_model, units = create_domain(unit_count=2)
    branch = Establishment.objects.create(
        organization=organization,
        name="Filial",
        kind=Establishment.Kind.BRANCH,
    )
    units[1].establishment = branch
    units[1].save(update_fields=["establishment", "updated_at"])
    quotation = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=aware(2026, 9, 1, 8),
        ends_at=aware(2026, 9, 3, 8),
        lines=(QuotationLineInput(tool_model, 2, BillingUnit.DAY),),
    )

    assert not available_establishments_for_quotation(
        organization=organization,
        quotation=quotation,
    ).exists()
    with pytest.raises(ValidationError, match="Não é possível enviar este orçamento"):
        transition_quotation(
            organization=organization,
            quotation=quotation,
            target_status=Quotation.Status.SENT,
        )

    quotation.refresh_from_db()
    assert quotation.status == Quotation.Status.DRAFT
    assert quotation.sent_at is None


@pytest.mark.django_db
def test_sending_considers_active_reservations_and_allows_adjacent_periods():
    organization, establishment, customer, tool_model, _ = create_domain(unit_count=1)
    reserved = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        starts_at=aware(2026, 9, 1, 8),
        ends_at=aware(2026, 9, 1, 10),
    )
    confirm_reservation(
        organization=organization,
        quotation=reserved,
        establishment=establishment,
    )
    overlapping = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=aware(2026, 9, 1, 9),
        ends_at=aware(2026, 9, 1, 11),
        lines=(QuotationLineInput(tool_model, 1, BillingUnit.DAY),),
    )
    adjacent = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=aware(2026, 9, 1, 10),
        ends_at=aware(2026, 9, 1, 12),
        lines=(QuotationLineInput(tool_model, 1, BillingUnit.DAY),),
    )

    with pytest.raises(ValidationError, match="Não é possível enviar este orçamento"):
        transition_quotation(
            organization=organization,
            quotation=overlapping,
            target_status=Quotation.Status.SENT,
        )
    sent = transition_quotation(
        organization=organization,
        quotation=adjacent,
        target_status=Quotation.Status.SENT,
    )

    assert sent.status == Quotation.Status.SENT


@pytest.mark.django_db
def test_confirmation_form_lists_only_establishments_that_can_fulfill_quote(client):
    organization, establishment, customer, tool_model, _ = create_domain(unit_count=1)
    unavailable_branch = Establishment.objects.create(
        organization=organization,
        name="Filial sem estoque",
        kind=Establishment.Kind.BRANCH,
    )
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    client.force_login(create_user(organization))

    response = client.get(reverse("reservations:create", args=[quotation.pk]))

    assert response.status_code == 200
    choices = response.context["form"].fields["establishment"].queryset
    assert list(choices) == [establishment]
    assert unavailable_branch not in choices


@pytest.mark.django_db
def test_transition_view_keeps_unavailable_quotation_as_draft(client):
    organization, _, customer, tool_model, _ = create_domain(unit_count=1)
    quotation = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=aware(2026, 9, 1, 8),
        ends_at=aware(2026, 9, 3, 8),
        lines=(QuotationLineInput(tool_model, 2, BillingUnit.DAY),),
    )
    client.force_login(create_user(organization))

    response = client.post(
        reverse("quotations:transition", args=[quotation.pk, Quotation.Status.SENT]),
        follow=True,
    )

    quotation.refresh_from_db()
    assert response.status_code == 200
    assert "Não é possível enviar este orçamento" in response.content.decode()
    assert quotation.status == Quotation.Status.DRAFT
    assert quotation.sent_at is None


@pytest.mark.django_db
def test_only_sent_quotation_can_create_one_reservation():
    organization, establishment, customer, tool_model, _ = create_domain()
    draft = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=aware(2026, 9, 1, 8),
        ends_at=aware(2026, 9, 2, 8),
        lines=(QuotationLineInput(tool_model, 1, BillingUnit.DAY),),
    )

    with pytest.raises(ValidationError, match="Somente um orçamento enviado"):
        confirm_reservation(
            organization=organization,
            quotation=draft,
            establishment=establishment,
        )

    sent = transition_quotation(
        organization=organization,
        quotation=draft,
        target_status=Quotation.Status.SENT,
    )
    confirm_reservation(
        organization=organization,
        quotation=sent,
        establishment=establishment,
    )
    with pytest.raises(ValidationError, match="já possui uma reserva"):
        confirm_reservation(
            organization=organization,
            quotation=sent,
            establishment=establishment,
        )


@pytest.mark.django_db
def test_cancel_releases_period_but_preserves_history():
    organization, establishment, customer, tool_model, units = create_domain(unit_count=1)
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    reservation, allocations = confirm_reservation(
        organization=organization,
        quotation=quotation,
        establishment=establishment,
    )

    cancelled = cancel_reservation(
        organization=organization,
        reservation=reservation,
    )
    allocations[0].refresh_from_db()
    available = available_units(
        organization=organization,
        establishment=establishment,
        tool_model=tool_model,
        starts_at=quotation.starts_at,
        ends_at=quotation.ends_at,
    )

    assert cancelled.status == Reservation.Status.CANCELLED
    assert cancelled.cancelled_at is not None
    assert allocations[0].released_at == cancelled.cancelled_at
    assert list(available) == [units[0]]
    assert Reservation.objects.filter(pk=reservation.pk).exists()
    assert ReservationAllocation.objects.filter(pk=allocations[0].pk).exists()
    with pytest.raises(ValidationError, match="Somente uma reserva confirmada"):
        cancel_reservation(organization=organization, reservation=cancelled)


@pytest.mark.django_db
def test_active_reservation_blocks_terminal_quotation_transition_until_cancelled():
    organization, establishment, customer, tool_model, _ = create_domain()
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    reservation, _ = confirm_reservation(
        organization=organization,
        quotation=quotation,
        establishment=establishment,
    )

    with pytest.raises(ValidationError, match="Cancele primeiro a reserva"):
        transition_quotation(
            organization=organization,
            quotation=quotation,
            target_status=Quotation.Status.CANCELLED,
        )

    cancel_reservation(organization=organization, reservation=reservation)
    cancelled_quote = transition_quotation(
        organization=organization,
        quotation=quotation,
        target_status=Quotation.Status.CANCELLED,
    )
    assert cancelled_quote.status == Quotation.Status.CANCELLED


@pytest.mark.django_db
def test_service_and_queries_reject_cross_tenant_relationships():
    organization_a, establishment_a, customer_a, tool_a, _ = create_domain("a")
    organization_b, establishment_b, _, tool_b, _ = create_domain("b")
    quotation = create_sent_quotation(
        organization=organization_a,
        customer=customer_a,
        tool_model=tool_a,
    )

    with pytest.raises(ValidationError, match="estabelecimento ativo"):
        confirm_reservation(
            organization=organization_a,
            quotation=quotation,
            establishment=establishment_b,
        )
    with pytest.raises(ValidationError, match="modelo deve pertencer"):
        available_units(
            organization=organization_a,
            establishment=establishment_a,
            tool_model=tool_b,
            starts_at=quotation.starts_at,
            ends_at=quotation.ends_at,
        )
    assert not Reservation.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("inactive_target", ["organization", "establishment", "tool_model"])
def test_availability_rejects_inactive_domain(inactive_target):
    organization, establishment, _, tool_model, _ = create_domain()
    target = {
        "organization": organization,
        "establishment": establishment,
        "tool_model": tool_model,
    }[inactive_target]
    target.active = False
    target.save(update_fields=["active", "updated_at"])

    with pytest.raises(ValidationError, match="precisa estar ativ"):
        available_units(
            organization=organization,
            establishment=establishment,
            tool_model=tool_model,
            starts_at=aware(2026, 9, 1, 8),
            ends_at=aware(2026, 9, 2, 8),
        )


@pytest.mark.django_db
def test_adjacent_reservations_can_share_the_same_unit():
    organization, establishment, customer, tool_model, units = create_domain(unit_count=1)
    first = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        starts_at=aware(2026, 9, 1, 8),
        ends_at=aware(2026, 9, 1, 10),
    )
    second = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        starts_at=aware(2026, 9, 1, 10),
        ends_at=aware(2026, 9, 1, 12),
    )

    _, first_allocations = confirm_reservation(
        organization=organization,
        quotation=first,
        establishment=establishment,
    )
    _, second_allocations = confirm_reservation(
        organization=organization,
        quotation=second,
        establishment=establishment,
    )

    assert first_allocations[0].tool_unit == units[0]
    assert second_allocations[0].tool_unit == units[0]


@pytest.mark.django_db
def test_model_validation_rejects_mismatched_allocation_period_and_model():
    organization, establishment, customer, tool_model, units = create_domain(unit_count=1)
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    reservation, _ = confirm_reservation(
        organization=organization,
        quotation=quotation,
        establishment=establishment,
    )
    other_category = Category.objects.create(organization=organization, name="Serras")
    other_model = ToolModel.objects.create(
        organization=organization,
        category=other_category,
        name="Serra",
    )
    other_unit = ToolUnit.objects.create(
        organization=organization,
        establishment=establishment,
        tool_model=other_model,
        asset_code="EQ-OTHER-001",
    )
    invalid = ReservationAllocation(
        organization=organization,
        reservation=reservation,
        quotation_item=quotation.items.get(),
        tool_unit=other_unit,
        starts_at=reservation.starts_at,
        ends_at=reservation.ends_at + timezone.timedelta(hours=1),
    )

    with pytest.raises(ValidationError) as error:
        invalid.full_clean(validate_constraints=False)

    assert "tool_unit" in error.value.message_dict
    assert "reservation" in error.value.message_dict
    assert units[0].reservation_allocations.count() == 1


@pytest.mark.django_db
def test_database_constraints_reject_invalid_status_and_period():
    organization, establishment, customer, tool_model, _ = create_domain()
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    reservation, _ = confirm_reservation(
        organization=organization,
        quotation=quotation,
        establishment=establishment,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Reservation.objects.filter(pk=reservation.pk).update(status="INVALID")
    with pytest.raises(IntegrityError), transaction.atomic():
        Reservation.objects.filter(pk=reservation.pk).update(ends_at=reservation.starts_at)


def test_reservation_admin_is_read_only():
    from django.contrib.admin.sites import AdminSite

    site = AdminSite()
    reservation_admin = ReservationAdmin(Reservation, site)
    allocation_admin = ReservationAllocationAdmin(ReservationAllocation, site)
    inline = ReservationAllocationInline(Reservation, site)

    assert not reservation_admin.has_add_permission(None)
    assert not reservation_admin.has_delete_permission(None)
    assert not allocation_admin.has_add_permission(None)
    assert not allocation_admin.has_delete_permission(None)
    assert not inline.has_add_permission(None)
    assert inline.can_delete is False


@pytest.mark.django_db
def test_operational_views_create_list_cancel_and_enforce_tenant(client):
    organization_a, establishment_a, customer_a, tool_a, _ = create_domain("a")
    organization_b, _, customer_b, tool_b, _ = create_domain("b")
    quotation_a = create_sent_quotation(
        organization=organization_a,
        customer=customer_a,
        tool_model=tool_a,
    )
    quotation_b = create_sent_quotation(
        organization=organization_b,
        customer=customer_b,
        tool_model=tool_b,
    )
    user = create_user(organization_a)
    client.force_login(user)

    availability = client.get(reverse("reservations:availability"))
    form = availability.context["form"]
    assert list(form.fields["establishment"].queryset) == [establishment_a]
    assert list(form.fields["tool_model"].queryset) == [tool_a]
    assert client.get(reverse("reservations:create", args=[quotation_b.pk])).status_code == 404

    created = client.post(
        reverse("reservations:create", args=[quotation_a.pk]),
        data={"establishment": str(establishment_a.pk)},
    )
    reservation = Reservation.objects.get()
    assert created.status_code == 302
    assert created.url == reverse("reservations:detail", args=[reservation.pk])
    assert client.get(created.url).status_code == 200
    assert quotation_a.display_code in client.get(created.url).content.decode()
    assert quotation_b.display_code not in client.get(reverse("reservations:list")).content.decode()

    cancelled = client.post(reverse("reservations:cancel", args=[reservation.pk]))
    reservation.refresh_from_db()
    assert cancelled.status_code == 302
    assert reservation.status == Reservation.Status.CANCELLED


@pytest.mark.django_db
def test_availability_view_validates_period_and_shows_units(client):
    organization, establishment, _, tool_model, units = create_domain(unit_count=1)
    user = create_user(organization)
    client.force_login(user)
    url = reverse("reservations:availability")

    invalid = client.get(
        url,
        data={
            "establishment": str(establishment.pk),
            "tool_model": str(tool_model.pk),
            "starts_at": "2026-09-02T08:00",
            "ends_at": "2026-09-01T08:00",
        },
    )
    valid = client.get(
        url,
        data={
            "establishment": str(establishment.pk),
            "tool_model": str(tool_model.pk),
            "starts_at": "2026-09-01T08:00",
            "ends_at": "2026-09-02T08:00",
        },
    )

    assert "O fim deve ser posterior" in invalid.content.decode()
    assert units[0].asset_code in valid.content.decode()


@pytest.mark.django_db
def test_quotation_detail_links_to_confirmation_and_then_to_reservation(client):
    organization, establishment, customer, tool_model, _ = create_domain()
    quotation = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    user = create_user(organization)
    client.force_login(user)

    before = client.get(reverse("quotations:detail", args=[quotation.pk]))
    assert reverse("reservations:create", args=[quotation.pk]) in before.content.decode()

    reservation, _ = confirm_reservation(
        organization=organization,
        quotation=quotation,
        establishment=establishment,
    )
    after = client.get(reverse("quotations:detail", args=[quotation.pk]))
    assert reverse("reservations:detail", args=[reservation.pk]) in after.content.decode()


@pytest.mark.django_db(transaction=True)
def test_postgresql_exclusion_rejects_direct_overlapping_allocation():
    if connection.vendor != "postgresql":
        pytest.skip("A exclusão temporal pertence ao PostgreSQL.")
    organization, establishment, customer, tool_model, units = create_domain(unit_count=1)
    first_quote = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
    )
    second_quote = create_sent_quotation(
        organization=organization,
        customer=customer,
        tool_model=tool_model,
        starts_at=aware(2026, 9, 2, 8),
        ends_at=aware(2026, 9, 4, 8),
    )
    confirm_reservation(
        organization=organization,
        quotation=first_quote,
        establishment=establishment,
    )
    second_reservation = Reservation.objects.create(
        organization=organization,
        quotation=second_quote,
        establishment=establishment,
        starts_at=second_quote.starts_at,
        ends_at=second_quote.ends_at,
        confirmed_at=timezone.now(),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ReservationAllocation.objects.create(
            organization=organization,
            reservation=second_reservation,
            quotation_item=second_quote.items.get(),
            tool_unit=units[0],
            starts_at=second_quote.starts_at,
            ends_at=second_quote.ends_at,
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_confirmations_never_allocate_the_same_unit_twice():
    if connection.vendor != "postgresql":
        pytest.skip("Concorrência com bloqueio de linha exige PostgreSQL.")
    organization, establishment, customer, tool_model, _ = create_domain(unit_count=1)
    quotations = tuple(
        create_sent_quotation(
            organization=organization,
            customer=customer,
            tool_model=tool_model,
        )
        for _ in range(2)
    )
    barrier = Barrier(2)

    def reserve(quotation_id):
        close_old_connections()
        barrier.wait()
        try:
            result, _ = confirm_reservation(
                organization=Organization.objects.get(pk=organization.pk),
                quotation=Quotation.objects.get(pk=quotation_id),
                establishment=Establishment.objects.get(pk=establishment.pk),
            )
        except (ReservationUnavailable, ValidationError):
            outcome = "unavailable"
        else:
            outcome = str(result.pk)
        finally:
            close_old_connections()
        return outcome

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(reserve, [quote.pk for quote in quotations]))

    assert outcomes.count("unavailable") == 1
    assert Reservation.objects.count() == 1
    assert ReservationAllocation.objects.count() == 1
