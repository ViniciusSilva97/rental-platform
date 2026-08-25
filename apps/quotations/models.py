from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.pricing.models import BillingUnit, PricingPolicy
from common.models import TimeStampedModel


class Quotation(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        SENT = "SENT", "Enviado"
        EXPIRED = "EXPIRED", "Expirado"
        CANCELLED = "CANCELLED", "Cancelado"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="quotations",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    starts_at = models.DateTimeField("início da locação")
    ends_at = models.DateTimeField("fim da locação")
    status = models.CharField(
        "situação",
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    total_amount = models.DecimalField(
        "valor total",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    sent_at = models.DateTimeField("enviado em", null=True, blank=True)
    expired_at = models.DateTimeField("expirado em", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelado em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="quotation_positive_period",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="quotation_non_negative_total",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["DRAFT", "SENT", "EXPIRED", "CANCELLED"]
                ),
                name="quotation_valid_status",
            ),
        ]
        verbose_name = "orçamento"
        verbose_name_plural = "orçamentos"

    def clean(self):
        super().clean()
        errors = {}
        if self.customer_id and self.organization_id:
            if self.customer.organization_id != self.organization_id:
                errors["customer"] = (
                    "O cliente deve pertencer à mesma organização do orçamento."
                )
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "O fim da locação deve ser posterior ao início."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def display_code(self) -> str:
        return f"ORC-{str(self.pk).split('-')[0].upper()}"

    def __str__(self) -> str:
        return f"{self.display_code} — {self.customer}"


class QuotationItem(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="quotation_items",
    )
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="items",
    )
    tool_model = models.ForeignKey(
        "catalog.ToolModel",
        on_delete=models.PROTECT,
        related_name="quotation_items",
    )
    pricing_policy = models.ForeignKey(
        "pricing.PricingPolicy",
        on_delete=models.PROTECT,
        related_name="quotation_items",
    )
    equipment_quantity = models.PositiveIntegerField(
        "quantidade de equipamentos",
        validators=[MinValueValidator(1)],
    )
    billing_unit = models.CharField(
        "unidade de cobrança",
        max_length=5,
        choices=BillingUnit.choices,
    )
    period_quantity = models.DecimalField(
        "quantidade do período",
        max_digits=14,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    billed_quantity = models.DecimalField(
        "quantidade cobrada",
        max_digits=14,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
    )
    unit_rate = models.DecimalField(
        "tarifa unitária",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    line_total = models.DecimalField(
        "total do item",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    policy_effective_from = models.DateField("vigência do preço")
    partial_unit_rounding = models.CharField(
        "regra de fração",
        max_length=12,
        choices=PricingPolicy.PartialUnitRounding.choices,
    )
    month_definition = models.CharField(
        "definição de mês",
        max_length=14,
        choices=PricingPolicy.MonthDefinition.choices,
    )
    fixed_month_days = models.PositiveSmallIntegerField(
        "dias do mês fixo",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["quotation", "tool_model", "billing_unit"],
                name="unique_quotation_model_billing_unit",
            ),
            models.CheckConstraint(
                condition=models.Q(equipment_quantity__gte=1),
                name="quotation_item_positive_equipment_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(period_quantity__gt=0),
                name="quotation_item_positive_period_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(billed_quantity__gt=0),
                name="quotation_item_positive_billed_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_rate__gte=0),
                name="quotation_item_non_negative_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(line_total__gte=0),
                name="quotation_item_non_negative_total",
            ),
            models.CheckConstraint(
                condition=models.Q(billing_unit__in=BillingUnit.values),
                name="quotation_item_valid_billing_unit",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    partial_unit_rounding__in=PricingPolicy.PartialUnitRounding.values
                ),
                name="quotation_item_valid_rounding",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        month_definition=PricingPolicy.MonthDefinition.FIXED_DAYS,
                        fixed_month_days__isnull=False,
                        fixed_month_days__gte=1,
                        fixed_month_days__lte=366,
                    )
                    | models.Q(
                        month_definition=PricingPolicy.MonthDefinition.CALENDAR_MONTH,
                        fixed_month_days__isnull=True,
                    )
                ),
                name="quotation_item_valid_month_definition",
            ),
        ]
        verbose_name = "item de orçamento"
        verbose_name_plural = "itens de orçamento"

    def clean(self):
        super().clean()
        errors = {}
        relationships = (
            ("quotation", getattr(self, "quotation", None), "orçamento"),
            ("tool_model", getattr(self, "tool_model", None), "modelo da ferramenta"),
            (
                "pricing_policy",
                getattr(self, "pricing_policy", None),
                "política de preço",
            ),
        )
        if self.organization_id:
            for field, related, label in relationships:
                if related and related.organization_id != self.organization_id:
                    errors[field] = f"O {label} deve pertencer à mesma organização."
        if self.pricing_policy_id and self.tool_model_id:
            if self.pricing_policy.tool_model_id != self.tool_model_id:
                errors["pricing_policy"] = (
                    "A política de preço deve pertencer ao modelo da ferramenta."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def calculation_summary(self) -> str:
        rate = f"{self.unit_rate:.2f}".replace(".", ",")
        total = f"{self.line_total:.2f}".replace(".", ",")
        return (
            f"{self.equipment_quantity} equipamento(s) × "
            f"{self.billed_quantity.normalize()} {self.get_billing_unit_display().lower()}(s) "
            f"× R$ {rate} = R$ {total}"
        )

    def __str__(self) -> str:
        return f"{self.quotation.display_code} — {self.tool_model}"
