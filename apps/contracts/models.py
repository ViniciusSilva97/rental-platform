from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from common.models import TimeStampedModel


class Contract(TimeStampedModel):
    class Status(models.TextChoices):
        PREPARED = "PREPARED", "Preparado"
        ACTIVE = "ACTIVE", "Em andamento"
        COMPLETED = "COMPLETED", "Concluído"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    reservation = models.OneToOneField(
        "reservations.Reservation",
        on_delete=models.PROTECT,
        related_name="contract",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="contracts",
    )
    establishment = models.ForeignKey(
        "organizations.Establishment",
        on_delete=models.PROTECT,
        related_name="contracts",
    )
    starts_at = models.DateTimeField("início contratado")
    ends_at = models.DateTimeField("fim contratado")
    total_amount_snapshot = models.DecimalField(
        "valor total contratado",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    customer_name_snapshot = models.CharField("nome do cliente", max_length=200)
    customer_document_snapshot = models.CharField(
        "documento do cliente",
        max_length=20,
        blank=True,
    )
    status = models.CharField(
        "situação",
        max_length=10,
        choices=Status.choices,
        default=Status.PREPARED,
    )
    activated_at = models.DateTimeField("retirada concluída em", null=True, blank=True)
    completed_at = models.DateTimeField("devolução concluída em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="contract_positive_period",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount_snapshot__gte=0),
                name="contract_non_negative_total",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["PREPARED", "ACTIVE", "COMPLETED"]),
                name="contract_valid_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="PREPARED",
                        activated_at__isnull=True,
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        status="ACTIVE",
                        activated_at__isnull=False,
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        status="COMPLETED",
                        activated_at__isnull=False,
                        completed_at__isnull=False,
                    )
                ),
                name="contract_status_timestamp_consistency",
            ),
        ]
        verbose_name = "contrato"
        verbose_name_plural = "contratos"

    def clean(self):
        super().clean()
        errors = {}
        relationships = (
            ("reservation", getattr(self, "reservation", None), "reserva"),
            ("customer", getattr(self, "customer", None), "cliente"),
            ("establishment", getattr(self, "establishment", None), "estabelecimento"),
        )
        if self.organization_id:
            for field, related, label in relationships:
                if related and related.organization_id != self.organization_id:
                    errors[field] = f"A organização de {label} deve ser a mesma do contrato."
        if self.reservation_id and self.customer_id:
            if self.reservation.quotation.customer_id != self.customer_id:
                errors["customer"] = "O cliente deve ser o mesmo do orçamento reservado."
        if self.reservation_id and self.establishment_id:
            if self.reservation.establishment_id != self.establishment_id:
                errors["establishment"] = "O estabelecimento deve ser o mesmo da reserva."
        if self.reservation_id and self.starts_at and self.ends_at:
            if (
                self.starts_at != self.reservation.starts_at
                or self.ends_at != self.reservation.ends_at
            ):
                errors["reservation"] = "O contrato deve preservar o período da reserva."
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "O fim do contrato deve ser posterior ao início."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def display_code(self) -> str:
        return f"CTR-{str(self.pk).split('-')[0].upper()}"

    def __str__(self) -> str:
        return f"{self.display_code} — {self.customer_name_snapshot}"


