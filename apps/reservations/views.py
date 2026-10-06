from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.quotations.models import Quotation

from .forms import AvailabilityForm, ReservationConfirmationForm
from .models import Reservation
from .services import available_units, cancel_reservation, confirm_reservation


def _active_organization_or_redirect(request):
    if request.organization is None:
        return None, redirect("workspace:home")
    return request.organization, None


@login_required
def reservation_list(request):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    reservations = (
        Reservation.objects.filter(organization=organization)
        .select_related("quotation__customer", "establishment")
        .prefetch_related("allocations")
    )
    return render(
        request,
        "reservations/reservation_list.html",
        {"reservations": reservations},
    )


@login_required
def availability_lookup(request):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    form = AvailabilityForm(
        request.GET or None,
        organization=organization,
    )
    units = None
    if form.is_bound and form.is_valid():
        units = available_units(
            organization=organization,
            establishment=form.cleaned_data["establishment"],
            tool_model=form.cleaned_data["tool_model"],
            starts_at=form.cleaned_data["starts_at"],
            ends_at=form.cleaned_data["ends_at"],
        )
    return render(
        request,
        "reservations/availability_lookup.html",
        {"form": form, "units": units},
    )


@login_required
def reservation_create(request, quotation_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    quotation = get_object_or_404(
        Quotation.objects.select_related("customer")
        .prefetch_related("items__tool_model"),
        pk=quotation_id,
        organization=organization,
    )
    try:
        existing_reservation = quotation.reservation
    except Reservation.DoesNotExist:
        existing_reservation = None
    if existing_reservation is not None:
        return redirect("reservations:detail", reservation_id=existing_reservation.pk)
    if quotation.status != Quotation.Status.SENT:
        messages.error(request, "Somente um orçamento enviado pode gerar uma reserva.")
        return redirect("quotations:detail", quotation_id=quotation.pk)
    form = ReservationConfirmationForm(
        request.POST or None,
        organization=organization,
        quotation=quotation,
    )
    if request.method == "POST" and form.is_valid():
        try:
            reservation, _ = confirm_reservation(
                organization=organization,
                quotation=quotation,
                establishment=form.cleaned_data["establishment"],
            )
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
        else:
            messages.success(
                request,
                f"{reservation.display_code} confirmada com equipamentos específicos.",
            )
            return redirect("reservations:detail", reservation_id=reservation.pk)
    return render(
        request,
        "reservations/reservation_confirm.html",
        {"form": form, "quotation": quotation},
    )


@login_required
def reservation_detail(request, reservation_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    reservation = get_object_or_404(
        Reservation.objects.select_related(
            "quotation__customer",
            "establishment",
            "contract",
        ).prefetch_related(
            "allocations__tool_unit__tool_model",
            "allocations__quotation_item",
            "allocations__quotation_item_offering",
            "offerings__quotation_item_offering",
        ),
        pk=reservation_id,
        organization=organization,
    )
    return render(
        request,
        "reservations/reservation_detail.html",
        {
            "reservation": reservation,
            "contract": getattr(reservation, "contract", None),
        },
    )


@login_required
@require_POST
def reservation_cancel(request, reservation_id):
    organization, response = _active_organization_or_redirect(request)
    if response:
        return response
    reservation = get_object_or_404(
        Reservation,
        pk=reservation_id,
        organization=organization,
    )
    try:
        cancelled = cancel_reservation(
            organization=organization,
            reservation=reservation,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"{cancelled.display_code} cancelada e período liberado.")
    return redirect("reservations:detail", reservation_id=reservation.pk)
