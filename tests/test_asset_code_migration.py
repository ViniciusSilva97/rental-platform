import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_asset_code_sequence_starts_after_existing_eq_codes():
    previous_target = ("catalog", "0005_remove_toolmodel_daily_rate")
    current_target = (
        "catalog",
        "0006_alter_toolunit_options_assetcodesequence",
    )

    executor = MigrationExecutor(connection)
    executor.migrate([previous_target])
    previous_apps = executor.loader.project_state([previous_target]).apps

    Organization = previous_apps.get_model("organizations", "Organization")
    Establishment = previous_apps.get_model("organizations", "Establishment")
    Category = previous_apps.get_model("catalog", "Category")
    ToolModel = previous_apps.get_model("catalog", "ToolModel")
    ToolUnit = previous_apps.get_model("catalog", "ToolUnit")

    organizations = []
    for index, codes in enumerate(
        (("EQ-000005", "LEGACY-900"), ("EQ-000099",)),
        start=1,
    ):
        organization = Organization.objects.create(
            name=f"Locadora {index}",
            slug=f"locadora-{index}",
        )
        organizations.append(organization)
        establishment = Establishment.objects.create(
            organization=organization,
            name="Matriz",
        )
        category = Category.objects.create(
            organization=organization,
            name="Furadeiras",
        )
        tool_model = ToolModel.objects.create(
            organization=organization,
            category=category,
            name="Furadeira",
        )
        for code in codes:
            ToolUnit.objects.create(
                organization=organization,
                establishment=establishment,
                tool_model=tool_model,
                asset_code=code,
            )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([current_target])
        current_apps = executor.loader.project_state([current_target]).apps
        AssetCodeSequence = current_apps.get_model("catalog", "AssetCodeSequence")

        assert AssetCodeSequence.objects.get(
            organization_id=organizations[0].pk
        ).next_value == 6
        assert AssetCodeSequence.objects.get(
            organization_id=organizations[1].pk
        ).next_value == 100
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
