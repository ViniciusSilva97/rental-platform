from django.contrib import admin
from django.urls import include, path

from common.views import health_check, health_live, health_ready, home

urlpatterns = [
    path("", home, name="home"),
    path("health/", health_check, name="health-check"),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("app/orcamentos/", include("apps.quotations.urls")),
    path("app/ferramentas/", include("apps.catalog.urls")),
    path("app/", include("apps.organizations.urls")),
    path("admin/", admin.site.urls),
]
