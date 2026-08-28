from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, ToolModel, ToolUnit
from apps.contracts.admin import (
    ContractAdmin,
    ContractItemAdmin,
    ContractItemInline,
)
from apps.contracts.models import Contract, ContractItem
from apps.contracts.services import (
    check_out_contract,
    create_contract,
    return_contract_item,
)
from apps.customers.models import Customer
from apps.organizations.models import Establishment, Membership, Organization
from apps.pricing.models import BillingUnit, PricingPolicy
from apps.quotations.services import QuotationLineInput, save_draft_quotation
from apps.reservations.models import Reservation
from apps.reservations.services import cancel_reservation, confirm_reservation

User = get_user_model()


def aware(year, month, day, hour=0):
    return timezone.make_aware(datetime(year, month, day, hour))


def create_domain(suffix="a", unit_count=2):
    organization = Organization.objects.create(
        name=f"Locadora {suffix.upper()}",
        slug=f"contratos-{suffix}",
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
    quotation = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=aware(2026, 10, 1, 8),
        ends_at=aware(2026, 10, 3, 8),
        lines=(
            QuotationLineInput(
                tool_model=tool_model,
                equipment_quantity=unit_count,
                billing_unit=BillingUnit.DAY,
            ),
        ),
    )
    quotation.status = quotation.Status.SENT
    quotation.sent_at = timezone.now()
    quotation.save(update_fields=["status", "sent_at", "updated_at"])
    reservation, _ = confirm_reservation(
        organization=organization,
        quotation=quotation,
        establishment=establishment,
    )
    return organization, establishment, customer, units, quotation, reservation


def create_user(organization, suffix="a"):
    user = User.objects.create_user(
        username=f"contrato-{suffix}",
        email=f"contrato-{suffix}@example.com",
        password="test-password-123",
    )
    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.Role.OWNER,
    )
    return user


@pytest.mark.django_db
def test_create_contract_preserves_snapshots_and_allocated_units():
    organization, establishment, customer, units, quotation, reservation = create_domain()

    contract, items = create_contract(
        organization=organization,
        reservation=reservation,
    )

    assert contract.status == Contract.Status.PREPARED
    assert contract.customer == customer
    assert contract.establishment == establishment
    assert contract.starts_at == reservation.starts_at
    assert contract.ends_at == reservation.ends_at
    assert contract.total_amount_snapshot == quotation.total_amount
    assert contract.customer_name_snapshot == customer.name
    assert contract.customer_document_snapshot == customer.document
    assert [item.tool_unit for item in items] == list(units)
    assert all(item.asset_code_snapshot == item.tool_unit.asset_code for item in items)


@pytest.mark.django_db
def test_create_contract_rejects_cancelled_cross_tenant_and_duplicate_reservations():
    organization, _, _, _, _, reservation = create_domain()
    other_organization, _, _, _, _, _ = create_domain("b")
    create_contract(organization=organization, reservation=reservation)

    with pytest.raises(ValidationError, match="já possui um contrato"):
        create_contract(organization=organization, reservation=reservation)
    with pytest.raises(ValidationError, match="organização atual"):
        create_contract(organization=other_organization, reservation=reservation)

    _, _, _, _, _, cancelled = create_domain("c")
    cancel_reservation(organization=cancelled.organization, reservation=cancelled)
    with pytest.raises(ValidationError, match="reserva confirmada"):
        create_contract(organization=cancelled.organization, reservation=cancelled)


@pytest.mark.django_db
def test_checkout_is_atomic_and_marks_every_unit_as_rented():
    organization, _, _, units, _, reservation = create_domain()
    user = create_user(organization)
    contract, items = create_contract(organization=organization, reservation=reservation)

    checked_out = check_out_contract(
        organization=organization,
        contract=contract,
        user=user,
    )

    assert checked_out.status == Contract.Status.ACTIVE
    assert checked_out.activated_at is not None
    for item in items:
        item.refresh_from_db()
        assert item.checked_out_at == checked_out.activated_at
        assert item.checked_out_by == user
    for unit in units:
        unit.refresh_from_db()
        assert unit.status == ToolUnit.Status.RENTED


