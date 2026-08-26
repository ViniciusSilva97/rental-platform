from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models

from common.models import TimeStampedModel


def reservation_period_expression():
    return models.Func(
        models.F("starts_at"),
        models.F("ends_at"),
        models.Value("[)"),
        function="TSTZRANGE",
        output_field=DateTimeRangeField(),
    )


class Reservation(TimeStampedModel):
    class Status(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmada"
        CANCELLED = "CANCELLED", "Cancelada"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    quotation = models.OneToOneField(
        "quotations.Quotation",
        on_delete=models.PROTECT,
        related_name="reservation",
    )
    establishment = models.ForeignKey(
        "organizations.Establishment",
        on_delete=models.PROTECT,
        related_name="reservations",
    )
    starts_at = models.DateTimeField("início da reserva")
    ends_at = models.DateTimeField("fim da reserva")
    status = models.CharField(
        "situação",
        max_length=10,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    confirmed_at = models.DateTimeField("confirmada em")
    cancelled_at = models.DateTimeField("cancelada em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="reservation_positive_period",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["CONFIRMED", "CANCELLED"]),
                name="reservation_valid_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="CONFIRMED", cancelled_at__isnull=True)
                    | models.Q(status="CANCELLED", cancelled_at__isnull=False)
                ),
                name="reservation_status_timestamp_consistency",
            ),
        ]
        verbose_name = "reserva"
        verbose_name_plural = "reservas"

    def clean(self):
        super().clean()
        errors = {}
        if self.quotation_id and self.organization_id:
            if self.quotation.organization_id != self.organization_id:
                errors["quotation"] = "O orçamento deve pertencer à mesma organização."
        if self.establishment_id and self.organization_id:
            if self.establishment.organization_id != self.organization_id:
                errors["establishment"] = (
                    "O estabelecimento deve pertencer à mesma organização."
                )
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "O fim da reserva deve ser posterior ao início."
        if self.quotation_id and self.starts_at and self.ends_at:
            if (
                self.starts_at != self.quotation.starts_at
                or self.ends_at != self.quotation.ends_at
            ):
                errors["quotation"] = "A reserva deve preservar o período do orçamento."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def display_code(self) -> str:
        return f"RES-{str(self.pk).split('-')[0].upper()}"

    def __str__(self) -> str:
        return f"{self.display_code} — {self.quotation.customer}"


class ReservationAllocation(TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="reservation_allocations",
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="allocations",
    )
    quotation_item = models.ForeignKey(
        "quotations.QuotationItem",
        on_delete=models.PROTECT,
        related_name="reservation_allocations",
    )
    tool_unit = models.ForeignKey(
        "catalog.ToolUnit",
        on_delete=models.PROTECT,
        related_name="reservation_allocations",
    )
    starts_at = models.DateTimeField("início reservado")
    ends_at = models.DateTimeField("fim reservado")
    released_at = models.DateTimeField("liberada em", null=True, blank=True)

    class Meta:
        ordering = ["tool_unit__asset_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["reservation", "tool_unit"],
                name="unique_tool_unit_per_reservation",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="reservation_allocation_positive_period",
            ),
            ExclusionConstraint(
                name="prevent_overlapping_active_reservations",
                expressions=[
                    ("tool_unit", RangeOperators.EQUAL),
                    (reservation_period_expression(), RangeOperators.OVERLAPS),
                ],
                condition=models.Q(released_at__isnull=True),
            ),
        ]
        verbose_name = "alocação de reserva"
        verbose_name_plural = "alocações de reserva"

    def clean(self):
        super().clean()
        errors = {}
        relationships = (
            ("reservation", getattr(self, "reservation", None), "reserva"),
            ("quotation_item", getattr(self, "quotation_item", None), "item do orçamento"),
            ("tool_unit", getattr(self, "tool_unit", None), "equipamento"),
        )
        if self.organization_id:
            for field, related, label in relationships:
                if related and related.organization_id != self.organization_id:
                    errors[field] = f"A organização de {label} deve ser a mesma da alocação."
        if self.reservation_id and self.quotation_item_id:
            if self.quotation_item.quotation_id != self.reservation.quotation_id:
                errors["quotation_item"] = "O item deve pertencer ao orçamento reservado."
        if self.tool_unit_id and self.quotation_item_id:
            if self.tool_unit.tool_model_id != self.quotation_item.tool_model_id:
                errors["tool_unit"] = "O equipamento deve corresponder ao modelo orçado."
        if self.tool_unit_id and self.reservation_id:
            if self.tool_unit.establishment_id != self.reservation.establishment_id:
                errors["tool_unit"] = "O equipamento deve pertencer ao estabelecimento reservado."
        if self.reservation_id and self.starts_at and self.ends_at:
            if (
                self.starts_at != self.reservation.starts_at
                or self.ends_at != self.reservation.ends_at
            ):
                errors["reservation"] = "A alocação deve preservar o período da reserva."
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            errors["ends_at"] = "O fim da alocação deve ser posterior ao início."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    @property
    def active(self) -> bool:
        return self.released_at is None

    def __str__(self) -> str:
        return f"{self.reservation.display_code} — {self.tool_unit.asset_code}"
