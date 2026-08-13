from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.equipment_list, name="equipment-list"),
    path("cadastrar/", views.assisted_registration, name="assisted-registration"),
]
