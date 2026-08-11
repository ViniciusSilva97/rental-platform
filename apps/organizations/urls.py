from django.urls import path

from . import views

app_name = "workspace"

urlpatterns = [
    path("", views.workspace_home, name="home"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("selecionar-locadora/", views.select_organization, name="select-organization"),
]
