from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from common.models import TimeStampedModel


class Category(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField("nome", max_length=100)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="unique_category_name_per_organization"
            )
        ]
        verbose_name = "categoria"

    def __str__(self) -> str:
        return self.name


class ToolModel(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="tool_models"
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="tool_models")
    name = models.CharField("nome", max_length=160)
    brand = models.CharField("marca", max_length=100, blank=True)
    model_number = models.CharField("modelo", max_length=100, blank=True)
    description = models.TextField("descrição", blank=True)
    deposit_amount = models.DecimalField(
        "valor da caução",
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name", "brand", "model_number"],
                name="unique_tool_model_per_organization",
            ),
            models.CheckConstraint(
                condition=models.Q(deposit_amount__gte=0),
                name="non_negative_deposit_amount",
            ),
        ]
        verbose_name = "modelo de ferramenta"
        verbose_name_plural = "modelos de ferramentas"

    def __str__(self) -> str:
        return " ".join(part for part in (self.brand, self.name, self.model_number) if part)

    def clean(self):
        super().clean()
        if self.category_id and self.organization_id:
            if self.category.organization_id != self.organization_id:
                raise ValidationError(
                    {"category": "A categoria deve pertencer à mesma organização do modelo."}
                )

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)


class AssetCodeSequence(TimeStampedModel):
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="asset_code_sequence",
    )
    next_value = models.PositiveBigIntegerField("próximo número", default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(next_value__gte=1),
                name="positive_asset_code_next_value",
            )
        ]
        verbose_name = "sequência de códigos internos"
        verbose_name_plural = "sequências de códigos internos"

    def __str__(self) -> str:
        return f"{self.organization} — próximo EQ-{self.next_value:06d}"


class ToolUnit(TimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Apta para locação"
        RESERVED = "RESERVED", "Reservada"
        RENTED = "RENTED", "Alugada"
        INSPECTION = "INSPECTION", "Em inspeção"
        MAINTENANCE = "MAINTENANCE", "Em manutenção"
        DAMAGED = "DAMAGED", "Danificada"
        INACTIVE = "INACTIVE", "Inativa"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="tool_units"
    )
    tool_model = models.ForeignKey(ToolModel, on_delete=models.PROTECT, related_name="units")
    establishment = models.ForeignKey(
        "organizations.Establishment",
        on_delete=models.PROTECT,
        related_name="tool_units",
        help_text="Estabelecimento responsável pela unidade física.",
    )
    asset_code = models.CharField("código patrimonial", max_length=50)
    serial_number = models.CharField("número de série", max_length=100, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    location = models.CharField("localização", max_length=120, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["asset_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "asset_code"],
                name="unique_asset_code_per_organization",
            )
        ]
        verbose_name = "equipamento físico"
        verbose_name_plural = "equipamentos físicos"

    def __str__(self) -> str:
        return f"{self.asset_code} — {self.tool_model}"

    def clean(self):
        super().clean()
        errors = {}

        if self.tool_model_id and self.organization_id:
            if self.tool_model.organization_id != self.organization_id:
                errors["tool_model"] = (
                    "O modelo de ferramenta deve pertencer à mesma organização da unidade."
                )

        if self.establishment_id and self.organization_id:
            if self.establishment.organization_id != self.organization_id:
                errors["establishment"] = (
                    "O estabelecimento deve pertencer à mesma organização da unidade."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)
