from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_tool_units_are_backfilled_before_establishment_becomes_required():
    previous_target = (
        "catalog",
        "0002_toolunit_establishment_alter_toolmodel_daily_rate_and_more",
    )
    current_target = ("catalog", "0003_require_toolunit_establishment")

    executor = MigrationExecutor(connection)
    executor.migrate([previous_target])
    previous_apps = executor.loader.project_state([previous_target]).apps

    Organization = previous_apps.get_model("organizations", "Organization")
    Establishment = previous_apps.get_model("organizations", "Establishment")
    Category = previous_apps.get_model("catalog", "Category")
    ToolModel = previous_apps.get_model("catalog", "ToolModel")
    ToolUnit = previous_apps.get_model("catalog", "ToolUnit")

    organization_without_establishment = Organization.objects.create(
        name="Locadora sem matriz",
        slug="locadora-sem-matriz",
    )
    organization_with_establishment = Organization.objects.create(
        name="Locadora com matriz",
        slug="locadora-com-matriz",
    )
    existing_headquarters = Establishment.objects.create(
        organization=organization_with_establishment,
        name="Matriz existente",
        kind="HEADQUARTERS",
    )

    created_units = []
    for index, organization in enumerate(
        (organization_without_establishment, organization_with_establishment),
        start=1,
    ):
        category = Category.objects.create(organization=organization, name="Furadeiras")
        tool_model = ToolModel.objects.create(
            organization=organization,
            category=category,
            name="Furadeira",
            daily_rate=Decimal("20.00"),
        )
        created_units.append(
            ToolUnit.objects.create(
                organization=organization,
                tool_model=tool_model,
                asset_code=f"FUR-{index:03}",
                establishment=None,
            )
        )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([current_target])
        current_apps = executor.loader.project_state([current_target]).apps
        MigratedEstablishment = current_apps.get_model("organizations", "Establishment")
        MigratedToolUnit = current_apps.get_model("catalog", "ToolUnit")

        generated_headquarters = MigratedEstablishment.objects.get(
            organization_id=organization_without_establishment.pk
        )
        migrated_generated_unit = MigratedToolUnit.objects.get(pk=created_units[0].pk)
        migrated_existing_unit = MigratedToolUnit.objects.get(pk=created_units[1].pk)

        assert generated_headquarters.name == "Matriz"
        assert generated_headquarters.kind == "HEADQUARTERS"
        assert migrated_generated_unit.establishment_id == generated_headquarters.pk
        assert migrated_existing_unit.establishment_id == existing_headquarters.pk
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
