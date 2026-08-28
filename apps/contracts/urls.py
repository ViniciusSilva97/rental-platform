from django.urls import path

from . import views

app_name = "contracts"

urlpatterns = [
    path("", views.contract_list, name="list"),
    path("novo/<uuid:reservation_id>/", views.contract_create, name="create"),
    path("<uuid:contract_id>/", views.contract_detail, name="detail"),
    path("<uuid:contract_id>/retirar/", views.contract_checkout, name="checkout"),
    path(
        "<uuid:contract_id>/devolver/<uuid:item_id>/",
        views.contract_return_item,
        name="return-item",
    ),
]
