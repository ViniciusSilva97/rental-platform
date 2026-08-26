from django import forms

from apps.catalog.models import ToolModel
from apps.organizations.models import Establishment


class AvailabilityForm(forms.Form):
    establishment = forms.ModelChoiceField(
        label="Estabelecimento",
        queryset=Establishment.objects.none(),
        empty_label="Selecione o estabelecimento",
    )
    tool_model = forms.ModelChoiceField(
        label="Modelo da ferramenta",
        queryset=ToolModel.objects.none(),
        empty_label="Selecione a ferramenta",
    )
    starts_at = forms.DateTimeField(
        label="Início",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    ends_at = forms.DateTimeField(
        label="Fim",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["establishment"].queryset = Establishment.objects.filter(
            organization=organization,
            active=True,
        )
        self.fields["tool_model"].queryset = ToolModel.objects.filter(
            organization=organization,
            active=True,
        ).select_related("category")

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "O fim deve ser posterior ao início.")
        return cleaned_data


class ReservationConfirmationForm(forms.Form):
    establishment = forms.ModelChoiceField(
        label="Estabelecimento para retirada",
        queryset=Establishment.objects.none(),
        empty_label="Selecione o estabelecimento",
        help_text="Todos os equipamentos deste orçamento serão separados nesta unidade.",
    )

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        establishments = Establishment.objects.filter(
            organization=organization,
            active=True,
        )
        self.fields["establishment"].queryset = establishments
        if establishments.count() == 1:
            self.fields["establishment"].initial = establishments.first()
