# Generated by Django 2.1.2 on 2024-02-14 04:13

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0363_auto_20240124_1011"),
    ]

    operations = [
        migrations.AddField(
            model_name="api_booking_quotes",
            name="delivery_timestamp",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="api_booking_quotes",
            name="notes",
            field=models.CharField(default=None, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="api_booking_quotes",
            name="pickup_timestamp",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
