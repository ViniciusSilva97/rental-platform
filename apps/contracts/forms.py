from django import forms

from .models import ContractItem


class ContractItemReturnForm(forms.Form):
    condition = forms.ChoiceField(
        label="Condição observada",
        choices=ContractItem.ReturnCondition.choices,
    )
    notes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Registre avarias, peças ausentes ou orientações para inspeção.",
    )
