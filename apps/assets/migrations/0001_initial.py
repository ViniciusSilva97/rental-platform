from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("catalog", "0005_remove_toolmodel_daily_rate"),
        ("organizations", "0002_establishment"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssetProfile",
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
                ("acquisition_date", models.DateField(verbose_name="data de aquisição")),
                (
                    "placed_in_service_date",
                    models.DateField(
                        help_text="Data em que o ativo ficou disponível para uso.",
                        verbose_name="data de entrada em operação",
                    ),
                ),
                (
                    "acquisition_cost",
                    models.DecimalField(
                        decimal_places=2,
                        help_text=(
                            "Valor aprovado para capitalização, incluindo "
                            "custos diretamente atribuíveis."
                        ),
                        max_digits=12,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="custo de aquisição",
                    ),
                ),
                (
                    "residual_value",
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00"))
                        ],
                        verbose_name="valor residual",
                    ),
                ),
                (
                    "useful_life_months",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)],
                        verbose_name="vida útil em meses",
                    ),
                ),
                (
                    "supplier_name",
                    models.CharField(
                        blank=True,
                        max_length=160,
                        verbose_name="fornecedor",
                    ),
                ),
                (
                    "invoice_number",
                    models.CharField(
                        blank=True,
                        max_length=60,
                        verbose_name="documento de aquisição",
                    ),
                ),
                (
                    "notes",
                    models.TextField(
                        blank=True,
                        verbose_name="observações patrimoniais",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asset_profiles",
                        to="organizations.organization",
                    ),
                ),
                (
                    "tool_unit",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asset_profile",
                        to="catalog.toolunit",
                    ),
                ),
            ],
            options={
                "verbose_name": "perfil patrimonial",
                "verbose_name_plural": "perfis patrimoniais",
                "ordering": ["tool_unit__asset_code"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("acquisition_cost__gte", 0)),
                        name="non_negative_asset_acquisition_cost",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("residual_value__gte", 0)),
                        name="non_negative_asset_residual_value",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("residual_value__lte", models.F("acquisition_cost"))
                        ),
                        name="asset_residual_not_greater_than_cost",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("useful_life_months__gte", 1)),
                        name="positive_asset_useful_life",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "placed_in_service_date__gte",
                                models.F("acquisition_date"),
                            )
                        ),
                        name="asset_service_date_not_before_acquisition",
                    ),
                ],
            },
        ),
    ]
