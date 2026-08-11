import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory
from django.urls import reverse

from apps.organizations.models import Establishment, Membership, Organization
from apps.organizations.services import (
    ACTIVE_ORGANIZATION_SESSION_KEY,
    available_memberships,
    create_organization_for_owner,
    set_active_organization,
)

User = get_user_model()


def create_user(username="vinicius"):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test-password-123",
    )


def add_membership(*, user, organization, active=True):
    return Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.OWNER,
        active=active,
    )


@pytest.mark.django_db
def test_workspace_requires_authentication(client):
    response = client.get(reverse("workspace:home"))

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={reverse('workspace:home')}"


@pytest.mark.django_db
def test_authenticated_user_without_organization_is_sent_to_onboarding(client):
    user = create_user()
    client.force_login(user)

    response = client.get(reverse("workspace:home"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:onboarding")


@pytest.mark.django_db
def test_onboarding_creates_company_headquarters_and_owner_atomically(client):
    user = create_user()
    client.force_login(user)

    response = client.post(
        reverse("workspace:onboarding"),
        data={
            "name": "Locadora Exemplo",
            "headquarters_name": "Unidade Principal",
            "cnpj": "12.abc.345/01de-35",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("workspace:home")

    organization = Organization.objects.get()
    establishment = Establishment.objects.get()
    membership = Membership.objects.get()
    assert organization.name == "Locadora Exemplo"
    assert establishment.organization == organization
    assert establishment.name == "Unidade Principal"
    assert establishment.kind == Establishment.Kind.HEADQUARTERS
    assert establishment.cnpj == "12ABC34501DE35"
    assert membership.organization == organization
    assert membership.user == user
    assert membership.role == Membership.Role.OWNER
    assert client.session[ACTIVE_ORGANIZATION_SESSION_KEY] == str(organization.pk)


@pytest.mark.django_db
def test_onboarding_rolls_back_when_headquarters_is_invalid():
    user = create_user()

    with pytest.raises(ValidationError):
        create_organization_for_owner(
            user=user,
            name="Locadora Inválida",
            headquarters_name="Matriz",
            cnpj="CNPJ inválido",
        )

    assert not Organization.objects.exists()
    assert not Establishment.objects.exists()
    assert not Membership.objects.exists()


@pytest.mark.django_db
def test_onboarding_generates_distinct_internal_slugs_for_equal_names():
    first_user = create_user("first")
    second_user = create_user("second")

    first = create_organization_for_owner(user=first_user, name="Locadora Exemplo")
    second = create_organization_for_owner(user=second_user, name="Locadora Exemplo")

    assert first.slug == "locadora-exemplo"
    assert second.slug == "locadora-exemplo-2"


@pytest.mark.django_db
def test_onboarding_service_rejects_blank_company_name():
    user = create_user()

    with pytest.raises(ValidationError) as error:
        create_organization_for_owner(user=user, name="   ")

    assert "name" in error.value.message_dict
    assert not Organization.objects.exists()


@pytest.mark.django_db
def test_anonymous_user_has_no_available_memberships():
    assert not available_memberships(AnonymousUser()).exists()


@pytest.mark.django_db
def test_single_membership_is_selected_automatically(client):
    user = create_user()
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    Establishment.objects.create(organization=organization, name="Matriz")
    add_membership(user=user, organization=organization)
    client.force_login(user)

    response = client.get(reverse("workspace:home"))

    assert response.status_code == 200
    assert "Locadora Exemplo" in response.content.decode()
    assert client.session[ACTIVE_ORGANIZATION_SESSION_KEY] == str(organization.pk)


@pytest.mark.django_db
def test_multiple_memberships_require_explicit_selection(client):
    user = create_user()
    first = Organization.objects.create(name="Locadora A", slug="locadora-a")
    second = Organization.objects.create(name="Locadora B", slug="locadora-b")
    add_membership(user=user, organization=first)
    add_membership(user=user, organization=second)
    client.force_login(user)

    response = client.get(reverse("workspace:home"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:select-organization")
    assert ACTIVE_ORGANIZATION_SESSION_KEY not in client.session

    selection = client.post(
        reverse("workspace:select-organization"),
        data={"organization": second.pk},
    )

    assert selection.status_code == 302
    assert selection.url == reverse("workspace:home")
    assert client.session[ACTIVE_ORGANIZATION_SESSION_KEY] == str(second.pk)

    dashboard = client.get(reverse("workspace:home"))
    assert dashboard.status_code == 200
    assert "Locadora B" in dashboard.content.decode()


@pytest.mark.django_db
def test_onboarding_redirects_existing_multi_company_user_to_selection(client):
    user = create_user()
    first = Organization.objects.create(name="Locadora A", slug="locadora-a")
    second = Organization.objects.create(name="Locadora B", slug="locadora-b")
    add_membership(user=user, organization=first)
    add_membership(user=user, organization=second)
    client.force_login(user)

    response = client.get(reverse("workspace:onboarding"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:select-organization")


@pytest.mark.django_db
def test_onboarding_redirects_existing_single_company_user_to_workspace(client):
    user = create_user()
    organization = Organization.objects.create(name="Locadora A", slug="locadora-a")
    add_membership(user=user, organization=organization)
    client.force_login(user)

    response = client.get(reverse("workspace:onboarding"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:home")


@pytest.mark.django_db
def test_invalid_onboarding_form_is_presented_without_partial_records(client):
    user = create_user()
    client.force_login(user)

    response = client.post(
        reverse("workspace:onboarding"),
        data={"name": "", "headquarters_name": "Matriz", "cnpj": "inválido"},
    )

    assert response.status_code == 200
    assert "Este campo é obrigatório" in response.content.decode()
    assert not Organization.objects.exists()


@pytest.mark.django_db
def test_selection_rejects_organization_without_membership(client):
    user = create_user()
    allowed_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    allowed_b = Organization.objects.create(name="Locadora B", slug="locadora-b")
    forbidden = Organization.objects.create(name="Locadora C", slug="locadora-c")
    add_membership(user=user, organization=allowed_a)
    add_membership(user=user, organization=allowed_b)
    client.force_login(user)

    options = client.get(reverse("workspace:select-organization"))
    content = options.content.decode()
    assert "Locadora A" in content
    assert "Locadora B" in content
    assert "Locadora C" not in content

    response = client.post(
        reverse("workspace:select-organization"),
        data={"organization": forbidden.pk},
    )

    assert response.status_code == 200
    assert "Faça uma escolha válida" in response.content.decode()
    assert ACTIVE_ORGANIZATION_SESSION_KEY not in client.session


@pytest.mark.django_db
def test_selection_without_membership_returns_to_onboarding(client):
    user = create_user()
    client.force_login(user)

    response = client.get(reverse("workspace:select-organization"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:onboarding")


@pytest.mark.django_db
def test_selection_with_one_membership_returns_to_workspace(client):
    user = create_user()
    organization = Organization.objects.create(name="Locadora A", slug="locadora-a")
    add_membership(user=user, organization=organization)
    client.force_login(user)

    response = client.get(reverse("workspace:select-organization"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:home")
    assert client.session[ACTIVE_ORGANIZATION_SESSION_KEY] == str(organization.pk)


@pytest.mark.django_db
def test_tampered_session_never_grants_access_to_another_organization(client):
    user = create_user()
    allowed = Organization.objects.create(name="Locadora Permitida", slug="permitida")
    forbidden = Organization.objects.create(name="Locadora Proibida", slug="proibida")
    add_membership(user=user, organization=allowed)
    client.force_login(user)
    session = client.session
    session[ACTIVE_ORGANIZATION_SESSION_KEY] = str(forbidden.pk)
    session.save()

    response = client.get(reverse("workspace:home"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Locadora Permitida" in content
    assert "Locadora Proibida" not in content
    assert client.session[ACTIVE_ORGANIZATION_SESSION_KEY] == str(allowed.pk)


@pytest.mark.django_db
def test_invalid_session_identifier_is_cleared_safely(client):
    user = create_user()
    first = Organization.objects.create(name="Locadora A", slug="locadora-a")
    second = Organization.objects.create(name="Locadora B", slug="locadora-b")
    add_membership(user=user, organization=first)
    add_membership(user=user, organization=second)
    client.force_login(user)
    session = client.session
    session[ACTIVE_ORGANIZATION_SESSION_KEY] = "identificador-manipulado"
    session.save()

    response = client.get(reverse("workspace:home"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:select-organization")
    assert ACTIVE_ORGANIZATION_SESSION_KEY not in client.session


@pytest.mark.django_db
def test_inactive_memberships_are_ignored(client):
    user = create_user()
    organization = Organization.objects.create(name="Locadora Inativa", slug="inativa")
    add_membership(user=user, organization=organization, active=False)
    client.force_login(user)

    response = client.get(reverse("workspace:home"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:onboarding")


@pytest.mark.django_db
def test_inactive_organizations_are_ignored(client):
    user = create_user()
    organization = Organization.objects.create(
        name="Locadora Inativa",
        slug="inativa",
        active=False,
    )
    add_membership(user=user, organization=organization)
    client.force_login(user)

    response = client.get(reverse("workspace:home"))

    assert response.status_code == 302
    assert response.url == reverse("workspace:onboarding")


@pytest.mark.django_db
def test_service_rejects_setting_organization_without_membership():
    user = create_user()
    organization = Organization.objects.create(name="Locadora Proibida", slug="proibida")
    request = RequestFactory().get("/app/")
    request.user = user

    with pytest.raises(PermissionDenied):
        set_active_organization(request, organization)


@pytest.mark.django_db
def test_login_redirects_to_operational_workspace(client):
    user = create_user()
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    add_membership(user=user, organization=organization)

    response = client.post(
        reverse("login"),
        data={"username": user.username, "password": "test-password-123"},
    )

    assert response.status_code == 302
    assert response.url == reverse("workspace:home")
