from django.contrib import admin

from .models import Contract, ContractItem, ContractOffering


class ContractItemInline(admin.TabularInline):
    model = ContractItem
    extra = 0
    readonly_fields = tuple(field.name for field in ContractItem._meta.fields)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ContractOfferingInline(admin.TabularInline):
    model = ContractOffering
    extra = 0
    readonly_fields = tuple(field.name for field in ContractOffering._meta.fields)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "display_code",
        "customer_name_snapshot",
        "establishment",
        "status",
        "organization",
    )
    list_filter = ("status", "establishment", "organization")
    search_fields = ("customer_name_snapshot", "customer_document_snapshot")
    readonly_fields = tuple(field.name for field in Contract._meta.fields)
    inlines = (ContractItemInline, ContractOfferingInline)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContractOffering)
class ContractOfferingAdmin(admin.ModelAdmin):
    list_display = ("contract", "offering_name", "kind", "quantity")
    readonly_fields = tuple(field.name for field in ContractOffering._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContractItem)
class ContractItemAdmin(admin.ModelAdmin):
    list_display = (
        "contract",
        "asset_code_snapshot",
        "checked_out_at",
        "returned_at",
        "return_condition",
    )
    list_filter = ("return_condition", "organization")
    search_fields = ("asset_code_snapshot", "tool_name_snapshot")
    readonly_fields = tuple(field.name for field in ContractItem._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
