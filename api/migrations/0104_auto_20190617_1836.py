# Generated by Django 2.1.2 on 2019-06-17 18:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0103_auto_20190614_2253'),
    ]

    operations = [
        migrations.AddField(
            model_name='bookings',
            name='z_downloaded_pod_sog_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
