# Generated by Django 2.1.2 on 2019-02-22 18:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_dme_attachments'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='bok_1_headers',
            name='b_021_pu_avail_from_date',
        ),
        migrations.AlterField(
            model_name='bok_1_headers',
            name='b_059_b_del_address_postalcode',
            field=models.CharField(blank=True, default='', max_length=16, null=True, verbose_name='Address Postal Code'),
        ),
    ]
