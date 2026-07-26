from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_prepare_daily_rate_migration"),
        ("pricing", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="toolmodel",
            name="daily_rate",
        ),
    ]
