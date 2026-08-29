from django import forms
from django.db import transaction
from django.forms import formset_factory
from django.utils import timezone

from apps.catalog.models import ToolModel
from apps.organizations.models import Establishment

from .models import (
    Offering,
    OfferingCompatibility,
    OfferingPricingPolicy,
    OfferingStock,
)


class OfferingForm(forms.ModelForm):
    compatible_models = forms.ModelMultipleChoiceField(
        label="Modelos compatíveis",
        queryset=ToolModel.objects.none(),
        help_text="Selecione os produtos principais nos quais esta opção pode ser usada.",
    )
    max_quantity_per_equipment = forms.IntegerField(
        label="Quantidade máxima por equipamento", min_value=1, initial=1
    )
    billing_method = forms.ChoiceField(
        label="Forma de cobrança", choices=OfferingPricingPolicy.BillingMethod.choices
    )
    effective_from = forms.DateField(
        label="Vigente a partir de",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    flat_amount = forms.DecimalField(
        label="Valor único", min_value=0, decimal_places=2, required=False
    )
    hourly_rate = forms.DecimalField(
        label="Valor por hora", min_value=0, decimal_places=2, required=False
    )
    daily_rate = forms.DecimalField(
        label="Valor por dia", min_value=0, decimal_places=2, required=False
    )
    monthly_rate = forms.DecimalField(
        label="Valor por mês", min_value=0, decimal_places=2, required=False
    )
    stock_establishment = forms.ModelChoiceField(
        label="Estabelecimento do estoque",
        queryset=Establishment.objects.none(),
        required=False,
    )
    on_hand_quantity = forms.IntegerField(
        label="Quantidade inicial em estoque", min_value=0, required=False
    )

    class Meta:
        model = Offering
        fields = (
            "name",
            "kind",
            "description",
            "inventory_tool_model",
            "requires_preparation",
            "active",
        )

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        models = ToolModel.objects.filter(organization=organization, active=True)
        self.fields["compatible_models"].queryset = models
        self.fields["inventory_tool_model"].queryset = models
        self.fields["stock_establishment"].queryset = Establishment.objects.filter(
            organization=organization, active=True
        )

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("billing_method")
        flat = cleaned.get("flat_amount")
        rates = (
            cleaned.get("hourly_rate"),
            cleaned.get("daily_rate"),
            cleaned.get("monthly_rate"),
        )
        if method == OfferingPricingPolicy.BillingMethod.FLAT:
            if flat is None:
                self.add_error("flat_amount", "Informe o valor único.")
            if any(rate is not None for rate in rates):
                self.add_error("hourly_rate", "Não informe tarifas por período.")
        elif method:
            if flat is not None:
                self.add_error("flat_amount", "Não informe valor único nesta modalidade.")
            if all(rate is None for rate in rates):
                self.add_error("hourly_rate", "Informe ao menos uma tarifa por período.")

        is_consumable = cleaned.get("kind") == Offering.Kind.CONSUMABLE
        establishment = cleaned.get("stock_establishment")
        quantity = cleaned.get("on_hand_quantity")
        if is_consumable and (establishment is None or quantity is None):
            self.add_error("stock_establishment", "Informe estabelecimento e estoque inicial.")
        if not is_consumable and (establishment is not None or quantity is not None):
            self.add_error("stock_establishment", "Somente consumíveis usam saldo quantitativo.")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)
        offering = super().save(commit=False)
        offering.organization = self.organization
        offering.save()
        for tool_model in self.cleaned_data["compatible_models"]:
            OfferingCompatibility.objects.create(
                organization=self.organization,
                offering=offering,
                tool_model=tool_model,
                max_quantity_per_equipment=self.cleaned_data[
                    "max_quantity_per_equipment"
                ],
            )
        OfferingPricingPolicy.objects.create(
            organization=self.organization,
            offering=offering,
            effective_from=self.cleaned_data["effective_from"],
            billing_method=self.cleaned_data["billing_method"],
            flat_amount=self.cleaned_data["flat_amount"],
            hourly_rate=self.cleaned_data["hourly_rate"],
            daily_rate=self.cleaned_data["daily_rate"],
            monthly_rate=self.cleaned_data["monthly_rate"],
        )
        if offering.kind == Offering.Kind.CONSUMABLE:
            OfferingStock.objects.create(
                organization=self.organization,
                offering=offering,
                establishment=self.cleaned_data["stock_establishment"],
                on_hand_quantity=self.cleaned_data["on_hand_quantity"],
            )
        return offering


class OfferingSelectionForm(forms.Form):
    offering = forms.ModelChoiceField(
        label="Adicional", queryset=Offering.objects.none(), empty_label="Selecione"
    )
    quantity = forms.IntegerField(label="Quantidade total", min_value=1, initial=1)

    def __init__(self, *args, organization, tool_model, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["offering"].queryset = Offering.objects.filter(
            organization=organization,
            active=True,
            compatibilities__tool_model=tool_model,
            compatibilities__active=True,
        ).distinct()


OfferingSelectionFormSet = formset_factory(
    OfferingSelectionForm,
    extra=0,
    can_delete=True,
    max_num=50,
    validate_max=True,
)