class ContractItem(TimeStampedModel):
    class ReturnCondition(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Apta para locação"
        INSPECTION = "INSPECTION", "Em inspeção"
        MAINTENANCE = "MAINTENANCE", "Em manutenção"
        DAMAGED = "DAMAGED", "Danificada"
        LOST = "LOST", "Perdida"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="contract_items",
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="items",
    )
    contract_offering = models.ForeignKey(
        "contracts.ContractOffering",
        on_delete=models.PROTECT,
        related_name="physical_items",
        null=True,
        blank=True,
    )
    reservation_allocation = models.OneToOneField(
        "reservations.ReservationAllocation",
        on_delete=models.PROTECT,
        related_name="contract_item",
    )
    tool_unit = models.ForeignKey(
        "catalog.ToolUnit",
        on_delete=models.PROTECT,
        related_name="contract_items",
    )
    asset_code_snapshot = models.CharField("código do equipamento", max_length=50)
    tool_name_snapshot = models.CharField("ferramenta", max_length=260)
    checked_out_at = models.DateTimeField("retirada em", null=True, blank=True)
    checked_out_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="checked_out_contract_items",
        null=True,
        blank=True,
    )
    returned_at = models.DateTimeField("devolvida em", null=True, blank=True)
    returned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="returned_contract_items",
        null=True,
        blank=True,
    )
    return_condition = models.CharField(
        "condição na devolução",
        max_length=16,
        choices=ReturnCondition.choices,
        blank=True,
    )
    return_notes = models.TextField("observações da devolução", blank=True)

    class Meta:
        ordering = ["asset_code_snapshot"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "tool_unit"],
                name="unique_tool_unit_per_contract",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        checked_out_at__isnull=True,
                        checked_out_by__isnull=True,
                        returned_at__isnull=True,
                        returned_by__isnull=True,
                        return_condition="",
                    )
                    | models.Q(
                        checked_out_at__isnull=False,
                        checked_out_by__isnull=False,
                        returned_at__isnull=True,
                        returned_by__isnull=True,
                        return_condition="",
                    )
                    | models.Q(
                        checked_out_at__isnull=False,
                        checked_out_by__isnull=False,
                        returned_at__isnull=False,
                        returned_by__isnull=False,
                        return_condition__in=[
                            "AVAILABLE",
                            "INSPECTION",
                            "MAINTENANCE",
                            "DAMAGED",
                            "LOST",
                        ],
                    )
                ),
                name="contract_item_event_consistency",
            ),
        ]
        verbose_name = "item de contrato"
        verbose_name_plural = "itens de contrato"

    def clean(self):
        super().clean()
        errors = {}
        relationships = (
            ("contract", getattr(self, "contract", None), "contrato"),
            (
                "reservation_allocation",
                getattr(self, "reservation_allocation", None),
                "alocação",
            ),
            ("tool_unit", getattr(self, "tool_unit", None), "equipamento"),
            (
                "contract_offering",
                getattr(self, "contract_offering", None),
                "adicional do contrato",
            ),
        )
        if self.organization_id:
            for field, related, label in relationships:
                if related and related.organization_id != self.organization_id:
                    errors[field] = f"A organização de {label} deve ser a mesma do item."
        if self.contract_id and self.reservation_allocation_id:
            if self.reservation_allocation.reservation_id != self.contract.reservation_id:
                errors["reservation_allocation"] = "A alocação deve pertencer à reserva contratada."
        if self.tool_unit_id and self.reservation_allocation_id:
            if self.reservation_allocation.tool_unit_id != self.tool_unit_id:
                errors["tool_unit"] = "O equipamento deve ser o mesmo da alocação."
        if self.contract_offering_id and self.contract_id:
            if self.contract_offering.contract_id != self.contract_id:
                errors["contract_offering"] = (
                    "O adicional físico deve pertencer ao mesmo contrato."
                )
        if self.checked_out_at and self.returned_at and self.returned_at < self.checked_out_at:
            errors["returned_at"] = "A devolução não pode anteceder a retirada."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.contract.display_code} — {self.asset_code_snapshot}"


class ContractOffering(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="contract_offerings",
    )
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name="offerings"
    )
    reservation_offering = models.OneToOneField(
        "reservations.ReservationOffering",
        on_delete=models.PROTECT,
        related_name="contract_offering",
    )
    offering_name = models.CharField("nome do adicional", max_length=160)
    kind = models.CharField("categoria", max_length=16)
    quantity = models.PositiveIntegerField("quantidade")
    price_effect = models.CharField("efeito no preço", max_length=8)
    line_total_snapshot = models.DecimalField(
        "total do adicional", max_digits=14, decimal_places=2
    )
    requires_preparation = models.BooleanField("exige preparação técnica", default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="contract_offering_positive_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(line_total_snapshot__gte=0),
                name="contract_offering_non_negative_total",
            ),
            models.CheckConstraint(
                condition=models.Q(price_effect__in=["ADDITION", "DISCOUNT"]),
                name="contract_offering_valid_effect",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=[
                        "CONFIGURATION",
                        "RETURNABLE",
                        "CONSUMABLE",
                        "SERVICE",
                        "REMOVAL",
                    ]
                ),
                name="contract_offering_valid_kind",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        for field, related in (
            ("contract", getattr(self, "contract", None)),
            ("reservation_offering", getattr(self, "reservation_offering", None)),
        ):
            if self.organization_id and related:
                if related.organization_id != self.organization_id:
                    errors[field] = "O registro deve pertencer à mesma organização."
        if self.contract_id and self.reservation_offering_id:
            if self.reservation_offering.reservation_id != self.contract.reservation_id:
                errors["reservation_offering"] = (
                    "O adicional deve pertencer à reserva contratada."
                )
            if self.kind != self.reservation_offering.kind:
                errors["kind"] = "A categoria deve preservar a reserva."
            if self.quantity != self.reservation_offering.quantity:
                errors["quantity"] = "A quantidade deve preservar a reserva."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)
