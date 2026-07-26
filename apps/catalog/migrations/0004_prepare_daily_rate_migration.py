from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_require_toolunit_establishment"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="toolmodel",
            name="non_negative_daily_rate",
        ),
        migrations.AlterField(
            model_name="toolmodel",
            name="daily_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.00"))
                ],
                verbose_name="valor da diária",
            ),
        ),
    ]
