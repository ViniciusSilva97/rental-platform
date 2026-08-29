from django.contrib import admin

from .models import Reservation, ReservationAllocation, ReservationOffering


class ReservationAllocationInline(admin.TabularInline):
    model = ReservationAllocation
    extra = 0
    readonly_fields = tuple(field.name for field in ReservationAllocation._meta.fields)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ReservationOfferingInline(admin.TabularInline):
    model = ReservationOffering
    extra = 0
    readonly_fields = tuple(field.name for field in ReservationOffering._meta.fields)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        "display_code",
        "quotation",
        "establishment",
        "organization",
        "status",
    )
    list_filter = ("status", "establishment", "organization")
    search_fields = ("quotation__customer__name", "quotation__customer__document")
    readonly_fields = tuple(field.name for field in Reservation._meta.fields)
    inlines = (ReservationAllocationInline, ReservationOfferingInline)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReservationAllocation)
class ReservationAllocationAdmin(admin.ModelAdmin):
    list_display = ("reservation", "tool_unit", "starts_at", "ends_at", "released_at")
    list_filter = ("organization", "released_at")
    search_fields = ("tool_unit__asset_code", "reservation__quotation__customer__name")
    readonly_fields = tuple(field.name for field in ReservationAllocation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReservationOffering)
class ReservationOfferingAdmin(admin.ModelAdmin):
    list_display = ("reservation", "offering_name", "kind", "quantity")
    readonly_fields = tuple(field.name for field in ReservationOffering._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
