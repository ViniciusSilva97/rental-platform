from django.urls import path

from . import views

app_name = "inspections"

urlpatterns = [
    path("iniciais/criar/<uuid:contract_id>/", views.inspection_create, name="create"),
    path("iniciais/<uuid:inspection_id>/", views.inspection_detail, name="detail"),
    path(
        "iniciais/<uuid:inspection_id>/evidencias/",
        views.inspection_evidence_add,
        name="evidence-add",
    ),
    path(
        "evidencias/<uuid:evidence_id>/baixar/",
        views.inspection_evidence_download,
        name="evidence-download",
    ),
    path(
        "evidencias/<uuid:evidence_id>/remover/",
        views.inspection_evidence_delete,
        name="evidence-delete",
    ),
]
