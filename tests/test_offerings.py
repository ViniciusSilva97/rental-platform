from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, ToolModel, ToolUnit
from apps.contracts.models import ContractOffering
from apps.contracts.services import check_out_contract, create_contract
from apps.customers.models import Customer
from apps.offerings.models import (
    Offering,
    OfferingCompatibility,
    OfferingPricingPolicy,
    OfferingStock,
)
from apps.offerings.services import (
    OfferingSelectionInput,
    save_quotation_item_offerings,
)
from apps.organizations.models import Establishment, Membership, Organization
from apps.pricing.models import BillingUnit, PricingPolicy
from apps.quotations.models import Quotation, QuotationItemOffering
from apps.quotations.services import (
    QuotationLineInput,
    save_draft_quotation,
    transition_quotation,
)
from apps.reservations.models import ReservationOffering
from apps.reservations.services import cancel_reservation, confirm_reservation

User = get_user_model()


def aware(day, hour=8):
    return timezone.make_aware(datetime(2026, 10, day, hour))


def create_domain(suffix="a"):
    organization = Organization.objects.create(
        name=f"Locadora {suffix}", slug=f"ofertas-{suffix}"
    )
    establishment = Establishment.objects.create(
        organization=organization,
        name=f"Matriz {suffix}",
        kind=Establishment.Kind.HEADQUARTERS,
    )
    customer = Customer.objects.create(
        organization=organization,
        kind=Customer.Kind.INDIVIDUAL,
        name=f"Cliente {suffix}",
        document="529.982.247-25",
    )
    category = Category.objects.create(
        organization=organization, name=f"Equipamentos {suffix}"
    )
    base_model = ToolModel.objects.create(
        organization=organization, category=category, name=f"Computador {suffix}"
    )
    accessory_model = ToolModel.objects.create(
        organization=organization, category=category, name=f"Placa de vídeo {suffix}"
    )
    PricingPolicy.objects.create(
        organization=organization,
        tool_model=base_model,
        effective_from=date(2026, 1, 1),
        daily_rate=Decimal("100.00"),
    )
    base_unit = ToolUnit.objects.create(
        organization=organization,
        establishment=establishment,
        tool_model=base_model,
        asset_code=f"EQ-{suffix}-BASE",
    )
    accessory_unit = ToolUnit.objects.create(
        organization=organization,
        establishment=establishment,
        tool_model=accessory_model,
        asset_code=f"EQ-{suffix}-GPU",
    )
    quotation = save_draft_quotation(
        organization=organization,
        customer=customer,
        starts_at=aware(1),
        ends_at=aware(3),
        rental_notes="Cliente precisa de cabo HDMI.",
        lines=(
            QuotationLineInput(
                tool_model=base_model,
                equipment_quantity=1,
                billing_unit=BillingUnit.DAY,
            ),
        ),
    )
    return {
        "organization": organization,
        "establishment": establishment,
        "customer": customer,
        "category": category,
        "base_model": base_model,
        "accessory_model": accessory_model,
        "base_unit": base_unit,
        "accessory_unit": accessory_unit,
        "quotation": quotation,
        "item": quotation.items.get(),
    }


def create_offering(
    domain,
    *,
    name,
    kind,
    amount,
    inventory_model=None,
    maximum=2,
    billing_method=OfferingPricingPolicy.BillingMethod.FLAT,
):
    offering = Offering.objects.create(
        organization=domain["organization"],
        name=name,
        kind=kind,
        inventory_tool_model=inventory_model,
    )
    OfferingCompatibility.objects.create(
        organization=domain["organization"],
        offering=offering,
        tool_model=domain["base_model"],
        max_quantity_per_equipment=maximum,
    )
    policy_values = {"flat_amount": amount}
    if billing_method == OfferingPricingPolicy.BillingMethod.PER_PERIOD:
        policy_values = {"flat_amount": None, "daily_rate": amount}
    OfferingPricingPolicy.objects.create(
        organization=domain["organization"],
        offering=offering,
        effective_from=date(2026, 1, 1),
        billing_method=billing_method,
        **policy_values,
    )
    return offering


def create_user(organization):
    user = User.objects.create_user(
        username=f"ofertas-{organization.slug}",
        email=f"{organization.slug}@example.com",
        password="test-password-123",
    )
    Membership.objects.create(
        organization=organization, user=user, role=Membership.Role.OWNER
    )
    return user


