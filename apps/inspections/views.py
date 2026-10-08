from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.contracts.models import Contract

from .forms import (
    InspectionEvidenceForm,
    OutboundInspectionForm,
    OutboundInspectionItemFormSet,
)
from .models import InspectionEvidence, OutboundInspection, OutboundInspectionItem
from .services import (
    OutboundInspectionItemInput,
    add_inspection_evidence,
    create_outbound_inspection,
    delete_inspection_evidence,
    save_outbound_inspection,
)


def _active_organization_or_redirect(request):
    if request.organization is None:
        return None, redirect("workspace:home")
    return request.organization, None


def _inspection_queryset():
    return OutboundInspection.objects.select_related(
        "contract",
        "created_by",
        "completed_by",
    ).prefetch_related(
        "items__contract_item",
        "items__evidences__uploaded_by",
    )


def _first_form_error(form, fallback):
    for errors in form.errors.values():
        if errors:
            return str(errors[0])
    return fallback


@login_required
@require_POST
def inspection_create(request, contract_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    contract = get_object_or_404(
        Contract,
        pk=contract_id,
        organization=organization,
    )
    try:
        inspection, _ = create_outbound_inspection(
            organization=organization,
            contract=contract,
            user=request.user,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("contracts:detail", contract_id=contract.pk)
    messages.success(request, f"{inspection.display_code} iniciada.")
    return redirect("inspections:detail", inspection_id=inspection.pk)


@login_required
def inspection_detail(request, inspection_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    inspection = get_object_or_404(
        _inspection_queryset(),
        pk=inspection_id,
        organization=organization,
    )
    item_queryset = OutboundInspectionItem.objects.filter(
        organization=organization,
        inspection=inspection,
    ).order_by("asset_code_snapshot")
    form = OutboundInspectionForm(request.POST or None, instance=inspection)
    formset = OutboundInspectionItemFormSet(
        request.POST or None,
        queryset=item_queryset,
        prefix="items",
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        item_inputs = tuple(
            OutboundInspectionItemInput(
                inspection_item=item_form.instance,
                condition=item_form.cleaned_data["condition"],
                functional_result=item_form.cleaned_data["functional_result"],
                cleanliness_confirmed=item_form.cleaned_data["cleanliness_confirmed"],
                safety_confirmed=item_form.cleaned_data["safety_confirmed"],
                components_snapshot=item_form.cleaned_data["components_snapshot"],
                notes=item_form.cleaned_data["notes"],
            )
            for item_form in formset
        )
        try:
            updated = save_outbound_inspection(
                organization=organization,
                inspection=inspection,
                user=request.user,
                general_notes=form.cleaned_data["general_notes"],
                customer_acknowledged=form.cleaned_data["customer_acknowledged"],
                customer_representative_name=form.cleaned_data[
                    "customer_representative_name"
                ],
                item_inputs=item_inputs,
                complete=request.POST.get("action") == "complete",
            )
        except ValidationError as error:
            form.add_error(None, error.messages[0])
        else:
            if updated.status == OutboundInspection.Status.COMPLETED:
                messages.success(request, "Inspeção inicial concluída e protegida.")
                return redirect("contracts:detail", contract_id=updated.contract_id)
            messages.success(request, "Rascunho da inspeção salvo.")
            return redirect("inspections:detail", inspection_id=updated.pk)

    evidence_form = InspectionEvidenceForm(
        organization=organization,
        inspection=inspection,
    )
    return render(
        request,
        "inspections/outbound_inspection_detail.html",
        {
            "inspection": inspection,
            "form": form,
            "formset": formset,
            "evidence_form": evidence_form,
        },
    )


@login_required
@require_POST
def inspection_evidence_add(request, inspection_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    inspection = get_object_or_404(
        OutboundInspection,
        pk=inspection_id,
        organization=organization,
    )
    form = InspectionEvidenceForm(
        request.POST,
        request.FILES,
        organization=organization,
        inspection=inspection,
    )
    if form.is_valid():
        try:
            add_inspection_evidence(
                organization=organization,
                inspection=inspection,
                inspection_item=form.cleaned_data["inspection_item"],
                evidence_file=form.cleaned_data["file"],
                caption=form.cleaned_data["caption"],
                user=request.user,
            )
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Evidência anexada.")
    else:
        messages.error(
            request,
            _first_form_error(
                form,
                "Revise o equipamento e o arquivo da evidência.",
            ),
        )
    return redirect("inspections:detail", inspection_id=inspection.pk)


@login_required
def inspection_evidence_download(request, evidence_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    evidence = get_object_or_404(
        InspectionEvidence,
        pk=evidence_id,
        organization=organization,
    )
    try:
        stored_file = evidence.file.open("rb")
    except FileNotFoundError as error:
        raise Http404("Arquivo de evidência não encontrado.") from error
    return FileResponse(
        stored_file,
        as_attachment=True,
        filename=evidence.original_name,
    )


@login_required
@require_POST
def inspection_evidence_delete(request, evidence_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    evidence = get_object_or_404(
        InspectionEvidence.objects.select_related("inspection"),
        pk=evidence_id,
        organization=organization,
    )
    inspection_id = evidence.inspection_id
    try:
        delete_inspection_evidence(
            organization=organization,
            evidence=evidence,
            user=request.user,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Evidência removida do rascunho.")
    return redirect("inspections:detail", inspection_id=inspection_id)
