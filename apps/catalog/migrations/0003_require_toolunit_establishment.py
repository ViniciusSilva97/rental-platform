import django.db.models.deletion
from django.db import migrations, models


def assign_units_to_establishments(apps, schema_editor):
    Establishment = apps.get_model("organizations", "Establishment")
    ToolUnit = apps.get_model("catalog", "ToolUnit")

    organization_ids = (
        ToolUnit.objects.filter(establishment__isnull=True)
        .values_list("organization_id", flat=True)
        .distinct()
    )

    for organization_id in organization_ids.iterator():
        establishment = (
            Establishment.objects.filter(
                organization_id=organization_id,
                kind="HEADQUARTERS",
                active=True,
            )
            .order_by("created_at")
            .first()
        )
        if establishment is None:
            establishment = (
                Establishment.objects.filter(organization_id=organization_id)
                .order_by("created_at")
                .first()
            )
        if establishment is None:
            establishment = Establishment.objects.create(
                organization_id=organization_id,
                name="Matriz",
                kind="HEADQUARTERS",
                active=True,
            )

        ToolUnit.objects.filter(
            organization_id=organization_id,
            establishment__isnull=True,
        ).update(establishment_id=establishment.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_toolunit_establishment_alter_toolmodel_daily_rate_and_more"),
        ("organizations", "0002_establishment"),
    ]

    operations = [
        migrations.RunPython(
            assign_units_to_establishments,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="toolunit",
            name="establishment",
            field=models.ForeignKey(
                help_text="Estabelecimento responsável pela unidade física.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tool_units",
                to="organizations.establishment",
            ),
        ),
    ]
