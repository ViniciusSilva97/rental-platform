from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.text import slugify

from .models import Establishment, Membership, Organization

ACTIVE_ORGANIZATION_SESSION_KEY = "active_organization_id"


def available_memberships(user):
    if not user.is_authenticated:
        return Membership.objects.none()
    return (
        Membership.objects.filter(
            user=user,
            active=True,
            organization__active=True,
        )
        .select_related("organization")
        .order_by("organization__name")
    )


def clear_active_organization(request) -> None:
    request.session.pop(ACTIVE_ORGANIZATION_SESSION_KEY, None)


def resolve_active_organization(request):
    if not request.user.is_authenticated:
        return None

    memberships = available_memberships(request.user)
    selected_id = request.session.get(ACTIVE_ORGANIZATION_SESSION_KEY)
    if selected_id:
        try:
            membership = memberships.filter(organization_id=selected_id).first()
        except (TypeError, ValueError, ValidationError):
            membership = None
        if membership:
            return membership.organization
        clear_active_organization(request)

    available = list(memberships[:2])
    if len(available) == 1:
        organization = available[0].organization
        request.session[ACTIVE_ORGANIZATION_SESSION_KEY] = str(organization.pk)
        return organization
    return None


def set_active_organization(request, organization: Organization) -> Organization:
    allowed = available_memberships(request.user).filter(organization=organization).exists()
    if not allowed:
        raise PermissionDenied("Você não possui acesso ativo a esta locadora.")
    request.session[ACTIVE_ORGANIZATION_SESSION_KEY] = str(organization.pk)
    return organization


def _available_slug(name: str) -> str:
    base = slugify(name)[:42] or "locadora"
    candidate = base
    suffix = 2
    while Organization.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@transaction.atomic
def create_organization_for_owner(
    *,
    user,
    name: str,
    headquarters_name: str = "Matriz",
    cnpj: str = "",
) -> Organization:
    name = name.strip()
    if not name:
        raise ValidationError({"name": "Informe o nome da locadora."})

    organization = Organization(
        name=name,
        slug=_available_slug(name),
    )
    organization.full_clean()
    organization.save()
    Establishment.objects.create(
        organization=organization,
        name=headquarters_name.strip() or "Matriz",
        cnpj=cnpj,
        kind=Establishment.Kind.HEADQUARTERS,
    )
    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.Role.OWNER,
    )
    return organization
