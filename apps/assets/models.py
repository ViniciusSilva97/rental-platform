from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from common.models import TimeStampedModel


class AssetProfile(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="asset_profiles",
    )
    tool_unit = models.OneToOneField(
        "catalog.ToolUnit",
        on_delete=models.CASCADE,
        related_name="asset_profile",
    )
    acquisition_date = models.DateField("data de aquisição")
    placed_in_service_date = models.DateField(
        "data de entrada em operação",
        help_text="Data em que o ativo ficou disponível para uso.",
    )
    acquisition_cost = models.DecimalField(
        "custo de aquisição",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Valor aprovado para capitalização, incluindo custos diretamente atribuíveis.",
    )
    residual_value = models.DecimalField(
        "valor residual",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    useful_life_months = models.PositiveIntegerField(
        "vida útil em meses",
        validators=[MinValueValidator(1)],
    )
    supplier_name = models.CharField("fornecedor", max_length=160, blank=True)
    invoice_number = models.CharField("documento de aquisição", max_length=60, blank=True)
    notes = models.TextField("observações patrimoniais", blank=True)

    class Meta:
        ordering = ["tool_unit__asset_code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(acquisition_cost__gte=0),
                name="non_negative_asset_acquisition_cost",
            ),
            models.CheckConstraint(
                condition=models.Q(residual_value__gte=0),
                name="non_negative_asset_residual_value",
            ),
            models.CheckConstraint(
                condition=models.Q(residual_value__lte=models.F("acquisition_cost")),
                name="asset_residual_not_greater_than_cost",
            ),
            models.CheckConstraint(
                condition=models.Q(useful_life_months__gte=1),
                name="positive_asset_useful_life",
            ),
            models.CheckConstraint(
                condition=models.Q(placed_in_service_date__gte=models.F("acquisition_date")),
                name="asset_service_date_not_before_acquisition",
            ),
        ]
        verbose_name = "perfil patrimonial"
        verbose_name_plural = "perfis patrimoniais"

    def clean(self):
        super().clean()
        errors = {}

        if self.tool_unit_id and self.organization_id:
            if self.tool_unit.organization_id != self.organization_id:
                errors["tool_unit"] = (
                    "A unidade deve pertencer à mesma organização do perfil patrimonial."
                )

        if (
            self.acquisition_cost is not None
            and self.residual_value is not None
            and self.residual_value > self.acquisition_cost
        ):
            errors["residual_value"] = (
                "O valor residual não pode ser maior que o custo de aquisição."
            )

        if (
            self.acquisition_date
            and self.placed_in_service_date
            and self.placed_in_service_date < self.acquisition_date
        ):
            errors["placed_in_service_date"] = (
                "A entrada em operação não pode ser anterior à aquisição."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def depreciable_amount(self) -> Decimal:
        return self.acquisition_cost - self.residual_value

    def __str__(self) -> str:
        return f"{self.tool_unit.asset_code} — perfil patrimonial"
