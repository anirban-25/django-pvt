# Generated by Django 2.1.2 on 2020-04-17 14:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0195_auto_20200417_0329"),
    ]

    operations = [
        migrations.AddField(
            model_name="fp_service_etds",
            name="service_cutoff_time",
            field=models.TimeField(blank=True, default=None, null=True),
        ),
    ]