@pytest.mark.django_db
def test_checkout_rolls_back_when_one_unit_is_not_operationally_available():
    organization, _, _, units, _, reservation = create_domain()
    user = create_user(organization)
    contract, items = create_contract(organization=organization, reservation=reservation)
    units[1].status = ToolUnit.Status.MAINTENANCE
    units[1].save(update_fields=["status", "updated_at"])

    with pytest.raises(ValidationError, match=units[1].asset_code):
        check_out_contract(organization=organization, contract=contract, user=user)

    contract.refresh_from_db()
    assert contract.status == Contract.Status.PREPARED
    assert all(
        item.checked_out_at is None
        for item in ContractItem.objects.filter(contract=contract)
    )
    units[0].refresh_from_db()
    assert units[0].status == ToolUnit.Status.AVAILABLE


@pytest.mark.django_db
def test_operator_must_have_active_membership():
    organization, _, _, _, _, reservation = create_domain()
    unrelated = User.objects.create_user(
        username="sem-vinculo",
        email="sem-vinculo@example.com",
        password="test-password-123",
    )
    contract, _ = create_contract(organization=organization, reservation=reservation)

    with pytest.raises(ValidationError, match="acesso ativo"):
        check_out_contract(
            organization=organization,
            contract=contract,
            user=unrelated,
        )


@pytest.mark.django_db
def test_inactive_organization_and_repeated_checkout_are_rejected():
    organization, _, _, _, _, reservation = create_domain()
    user = create_user(organization)
    contract, _ = create_contract(organization=organization, reservation=reservation)
    check_out_contract(organization=organization, contract=contract, user=user)

    with pytest.raises(ValidationError, match="contrato preparado"):
        check_out_contract(organization=organization, contract=contract, user=user)

    organization.active = False
    organization.save(update_fields=["active", "updated_at"])
    with pytest.raises(ValidationError, match="organização atual precisa estar ativa"):
        check_out_contract(organization=organization, contract=contract, user=user)


@pytest.mark.django_db
def test_partial_and_complete_returns_preserve_history_and_update_condition():
    organization, _, _, units, _, reservation = create_domain()
    user = create_user(organization)
    contract, items = create_contract(organization=organization, reservation=reservation)
    check_out_contract(organization=organization, contract=contract, user=user)

    first, active_contract = return_contract_item(
        organization=organization,
        contract=contract,
        contract_item=items[0],
        condition=ContractItem.ReturnCondition.MAINTENANCE,
        notes="Cabo danificado",
        user=user,
    )

    assert active_contract.status == Contract.Status.ACTIVE
    assert first.return_notes == "Cabo danificado"
    units[0].refresh_from_db()
    units[1].refresh_from_db()
    assert units[0].status == ToolUnit.Status.MAINTENANCE
    assert units[1].status == ToolUnit.Status.RENTED
    first.reservation_allocation.refresh_from_db()
    assert first.reservation_allocation.released_at == first.returned_at

    second, completed = return_contract_item(
        organization=organization,
        contract=contract,
        contract_item=items[1],
        condition=ContractItem.ReturnCondition.AVAILABLE,
        notes="",
        user=user,
    )

    assert completed.status == Contract.Status.COMPLETED
    assert completed.completed_at == second.returned_at
    units[1].refresh_from_db()
    assert units[1].status == ToolUnit.Status.AVAILABLE
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.CONFIRMED


@pytest.mark.django_db
def test_lost_return_condition_is_preserved_on_item_and_unit():
    organization, _, _, units, _, reservation = create_domain(unit_count=1)
    user = create_user(organization)
    contract, items = create_contract(organization=organization, reservation=reservation)
    check_out_contract(organization=organization, contract=contract, user=user)

    returned, _ = return_contract_item(
        organization=organization,
        contract=contract,
        contract_item=items[0],
        condition=ContractItem.ReturnCondition.LOST,
        notes="Não devolvida pelo cliente",
        user=user,
    )

    units[0].refresh_from_db()
    assert returned.return_condition == ContractItem.ReturnCondition.LOST
    assert units[0].status == ToolUnit.Status.LOST


