# Generated by Django 2.1.2 on 2019-05-21 21:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0094_auto_20190521_1747'),
    ]

    operations = [
        migrations.RenameField(
            model_name='bookings',
            old_name='dev_notes',
            new_name='z_status_process_notes',
        ),
    ]
