import django.db.models.deletion
import uuid
from django.db import migrations, models

import common.locations


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organizations", "0002_establishment"),
    ]

    operations = [
        migrations.CreateModel(
            name="Customer",
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
                    "kind",
                    models.CharField(
                        choices=[
                            ("INDIVIDUAL", "Pessoa física"),
                            ("COMPANY", "Pessoa jurídica"),
                        ],
                        default="INDIVIDUAL",
                        max_length=10,
                        verbose_name="tipo",
                    ),
                ),
                ("name", models.CharField(max_length=160, verbose_name="nome ou razão social")),
                (
                    "trade_name",
                    models.CharField(blank=True, max_length=160, verbose_name="nome fantasia"),
                ),
                (
                    "document",
                    models.CharField(
                        help_text=(
                            "Aceita CPF, CNPJ numérico ou CNPJ alfanumérico, "
                            "com ou sem máscara."
                        ),
                        max_length=18,
                        verbose_name="CPF ou CNPJ",
                    ),
                ),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="e-mail")),
                ("phone", models.CharField(blank=True, max_length=20, verbose_name="telefone")),
                ("notes", models.TextField(blank=True, verbose_name="observações")),
                ("active", models.BooleanField(default=True, verbose_name="ativo")),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customers",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "cliente",
                "verbose_name_plural": "clientes",
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "document"),
                        name="unique_customer_document_per_organization",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("document__regex", "^[0-9]{11}$"),
                                ("kind", "INDIVIDUAL"),
                            )
                            | models.Q(
                                ("document__regex", "^[A-Z0-9]{12}[0-9]{2}$"),
                                ("kind", "COMPANY"),
                            )
                        ),
                        name="customer_document_matches_kind",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CustomerAddress",
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
                    "kind",
                    models.CharField(
                        choices=[
                            ("MAIN", "Principal"),
                            ("BILLING", "Cobrança"),
                            ("DELIVERY", "Entrega"),
                            ("OTHER", "Outro"),
                        ],
                        default="MAIN",
                        max_length=10,
                        verbose_name="tipo",
                    ),
                ),
                (
                    "postal_code",
                    models.CharField(
                        max_length=9,
                        validators=[common.locations.validate_brazilian_postal_code],
                        verbose_name="CEP",
                    ),
                ),
                ("street", models.CharField(max_length=160, verbose_name="logradouro")),
                ("number", models.CharField(max_length=20, verbose_name="número")),
                (
                    "complement",
                    models.CharField(blank=True, max_length=100, verbose_name="complemento"),
                ),
                ("district", models.CharField(max_length=100, verbose_name="bairro")),
                ("city", models.CharField(max_length=100, verbose_name="cidade")),
                ("state", models.CharField(max_length=2, verbose_name="UF")),
                ("country", models.CharField(default="BR", max_length=2, verbose_name="país")),
                ("active", models.BooleanField(default=True, verbose_name="ativo")),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addresses",
                        to="customers.customer",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_addresses",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "endereço de cliente",
                "verbose_name_plural": "endereços de clientes",
                "ordering": ["customer__name", "kind", "created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("active", True), ("kind", "MAIN")),
                        fields=("customer",),
                        name="unique_active_main_address_per_customer",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("postal_code__regex", "^[0-9]{8}$")),
                        name="normalized_customer_postal_code",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("state__regex", "^[A-Z]{2}$")),
                        name="normalized_customer_state",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("country__regex", "^[A-Z]{2}$")),
                        name="normalized_customer_country",
                    ),
                ],
            },
        ),
    ]
