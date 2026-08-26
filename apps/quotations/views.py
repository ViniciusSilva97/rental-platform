from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    QuotationForm,
    QuotationItemFormSet,
    quotation_initial,
    quotation_items_initial,
)
from .models import Quotation
from .services import (
    QuotationLineInput,
    recalculate_draft_quotation,
    save_draft_quotation,
    transition_quotation,
)


def _active_organization_or_redirect(request):
    if request.organization is None:
        return None, redirect("workspace:home")
    return request.organization, None


def _add_validation_error(form, error):
    if hasattr(error, "message_dict"):
        for field, errors in error.message_dict.items():
            target = field if field in form.fields else None
            for message in errors:
                form.add_error(target, message)
    else:
        form.add_error(None, error)


@login_required
def quotation_list(request):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    quotations = (
        Quotation.objects.filter(organization=organization)
        .select_related("customer")
        .prefetch_related("items")
    )
    return render(
        request,
        "quotations/quotation_list.html",
        {"quotations": quotations},
    )


def _quotation_form_view(request, *, quotation=None):
    organization = request.organization
    if quotation is not None and quotation.status != Quotation.Status.DRAFT:
        messages.error(request, "Somente orçamentos em rascunho podem ser alterados.")
        return redirect("quotations:detail", quotation_id=quotation.pk)

    header_initial = quotation_initial(quotation) if quotation else None
    items_initial = quotation_items_initial(quotation) if quotation else None
    form = QuotationForm(
        request.POST or None,
        organization=organization,
        initial=header_initial,
    )
    formset = QuotationItemFormSet(
        request.POST or None,
        prefix="items",
        initial=items_initial,
        form_kwargs={"organization": organization},
    )
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        lines = tuple(
            QuotationLineInput(
                tool_model=item_form.cleaned_data["tool_model"],
                equipment_quantity=item_form.cleaned_data["equipment_quantity"],
                billing_unit=item_form.cleaned_data["billing_unit"],
            )
            for item_form in formset
            if item_form.cleaned_data and not item_form.cleaned_data.get("DELETE")
        )
        try:
            saved = save_draft_quotation(
                organization=organization,
                customer=form.cleaned_data["customer"],
                starts_at=form.cleaned_data["starts_at"],
                ends_at=form.cleaned_data["ends_at"],
                lines=lines,
                quotation=quotation,
            )
        except ValidationError as error:
            _add_validation_error(form, error)
        except ValueError as error:
            form.add_error(None, str(error))
        except IntegrityError:
            form.add_error(
                None,
                "O orçamento entrou em conflito com outra operação e não foi salvo.",
            )
        else:
            messages.success(request, f"{saved.display_code} salvo como rascunho.")
            return redirect("quotations:detail", quotation_id=saved.pk)

    return render(
        request,
        "quotations/quotation_form.html",
        {"form": form, "formset": formset, "quotation": quotation},
    )


@login_required
def quotation_create(request):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    return _quotation_form_view(request)


@login_required
def quotation_edit(request, quotation_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    quotation = get_object_or_404(
        Quotation.objects.prefetch_related("items__tool_model"),
        pk=quotation_id,
        organization=organization,
    )
    return _quotation_form_view(request, quotation=quotation)


@login_required
def quotation_detail(request, quotation_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    quotation = get_object_or_404(
        Quotation.objects.select_related("customer", "reservation").prefetch_related(
            "items__tool_model"
        ),
        pk=quotation_id,
        organization=organization,
    )
    return render(
        request,
        "quotations/quotation_detail.html",
        {"quotation": quotation},
    )


@login_required
@require_POST
def quotation_recalculate(request, quotation_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    quotation = get_object_or_404(Quotation, pk=quotation_id, organization=organization)
    try:
        recalculate_draft_quotation(organization=organization, quotation=quotation)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Orçamento recalculado com os preços vigentes.")
    return redirect("quotations:detail", quotation_id=quotation.pk)


@login_required
@require_POST
def quotation_transition(request, quotation_id, target_status):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    quotation = get_object_or_404(Quotation, pk=quotation_id, organization=organization)
    normalized_status = target_status.upper()
    if normalized_status not in Quotation.Status.values:
        raise Http404
    try:
        updated = transition_quotation(
            organization=organization,
            quotation=quotation,
            target_status=normalized_status,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"Orçamento marcado como {updated.get_status_display()}.")
    return redirect("quotations:detail", quotation_id=quotation.pk)
