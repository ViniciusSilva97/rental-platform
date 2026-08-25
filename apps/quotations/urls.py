from django.urls import path

from . import views

app_name = "quotations"

urlpatterns = [
    path("", views.quotation_list, name="list"),
    path("novo/", views.quotation_create, name="create"),
    path("<uuid:quotation_id>/", views.quotation_detail, name="detail"),
    path("<uuid:quotation_id>/editar/", views.quotation_edit, name="edit"),
    path(
        "<uuid:quotation_id>/recalcular/",
        views.quotation_recalculate,
        name="recalculate",
    ),
    path(
        "<uuid:quotation_id>/situacao/<str:target_status>/",
        views.quotation_transition,
        name="transition",
    ),
]
