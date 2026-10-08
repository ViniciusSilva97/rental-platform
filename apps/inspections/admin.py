from django.contrib import admin

from .models import InspectionEvidence, OutboundInspection, OutboundInspectionItem


class OutboundInspectionItemInline(admin.TabularInline):
    model = OutboundInspectionItem
    extra = 0
    readonly_fields = tuple(field.name for field in OutboundInspectionItem._meta.fields)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class InspectionEvidenceInline(admin.TabularInline):
    model = InspectionEvidence
    extra = 0
    readonly_fields = tuple(field.name for field in InspectionEvidence._meta.fields)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OutboundInspection)
class OutboundInspectionAdmin(admin.ModelAdmin):
    list_display = ("display_code", "contract", "status", "completed_at", "organization")
    list_filter = ("status", "organization")
    search_fields = ("contract__customer_name_snapshot",)
    readonly_fields = tuple(field.name for field in OutboundInspection._meta.fields)
    inlines = (OutboundInspectionItemInline, InspectionEvidenceInline)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OutboundInspectionItem)
class OutboundInspectionItemAdmin(admin.ModelAdmin):
    list_display = ("inspection", "asset_code_snapshot", "functional_result", "condition")
    readonly_fields = tuple(field.name for field in OutboundInspectionItem._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InspectionEvidence)
class InspectionEvidenceAdmin(admin.ModelAdmin):
    list_display = ("inspection", "inspection_item", "original_name", "size_bytes")
    readonly_fields = tuple(field.name for field in InspectionEvidence._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
