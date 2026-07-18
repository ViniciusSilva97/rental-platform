from django.conf import settings
from django.db import models

from common.documents import format_cnpj, normalize_cnpj, validate_cnpj
from common.models import TimeStampedModel


class Organization(TimeStampedModel):
    name = models.CharField("nome", max_length=160)
    slug = models.SlugField(unique=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "organização"
        verbose_name_plural = "organizações"

    def __str__(self) -> str:
        return self.name


class Membership(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Proprietário"
        MANAGER = "MANAGER", "Gerente"
        ATTENDANT = "ATTENDANT", "Atendente"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.ATTENDANT)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="unique_organization_membership"
            )
        ]
        verbose_name = "vínculo"
        verbose_name_plural = "vínculos"

    def __str__(self) -> str:
        return f"{self.user} — {self.organization}"


class Establishment(TimeStampedModel):
    class Kind(models.TextChoices):
        HEADQUARTERS = "HEADQUARTERS", "Matriz"
        BRANCH = "BRANCH", "Filial"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="establishments",
    )
    name = models.CharField("nome", max_length=160)
    cnpj = models.CharField(
        "CNPJ",
        max_length=18,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_cnpj],
        help_text="Aceita CNPJ numérico ou alfanumérico, com ou sem máscara.",
    )
    kind = models.CharField(
        "tipo",
        max_length=12,
        choices=Kind.choices,
        default=Kind.HEADQUARTERS,
    )
    active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["organization__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_establishment_name_per_organization",
            ),
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(kind="HEADQUARTERS", active=True),
                name="unique_active_headquarters_per_organization",
            ),
            models.CheckConstraint(
                condition=models.Q(cnpj__isnull=True)
                | models.Q(cnpj__regex=r"^[A-Z0-9]{12}[0-9]{2}$"),
                name="normalized_cnpj_format",
            ),
        ]
        verbose_name = "estabelecimento"
        verbose_name_plural = "estabelecimentos"

    def clean(self):
        super().clean()
        self.cnpj = normalize_cnpj(self.cnpj) or None

    def save(self, *args, **kwargs):
        self.cnpj = normalize_cnpj(self.cnpj) or None
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def formatted_cnpj(self) -> str:
        return format_cnpj(self.cnpj)

    def __str__(self) -> str:
        return f"{self.name} — {self.organization}"
