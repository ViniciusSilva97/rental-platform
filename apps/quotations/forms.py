from django import forms
from django.forms import formset_factory
from django.utils import timezone

from apps.catalog.models import ToolModel
from apps.customers.models import Customer
from apps.pricing.models import BillingUnit


class QuotationForm(forms.Form):
    customer = forms.ModelChoiceField(
        label="Cliente",
        queryset=Customer.objects.none(),
        empty_label="Selecione o cliente",
    )
    starts_at = forms.DateTimeField(
        label="Início da locação",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    ends_at = forms.DateTimeField(
        label="Fim da locação",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    rental_notes = forms.CharField(
        label="Observações da locação",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Não altera automaticamente preço, estoque ou disponibilidade.",
    )

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["customer"].queryset = Customer.objects.filter(
            organization=organization,
            active=True,
        )

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if starts_at and ends_at and ends_at <= starts_at:
            self.add_error("ends_at", "O fim da locação deve ser posterior ao início.")
        return cleaned_data


class QuotationItemForm(forms.Form):
    tool_model = forms.ModelChoiceField(
        label="Modelo da ferramenta",
        queryset=ToolModel.objects.none(),
        empty_label="Selecione a ferramenta",
    )
    equipment_quantity = forms.IntegerField(
        label="Quantidade de equipamentos",
        min_value=1,
        initial=1,
    )
    billing_unit = forms.ChoiceField(
        label="Cobrar por",
        choices=BillingUnit.choices,
        initial=BillingUnit.DAY,
    )

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tool_model"].queryset = ToolModel.objects.filter(
            organization=organization,
            active=True,
        ).select_related("category")


QuotationItemFormSet = formset_factory(
    QuotationItemForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
    max_num=20,
    validate_max=True,
)


def quotation_initial(quotation):
    return {
        "customer": quotation.customer,
        "starts_at": timezone.localtime(quotation.starts_at).strftime("%Y-%m-%dT%H:%M"),
        "ends_at": timezone.localtime(quotation.ends_at).strftime("%Y-%m-%dT%H:%M"),
        "rental_notes": quotation.rental_notes,
    }


def quotation_items_initial(quotation):
    return [
        {
            "tool_model": item.tool_model,
            "equipment_quantity": item.equipment_quantity,
            "billing_unit": item.billing_unit,
        }
        for item in quotation.items.select_related("tool_model")
    ]
