import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from common.models import TimeStampedModel

MAX_EVIDENCE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EVIDENCE_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}


def detect_evidence_content_type(value):
    position = value.tell()
    header = value.read(12)
    value.seek(position)
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_evidence_size(value):
    if value.size > MAX_EVIDENCE_SIZE_BYTES:
        raise ValidationError("Cada evidência pode ter no máximo 10 MB.")


def inspection_evidence_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return (
        f"inspections/{instance.organization_id}/{instance.inspection_id}/"
        f"{uuid.uuid4().hex}{suffix}"
    )


class OutboundInspection(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        COMPLETED = "COMPLETED", "Concluída"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="outbound_inspections",
    )
    contract = models.OneToOneField(
        "contracts.Contract",
        on_delete=models.PROTECT,
        related_name="outbound_inspection",
    )
    status = models.CharField(
        "situação", max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    general_notes = models.TextField("observações gerais", blank=True)
    customer_acknowledged = models.BooleanField(
        "cliente acompanhou a conferência", default=False
    )
    customer_representative_name = models.CharField(
        "nome de quem acompanhou", max_length=200, blank=True
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_outbound_inspections",
    )
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="completed_outbound_inspections",
        null=True,
        blank=True,
    )
    completed_at = models.DateTimeField("concluída em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["DRAFT", "COMPLETED"]),
                name="outbound_inspection_valid_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="DRAFT",
                        completed_by__isnull=True,
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        status="COMPLETED",
                        completed_by__isnull=False,
                        completed_at__isnull=False,
                        customer_acknowledged=True,
                    )
                ),
                name="outbound_inspection_status_consistency",
            ),
        ]
        verbose_name = "inspeção inicial"
        verbose_name_plural = "inspeções iniciais"

    def clean(self):
        super().clean()
        errors = {}
        if self.organization_id and self.contract_id:
            if self.contract.organization_id != self.organization_id:
                errors["contract"] = "O contrato deve pertencer à mesma organização."
        for field in ("created_by", "completed_by"):
            related = getattr(self, field, None)
            if related and not related.is_active:
                errors[field] = "O usuário responsável precisa estar ativo."
        if self.status == self.Status.COMPLETED:
            if not self.customer_acknowledged:
                errors["customer_acknowledged"] = (
                    "Confirme que o cliente acompanhou a conferência."
                )
            if not self.customer_representative_name.strip():
                errors["customer_representative_name"] = (
                    "Informe quem acompanhou a conferência."
                )
            if not self.completed_by_id or not self.completed_at:
                errors["status"] = "A conclusão precisa registrar usuário e horário."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            current = type(self).objects.filter(pk=self.pk).values("status").first()
            if current and current["status"] == self.Status.COMPLETED:
                raise ValidationError("Uma inspeção concluída não pode ser alterada.")
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def display_code(self):
        return f"INI-{str(self.pk).split('-')[0].upper()}"

    def __str__(self):
        return f"{self.display_code} — {self.contract.display_code}"


