import pytest
from django.core.exceptions import ValidationError
from django.forms import modelform_factory

from apps.organizations.models import Establishment, Organization


@pytest.mark.django_db
def test_establishment_normalizes_and_displays_alphanumeric_cnpj():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")

    establishment = Establishment.objects.create(
        organization=organization,
        name="Unidade Centro",
        cnpj="12.abc.345/01de-35",
    )

    assert establishment.cnpj == "12ABC34501DE35"
    assert establishment.formatted_cnpj == "12.ABC.345/01DE-35"
    assert establishment.kind == Establishment.Kind.HEADQUARTERS


@pytest.mark.django_db
def test_only_one_active_headquarters_per_organization():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    Establishment.objects.create(organization=organization, name="Matriz")

    with pytest.raises(ValidationError):
        Establishment.objects.create(organization=organization, name="Outra matriz")


@pytest.mark.django_db
def test_establishment_form_accepts_masked_cnpj():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    establishment_form = modelform_factory(
        Establishment,
        fields=("organization", "name", "cnpj", "kind", "active"),
    )

    form = establishment_form(
        data={
            "organization": organization.pk,
            "name": "Unidade Centro",
            "cnpj": "12.ABC.345/01DE-35",
            "kind": Establishment.Kind.HEADQUARTERS,
            "active": True,
        }
    )

    assert form.is_valid(), form.errors
    establishment = form.save()
    assert establishment.cnpj == "12ABC34501DE35"
