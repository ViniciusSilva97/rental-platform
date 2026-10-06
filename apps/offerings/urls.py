from django.urls import path

from . import views

app_name = "offerings"

urlpatterns = [
    path("", views.offering_list, name="list"),
    path("novo/", views.offering_create, name="create"),
    path(
        "orcamentos/<uuid:quotation_id>/itens/<uuid:item_id>/",
        views.quotation_item_offerings,
        name="quotation-item",
    ),
]
