from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class BillingUnit(models.TextChoices):
    HOUR = "HOUR", "Hora"
    DAY = "DAY", "Dia"
    MONTH = "MONTH", "Mês"


class PricingPolicy(TimeStampedModel):
    class PartialUnitRounding(models.TextChoices):
        UP = "UP", "Arredondar para cima"
        PROPORTIONAL = "PROPORTIONAL", "Cobrança proporcional"

    class MonthDefinition(models.TextChoices):
        FIXED_DAYS = "FIXED_DAYS", "Quantidade fixa de dias"
        CALENDAR_MONTH = "CALENDAR_MONTH", "Mês-calendário"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="pricing_policies",
    )
    tool_model = models.ForeignKey(
        "catalog.ToolModel",
        on_delete=models.CASCADE,
        related_name="pricing_policies",
    )
    effective_from = models.DateField(
        "vigente a partir de",
        default=timezone.localdate,
        help_text="Uma versão mais recente substitui esta política a partir de sua vigência.",
    )
    hourly_rate = models.DecimalField(
        "valor por hora",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    daily_rate = models.DecimalField(
        "valor por dia",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    monthly_rate = models.DecimalField(
        "valor por mês",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    partial_unit_rounding = models.CharField(
        "fração da unidade",
        max_length=12,
        choices=PartialUnitRounding.choices,
        default=PartialUnitRounding.UP,
    )
    month_definition = models.CharField(
        "definição de mês",
        max_length=14,
        choices=MonthDefinition.choices,
        default=MonthDefinition.FIXED_DAYS,
    )
    fixed_month_days = models.PositiveSmallIntegerField(
        "dias do mês fixo",
        default=30,
        null=True,
        blank=True,
    )
    active = models.BooleanField("ativa", default=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        ordering = ["tool_model__name", "-effective_from", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tool_model", "effective_from"],
                name="unique_pricing_policy_version_per_tool_model",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(hourly_rate__isnull=False)
                    | models.Q(daily_rate__isnull=False)
                    | models.Q(monthly_rate__isnull=False)
                ),
                name="pricing_policy_has_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gte=0) | models.Q(hourly_rate__isnull=True),
                name="non_negative_hourly_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(daily_rate__gte=0) | models.Q(daily_rate__isnull=True),
                name="non_negative_policy_daily_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(monthly_rate__gte=0) | models.Q(monthly_rate__isnull=True),
                name="non_negative_monthly_rate",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        month_definition="FIXED_DAYS",
                        fixed_month_days__gte=1,
                        fixed_month_days__lte=366,
                    )
                    | models.Q(
                        month_definition="CALENDAR_MONTH",
                        fixed_month_days__isnull=True,
                    )
                ),
                name="valid_pricing_month_definition",
            ),
        ]
        verbose_name = "política de preço"
        verbose_name_plural = "políticas de preço"

    def clean(self):
        super().clean()
        errors = {}

        if self.tool_model_id and self.organization_id:
            if self.tool_model.organization_id != self.organization_id:
                errors["tool_model"] = (
                    "O modelo de ferramenta deve pertencer à mesma organização da política."
                )

        if all(
            rate is None
            for rate in (self.hourly_rate, self.daily_rate, self.monthly_rate)
        ):
            errors["hourly_rate"] = "Informe ao menos um valor por hora, dia ou mês."

        if self.month_definition == self.MonthDefinition.CALENDAR_MONTH:
            self.fixed_month_days = None
        elif not self.fixed_month_days or not 1 <= self.fixed_month_days <= 366:
            errors["fixed_month_days"] = "Informe uma quantidade entre 1 e 366 dias."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.tool_model} — {self.effective_from:%d/%m/%Y}"
