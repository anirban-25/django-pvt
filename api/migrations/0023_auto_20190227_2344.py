# Generated by Django 2.1.2 on 2019-02-27 23:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_booking_lines_client_item_reference'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bookings',
            name='pu_addressed_Saved',
            field=models.IntegerField(blank=True, default=0, null=True, verbose_name='PU Addressed Saved'),
        ),
        migrations.AlterField(
            model_name='bookings',
            name='z_API_Issue',
            field=models.IntegerField(blank=True, default=0, null=True, verbose_name='Api Issue'),
        ),
    ]
