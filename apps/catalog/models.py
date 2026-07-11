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
    daily_rate = models.DecimalField("valor da diária", max_digits=10, decimal_places=2)
    deposit_amount = models.DecimalField(
        "valor da caução", max_digits=10, decimal_places=2, default=0
    )
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name", "brand", "model_number"],
                name="unique_tool_model_per_organization",
            )
        ]
        verbose_name = "modelo de ferramenta"
        verbose_name_plural = "modelos de ferramentas"

    def __str__(self) -> str:
        return " ".join(part for part in (self.brand, self.name, self.model_number) if part)


class ToolUnit(TimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponível"
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
        verbose_name = "unidade de ferramenta"
        verbose_name_plural = "unidades de ferramentas"

    def __str__(self) -> str:
        return f"{self.asset_code} — {self.tool_model}"

