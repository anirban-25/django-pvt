# Generated by Django 2.1.2 on 2022-12-27 06:25

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0336_auto_20221121_0548"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dme_clients",
            name="augment_pu_available_time",
            field=models.TimeField(default=None, null=True),
        ),
        migrations.AlterField(
            model_name="dme_clients",
            name="augment_pu_by_time",
            field=models.TimeField(default=None, null=True),
        ),
        migrations.AlterField(
            model_name="dme_clients",
            name="client_customer_mark_up",
            field=models.FloatField(default=0, null=True),
        ),
        migrations.AlterField(
            model_name="dme_clients",
            name="client_mark_up_percent",
            field=models.FloatField(default=0, null=True),
        ),
        migrations.AlterField(
            model_name="dme_clients",
            name="client_min_markup_startingcostvalue",
            field=models.FloatField(default=0, null=True),
        ),
        migrations.AlterField(
            model_name="dme_clients",
            name="client_min_markup_value",
            field=models.FloatField(default=0, null=True),
        ),
        migrations.AlterField(
            model_name="dme_clients",
            name="gap_percent",
            field=models.FloatField(default=0, null=True),
        ),
    ]
