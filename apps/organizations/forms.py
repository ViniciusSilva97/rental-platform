from django import forms

from common.documents import validate_cnpj

from .models import Organization
from .services import available_memberships, create_organization_for_owner


class OrganizationOnboardingForm(forms.Form):
    name = forms.CharField(
        label="Nome da locadora",
        max_length=160,
        help_text="Nome comercial apresentado dentro do sistema.",
    )
    headquarters_name = forms.CharField(
        label="Nome da unidade principal",
        max_length=160,
        initial="Matriz",
        help_text="Exemplo: Matriz, Loja Centro ou Unidade Principal.",
    )
    cnpj = forms.CharField(
        label="CNPJ da unidade principal",
        max_length=18,
        required=False,
        validators=[validate_cnpj],
        help_text="Opcional. Aceita CNPJ numérico ou alfanumérico, com ou sem máscara.",
    )

    def save(self, *, user) -> Organization:
        return create_organization_for_owner(user=user, **self.cleaned_data)


class OrganizationSelectionForm(forms.Form):
    organization = forms.ModelChoiceField(
        label="Locadora",
        queryset=Organization.objects.none(),
        empty_label=None,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        organization_ids = available_memberships(user).values("organization_id")
        self.fields["organization"].queryset = Organization.objects.filter(
            id__in=organization_ids
        ).order_by("name")
