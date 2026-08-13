from django.contrib import admin

from .models import Quotation, QuotationItem


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0
    readonly_fields = (
        "organization",
        "tool_model",
        "pricing_policy",
        "equipment_quantity",
        "billing_unit",
        "period_quantity",
        "billed_quantity",
        "unit_rate",
        "line_total",
        "policy_effective_from",
        "partial_unit_rounding",
        "month_definition",
        "fixed_month_days",
    )
    can_delete = False


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("display_code", "customer", "organization", "status", "total_amount")
    list_filter = ("status", "organization")
    search_fields = ("customer__name", "customer__document")
    readonly_fields = tuple(field.name for field in Quotation._meta.fields)
    inlines = (QuotationItemInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(QuotationItem)
class QuotationItemAdmin(admin.ModelAdmin):
    list_display = (
        "quotation",
        "tool_model",
        "equipment_quantity",
        "billing_unit",
        "line_total",
    )
    list_filter = ("billing_unit", "organization")
    readonly_fields = tuple(field.name for field in QuotationItem._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
