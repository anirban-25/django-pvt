# Generated by Django 2.1.2 on 2022-06-27 02:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0321_auto_20220615_0111"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookings",
            name="packed_status",
            field=models.CharField(
                choices=[
                    ("original", "original"),
                    ("auto", "auto"),
                    ("manual", "manual"),
                    ("scanned", "scanned"),
                ],
                default=None,
                max_length=16,
                null=True,
            ),
        ),
    ]
