import hashlib
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.contracts.models import Contract, ContractItem
from apps.organizations.models import Membership

from .models import (
    ALLOWED_EVIDENCE_CONTENT_TYPES,
    MAX_EVIDENCE_SIZE_BYTES,
    InspectionEvidence,
    OutboundInspection,
    OutboundInspectionItem,
    detect_evidence_content_type,
)


@dataclass(frozen=True)
class OutboundInspectionItemInput:
    inspection_item: OutboundInspectionItem
    condition: str
    functional_result: str
    cleanliness_confirmed: bool
    safety_confirmed: bool
    components_snapshot: str = ""
    notes: str = ""


def _validate_organization(organization):
    if not organization or not organization.active:
        raise ValidationError("A organização atual precisa estar ativa.")


def _validate_operator(*, organization, user):
    if not user or not user.is_authenticated:
        raise ValidationError("Um usuário autenticado deve registrar a operação.")
    if not Membership.objects.filter(
        organization=organization,
        user=user,
        active=True,
    ).exists():
        raise ValidationError("O usuário não possui acesso ativo à organização atual.")


def _locked_inspection(*, organization, inspection):
    try:
        return (
            OutboundInspection.objects.select_for_update()
            .select_related("contract")
            .get(pk=inspection.pk, organization=organization)
        )
    except OutboundInspection.DoesNotExist as error:
        raise ValidationError("Selecione uma inspeção da organização atual.") from error


def create_outbound_inspection(*, organization, contract, user):
    _validate_organization(organization)
    _validate_operator(organization=organization, user=user)
    try:
        with transaction.atomic():
            try:
                locked_contract = Contract.objects.select_for_update().get(
                    pk=contract.pk,
                    organization=organization,
                )
            except Contract.DoesNotExist as error:
                raise ValidationError(
                    "Selecione um contrato da organização atual."
                ) from error
            if locked_contract.status != Contract.Status.PREPARED:
                raise ValidationError(
                    "Somente um contrato preparado pode iniciar a inspeção."
                )
            if OutboundInspection.objects.filter(contract=locked_contract).exists():
                raise ValidationError("Este contrato já possui uma inspeção inicial.")

            contract_items = list(
                ContractItem.objects.select_for_update()
                .filter(organization=organization, contract=locked_contract)
                .order_by("asset_code_snapshot")
            )
            if not contract_items:
                raise ValidationError("O contrato precisa possuir equipamentos físicos.")

            inspection = OutboundInspection(
                organization=organization,
                contract=locked_contract,
                created_by=user,
            )
            inspection.save()
            items = []
            for contract_item in contract_items:
                item = OutboundInspectionItem(
                    organization=organization,
                    inspection=inspection,
                    contract_item=contract_item,
                    asset_code_snapshot=contract_item.asset_code_snapshot,
                    tool_name_snapshot=contract_item.tool_name_snapshot,
                )
                item.save()
                items.append(item)
            return inspection, tuple(items)
    except IntegrityError as error:
        raise ValidationError(
            "A inspeção já foi criada por outra operação. Atualize a página."
        ) from error


