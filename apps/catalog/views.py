from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render

from apps.reservations.services import units_with_reservation_schedule

from .forms import AssistedToolRegistrationForm
from .models import ToolUnit


@login_required
def equipment_list(request):
    if request.organization is None:
        return redirect("workspace:home")
    units = units_with_reservation_schedule(
        organization=request.organization,
        queryset=(
            ToolUnit.objects.filter(organization=request.organization)
            .select_related("tool_model", "establishment")
            .order_by("asset_code")
        ),
    )
    return render(request, "catalog/equipment_list.html", {"units": units})


@login_required
def assisted_registration(request):
    if request.organization is None:
        return redirect("workspace:home")

    form = AssistedToolRegistrationForm(
        request.POST or None,
        organization=request.organization,
    )
    if request.method == "POST" and form.is_valid():
        try:
            result = form.save()
        except ValidationError as error:
            if hasattr(error, "message_dict"):
                for field, errors in error.message_dict.items():
                    target = field if field in form.fields else None
                    for message in errors:
                        form.add_error(target, message)
            else:
                form.add_error(None, error)
        except IntegrityError:
            form.add_error(
                None,
                "O cadastro entrou em conflito com outra operação. Nenhum item foi "
                "criado; revise os dados e tente novamente.",
            )
        else:
            messages.success(
                request,
                f"{len(result.units)} equipamento(s) criado(s) para {result.tool_model}.",
            )
            return redirect("catalog:equipment-list")

    return render(request, "catalog/assisted_registration.html", {"form": form})