@pytest.mark.django_db
def test_additions_discounts_snapshots_and_free_notes_are_separate():
    domain = create_domain()
    service = create_offering(
        domain,
        name="Instalação",
        kind=Offering.Kind.SERVICE,
        amount=Decimal("30.00"),
    )
    removal = create_offering(
        domain,
        name="Sem placa sem fio",
        kind=Offering.Kind.REMOVAL,
        amount=Decimal("20.00"),
    )

    snapshots = save_quotation_item_offerings(
        organization=domain["organization"],
        quotation_item=domain["item"],
        selections=(
            OfferingSelectionInput(offering=service, quantity=2),
            OfferingSelectionInput(offering=removal, quantity=1),
        ),
    )

    domain["quotation"].refresh_from_db()
    assert domain["quotation"].total_amount == Decimal("240.00")
    assert domain["quotation"].rental_notes == "Cliente precisa de cabo HDMI."
    assert snapshots[0].price_effect == QuotationItemOffering.PriceEffect.ADDITION
    assert snapshots[1].price_effect == QuotationItemOffering.PriceEffect.DISCOUNT
    assert snapshots[0].offering_name == "Instalação"


@pytest.mark.django_db
def test_selection_validates_compatibility_duplicates_limits_and_negative_total():
    domain = create_domain()
    discount = create_offering(
        domain,
        name="Desconto seguro",
        kind=Offering.Kind.REMOVAL,
        amount=Decimal("250.00"),
        maximum=1,
    )
    incompatible = Offering.objects.create(
        organization=domain["organization"],
        name="Incompatível",
        kind=Offering.Kind.SERVICE,
    )

    with pytest.raises(ValidationError, match="compatível"):
        save_quotation_item_offerings(
            organization=domain["organization"],
            quotation_item=domain["item"],
            selections=(OfferingSelectionInput(incompatible, 1),),
        )
    with pytest.raises(ValidationError, match="máximo"):
        save_quotation_item_offerings(
            organization=domain["organization"],
            quotation_item=domain["item"],
            selections=(OfferingSelectionInput(discount, 2),),
        )
    with pytest.raises(ValidationError, match="negativo"):
        save_quotation_item_offerings(
            organization=domain["organization"],
            quotation_item=domain["item"],
            selections=(OfferingSelectionInput(discount, 1),),
        )
    assert not QuotationItemOffering.objects.exists()


@pytest.mark.django_db
def test_sent_quotation_blocks_changes_and_empty_selection_restores_base_total():
    domain = create_domain()
    service = create_offering(
        domain,
        name="Configuração inicial",
        kind=Offering.Kind.SERVICE,
        amount=Decimal("25.00"),
    )
    save_quotation_item_offerings(
        organization=domain["organization"],
        quotation_item=domain["item"],
        selections=(OfferingSelectionInput(service, 1),),
    )
    save_quotation_item_offerings(
        organization=domain["organization"],
        quotation_item=domain["item"],
        selections=(),
    )
    domain["quotation"].refresh_from_db()
    assert domain["quotation"].total_amount == Decimal("200.00")
    transition_quotation(
        organization=domain["organization"],
        quotation=domain["quotation"],
        target_status=Quotation.Status.SENT,
    )
    with pytest.raises(ValidationError, match="rascunhos"):
        save_quotation_item_offerings(
            organization=domain["organization"],
            quotation_item=domain["item"],
            selections=(OfferingSelectionInput(service, 1),),
        )


@pytest.mark.django_db
def test_editing_draft_preserves_and_recalculates_compatible_options():
    domain = create_domain()
    option = create_offering(
        domain,
        name="Suporte",
        kind=Offering.Kind.SERVICE,
        amount=Decimal("10.00"),
        billing_method=OfferingPricingPolicy.BillingMethod.PER_PERIOD,
    )
    save_quotation_item_offerings(
        organization=domain["organization"],
        quotation_item=domain["item"],
        selections=(OfferingSelectionInput(option, 1),),
    )

    updated = save_draft_quotation(
        organization=domain["organization"],
        customer=domain["customer"],
        starts_at=aware(1),
        ends_at=aware(4),
        rental_notes="Nova duração",
        quotation=domain["quotation"],
        lines=(QuotationLineInput(domain["base_model"], 1, BillingUnit.DAY),),
    )

    selection = updated.offerings.get()
    assert selection.billed_quantity == Decimal("3.000000")
    assert selection.line_total == Decimal("30.00")
    assert updated.total_amount == Decimal("330.00")
    assert updated.rental_notes == "Nova duração"


