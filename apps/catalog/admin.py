from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from apps.assets.models import AssetProfile
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


class AssetProfileInlineFormSet(BaseInlineFormSet):
    def save_new(self, form, commit=True):
        profile = super().save_new(form, commit=False)
        profile.organization_id = self.instance.organization_id
        if commit:
            profile.save()
        return profile


class AssetProfileInline(admin.StackedInline):
    model = AssetProfile
    formset = AssetProfileInlineFormSet
    extra = 1
    max_num = 1
    fields = (
        "acquisition_date",
        "placed_in_service_date",
        "acquisition_cost",
        "residual_value",
        "useful_life_months",
        "supplier_name",
        "invoice_number",
        "notes",
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
    inlines = (AssetProfileInline,)