@pytest.mark.django_db
def test_item_cannot_be_returned_twice_or_before_checkout():
    organization, _, _, _, _, reservation = create_domain(unit_count=1)
    user = create_user(organization)
    contract, items = create_contract(organization=organization, reservation=reservation)

    with pytest.raises(ValidationError, match="contrato em andamento"):
        return_contract_item(
            organization=organization,
            contract=contract,
            contract_item=items[0],
            condition=ContractItem.ReturnCondition.AVAILABLE,
            notes="",
            user=user,
        )

    check_out_contract(organization=organization, contract=contract, user=user)
    return_contract_item(
        organization=organization,
        contract=contract,
        contract_item=items[0],
        condition=ContractItem.ReturnCondition.AVAILABLE,
        notes="",
        user=user,
    )
    with pytest.raises(ValidationError, match="em andamento"):
        return_contract_item(
            organization=organization,
            contract=contract,
            contract_item=items[0],
            condition=ContractItem.ReturnCondition.AVAILABLE,
            notes="",
            user=user,
        )


@pytest.mark.django_db
def test_return_rejects_invalid_condition_and_item_from_another_contract():
    organization, _, _, _, _, reservation = create_domain()
    user = create_user(organization)
    contract, items = create_contract(organization=organization, reservation=reservation)
    check_out_contract(organization=organization, contract=contract, user=user)

    with pytest.raises(ValidationError, match="condição de devolução válida"):
        return_contract_item(
            organization=organization,
            contract=contract,
            contract_item=items[0],
            condition="UNKNOWN",
            notes="",
            user=user,
        )

    other_organization, _, _, _, _, other_reservation = create_domain("b")
    other_user = create_user(other_organization, "b")
    other_contract, _ = create_contract(
        organization=other_organization,
        reservation=other_reservation,
    )
    check_out_contract(
        organization=other_organization,
        contract=other_contract,
        user=other_user,
    )
    with pytest.raises(ValidationError, match="equipamento deste contrato"):
        return_contract_item(
            organization=other_organization,
            contract=other_contract,
            contract_item=items[0],
            condition=ContractItem.ReturnCondition.AVAILABLE,
            notes="",
            user=other_user,
        )

@pytest.mark.django_db
def test_reservation_with_contract_cannot_be_cancelled():
    organization, _, _, _, _, reservation = create_domain()
    create_contract(organization=organization, reservation=reservation)

    with pytest.raises(ValidationError, match="possui contrato"):
        cancel_reservation(organization=organization, reservation=reservation)


@pytest.mark.django_db
def test_contract_views_execute_lifecycle_and_filter_by_active_organization(client):
    organization, _, _, units, _, reservation = create_domain(unit_count=1)
    other_organization, _, _, _, _, _ = create_domain("b", unit_count=1)
    user = create_user(organization)
    client.force_login(user)

    response = client.post(reverse("contracts:create", args=[reservation.pk]))
    contract = Contract.objects.get(reservation=reservation)
    assert response.status_code == 302
    assert response.url == reverse("contracts:detail", args=[contract.pk])

    response = client.post(reverse("contracts:checkout", args=[contract.pk]))
    assert response.status_code == 302
    contract.refresh_from_db()
    assert contract.status == Contract.Status.ACTIVE

    item = contract.items.get()
    response = client.post(
        reverse("contracts:return-item", args=[contract.pk, item.pk]),
        {"condition": ContractItem.ReturnCondition.AVAILABLE, "notes": "Tudo certo"},
    )
    assert response.status_code == 302
    contract.refresh_from_db()
    assert contract.status == Contract.Status.COMPLETED
    units[0].refresh_from_db()
    assert units[0].status == ToolUnit.Status.AVAILABLE

    response = client.get(reverse("contracts:list"))
    assert list(response.context["contracts"]) == [contract]
    assert all(item.organization != other_organization for item in response.context["contracts"])


