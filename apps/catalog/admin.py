from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from apps.pricing.models import PricingPolicy

from .models import Category, ToolModel, ToolUnit


class PricingPolicyInlineFormSet(BaseInlineFormSet):
    def save_new(self, form, commit=True):
        policy = super().save_new(form, commit=False)
        policy.organization_id = self.instance.organization_id
        if commit:
            policy.save()
        return policy


class PricingPolicyInline(admin.TabularInline):
    model = PricingPolicy
    formset = PricingPolicyInlineFormSet
    extra = 1
    fields = (
        "effective_from",
        "hourly_rate",
        "daily_rate",
        "monthly_rate",
        "partial_unit_rounding",
        "month_definition",
        "fixed_month_days",
        "active",
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "active")
    list_filter = ("active", "organization")
    search_fields = ("name",)


@admin.register(ToolModel)
class ToolModelAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "active")
    list_filter = ("active", "category", "organization")
    search_fields = ("name", "brand", "model_number")
    inlines = (PricingPolicyInline,)


@admin.register(ToolUnit)
class ToolUnitAdmin(admin.ModelAdmin):
    list_display = ("asset_code", "tool_model", "establishment", "status", "location")
    list_filter = ("status", "organization", "establishment")
    search_fields = ("asset_code", "serial_number", "tool_model__name")
