from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import OrganizationOnboardingForm, OrganizationSelectionForm
from .services import available_memberships, set_active_organization


@login_required
def workspace_home(request):
    if request.organization is None:
        if not available_memberships(request.user).exists():
            return redirect("workspace:onboarding")
        return redirect("workspace:select-organization")

    return render(
        request,
        "organizations/workspace_home.html",
        {
            "organization": request.organization,
            "establishments": request.organization.establishments.filter(active=True),
            "can_switch_organization": available_memberships(request.user).count() > 1,
        },
    )


@login_required
def onboarding(request):
    memberships = available_memberships(request.user)
    if memberships.exists():
        if request.organization is None:
            return redirect("workspace:select-organization")
        return redirect("workspace:home")

    form = OrganizationOnboardingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        organization = form.save(user=request.user)
        set_active_organization(request, organization)
        messages.success(request, "Sua locadora e a unidade principal foram criadas.")
        return redirect("workspace:home")

    return render(request, "organizations/onboarding.html", {"form": form})


@login_required
def select_organization(request):
    memberships = available_memberships(request.user)
    available = list(memberships[:2])
    if not available:
        return redirect("workspace:onboarding")
    if len(available) == 1:
        set_active_organization(request, available[0].organization)
        return redirect("workspace:home")

    form = OrganizationSelectionForm(
        request.POST or None,
        user=request.user,
        initial={"organization": request.organization},
    )
    if request.method == "POST" and form.is_valid():
        set_active_organization(request, form.cleaned_data["organization"])
        messages.success(request, "Locadora ativa alterada com segurança.")
        return redirect("workspace:home")

    return render(request, "organizations/select_organization.html", {"form": form})
