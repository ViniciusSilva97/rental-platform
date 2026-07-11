from django.contrib import admin
from django.urls import path

from common.views import health_check, home

urlpatterns = [
    path("", home, name="home"),
    path("health/", health_check, name="health-check"),
    path("admin/", admin.site.urls),
]

