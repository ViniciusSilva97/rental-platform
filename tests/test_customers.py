import pytest
from django.core.exceptions import ValidationError
from django.forms import modelform_factory
from django.forms.models import inlineformset_factory

from apps.customers.admin import CustomerAddressInlineFormSet
from apps.customers.models import Customer, CustomerAddress
from apps.organizations.models import Organization


@pytest.mark.django_db
def test_individual_customer_normalizes_and_formats_cpf():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")

    customer = Customer.objects.create(
        organization=organization,
        kind=Customer.Kind.INDIVIDUAL,
        name="Maria da Silva",
        document="529.982.247-25",
    )

    assert customer.document == "52998224725"
    assert customer.formatted_document == "529.982.247-25"
    assert str(customer) == "Maria da Silva"


@pytest.mark.django_db
def test_company_customer_accepts_alphanumeric_cnpj():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")

    customer = Customer.objects.create(
        organization=organization,
        kind=Customer.Kind.COMPANY,
        name="Construtora Exemplo Ltda.",
        trade_name="Construtora Exemplo",
        document="12.abc.345/01de-35",
    )

    assert customer.document == "12ABC34501DE35"
    assert customer.formatted_document == "12.ABC.345/01DE-35"


@pytest.mark.django_db
def test_customer_form_accepts_masked_document():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    customer_form = modelform_factory(
        Customer,
        fields=(
            "organization",
            "kind",
            "name",
            "trade_name",
            "document",
            "email",
            "phone",
            "notes",
            "active",
        ),
    )
    form = customer_form(
        data={
            "organization": organization.pk,
            "kind": Customer.Kind.COMPANY,
            "name": "Construtora Exemplo Ltda.",
            "trade_name": "Construtora Exemplo",
            "document": "12.ABC.345/01DE-35",
            "email": "",
            "phone": "",
            "notes": "",
            "active": True,
        }
    )

    assert form.is_valid(), form.errors
    customer = form.save()
    assert customer.document == "12ABC34501DE35"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kind,document",
    [
        (Customer.Kind.INDIVIDUAL, "12.345.678/0001-95"),
        (Customer.Kind.COMPANY, "529.982.247-25"),
    ],
)
def test_customer_rejects_document_that_does_not_match_kind(kind, document):
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")

    with pytest.raises(ValidationError) as error:
        Customer.objects.create(
            organization=organization,
            kind=kind,
            name="Cliente inválido",
            document=document,
        )

    assert "document" in error.value.message_dict


@pytest.mark.django_db
def test_customer_document_is_unique_inside_organization():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    Customer.objects.create(
        organization=organization,
        name="Maria da Silva",
        document="529.982.247-25",
    )

    with pytest.raises(ValidationError):
        Customer.objects.create(
            organization=organization,
            name="Cadastro duplicado",
            document="52998224725",
        )


@pytest.mark.django_db
def test_same_customer_document_is_allowed_in_different_organizations():
    organization_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    organization_b = Organization.objects.create(name="Locadora B", slug="locadora-b")

    Customer.objects.create(
        organization=organization_a,
        name="Maria da Silva",
        document="529.982.247-25",
    )
    customer_b = Customer.objects.create(
        organization=organization_b,
        name="Maria da Silva",
        document="529.982.247-25",
    )

    assert customer_b.document == "52998224725"


@pytest.mark.django_db
def test_customer_address_normalizes_location_fields():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    customer = Customer.objects.create(
        organization=organization,
        name="Maria da Silva",
        document="529.982.247-25",
    )

    address = CustomerAddress.objects.create(
        organization=organization,
        customer=customer,
        postal_code="01310-100",
        street="Avenida Paulista",
        number="1000",
        district="Bela Vista",
        city="São Paulo",
        state="sp",
        country="br",
    )

    assert address.postal_code == "01310100"
    assert address.formatted_postal_code == "01310-100"
    assert address.state == "SP"
    assert address.country == "BR"
    assert str(address) == "Avenida Paulista, 1000 — São Paulo/SP"


@pytest.mark.django_db
def test_customer_address_rejects_customer_from_another_organization():
    organization_a = Organization.objects.create(name="Locadora A", slug="locadora-a")
    organization_b = Organization.objects.create(name="Locadora B", slug="locadora-b")
    customer_a = Customer.objects.create(
        organization=organization_a,
        name="Maria da Silva",
        document="529.982.247-25",
    )

    with pytest.raises(ValidationError) as error:
        CustomerAddress.objects.create(
            organization=organization_b,
            customer=customer_a,
            postal_code="01310-100",
            street="Avenida Paulista",
            number="1000",
            district="Bela Vista",
            city="São Paulo",
            state="SP",
        )

    assert "customer" in error.value.message_dict


@pytest.mark.django_db
def test_customer_has_only_one_active_main_address():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    customer = Customer.objects.create(
        organization=organization,
        name="Maria da Silva",
        document="529.982.247-25",
    )
    address_data = {
        "organization": organization,
        "customer": customer,
        "postal_code": "01310-100",
        "street": "Avenida Paulista",
        "number": "1000",
        "district": "Bela Vista",
        "city": "São Paulo",
        "state": "SP",
    }
    CustomerAddress.objects.create(**address_data)

    with pytest.raises(ValidationError):
        CustomerAddress.objects.create(**address_data)


@pytest.mark.django_db
def test_customer_address_inline_inherits_customer_organization():
    organization = Organization.objects.create(name="Locadora Exemplo", slug="locadora-exemplo")
    customer = Customer(
        organization=organization,
        name="Maria da Silva",
        document="529.982.247-25",
    )
    address_formset = inlineformset_factory(
        Customer,
        CustomerAddress,
        formset=CustomerAddressInlineFormSet,
        fields=(
            "kind",
            "postal_code",
            "street",
            "number",
            "complement",
            "district",
            "city",
            "state",
            "active",
        ),
        extra=1,
    )
    formset = address_formset(
        data={
            "addresses-TOTAL_FORMS": "1",
            "addresses-INITIAL_FORMS": "0",
            "addresses-MIN_NUM_FORMS": "0",
            "addresses-MAX_NUM_FORMS": "1000",
            "addresses-0-kind": CustomerAddress.Kind.MAIN,
            "addresses-0-postal_code": "01310-100",
            "addresses-0-street": "Avenida Paulista",
            "addresses-0-number": "1000",
            "addresses-0-complement": "",
            "addresses-0-district": "Bela Vista",
            "addresses-0-city": "São Paulo",
            "addresses-0-state": "SP",
            "addresses-0-active": "on",
        },
        instance=customer,
        prefix="addresses",
    )

    assert formset.is_valid(), formset.errors
    customer.save()
    address = formset.save()[0]
    assert address.organization == organization
    assert address.customer == customer
