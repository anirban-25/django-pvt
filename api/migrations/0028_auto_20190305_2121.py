# Generated by Django 2.1.2 on 2019-03-05 21:21

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_auto_20190305_0001'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking_status_history',
            name='event_time_stamp',
            field=models.DateTimeField(blank=True, default=datetime.datetime.now, verbose_name='Event Timestamp'),
        ),
        migrations.AddField(
            model_name='bookings',
            name='z_pod_signed_url',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
    ]
