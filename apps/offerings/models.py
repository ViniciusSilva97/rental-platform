from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class Offering(TimeStampedModel):
    class Kind(models.TextChoices):
        CONFIGURATION = "CONFIGURATION", "Configuração"
        RETURNABLE_ACCESSORY = "RETURNABLE", "Acessório retornável"
        CONSUMABLE = "CONSUMABLE", "Consumível"
        SERVICE = "SERVICE", "Serviço"
        REMOVAL = "REMOVAL", "Remoção com desconto"

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="offerings"
    )
    name = models.CharField("nome", max_length=160)
    kind = models.CharField("categoria", max_length=16, choices=Kind.choices)
    description = models.TextField("descrição", blank=True)
    inventory_tool_model = models.ForeignKey(
        "catalog.ToolModel",
        on_delete=models.PROTECT,
        related_name="inventory_offerings",
        null=True,
        blank=True,
        help_text="Modelo físico reservado para esta configuração ou acessório.",
    )
    requires_preparation = models.BooleanField("exige preparação técnica", default=False)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name", "kind"],
                name="unique_offering_name_kind_per_organization",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind="RETURNABLE", inventory_tool_model__isnull=False)
                    | models.Q(kind="CONFIGURATION")
                    | models.Q(
                        kind__in=["CONSUMABLE", "SERVICE", "REMOVAL"],
                        inventory_tool_model__isnull=True,
                    )
                ),
                name="offering_inventory_kind_consistency",
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
                name="offering_valid_kind",
            ),
        ]
        verbose_name = "adicional configurável"
        verbose_name_plural = "adicionais configuráveis"

    def clean(self):
        super().clean()
        errors = {}
        if self.inventory_tool_model_id and self.organization_id:
            if self.inventory_tool_model.organization_id != self.organization_id:
                errors["inventory_tool_model"] = (
                    "O modelo de estoque deve pertencer à mesma organização."
                )
        if self.kind == self.Kind.RETURNABLE_ACCESSORY and not self.inventory_tool_model_id:
            errors["inventory_tool_model"] = (
                "Acessórios retornáveis precisam de um modelo físico de estoque."
            )
        if self.kind in {self.Kind.CONSUMABLE, self.Kind.SERVICE, self.Kind.REMOVAL}:
            if self.inventory_tool_model_id:
                errors["inventory_tool_model"] = (
                    "Esta categoria não utiliza unidades físicas retornáveis."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def is_discount(self):
        return self.kind == self.Kind.REMOVAL

    @property
    def tracks_physical_units(self):
        return self.inventory_tool_model_id is not None

    def __str__(self):
        return f"{self.name} — {self.get_kind_display()}"


class OfferingCompatibility(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="offering_compatibilities",
    )
    offering = models.ForeignKey(
        Offering, on_delete=models.CASCADE, related_name="compatibilities"
    )
    tool_model = models.ForeignKey(
        "catalog.ToolModel",
        on_delete=models.CASCADE,
        related_name="offering_compatibilities",
    )
    max_quantity_per_equipment = models.PositiveSmallIntegerField(
        "quantidade máxima por equipamento",
        default=1,
        validators=[MinValueValidator(1)],
    )
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["tool_model__name", "offering__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "tool_model"],
                name="unique_offering_compatibility",
            ),
            models.CheckConstraint(
                condition=models.Q(max_quantity_per_equipment__gte=1),
                name="positive_offering_max_quantity",
            ),
        ]

    def clean(self):
        super().clean()
        for field, related in (
            ("offering", getattr(self, "offering", None)),
            ("tool_model", getattr(self, "tool_model", None)),
        ):
            if self.organization_id and related:
                if related.organization_id != self.organization_id:
                    raise ValidationError({field: "O registro deve pertencer à mesma organização."})

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)


