from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_quotation_migration_is_additive_and_preserves_existing_domain_data():
    previous_targets = [
        ("catalog", "0006_alter_toolunit_options_assetcodesequence"),
        ("customers", "0001_initial"),
        ("organizations", "0002_establishment"),
        ("pricing", "0001_initial"),
        ("quotations", None),
    ]
    quotation_target = ("quotations", "0001_initial")

    executor = MigrationExecutor(connection)
    executor.migrate(previous_targets)
    previous_apps = executor.loader.project_state(previous_targets[:-1]).apps

    Organization = previous_apps.get_model("organizations", "Organization")
    Category = previous_apps.get_model("catalog", "Category")
    ToolModel = previous_apps.get_model("catalog", "ToolModel")
    Customer = previous_apps.get_model("customers", "Customer")
    PricingPolicy = previous_apps.get_model("pricing", "PricingPolicy")

    organization = Organization.objects.create(
        name="Locadora existente",
        slug="locadora-existente",
    )
    category = Category.objects.create(organization=organization, name="Furadeiras")
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name="Furadeira",
    )
    customer = Customer.objects.create(
        organization=organization,
        kind="INDIVIDUAL",
        name="Cliente existente",
        document="52998224725",
    )
    policy = PricingPolicy.objects.create(
        organization=organization,
        tool_model=tool_model,
        effective_from=date(2026, 1, 1),
        daily_rate=Decimal("60.00"),
        fixed_month_days=30,
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([quotation_target])
        current_apps = executor.loader.project_state([quotation_target]).apps
        MigratedCustomer = current_apps.get_model("customers", "Customer")
        MigratedPricingPolicy = current_apps.get_model("pricing", "PricingPolicy")
        Quotation = current_apps.get_model("quotations", "Quotation")
        QuotationItem = current_apps.get_model("quotations", "QuotationItem")

        assert MigratedCustomer.objects.get(pk=customer.pk).name == "Cliente existente"
        assert MigratedPricingPolicy.objects.get(pk=policy.pk).daily_rate == Decimal("60.00")
        assert not Quotation.objects.exists()
        assert not QuotationItem.objects.exists()
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
