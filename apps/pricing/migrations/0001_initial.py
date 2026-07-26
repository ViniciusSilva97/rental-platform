from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


def migrate_daily_rates_to_policies(apps, schema_editor):
    PricingPolicy = apps.get_model("pricing", "PricingPolicy")
    ToolModel = apps.get_model("catalog", "ToolModel")

    for tool_model in ToolModel.objects.exclude(daily_rate__isnull=True).iterator():
        PricingPolicy.objects.create(
            organization_id=tool_model.organization_id,
            tool_model_id=tool_model.pk,
            effective_from=django.utils.timezone.localtime(tool_model.created_at).date(),
            daily_rate=tool_model.daily_rate,
            partial_unit_rounding="UP",
            month_definition="FIXED_DAYS",
            fixed_month_days=30,
            active=True,
        )


def restore_daily_rates_from_policies(apps, schema_editor):
    PricingPolicy = apps.get_model("pricing", "PricingPolicy")
    ToolModel = apps.get_model("catalog", "ToolModel")

    for tool_model in ToolModel.objects.all().iterator():
        policy = (
            PricingPolicy.objects.filter(
                tool_model_id=tool_model.pk,
                daily_rate__isnull=False,
            )
            .order_by("-effective_from", "-created_at")
            .first()
        )
        daily_rate = policy.daily_rate if policy else Decimal("0.00")
        ToolModel.objects.filter(pk=tool_model.pk).update(daily_rate=daily_rate)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0004_prepare_daily_rate_migration"),
        ("organizations", "0002_establishment"),
    ]

    operations = [
        migrations.CreateModel(
            name="PricingPolicy",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "effective_from",
                    models.DateField(
                        default=django.utils.timezone.localdate,
                        help_text=(
                            "Uma versão mais recente substitui esta política "
                            "a partir de sua vigência."
                        ),
                        verbose_name="vigente a partir de",
                    ),
                ),
                (
                    "hourly_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="valor por hora",
                    ),
                ),
                (
                    "daily_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="valor por dia",
                    ),
                ),
                (
                    "monthly_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="valor por mês",
                    ),
                ),
                (
                    "partial_unit_rounding",
                    models.CharField(
                        choices=[
                            ("UP", "Arredondar para cima"),
                            ("PROPORTIONAL", "Cobrança proporcional"),
                        ],
                        default="UP",
                        max_length=12,
                        verbose_name="fração da unidade",
                    ),
                ),
                (
                    "month_definition",
                    models.CharField(
                        choices=[
                            ("FIXED_DAYS", "Quantidade fixa de dias"),
                            ("CALENDAR_MONTH", "Mês-calendário"),
                        ],
                        default="FIXED_DAYS",
                        max_length=14,
                        verbose_name="definição de mês",
                    ),
                ),
                (
                    "fixed_month_days",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        default=30,
                        null=True,
                        verbose_name="dias do mês fixo",
                    ),
                ),
                ("active", models.BooleanField(default=True, verbose_name="ativa")),
                ("notes", models.TextField(blank=True, verbose_name="observações")),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pricing_policies",
                        to="organizations.organization",
                    ),
                ),
                (
                    "tool_model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pricing_policies",
                        to="catalog.toolmodel",
                    ),
                ),
            ],
            options={
                "verbose_name": "política de preço",
                "verbose_name_plural": "políticas de preço",
                "ordering": [
                    "tool_model__name",
                    "-effective_from",
                    "-created_at",
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tool_model", "effective_from"),
                        name="unique_pricing_policy_version_per_tool_model",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("hourly_rate__isnull", False),
                            ("daily_rate__isnull", False),
                            ("monthly_rate__isnull", False),
                            _connector="OR",
                        ),
                        name="pricing_policy_has_rate",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("hourly_rate__gte", 0),
                            ("hourly_rate__isnull", True),
                            _connector="OR",
                        ),
                        name="non_negative_hourly_rate",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("daily_rate__gte", 0),
                            ("daily_rate__isnull", True),
                            _connector="OR",
                        ),
                        name="non_negative_policy_daily_rate",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("monthly_rate__gte", 0),
                            ("monthly_rate__isnull", True),
                            _connector="OR",
                        ),
                        name="non_negative_monthly_rate",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("fixed_month_days__gte", 1),
                                ("fixed_month_days__lte", 366),
                                ("month_definition", "FIXED_DAYS"),
                            ),
                            models.Q(
                                ("fixed_month_days__isnull", True),
                                ("month_definition", "CALENDAR_MONTH"),
                            ),
                            _connector="OR",
                        ),
                        name="valid_pricing_month_definition",
                    ),
                ],
            },
        ),
        migrations.RunPython(
            migrate_daily_rates_to_policies,
            reverse_code=restore_daily_rates_from_policies,
        ),
    ]
