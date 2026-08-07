from django.contrib import admin

from .models import AssetProfile


@admin.register(AssetProfile)
class AssetProfileAdmin(admin.ModelAdmin):
    list_display = (
        "tool_unit",
        "acquisition_date",
        "acquisition_cost",
        "residual_value",
        "useful_life_months",
    )
    list_filter = ("organization", "acquisition_date", "placed_in_service_date")
    search_fields = (
        "tool_unit__asset_code",
        "tool_unit__serial_number",
        "supplier_name",
        "invoice_number",
    )
