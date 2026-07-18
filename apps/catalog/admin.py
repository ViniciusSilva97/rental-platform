from django.contrib import admin

from .models import Category, ToolModel, ToolUnit


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "active")
    list_filter = ("active", "organization")
    search_fields = ("name",)


@admin.register(ToolModel)
class ToolModelAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "daily_rate", "active")
    list_filter = ("active", "category", "organization")
    search_fields = ("name", "brand", "model_number")


@admin.register(ToolUnit)
class ToolUnitAdmin(admin.ModelAdmin):
    list_display = ("asset_code", "tool_model", "establishment", "status", "location")
    list_filter = ("status", "organization", "establishment")
    search_fields = ("asset_code", "serial_number", "tool_model__name")
