import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_reservation_migration_is_additive_and_installs_postgresql_exclusion():
    previous_targets = [
        ("catalog", "0006_alter_toolunit_options_assetcodesequence"),
        ("organizations", "0002_establishment"),
        ("quotations", "0001_initial"),
        ("reservations", None),
    ]
    target = ("reservations", "0001_initial")

    executor = MigrationExecutor(connection)
    executor.migrate(previous_targets)
    previous_apps = executor.loader.project_state(previous_targets[:-1]).apps

    Organization = previous_apps.get_model("organizations", "Organization")
    Establishment = previous_apps.get_model("organizations", "Establishment")
    organization = Organization.objects.create(
        name="Locadora existente",
        slug="locadora-existente-reservas",
    )
    establishment = Establishment.objects.create(
        organization=organization,
        name="Matriz existente",
        kind="HEADQUARTERS",
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        current_apps = executor.loader.project_state([target]).apps
        MigratedOrganization = current_apps.get_model("organizations", "Organization")
        MigratedEstablishment = current_apps.get_model("organizations", "Establishment")
        Reservation = current_apps.get_model("reservations", "Reservation")
        ReservationAllocation = current_apps.get_model(
            "reservations",
            "ReservationAllocation",
        )

        assert MigratedOrganization.objects.get(pk=organization.pk).name == "Locadora existente"
        assert MigratedEstablishment.objects.get(pk=establishment.pk).name == "Matriz existente"
        assert not Reservation.objects.exists()
        assert not ReservationAllocation.objects.exists()

        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    ["prevent_overlapping_active_reservations"],
                )
                assert cursor.fetchone() == (1,)
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