class OfferingPricingPolicy(TimeStampedModel):
    class BillingMethod(models.TextChoices):
        FLAT = "FLAT", "Valor único por locação"
        PER_PERIOD = "PER_PERIOD", "Por período"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="offering_pricing_policies",
    )
    offering = models.ForeignKey(
        Offering, on_delete=models.CASCADE, related_name="pricing_policies"
    )
    effective_from = models.DateField("vigente a partir de", default=timezone.localdate)
    billing_method = models.CharField(
        "forma de cobrança",
        max_length=10,
        choices=BillingMethod.choices,
        default=BillingMethod.FLAT,
    )
    flat_amount = models.DecimalField(
        "valor único", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    hourly_rate = models.DecimalField(
        "valor por hora", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    daily_rate = models.DecimalField(
        "valor por dia", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    monthly_rate = models.DecimalField(
        "valor por mês", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["offering__name", "-effective_from", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "effective_from"],
                name="unique_offering_price_version",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        billing_method="FLAT", flat_amount__isnull=False,
                        hourly_rate__isnull=True, daily_rate__isnull=True,
                        monthly_rate__isnull=True,
                    )
                    | models.Q(billing_method="PER_PERIOD", flat_amount__isnull=True)
                ),
                name="offering_price_billing_consistency",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(billing_method="FLAT")
                    | models.Q(hourly_rate__isnull=False)
                    | models.Q(daily_rate__isnull=False)
                    | models.Q(monthly_rate__isnull=False)
                ),
                name="offering_period_price_has_rate",
            ),
            models.CheckConstraint(
                condition=models.Q(billing_method__in=["FLAT", "PER_PERIOD"]),
                name="offering_price_valid_billing_method",
            ),
            models.CheckConstraint(
                condition=models.Q(flat_amount__gte=0) | models.Q(flat_amount__isnull=True),
                name="offering_price_non_negative_flat",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(hourly_rate__gte=0) | models.Q(hourly_rate__isnull=True)
                ),
                name="offering_price_non_negative_hourly",
            ),
            models.CheckConstraint(
                condition=models.Q(daily_rate__gte=0) | models.Q(daily_rate__isnull=True),
                name="offering_price_non_negative_daily",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(monthly_rate__gte=0) | models.Q(monthly_rate__isnull=True)
                ),
                name="offering_price_non_negative_monthly",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.offering_id and self.organization_id:
            if self.offering.organization_id != self.organization_id:
                errors["offering"] = "O adicional deve pertencer à mesma organização."
        rates = (self.hourly_rate, self.daily_rate, self.monthly_rate)
        if self.billing_method == self.BillingMethod.FLAT:
            if self.flat_amount is None:
                errors["flat_amount"] = "Informe o valor único."
            if any(rate is not None for rate in rates):
                errors["hourly_rate"] = "Valores por período não se aplicam ao valor único."
        else:
            if self.flat_amount is not None:
                errors["flat_amount"] = "Valor único não se aplica à cobrança por período."
            if all(rate is None for rate in rates):
                errors["hourly_rate"] = "Informe ao menos um valor por hora, dia ou mês."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class OfferingStock(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="offering_stocks",
    )
    offering = models.ForeignKey(Offering, on_delete=models.CASCADE, related_name="stocks")
    establishment = models.ForeignKey(
        "organizations.Establishment",
        on_delete=models.PROTECT,
        related_name="offering_stocks",
    )
    on_hand_quantity = models.PositiveIntegerField("quantidade em estoque", default=0)
    reserved_quantity = models.PositiveIntegerField("quantidade reservada", default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["offering", "establishment"],
                name="unique_offering_stock_per_establishment",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__lte=models.F("on_hand_quantity")),
                name="offering_reserved_not_above_stock",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        for field, related in (
            ("offering", getattr(self, "offering", None)),
            ("establishment", getattr(self, "establishment", None)),
        ):
            if self.organization_id and related:
                if related.organization_id != self.organization_id:
                    errors[field] = "O registro deve pertencer à mesma organização."
        if self.offering_id and self.offering.kind != Offering.Kind.CONSUMABLE:
            errors["offering"] = "Somente consumíveis utilizam saldo quantitativo."
        if self.reserved_quantity > self.on_hand_quantity:
            errors["reserved_quantity"] = "A quantidade reservada não pode superar o estoque."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def available_quantity(self):
        return self.on_hand_quantity - self.reserved_quantity
