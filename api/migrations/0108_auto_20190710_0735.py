# Generated by Django 2.1.2 on 2019-07-10 07:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("api", "0107_auto_20190704_1544")]

    operations = [
        migrations.AddField(
            model_name="bookings",
            name="inv_billing_status",
            field=models.CharField(blank=True, default="", max_length=32, null=True),
        ),
        migrations.AddField(
            model_name="bookings",
            name="inv_billing_status_note",
            field=models.CharField(blank=True, default="", max_length=255, null=True),
        ),
    ]
