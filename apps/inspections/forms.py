from django import forms
from django.core.validators import FileExtensionValidator
from django.forms import modelformset_factory

from .models import (
    ALLOWED_EVIDENCE_CONTENT_TYPES,
    MAX_EVIDENCE_SIZE_BYTES,
    OutboundInspection,
    OutboundInspectionItem,
    detect_evidence_content_type,
)


class OutboundInspectionForm(forms.ModelForm):
    class Meta:
        model = OutboundInspection
        fields = (
            "general_notes",
            "customer_acknowledged",
            "customer_representative_name",
        )
        widgets = {"general_notes": forms.Textarea(attrs={"rows": 3})}


class OutboundInspectionItemForm(forms.ModelForm):
    condition = forms.ChoiceField(
        label="Condição externa",
        choices=(("", "Selecione"), *OutboundInspectionItem.Condition.choices),
        required=False,
    )

    class Meta:
        model = OutboundInspectionItem
        fields = (
            "condition",
            "functional_result",
            "cleanliness_confirmed",
            "safety_confirmed",
            "components_snapshot",
            "notes",
        )
        widgets = {
            "components_snapshot": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


OutboundInspectionItemFormSet = modelformset_factory(
    OutboundInspectionItem,
    form=OutboundInspectionItemForm,
    extra=0,
)


class InspectionEvidenceForm(forms.Form):
    inspection_item = forms.ModelChoiceField(
        label="Equipamento",
        queryset=OutboundInspectionItem.objects.none(),
        empty_label="Selecione",
    )
    file = forms.FileField(
        label="Imagem ou PDF",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp", "pdf"])],
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}
        ),
    )
    caption = forms.CharField(label="Descrição", max_length=240, required=False)

    def __init__(self, *args, organization, inspection, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["inspection_item"].queryset = OutboundInspectionItem.objects.filter(
            organization=organization,
            inspection=inspection,
        )

    def clean_file(self):
        evidence_file = self.cleaned_data["file"]
        if evidence_file.size < 1:
            raise forms.ValidationError("Selecione um arquivo não vazio.")
        if evidence_file.size > MAX_EVIDENCE_SIZE_BYTES:
            raise forms.ValidationError("Cada evidência pode ter no máximo 10 MB.")
        content_type = getattr(evidence_file, "content_type", "")
        if content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES:
            raise forms.ValidationError("Envie uma imagem JPG, PNG, WebP ou um PDF.")
        if detect_evidence_content_type(evidence_file) != content_type:
            raise forms.ValidationError(
                "O conteúdo do arquivo não corresponde ao formato informado."
            )
        return evidence_file
