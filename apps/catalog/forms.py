from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.organizations.models import Establishment

from .models import Category, ToolModel
from .services import (
    MAX_BATCH_SIZE,
    AssetConfiguration,
    PricingConfiguration,
    create_tool_batch,
)


class AssistedToolRegistrationForm(forms.Form):
    category = forms.ModelChoiceField(
        label="Categoria existente",
        queryset=Category.objects.none(),
        required=False,
        empty_label="Criar uma nova categoria",
    )
    new_category_name = forms.CharField(
        label="Nome da nova categoria",
        max_length=100,
        required=False,
        help_text="Preencha somente quando a categoria ainda não existir.",
    )
    model_name = forms.CharField(label="Nome do modelo da ferramenta", max_length=160)
    brand = forms.CharField(label="Marca", max_length=100, required=False)
    model_number = forms.CharField(
        label="Referência do fabricante",
        max_length=100,
        required=False,
    )
    description = forms.CharField(
        label="Descrição",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    deposit_amount = forms.DecimalField(
        label="Valor da caução",
        max_digits=10,
        decimal_places=2,
        initial=Decimal("0.00"),
        min_value=Decimal("0.00"),
    )

    quantity = forms.IntegerField(
        label="Quantidade de equipamentos físicos",
        min_value=1,
        max_value=MAX_BATCH_SIZE,
        initial=1,
        help_text="Os códigos internos serão gerados automaticamente.",
    )
    establishment = forms.ModelChoiceField(
        label="Unidade/filial responsável",
        queryset=Establishment.objects.none(),
        empty_label=None,
    )
    serial_numbers = forms.CharField(
        label="Números de série individuais",
        required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text=(
            "Opcional. Use uma linha para cada equipamento e deixe a linha vazia "
            "quando ele não tiver número de série."
        ),
    )

    effective_from = forms.DateField(
        label="Preços vigentes a partir de",
        required=False,
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    hourly_rate = forms.DecimalField(
        label="Valor por hora",
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
    )
    daily_rate = forms.DecimalField(
        label="Valor por dia",
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
    )
    monthly_rate = forms.DecimalField(
        label="Valor por mês",
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
    )

    confirm_asset_data = forms.BooleanField(
        label="Aplicar os dados de aquisição abaixo a todos os equipamentos do lote",
        required=False,
    )
    acquisition_date = forms.DateField(
        label="Data de aquisição",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    placed_in_service_date = forms.DateField(
        label="Data de entrada em operação",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    acquisition_cost = forms.DecimalField(
        label="Custo por equipamento",
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
    )
    residual_value = forms.DecimalField(
        label="Valor residual por equipamento",
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
    )
    useful_life_months = forms.IntegerField(
        label="Vida útil estimada em meses",
        required=False,
        min_value=1,
    )
    supplier_name = forms.CharField(label="Fornecedor", max_length=160, required=False)
    invoice_number = forms.CharField(
        label="Documento de aquisição",
        max_length=60,
        required=False,
    )

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["category"].queryset = Category.objects.filter(
            organization=organization,
            active=True,
        )
        establishments = Establishment.objects.filter(
            organization=organization,
            active=True,
        ).order_by("name")
        self.fields["establishment"].queryset = establishments
        if establishments.count() == 1:
            self.fields["establishment"].initial = establishments.first()
        else:
            headquarters = establishments.filter(
                kind=Establishment.Kind.HEADQUARTERS
            ).first()
            if headquarters:
                self.fields["establishment"].initial = headquarters

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        new_category_name = (cleaned_data.get("new_category_name") or "").strip()
        if category and new_category_name:
            self.add_error(
                "new_category_name",
                "Escolha uma categoria existente ou informe uma nova, não as duas.",
            )
        elif not category and not new_category_name:
            self.add_error(
                "new_category_name",
                "Escolha uma categoria existente ou informe uma nova.",
            )

        model_name = (cleaned_data.get("model_name") or "").strip()
        brand = (cleaned_data.get("brand") or "").strip()
        model_number = (cleaned_data.get("model_number") or "").strip()
        if model_name and ToolModel.objects.filter(
            organization=self.organization,
            name=model_name,
            brand=brand,
            model_number=model_number,
        ).exists():
            self.add_error(
                "model_name",
                "Este modelo já existe. O cadastro de novas unidades dele será uma próxima etapa.",
            )

        quantity = cleaned_data.get("quantity")
        if quantity:
            raw_serials = cleaned_data.get("serial_numbers") or ""
            serials = raw_serials.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if serials == [""]:
                serials = []
            if len(serials) > quantity:
                self.add_error(
                    "serial_numbers",
                    "Existem mais linhas de número de série do que equipamentos.",
                )
            else:
                cleaned_data["parsed_serial_numbers"] = tuple(
                    [value.strip() for value in serials]
                    + [""] * (quantity - len(serials))
                )

        rates = (
            cleaned_data.get("hourly_rate"),
            cleaned_data.get("daily_rate"),
            cleaned_data.get("monthly_rate"),
        )
        if any(rate is not None for rate in rates) and not cleaned_data.get("effective_from"):
            self.add_error("effective_from", "Informe quando estes preços entram em vigor.")

        asset_fields = (
            "acquisition_date",
            "placed_in_service_date",
            "acquisition_cost",
            "useful_life_months",
        )
        has_asset_data = any(cleaned_data.get(field) is not None for field in asset_fields)
        if has_asset_data and not cleaned_data.get("confirm_asset_data"):
            self.add_error(
                "confirm_asset_data",
                "Confirme antes de copiar os dados de aquisição para todo o lote.",
            )
        if cleaned_data.get("confirm_asset_data"):
            for field in asset_fields:
                if cleaned_data.get(field) is None:
                    self.add_error(field, "Este campo é obrigatório após a confirmação.")
            cost = cleaned_data.get("acquisition_cost")
            residual = cleaned_data.get("residual_value") or Decimal("0.00")
            if cost is not None and residual > cost:
                self.add_error(
                    "residual_value",
                    "O valor residual não pode ser maior que o custo.",
                )
            acquired = cleaned_data.get("acquisition_date")
            in_service = cleaned_data.get("placed_in_service_date")
            if acquired and in_service and in_service < acquired:
                self.add_error(
                    "placed_in_service_date",
                    "A entrada em operação não pode ser anterior à aquisição.",
                )
        return cleaned_data

    def save(self):
        data = self.cleaned_data
        rates = (data["hourly_rate"], data["daily_rate"], data["monthly_rate"])
        pricing = None
        if any(rate is not None for rate in rates):
            pricing = PricingConfiguration(
                effective_from=data["effective_from"],
                hourly_rate=data["hourly_rate"],
                daily_rate=data["daily_rate"],
                monthly_rate=data["monthly_rate"],
            )

        asset = None
        if data["confirm_asset_data"]:
            asset = AssetConfiguration(
                acquisition_date=data["acquisition_date"],
                placed_in_service_date=data["placed_in_service_date"],
                acquisition_cost=data["acquisition_cost"],
                residual_value=data["residual_value"] or Decimal("0.00"),
                useful_life_months=data["useful_life_months"],
                supplier_name=data["supplier_name"],
                invoice_number=data["invoice_number"],
            )

        return create_tool_batch(
            organization=self.organization,
            category=data["category"],
            new_category_name=data["new_category_name"],
            establishment=data["establishment"],
            model_name=data["model_name"],
            brand=data["brand"],
            model_number=data["model_number"],
            description=data["description"],
            deposit_amount=data["deposit_amount"],
            quantity=data["quantity"],
            serial_numbers=data["parsed_serial_numbers"],
            pricing=pricing,
            asset=asset,
        )