class OutboundInspectionItem(TimeStampedModel):
    class Condition(models.TextChoices):
        EXCELLENT = "EXCELLENT", "Excelente"
        GOOD = "GOOD", "Boa"
        FAIR = "FAIR", "Desgaste aparente"
        DAMAGED = "DAMAGED", "Avaria preexistente"

    class FunctionalResult(models.TextChoices):
        PENDING = "PENDING", "Não testado"
        APPROVED = "APPROVED", "Aprovado"
        REJECTED = "REJECTED", "Reprovado"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="outbound_inspection_items",
    )
    inspection = models.ForeignKey(
        OutboundInspection,
        on_delete=models.CASCADE,
        related_name="items",
    )
    contract_item = models.OneToOneField(
        "contracts.ContractItem",
        on_delete=models.PROTECT,
        related_name="outbound_inspection_item",
    )
    asset_code_snapshot = models.CharField("código do equipamento", max_length=50)
    tool_name_snapshot = models.CharField("equipamento", max_length=260)
    condition = models.CharField(
        "condição externa", max_length=16, choices=Condition.choices, blank=True
    )
    functional_result = models.CharField(
        "teste funcional",
        max_length=10,
        choices=FunctionalResult.choices,
        default=FunctionalResult.PENDING,
    )
    cleanliness_confirmed = models.BooleanField("limpeza conferida", default=False)
    safety_confirmed = models.BooleanField("segurança conferida", default=False)
    components_snapshot = models.TextField(
        "componentes e acessórios entregues", blank=True
    )
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["asset_code_snapshot"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    condition__in=["", "EXCELLENT", "GOOD", "FAIR", "DAMAGED"]
                ),
                name="outbound_item_valid_condition",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    functional_result__in=["PENDING", "APPROVED", "REJECTED"]
                ),
                name="outbound_item_valid_functional_result",
            ),
        ]
        verbose_name = "item da inspeção inicial"
        verbose_name_plural = "itens da inspeção inicial"

    def clean(self):
        super().clean()
        errors = {}
        for field, related in (
            ("inspection", getattr(self, "inspection", None)),
            ("contract_item", getattr(self, "contract_item", None)),
        ):
            if self.organization_id and related:
                if related.organization_id != self.organization_id:
                    errors[field] = "O registro deve pertencer à mesma organização."
        if self.inspection_id and self.contract_item_id:
            if self.contract_item.contract_id != self.inspection.contract_id:
                errors["contract_item"] = "O item deve pertencer ao contrato inspecionado."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            current = (
                type(self)
                .objects.select_related("inspection")
                .filter(pk=self.pk)
                .first()
            )
            if current and current.inspection.status == OutboundInspection.Status.COMPLETED:
                raise ValidationError("Itens de uma inspeção concluída são imutáveis.")
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.inspection.display_code} — {self.asset_code_snapshot}"


class InspectionEvidence(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="inspection_evidences",
    )
    inspection = models.ForeignKey(
        OutboundInspection,
        on_delete=models.CASCADE,
        related_name="evidences",
    )
    inspection_item = models.ForeignKey(
        OutboundInspectionItem,
        on_delete=models.CASCADE,
        related_name="evidences",
    )
    file = models.FileField(
        "arquivo",
        upload_to=inspection_evidence_path,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "webp", "pdf"]),
            validate_evidence_size,
        ],
    )
    original_name = models.CharField("nome original", max_length=255)
    content_type = models.CharField("tipo de conteúdo", max_length=100)
    size_bytes = models.PositiveIntegerField("tamanho em bytes")
    sha256 = models.CharField("SHA-256", max_length=64)
    caption = models.CharField("descrição", max_length=240, blank=True)
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="uploaded_inspection_evidences",
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(size_bytes__gte=1),
                name="inspection_evidence_positive_size",
            ),
        ]
        verbose_name = "evidência de inspeção"
        verbose_name_plural = "evidências de inspeção"

    def clean(self):
        super().clean()
        errors = {}
        for field, related in (
            ("inspection", getattr(self, "inspection", None)),
            ("inspection_item", getattr(self, "inspection_item", None)),
        ):
            if self.organization_id and related:
                if related.organization_id != self.organization_id:
                    errors[field] = "O registro deve pertencer à mesma organização."
        if self.inspection_id and self.inspection_item_id:
            if self.inspection_item.inspection_id != self.inspection_id:
                errors["inspection_item"] = "A evidência deve pertencer à mesma inspeção."
        if self.content_type and self.content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES:
            errors["content_type"] = "Envie uma imagem JPG, PNG, WebP ou um PDF."
        if len(self.sha256) != 64:
            errors["sha256"] = "O hash SHA-256 da evidência é inválido."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Evidências registradas não podem ser alteradas.")
        if self.inspection.status == OutboundInspection.Status.COMPLETED:
            raise ValidationError("Uma inspeção concluída não aceita novas evidências.")
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.inspection_item.asset_code_snapshot} — {self.original_name}"
