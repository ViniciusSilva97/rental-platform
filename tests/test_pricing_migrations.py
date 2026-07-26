from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_daily_rates_are_migrated_to_versioned_policies():
    catalog_before_pricing = ("catalog", "0004_prepare_daily_rate_migration")
    pricing_target = ("pricing", "0001_initial")

    executor = MigrationExecutor(connection)
    executor.migrate([catalog_before_pricing, ("pricing", None)])
    previous_apps = executor.loader.project_state([catalog_before_pricing]).apps

    Organization = previous_apps.get_model("organizations", "Organization")
    Category = previous_apps.get_model("catalog", "Category")
    ToolModel = previous_apps.get_model("catalog", "ToolModel")

    organization = Organization.objects.create(
        name="Locadora Exemplo",
        slug="locadora-exemplo",
    )
    category = Category.objects.create(
        organization=organization,
        name="Furadeiras",
    )
    tool_model = ToolModel.objects.create(
        organization=organization,
        category=category,
        name="Furadeira",
        daily_rate=Decimal("45.00"),
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([pricing_target])
        pricing_apps = executor.loader.project_state([pricing_target]).apps
        PricingPolicy = pricing_apps.get_model("pricing", "PricingPolicy")

        policy = PricingPolicy.objects.get(tool_model_id=tool_model.pk)

        assert policy.organization_id == organization.pk
        assert policy.daily_rate == Decimal("45.00")
        assert policy.effective_from == date.today()
        assert policy.hourly_rate is None
        assert policy.monthly_rate is None

        PricingPolicy.objects.create(
            organization_id=organization.pk,
            tool_model_id=tool_model.pk,
            effective_from=policy.effective_from + timedelta(days=1),
            daily_rate=Decimal("50.00"),
            fixed_month_days=30,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([catalog_before_pricing, ("pricing", None)])
        restored_apps = executor.loader.project_state([catalog_before_pricing]).apps
        RestoredToolModel = restored_apps.get_model("catalog", "ToolModel")

        restored_tool_model = RestoredToolModel.objects.get(pk=tool_model.pk)
        assert restored_tool_model.daily_rate == Decimal("50.00")
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
