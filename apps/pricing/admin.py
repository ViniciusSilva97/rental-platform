from django.contrib import admin

from .models import PricingPolicy


@admin.register(PricingPolicy)
class PricingPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "tool_model",
        "effective_from",
        "hourly_rate",
        "daily_rate",
        "monthly_rate",
        "active",
    )
    list_filter = (
        "active",
        "partial_unit_rounding",
        "month_definition",
        "organization",
    )
    search_fields = ("tool_model__name", "tool_model__brand", "tool_model__model_number")