@pytest.mark.django_db
def test_reservation_contract_and_checkout_propagate_physical_and_consumable_options():
    domain = create_domain()
    accessory = create_offering(
        domain,
        name="Placa dedicada",
        kind=Offering.Kind.RETURNABLE_ACCESSORY,
        amount=Decimal("40.00"),
        inventory_model=domain["accessory_model"],
    )
    consumable = create_offering(
        domain,
        name="Kit de limpeza",
        kind=Offering.Kind.CONSUMABLE,
        amount=Decimal("15.00"),
    )
    stock = OfferingStock.objects.create(
        organization=domain["organization"],
        offering=consumable,
        establishment=domain["establishment"],
        on_hand_quantity=5,
    )
    save_quotation_item_offerings(
        organization=domain["organization"],
        quotation_item=domain["item"],
        selections=(
            OfferingSelectionInput(accessory, 1),
            OfferingSelectionInput(consumable, 2),
        ),
    )
    transition_quotation(
        organization=domain["organization"],
        quotation=domain["quotation"],
        target_status=Quotation.Status.SENT,
    )
    reservation, allocations = confirm_reservation(
        organization=domain["organization"],
        quotation=domain["quotation"],
        establishment=domain["establishment"],
    )

    assert len(allocations) == 2
    assert sum(a.quotation_item_offering_id is not None for a in allocations) == 1
    stock.refresh_from_db()
    assert stock.on_hand_quantity == 5
    assert stock.reserved_quantity == 2
    assert ReservationOffering.objects.filter(reservation=reservation).count() == 2

    contract, items = create_contract(
        organization=domain["organization"], reservation=reservation
    )
    assert ContractOffering.objects.filter(contract=contract).count() == 2
    assert sum(item.contract_offering_id is not None for item in items) == 1

    check_out_contract(
        organization=domain["organization"],
        contract=contract,
        user=create_user(domain["organization"]),
    )
    stock.refresh_from_db()
    assert stock.on_hand_quantity == 3
    assert stock.reserved_quantity == 0
    assert reservation.offerings.get(kind=Offering.Kind.CONSUMABLE).consumed_at
    for item in items:
        item.tool_unit.refresh_from_db()
        assert item.tool_unit.status == ToolUnit.Status.RENTED


@pytest.mark.django_db
def test_cancelling_reservation_releases_consumable_without_consuming_stock():
    domain = create_domain()
    consumable = create_offering(
        domain,
        name="Disco de corte",
        kind=Offering.Kind.CONSUMABLE,
        amount=Decimal("12.00"),
    )
    stock = OfferingStock.objects.create(
        organization=domain["organization"],
        offering=consumable,
        establishment=domain["establishment"],
        on_hand_quantity=3,
    )
    save_quotation_item_offerings(
        organization=domain["organization"],
        quotation_item=domain["item"],
        selections=(OfferingSelectionInput(consumable, 2),),
    )
    transition_quotation(
        organization=domain["organization"],
        quotation=domain["quotation"],
        target_status=Quotation.Status.SENT,
    )
    reservation, _ = confirm_reservation(
        organization=domain["organization"],
        quotation=domain["quotation"],
        establishment=domain["establishment"],
    )

    cancel_reservation(organization=domain["organization"], reservation=reservation)

    stock.refresh_from_db()
    reserved = reservation.offerings.get()
    assert stock.on_hand_quantity == 3
    assert stock.reserved_quantity == 0
    assert reserved.released_at is not None
    assert reserved.consumed_at is None


@pytest.mark.django_db
def test_operational_views_are_tenant_scoped(client):
    domain = create_domain()
    other = create_domain("b")
    option = create_offering(
        domain,
        name="Transformador",
        kind=Offering.Kind.RETURNABLE_ACCESSORY,
        amount=Decimal("10.00"),
        inventory_model=domain["accessory_model"],
    )
    create_offering(
        other,
        name="Segredo da outra locadora",
        kind=Offering.Kind.SERVICE,
        amount=Decimal("99.00"),
    )
    user = create_user(domain["organization"])
    client.force_login(user)

    response = client.get(reverse("offerings:list"))
    assert response.status_code == 200
    assert option.name in response.content.decode()
    assert "Segredo da outra locadora" not in response.content.decode()

    response = client.get(
        reverse(
            "offerings:quotation-item",
            args=[domain["quotation"].pk, domain["item"].pk],
        )
    )
    assert response.status_code == 200
    assert option.name in response.content.decode()
    assert "Segredo da outra locadora" not in response.content.decode()


