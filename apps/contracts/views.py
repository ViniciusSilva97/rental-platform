from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.reservations.models import Reservation

from .forms import ContractItemReturnForm
from .models import Contract, ContractItem
from .services import check_out_contract, create_contract, return_contract_item


def _active_organization_or_redirect(request):
    if request.organization is None:
        return None, redirect("workspace:home")
    return request.organization, None


@login_required
def contract_list(request):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    contracts = Contract.objects.filter(organization=organization).select_related(
        "customer",
        "establishment",
        "reservation",
    )
    return render(request, "contracts/contract_list.html", {"contracts": contracts})


@login_required
@require_POST
def contract_create(request, reservation_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    reservation = get_object_or_404(
        Reservation,
        pk=reservation_id,
        organization=organization,
    )
    try:
        contract, _ = create_contract(
            organization=organization,
            reservation=reservation,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("reservations:detail", reservation_id=reservation.pk)
    messages.success(request, f"{contract.display_code} preparado para retirada.")
    return redirect("contracts:detail", contract_id=contract.pk)


@login_required
def contract_detail(request, contract_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    contract = get_object_or_404(
        Contract.objects.select_related(
            "customer",
            "establishment",
            "reservation__quotation",
        ).prefetch_related(
            Prefetch(
                "items",
                queryset=ContractItem.objects.select_related(
                    "tool_unit",
                    "contract_offering",
                    "checked_out_by",
                    "returned_by",
                ),
            ),
            "offerings",
        ),
        pk=contract_id,
        organization=organization,
    )
    return render(
        request,
        "contracts/contract_detail.html",
        {
            "contract": contract,
            "return_conditions": ContractItem.ReturnCondition.choices,
        },
    )


@login_required
@require_POST
def contract_checkout(request, contract_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    contract = get_object_or_404(
        Contract,
        pk=contract_id,
        organization=organization,
    )
    try:
        checked_out = check_out_contract(
            organization=organization,
            contract=contract,
            user=request.user,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"Retirada do {checked_out.display_code} registrada.")
    return redirect("contracts:detail", contract_id=contract.pk)


@login_required
@require_POST
def contract_return_item(request, contract_id, item_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    contract = get_object_or_404(
        Contract,
        pk=contract_id,
        organization=organization,
    )
    item = get_object_or_404(
        ContractItem,
        pk=item_id,
        contract=contract,
        organization=organization,
    )
    form = ContractItemReturnForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revise a condição e as observações da devolução.")
    else:
        try:
            returned, updated_contract = return_contract_item(
                organization=organization,
                contract=contract,
                contract_item=item,
                condition=form.cleaned_data["condition"],
                notes=form.cleaned_data["notes"],
                user=request.user,
            )
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            message = f"Devolução de {returned.asset_code_snapshot} registrada."
            if updated_contract.status == Contract.Status.COMPLETED:
                message += " O contrato foi concluído."
            messages.success(request, message)
    return redirect("contracts:detail", contract_id=contract.pk)
