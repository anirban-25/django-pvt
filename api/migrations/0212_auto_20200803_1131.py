# Generated by Django 2.1.2 on 2020-08-03 11:31

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0211_auto_20200728_0945"),
    ]

    operations = [
        migrations.RemoveField(model_name="bookings", name="dme_status_history_notes",),
    ]