@pytest.mark.django_db
def test_operational_create_view_persists_catalog_price_and_compatibility(client):
    domain = create_domain()
    client.force_login(create_user(domain["organization"]))
    response = client.post(
        reverse("offerings:create"),
        {
            "name": "Entrega técnica",
            "kind": Offering.Kind.SERVICE,
            "description": "Entrega e orientação",
            "requires_preparation": "on",
            "active": "on",
            "compatible_models": [str(domain["base_model"].pk)],
            "max_quantity_per_equipment": "1",
            "billing_method": OfferingPricingPolicy.BillingMethod.FLAT,
            "effective_from": "2026-01-01",
            "flat_amount": "35.00",
            "hourly_rate": "",
            "daily_rate": "",
            "monthly_rate": "",
            "stock_establishment": "",
            "on_hand_quantity": "",
        },
    )

    assert response.status_code == 302
    offering = Offering.objects.get(name="Entrega técnica")
    assert offering.organization == domain["organization"]
    assert offering.compatibilities.get().tool_model == domain["base_model"]
    assert offering.pricing_policies.get().flat_amount == Decimal("35.00")

@pytest.mark.django_db
def test_offering_model_rejects_invalid_inventory_and_cross_tenant_stock():
    domain = create_domain()
    other = create_domain("b")
    with pytest.raises(ValidationError, match="modelo físico"):
        Offering.objects.create(
            organization=domain["organization"],
            name="Sem estoque físico",
            kind=Offering.Kind.RETURNABLE_ACCESSORY,
        )
    consumable = create_offering(
        domain,
        name="Óleo",
        kind=Offering.Kind.CONSUMABLE,
        amount=Decimal("5.00"),
    )
    with pytest.raises(ValidationError, match="mesma organização"):
        OfferingStock.objects.create(
            organization=domain["organization"],
            offering=consumable,
            establishment=other["establishment"],
            on_hand_quantity=1,
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_consumable_reservations_never_exceed_stock():
    if connection.vendor != "postgresql":
        pytest.skip("Bloqueio concorrente exige PostgreSQL.")

    domain = create_domain()
    ToolUnit.objects.create(
        organization=domain["organization"],
        establishment=domain["establishment"],
        tool_model=domain["base_model"],
        asset_code="EQ-CONCURRENT-2",
    )
    consumable = create_offering(
        domain,
        name="Único consumível",
        kind=Offering.Kind.CONSUMABLE,
        amount=Decimal("5.00"),
    )
    OfferingStock.objects.create(
        organization=domain["organization"],
        offering=consumable,
        establishment=domain["establishment"],
        on_hand_quantity=1,
    )
    quotations = [domain["quotation"]]
    quotations.append(
        save_draft_quotation(
            organization=domain["organization"],
            customer=domain["customer"],
            starts_at=aware(1),
            ends_at=aware(3),
            lines=(QuotationLineInput(domain["base_model"], 1, BillingUnit.DAY),),
        )
    )
    for quotation in quotations:
        save_quotation_item_offerings(
            organization=domain["organization"],
            quotation_item=quotation.items.get(),
            selections=(OfferingSelectionInput(consumable, 1),),
        )
        transition_quotation(
            organization=domain["organization"],
            quotation=quotation,
            target_status=Quotation.Status.SENT,
        )

    barrier = Barrier(2)

    def reserve(quotation_id):
        close_old_connections()
        try:
            organization = Organization.objects.get(pk=domain["organization"].pk)
            establishment = Establishment.objects.get(pk=domain["establishment"].pk)
            quotation = Quotation.objects.get(pk=quotation_id)
            barrier.wait()
            confirm_reservation(
                organization=organization,
                quotation=quotation,
                establishment=establishment,
            )
            return "confirmed"
        except ValidationError:
            return "unavailable"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, [quote.pk for quote in quotations]))

    stock = OfferingStock.objects.get(offering=consumable)
    assert sorted(results) == ["confirmed", "unavailable"]
    assert stock.reserved_quantity == 1
    assert stock.on_hand_quantity == 1
