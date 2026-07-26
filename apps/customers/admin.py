from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from .models import Customer, CustomerAddress


class CustomerAddressInlineFormSet(BaseInlineFormSet):
    def save_new(self, form, commit=True):
        address = form.save(commit=False)
        address.organization_id = self.instance.organization_id
        if commit:
            address.save()
        return address


class CustomerAddressInline(admin.TabularInline):
    model = CustomerAddress
    formset = CustomerAddressInlineFormSet
    extra = 0
    fields = (
        "kind",
        "postal_code",
        "street",
        "number",
        "complement",
        "district",
        "city",
        "state",
        "active",
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "display_document", "email", "phone", "active")
    list_filter = ("kind", "active", "organization")
    search_fields = ("name", "trade_name", "document", "email", "phone")
    inlines = (CustomerAddressInline,)

    @admin.display(description="CPF/CNPJ", ordering="document")
    def display_document(self, customer):
        return customer.formatted_document


@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ("customer", "kind", "city", "state", "display_postal_code", "active")
    list_filter = ("kind", "active", "state", "organization")
    search_fields = ("customer__name", "street", "district", "city", "postal_code")

    @admin.display(description="CEP", ordering="postal_code")
    def display_postal_code(self, address):
        return address.formatted_postal_code
