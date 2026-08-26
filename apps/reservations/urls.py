from django.urls import path

from . import views

app_name = "reservations"

urlpatterns = [
    path("", views.reservation_list, name="list"),
    path("disponibilidade/", views.availability_lookup, name="availability"),
    path("nova/<uuid:quotation_id>/", views.reservation_create, name="create"),
    path("<uuid:reservation_id>/", views.reservation_detail, name="detail"),
    path("<uuid:reservation_id>/cancelar/", views.reservation_cancel, name="cancel"),
]
