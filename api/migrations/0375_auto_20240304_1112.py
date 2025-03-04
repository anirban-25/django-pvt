# Generated by Django 2.1.2 on 2024-03-04 11:12

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0374_merge_20240303_2354"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookings",
            name="quote_id",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="quoted_quote",
                to="api.API_booking_quotes",
            ),
        ),
        migrations.AlterField(
            model_name="bookings",
            name="api_booking_quote",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="booked_quote",
                to="api.API_booking_quotes",
            ),
        ),
    ]
