from django.contrib import admin

from .models import Establishment, Membership, Organization


class EstablishmentInline(admin.TabularInline):
    model = Establishment
    extra = 0
    fields = ("name", "cnpj", "kind", "active")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (EstablishmentInline,)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "active")
    list_filter = ("role", "active")
    search_fields = ("user__username", "user__email", "organization__name")


@admin.register(Establishment)
class EstablishmentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "kind", "display_cnpj", "active")
    list_filter = ("kind", "active", "organization")
    search_fields = ("name", "cnpj", "organization__name")

    @admin.display(description="CNPJ", ordering="cnpj")
    def display_cnpj(self, establishment):
        return establishment.formatted_cnpj or "—"
