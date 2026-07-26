from django.core.exceptions import ValidationError
from django.db import models

from common.documents import (
    format_cnpj,
    format_cpf,
    normalize_cnpj,
    normalize_cpf,
    validate_cnpj,
    validate_cpf,
)
from common.locations import (
    format_brazilian_postal_code,
    normalize_brazilian_postal_code,
    validate_brazilian_postal_code,
)
from common.models import TimeStampedModel


class Customer(TimeStampedModel):
    class Kind(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Pessoa física"
        COMPANY = "COMPANY", "Pessoa jurídica"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="customers",
    )
    kind = models.CharField(
        "tipo",
        max_length=10,
        choices=Kind.choices,
        default=Kind.INDIVIDUAL,
    )
    name = models.CharField("nome ou razão social", max_length=160)
    trade_name = models.CharField("nome fantasia", max_length=160, blank=True)
    document = models.CharField(
        "CPF ou CNPJ",
        max_length=18,
        help_text="Aceita CPF, CNPJ numérico ou CNPJ alfanumérico, com ou sem máscara.",
    )
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "document"],
                name="unique_customer_document_per_organization",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind="INDIVIDUAL", document__regex=r"^[0-9]{11}$")
                    | models.Q(
                        kind="COMPANY",
                        document__regex=r"^[A-Z0-9]{12}[0-9]{2}$",
                    )
                ),
                name="customer_document_matches_kind",
            ),
        ]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def clean(self):
        super().clean()
        errors = {}

        if self.kind == self.Kind.INDIVIDUAL:
            self.document = normalize_cpf(self.document)
            validator = validate_cpf
        elif self.kind == self.Kind.COMPANY:
            self.document = normalize_cnpj(self.document)
            validator = validate_cnpj
        else:
            validator = None

        if validator is not None:
            try:
                validator(self.document)
            except ValidationError as error:
                errors["document"] = error.messages

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def formatted_document(self) -> str:
        if self.kind == self.Kind.INDIVIDUAL:
            return format_cpf(self.document)
        return format_cnpj(self.document)

    def __str__(self) -> str:
        return self.name


class CustomerAddress(TimeStampedModel):
    class Kind(models.TextChoices):
        MAIN = "MAIN", "Principal"
        BILLING = "BILLING", "Cobrança"
        DELIVERY = "DELIVERY", "Entrega"
        OTHER = "OTHER", "Outro"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="customer_addresses",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    kind = models.CharField(
        "tipo",
        max_length=10,
        choices=Kind.choices,
        default=Kind.MAIN,
    )
    postal_code = models.CharField(
        "CEP",
        max_length=9,
        validators=[validate_brazilian_postal_code],
    )
    street = models.CharField("logradouro", max_length=160)
    number = models.CharField("número", max_length=20)
    complement = models.CharField("complemento", max_length=100, blank=True)
    district = models.CharField("bairro", max_length=100)
    city = models.CharField("cidade", max_length=100)
    state = models.CharField("UF", max_length=2)
    country = models.CharField("país", max_length=2, default="BR")
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["customer__name", "kind", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(kind="MAIN", active=True),
                name="unique_active_main_address_per_customer",
            ),
            models.CheckConstraint(
                condition=models.Q(postal_code__regex=r"^[0-9]{8}$"),
                name="normalized_customer_postal_code",
            ),
            models.CheckConstraint(
                condition=models.Q(state__regex=r"^[A-Z]{2}$"),
                name="normalized_customer_state",
            ),
            models.CheckConstraint(
                condition=models.Q(country__regex=r"^[A-Z]{2}$"),
                name="normalized_customer_country",
            ),
        ]
        verbose_name = "endereço de cliente"
        verbose_name_plural = "endereços de clientes"

    def clean(self):
        super().clean()
        self.postal_code = normalize_brazilian_postal_code(self.postal_code)
        self.state = (self.state or "").strip().upper()
        self.country = (self.country or "").strip().upper()

        if self.customer_id and self.organization_id:
            if self.customer.organization_id != self.organization_id:
                raise ValidationError(
                    {"customer": "O cliente deve pertencer à mesma organização do endereço."}
                )

    def save(self, *args, **kwargs):
        self.postal_code = normalize_brazilian_postal_code(self.postal_code)
        self.state = (self.state or "").strip().upper()
        self.country = (self.country or "").strip().upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def formatted_postal_code(self) -> str:
        return format_brazilian_postal_code(self.postal_code)

    def __str__(self) -> str:
        return f"{self.street}, {self.number} — {self.city}/{self.state}"
