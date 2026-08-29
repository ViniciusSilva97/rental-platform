from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorList
from django.shortcuts import get_object_or_404, redirect, render

from apps.quotations.models import Quotation, QuotationItem

from .forms import OfferingForm, OfferingSelectionFormSet
from .models import Offering
from .services import OfferingSelectionInput, save_quotation_item_offerings


def _active_organization_or_redirect(request):
    if request.organization is None:
        return None, redirect("workspace:home")
    return request.organization, None


@login_required
def offering_list(request):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    offerings = (
        Offering.objects.filter(organization=organization)
        .select_related("inventory_tool_model")
        .prefetch_related("compatibilities__tool_model", "pricing_policies", "stocks")
    )
    return render(request, "offerings/offering_list.html", {"offerings": offerings})


@login_required
def offering_create(request):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    form = OfferingForm(request.POST or None, organization=organization)
    if request.method == "POST" and form.is_valid():
        offering = form.save()
        messages.success(request, f"{offering.name} cadastrado com sucesso.")
        return redirect("offerings:list")
    return render(request, "offerings/offering_form.html", {"form": form})


@login_required
def quotation_item_offerings(request, quotation_id, item_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    quotation = get_object_or_404(
        Quotation, pk=quotation_id, organization=organization
    )
    item = get_object_or_404(
        QuotationItem.objects.select_related("tool_model"),
        pk=item_id,
        quotation=quotation,
        organization=organization,
    )
    initial = [
        {"offering": selection.offering, "quantity": selection.quantity}
        for selection in item.offerings.select_related("offering")
    ]
    formset = OfferingSelectionFormSet(
        request.POST or None,
        prefix="offerings",
        initial=initial,
        form_kwargs={"organization": organization, "tool_model": item.tool_model},
    )
    if request.method == "POST" and formset.is_valid():
        selections = tuple(
            OfferingSelectionInput(
                offering=form.cleaned_data["offering"],
                quantity=form.cleaned_data["quantity"],
            )
            for form in formset
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        )
        try:
            save_quotation_item_offerings(
                organization=organization, quotation_item=item, selections=selections
            )
        except ValidationError as error:
            formset._non_form_errors = ErrorList(error.messages)
        else:
            messages.success(request, "Adicionais do item atualizados.")
            return redirect("quotations:detail", quotation_id=quotation.pk)
    return render(
        request,
        "offerings/quotation_item_offerings.html",
        {"quotation": quotation, "item": item, "formset": formset},
    )
