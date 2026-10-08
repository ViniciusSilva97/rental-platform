import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from threading import Barrier

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, ToolModel, ToolUnit
from apps.contracts.models import Contract
from apps.contracts.services import check_out_contract, create_contract
from apps.customers.models import Customer
from apps.inspections.admin import (
    InspectionEvidenceAdmin,
    OutboundInspectionAdmin,
    OutboundInspectionItemAdmin,
    OutboundInspectionItemInline,
)
from apps.inspections.models import (
    InspectionEvidence,
    OutboundInspection,
    OutboundInspectionItem,
)
from apps.inspections.services import (
    OutboundInspectionItemInput,
    add_inspection_evidence,
    create_outbound_inspection,
    save_outbound_inspection,
)
from apps.organizations.models import Establishment, Membership, Organization
from apps.pricing.models import BillingUnit, PricingPolicy
from apps.quotations.services import QuotationLineInput, save_draft_quotation
from apps.reservations.services import confirm_reservation

User = get_user_model()


def aware(day, hour=8):
    return timezone.make_aware(datetime(2026, 10, day, hour))


def create_domain(suffix="a", unit_count=2):
    organization = Organization.objects.create(
        name=f"Locadora inspeção {suffix}",
        slug=f"inspecao-{suffix}",
    )
    establishment = Establishment.objects.create(
        organization=organization,
        name=f"Matriz {suffix}",
        kind=Establishment.Kind.HEADQUARTERS,
    )
    user = User.objects.create_user(
        username=f"inspetor-{suffix}",
        email=f"inspetor-{suffix}@example.com",
        password="test-password-123",
    )
    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.Role.OWNER,
    )
    customer = Customer.objects.create(
        organization=organization,
        kind=Customer.Kind.INDIVIDUAL,
        name=f"Cliente {suffix}",
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
        daily_rate=Decimal("50.00"),
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
        starts_at=aware(20),
        ends_at=aware(22),
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
    contract, contract_items = create_contract(
        organization=organization,
        reservation=reservation,
    )
    return organization, user, contract, contract_items, units


def approved_inputs(items):
    return tuple(
        OutboundInspectionItemInput(
            inspection_item=item,
            condition=OutboundInspectionItem.Condition.GOOD,
            functional_result=OutboundInspectionItem.FunctionalResult.APPROVED,
            cleanliness_confirmed=True,
            safety_confirmed=True,
            components_snapshot="Maleta e chave",
            notes="Sem avarias",
        )
        for item in items
    )


def complete_inspection(*, organization, user, contract):
    inspection, items = create_outbound_inspection(
        organization=organization,
        contract=contract,
        user=user,
    )
    return save_outbound_inspection(
        organization=organization,
        inspection=inspection,
        user=user,
        general_notes="Equipamentos testados na presença do cliente.",
        customer_acknowledged=True,
        customer_representative_name="Maria Cliente",
        item_inputs=approved_inputs(items),
        complete=True,
    )


@pytest.mark.django_db
def test_creation_snapshots_every_physical_item_and_rejects_duplicates_and_other_tenant():
    organization, user, contract, contract_items, _ = create_domain()
    inspection, items = create_outbound_inspection(
        organization=organization,
        contract=contract,
        user=user,
    )

    assert inspection.status == OutboundInspection.Status.DRAFT
    assert [item.contract_item for item in items] == list(contract_items)
    assert [item.asset_code_snapshot for item in items] == [
        item.asset_code_snapshot for item in contract_items
    ]
    with pytest.raises(ValidationError, match="já possui"):
        create_outbound_inspection(
            organization=organization,
            contract=contract,
            user=user,
        )

    other_organization, other_user, _, _, _ = create_domain("b", unit_count=1)
    with pytest.raises(ValidationError, match="organização atual"):
        create_outbound_inspection(
            organization=other_organization,
            contract=contract,
            user=other_user,
        )


@pytest.mark.django_db
def test_checkout_requires_completed_inspection_and_completion_requires_approval():
    organization, user, contract, _, units = create_domain(unit_count=1)
    with pytest.raises(ValidationError, match="inspeção inicial"):
        check_out_contract(organization=organization, contract=contract, user=user)

    inspection, items = create_outbound_inspection(
        organization=organization,
        contract=contract,
        user=user,
    )
    with pytest.raises(ValidationError, match="inspeção inicial"):
        check_out_contract(organization=organization, contract=contract, user=user)
    with pytest.raises(ValidationError, match="Revise"):
        save_outbound_inspection(
            organization=organization,
            inspection=inspection,
            user=user,
            general_notes="",
            customer_acknowledged=True,
            customer_representative_name="Maria Cliente",
            item_inputs=(
                OutboundInspectionItemInput(
                    inspection_item=items[0],
                    condition=OutboundInspectionItem.Condition.GOOD,
                    functional_result=OutboundInspectionItem.FunctionalResult.REJECTED,
                    cleanliness_confirmed=True,
                    safety_confirmed=True,
                ),
            ),
            complete=True,
        )

    completed = save_outbound_inspection(
        organization=organization,
        inspection=inspection,
        user=user,
        general_notes="Aprovada apó novo teste.",
        customer_acknowledged=True,
        customer_representative_name="Maria Cliente",
        item_inputs=approved_inputs(items),
        complete=True,
    )
    checked_out = check_out_contract(
        organization=organization,
        contract=contract,
        user=user,
    )

    assert completed.completed_by == user
    assert completed.completed_at is not None
    assert checked_out.status == Contract.Status.ACTIVE
    units[0].refresh_from_db()
    assert units[0].status == ToolUnit.Status.RENTED


@pytest.mark.django_db
def test_completed_inspection_and_items_are_immutable():
    organization, user, contract, _, _ = create_domain(unit_count=1)
    inspection = complete_inspection(
        organization=organization,
        user=user,
        contract=contract,
    )

    inspection.general_notes = "Tentativa de alteração"
    with pytest.raises(ValidationError, match="não pode ser alterada"):
        inspection.save()
    item = inspection.items.get()
    item.notes = "Tentativa de alteração"
    with pytest.raises(ValidationError, match="imutáveis"):
        item.save()


@pytest.mark.django_db
def test_evidence_records_hash_downloads_only_in_tenant_and_can_be_deleted_from_draft(
    client,
    settings,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    settings.MEDIA_ROOT = tmp_path
    organization, user, contract, _, _ = create_domain(unit_count=1)
    inspection, items = create_outbound_inspection(
        organization=organization,
        contract=contract,
        user=user,
    )
    payload = b"\x89PNG\r\n\x1a\ninspection-proof"
    upload = SimpleUploadedFile("estado-inicial.png", payload, content_type="image/png")
    evidence = add_inspection_evidence(
        organization=organization,
        inspection=inspection,
        inspection_item=items[0],
        evidence_file=upload,
        caption="Lado esquerdo",
        user=user,
    )

    assert evidence.sha256 == hashlib.sha256(payload).hexdigest()
    assert evidence.original_name == "estado-inicial.png"
    assert evidence.size_bytes == len(payload)
    assert evidence.file.name.startswith(
        f"inspections/{organization.pk}/{inspection.pk}/"
    )
    assert evidence.file.storage.exists(evidence.file.name)

    client.force_login(user)
    response = client.get(reverse("inspections:evidence-download", args=[evidence.pk]))
    assert response.status_code == 200
    assert "estado-inicial.png" in response.headers["Content-Disposition"]

    _, other_user, _, _, _ = create_domain("b", unit_count=1)
    client.force_login(other_user)
    assert (
        client.get(reverse("inspections:evidence-download", args=[evidence.pk])).status_code
        == 404
    )

    client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("inspections:evidence-delete", args=[evidence.pk])
        )
    assert response.status_code == 302
    assert not InspectionEvidence.objects.filter(pk=evidence.pk).exists()
    assert not evidence.file.storage.exists(evidence.file.name)


@pytest.mark.django_db
def test_evidence_rejects_disguised_content_and_completed_inspections():
    organization, user, contract, _, _ = create_domain(unit_count=1)
    inspection, items = create_outbound_inspection(
        organization=organization,
        contract=contract,
        user=user,
    )
    disguised = SimpleUploadedFile(
        "falsa.png",
        b"isto nao e uma imagem",
        content_type="image/png",
    )
    with pytest.raises(ValidationError, match="conteúdo do arquivo"):
        add_inspection_evidence(
            organization=organization,
            inspection=inspection,
            inspection_item=items[0],
            evidence_file=disguised,
            caption="",
            user=user,
        )

    save_outbound_inspection(
        organization=organization,
        inspection=inspection,
        user=user,
        general_notes="",
        customer_acknowledged=True,
        customer_representative_name="Maria Cliente",
        item_inputs=approved_inputs(items),
        complete=True,
    )
    pdf = SimpleUploadedFile(
        "prova.pdf",
        b"%PDF-1.7\nproof",
        content_type="application/pdf",
    )
    with pytest.raises(ValidationError, match="concluída"):
        add_inspection_evidence(
            organization=organization,
            inspection=inspection,
            inspection_item=items[0],
            evidence_file=pdf,
            caption="",
            user=user,
        )


@pytest.mark.django_db
def test_views_create_complete_and_expose_checkout_only_after_inspection(client):
    organization, user, contract, _, _ = create_domain(unit_count=1)
    client.force_login(user)

    response = client.get(reverse("contracts:detail", args=[contract.pk]))
    assert "Iniciar inspeção inicial" in response.content.decode()
    assert "Confirmar retirada" not in response.content.decode()

    response = client.post(reverse("inspections:create", args=[contract.pk]))
    inspection = OutboundInspection.objects.get(contract=contract)
    item = inspection.items.get()
    assert response.url == reverse("inspections:detail", args=[inspection.pk])
    response = client.get(response.url)
    assert response.status_code == 200
    assert "Adicionar evidência" in response.content.decode()

    response = client.post(
        reverse("inspections:detail", args=[inspection.pk]),
        {
            "general_notes": "Tudo conferido",
            "customer_acknowledged": "on",
            "customer_representative_name": "Maria Cliente",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "1",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": str(item.pk),
            "items-0-condition": OutboundInspectionItem.Condition.GOOD,
            "items-0-functional_result": (
                OutboundInspectionItem.FunctionalResult.APPROVED
            ),
            "items-0-cleanliness_confirmed": "on",
            "items-0-safety_confirmed": "on",
            "items-0-components_snapshot": "Maleta",
            "items-0-notes": "Sem avarias",
            "action": "complete",
        },
    )
    inspection.refresh_from_db()
    assert response.url == reverse("contracts:detail", args=[contract.pk])
    assert inspection.status == OutboundInspection.Status.COMPLETED
    response = client.get(response.url)
    assert "Confirmar retirada" in response.content.decode()


@pytest.mark.django_db
def test_evidence_views_explain_invalid_files_and_lock_completed_records(
    client,
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path
    organization, user, contract, _, _ = create_domain(unit_count=1)
    inspection, items = create_outbound_inspection(
        organization=organization,
        contract=contract,
        user=user,
    )
    client.force_login(user)

    response = client.post(
        reverse("inspections:evidence-add", args=[inspection.pk]),
        {
            "inspection_item": str(items[0].pk),
            "caption": "Arquivo disfarçado",
            "file": SimpleUploadedFile(
                "falsa.png",
                b"nao e png",
                content_type="image/png",
            ),
        },
        follow=True,
    )
    assert response.status_code == 200
    assert "conteúdo do arquivo não corresponde" in response.content.decode()
    assert not InspectionEvidence.objects.exists()

    response = client.post(
        reverse("inspections:evidence-add", args=[inspection.pk]),
        {
            "inspection_item": str(items[0].pk),
            "caption": "Antes da entrega",
            "file": SimpleUploadedFile(
                "frente.jpg",
                b"\xff\xd8\xffinspection-proof",
                content_type="image/jpeg",
            ),
        },
    )
    evidence = InspectionEvidence.objects.get()
    assert response.status_code == 302

    save_outbound_inspection(
        organization=organization,
        inspection=inspection,
        user=user,
        general_notes="",
        customer_acknowledged=True,
        customer_representative_name="Maria Cliente",
        item_inputs=approved_inputs(items),
        complete=True,
    )
    response = client.post(
        reverse("inspections:evidence-delete", args=[evidence.pk]),
        follow=True,
    )
    assert response.status_code == 200
    assert "não podem ser removidas" in response.content.decode()
    assert InspectionEvidence.objects.filter(pk=evidence.pk).exists()

    response = client.post(
        reverse("inspections:evidence-add", args=[inspection.pk]),
        {
            "inspection_item": str(items[0].pk),
            "caption": "Depois da conclusão",
            "file": SimpleUploadedFile(
                "depois.pdf",
                b"%PDF-1.7\nproof",
                content_type="application/pdf",
            ),
        },
        follow=True,
    )
    assert response.status_code == 200
    assert "não aceita novas evidências" in response.content.decode()
    assert InspectionEvidence.objects.count() == 1

    evidence.caption = "Tentativa de alteração"
    with pytest.raises(ValidationError, match="não podem ser alteradas"):
        evidence.save()


@pytest.mark.django_db
def test_inspection_urls_reject_other_tenant_and_redirect_user_without_organization(
    client,
):
    _, _, contract, _, _ = create_domain(unit_count=1)
    _, other_user, other_contract, _, _ = create_domain("b", unit_count=1)
    inspection = complete_inspection(
        organization=other_contract.organization,
        user=other_user,
        contract=other_contract,
    )

    client.force_login(other_user)
    assert (
        client.post(reverse("inspections:create", args=[contract.pk])).status_code
        == 404
    )

    user_without_membership = User.objects.create_user(
        username="sem-organizacao",
        email="sem-organizacao@example.com",
        password="test-password-123",
    )
    client.force_login(user_without_membership)
    response = client.get(reverse("inspections:detail", args=[inspection.pk]))
    assert response.status_code == 302
    assert response.url == reverse("workspace:home")


@pytest.mark.django_db
def test_inspection_admin_is_read_only(rf, admin_user):
    request = rf.get("/admin/")
    request.user = admin_user
    inspection_admin = OutboundInspectionAdmin(OutboundInspection, admin.site)
    item_admin = OutboundInspectionItemAdmin(OutboundInspectionItem, admin.site)
    evidence_admin = InspectionEvidenceAdmin(InspectionEvidence, admin.site)
    inline = OutboundInspectionItemInline(OutboundInspection, admin.site)

    assert inspection_admin.has_add_permission(request) is False
    assert inspection_admin.has_delete_permission(request) is False
    assert item_admin.has_add_permission(request) is False
    assert item_admin.has_delete_permission(request) is False
    assert evidence_admin.has_add_permission(request) is False
    assert evidence_admin.has_delete_permission(request) is False
    assert inline.has_add_permission(request) is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="A concorrência real exige PostgreSQL.",
)
def test_concurrent_creation_keeps_single_outbound_inspection():
    organization, user, contract, _, _ = create_domain(unit_count=1)
    barrier = Barrier(2)

    def worker():
        close_old_connections()
        barrier.wait()
        try:
            inspection, _ = create_outbound_inspection(
                organization=Organization.objects.get(pk=organization.pk),
                contract=Contract.objects.get(pk=contract.pk),
                user=User.objects.get(pk=user.pk),
            )
            return inspection.pk
        except ValidationError:
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: worker(), range(2)))

    assert sum(result is not None for result in results) == 1
    assert OutboundInspection.objects.filter(contract=contract).count() == 1