@pytest.mark.django_db
def test_cross_tenant_contract_and_item_urls_return_404(client):
    organization, _, _, _, _, reservation = create_domain()
    other_organization, _, _, _, _, _ = create_domain("b")
    other_user = create_user(other_organization, "b")
    contract, items = create_contract(organization=organization, reservation=reservation)
    client.force_login(other_user)

    assert client.get(reverse("contracts:detail", args=[contract.pk])).status_code == 404
    assert client.post(reverse("contracts:checkout", args=[contract.pk])).status_code == 404
    assert (
        client.post(
            reverse("contracts:return-item", args=[contract.pk, items[0].pk]),
            {"condition": ContractItem.ReturnCondition.AVAILABLE},
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_contract_admin_is_read_only(rf, admin_user):
    request = rf.get("/admin/")
    request.user = admin_user
    contract_admin = ContractAdmin(Contract, None)
    item_admin = ContractItemAdmin(ContractItem, None)
    inline = ContractItemInline(Contract, admin.site)

    assert contract_admin.has_add_permission(request) is False
    assert contract_admin.has_delete_permission(request) is False
    assert item_admin.has_add_permission(request) is False
    assert item_admin.has_delete_permission(request) is False
    assert inline.has_add_permission(request) is False


@pytest.mark.django_db
def test_contract_models_validate_cross_tenant_relationships_and_display_codes():
    organization, _, _, _, _, reservation = create_domain()
    other_organization, other_establishment, other_customer, _, _, _ = create_domain("b")
    contract, items = create_contract(organization=organization, reservation=reservation)

    contract.customer = other_customer
    contract.establishment = other_establishment
    with pytest.raises(ValidationError) as error:
        contract.full_clean(validate_unique=False, validate_constraints=False)
    assert "customer" in error.value.message_dict
    assert "establishment" in error.value.message_dict

    item = items[0]
    item.organization = other_organization
    with pytest.raises(ValidationError) as error:
        item.full_clean(validate_unique=False, validate_constraints=False)
    assert "contract" in error.value.message_dict
    assert "reservation_allocation" in error.value.message_dict
    assert "tool_unit" in error.value.message_dict
    assert contract.display_code in str(contract)
    assert item.asset_code_snapshot in str(item)


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="A concorrência real exige PostgreSQL.",
)
def test_concurrent_contract_creation_keeps_single_contract():
    organization, _, _, _, _, reservation = create_domain(unit_count=1)
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        barrier.wait()
        try:
            contract, _ = create_contract(
                organization=Organization.objects.get(pk=organization.pk),
                reservation=Reservation.objects.get(pk=reservation.pk),
            )
            return contract.pk
        except ValidationError:
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))

    assert sum(result is not None for result in results) == 1
    assert Contract.objects.filter(reservation=reservation).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="A concorrência real exige PostgreSQL.",
)
def test_concurrent_return_keeps_single_event():
    organization, _, _, _, _, reservation = create_domain(unit_count=1)
    user = create_user(organization)
    contract, items = create_contract(organization=organization, reservation=reservation)
    check_out_contract(organization=organization, contract=contract, user=user)
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        barrier.wait()
        try:
            returned, _ = return_contract_item(
                organization=Organization.objects.get(pk=organization.pk),
                contract=Contract.objects.get(pk=contract.pk),
                contract_item=ContractItem.objects.get(pk=items[0].pk),
                condition=ContractItem.ReturnCondition.AVAILABLE,
                notes="",
                user=User.objects.get(pk=user.pk),
            )
            return returned.pk
        except ValidationError:
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))

    assert sum(result is not None for result in results) == 1
    item = ContractItem.objects.get(pk=items[0].pk)
    assert item.returned_at is not None
