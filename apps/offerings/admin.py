from django.contrib import admin

from .models import (
    Offering,
    OfferingCompatibility,
    OfferingPricingPolicy,
    OfferingStock,
)


class OfferingCompatibilityInline(admin.TabularInline):
    model = OfferingCompatibility
    extra = 0


class OfferingPricingPolicyInline(admin.TabularInline):
    model = OfferingPricingPolicy
    extra = 0


class OfferingStockInline(admin.TabularInline):
    model = OfferingStock
    extra = 0


@admin.register(Offering)
class OfferingAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organization", "active")
    list_filter = ("kind", "active", "organization")
    search_fields = ("name", "description")
    inlines = (
        OfferingCompatibilityInline,
        OfferingPricingPolicyInline,
        OfferingStockInline,
    )


admin.site.register(OfferingCompatibility)
admin.site.register(OfferingPricingPolicy)
admin.site.register(OfferingStock)