def save_outbound_inspection(
    *,
    organization,
    inspection,
    user,
    general_notes,
    customer_acknowledged,
    customer_representative_name,
    item_inputs,
    complete=False,
):
    _validate_organization(organization)
    _validate_operator(organization=organization, user=user)
    inputs = tuple(item_inputs)
    with transaction.atomic():
        locked = _locked_inspection(
            organization=organization,
            inspection=inspection,
        )
        if locked.status != OutboundInspection.Status.DRAFT:
            raise ValidationError("Uma inspeção concluída não pode ser alterada.")
        if locked.contract.status != Contract.Status.PREPARED:
            raise ValidationError("O contrato não está mais preparado para inspeção.")

        items = {
            item.pk: item
            for item in OutboundInspectionItem.objects.select_for_update().filter(
                organization=organization,
                inspection=locked,
            )
        }
        input_ids = [entry.inspection_item.pk for entry in inputs]
        if len(input_ids) != len(set(input_ids)) or set(input_ids) != set(items):
            raise ValidationError("Confira todos os equipamentos desta inspeção.")

        valid_conditions = set(OutboundInspectionItem.Condition.values)
        valid_results = set(OutboundInspectionItem.FunctionalResult.values)
        for entry in inputs:
            if entry.condition and entry.condition not in valid_conditions:
                raise ValidationError("Selecione uma condição externa válida.")
            if entry.functional_result not in valid_results:
                raise ValidationError("Selecione um resultado funcional válido.")
            item = items[entry.inspection_item.pk]
            item.condition = entry.condition
            item.functional_result = entry.functional_result
            item.cleanliness_confirmed = bool(entry.cleanliness_confirmed)
            item.safety_confirmed = bool(entry.safety_confirmed)
            item.components_snapshot = (entry.components_snapshot or "").strip()
            item.notes = (entry.notes or "").strip()
            item.save()

        locked.general_notes = (general_notes or "").strip()
        locked.customer_acknowledged = bool(customer_acknowledged)
        locked.customer_representative_name = (
            customer_representative_name or ""
        ).strip()

        if complete:
            if not locked.customer_acknowledged:
                raise ValidationError(
                    "Confirme que o cliente acompanhou a conferência."
                )
            if not locked.customer_representative_name:
                raise ValidationError("Informe quem acompanhou a conferência.")
            not_ready = [
                item.asset_code_snapshot
                for item in items.values()
                if not item.condition
                or item.functional_result
                != OutboundInspectionItem.FunctionalResult.APPROVED
                or not item.cleanliness_confirmed
                or not item.safety_confirmed
            ]
            if not_ready:
                raise ValidationError(
                    "A inspeção não pode ser concluída. Revise: " + ", ".join(not_ready)
                )
            locked.status = OutboundInspection.Status.COMPLETED
            locked.completed_by = user
            locked.completed_at = timezone.now()

        locked.save()
        return locked


def add_inspection_evidence(
    *, organization, inspection, inspection_item, evidence_file, caption, user
):
    _validate_organization(organization)
    _validate_operator(organization=organization, user=user)
    if not evidence_file or evidence_file.size < 1:
        raise ValidationError("Selecione um arquivo não vazio.")
    if evidence_file.size > MAX_EVIDENCE_SIZE_BYTES:
        raise ValidationError("Cada evidência pode ter no máximo 10 MB.")
    content_type = getattr(evidence_file, "content_type", "")
    if content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES:
        raise ValidationError("Envie uma imagem JPG, PNG, WebP ou um PDF.")
    if detect_evidence_content_type(evidence_file) != content_type:
        raise ValidationError(
            "O conteúdo do arquivo não corresponde ao formato informado."
        )

    with transaction.atomic():
        locked = _locked_inspection(
            organization=organization,
            inspection=inspection,
        )
        if locked.status != OutboundInspection.Status.DRAFT:
            raise ValidationError("Uma inspeção concluída não aceita novas evidências.")
        try:
            item = OutboundInspectionItem.objects.select_for_update().get(
                pk=inspection_item.pk,
                organization=organization,
                inspection=locked,
            )
        except OutboundInspectionItem.DoesNotExist as error:
            raise ValidationError(
                "Selecione um equipamento desta inspeção."
            ) from error

        digest = hashlib.sha256()
        for chunk in evidence_file.chunks():
            digest.update(chunk)
        evidence_file.seek(0)
        evidence = InspectionEvidence(
            organization=organization,
            inspection=locked,
            inspection_item=item,
            file=evidence_file,
            original_name=Path(evidence_file.name).name[:255],
            content_type=content_type,
            size_bytes=evidence_file.size,
            sha256=digest.hexdigest(),
            caption=(caption or "").strip(),
            uploaded_by=user,
        )
        evidence.save()
        return evidence


def delete_inspection_evidence(*, organization, evidence, user):
    _validate_organization(organization)
    _validate_operator(organization=organization, user=user)
    with transaction.atomic():
        try:
            locked = (
                InspectionEvidence.objects.select_for_update()
                .select_related("inspection")
                .get(pk=evidence.pk, organization=organization)
            )
        except InspectionEvidence.DoesNotExist as error:
            raise ValidationError(
                "Selecione uma evidência da organização atual."
            ) from error
        if locked.inspection.status != OutboundInspection.Status.DRAFT:
            raise ValidationError("Evidências concluídas não podem ser removidas.")
        storage = locked.file.storage
        stored_name = locked.file.name
        locked.delete()
        transaction.on_commit(lambda: storage.delete(stored_name))
