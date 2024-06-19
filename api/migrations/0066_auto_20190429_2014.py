# Generated by Django 2.1.2 on 2019-04-29 20:14

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0065_auto_20190429_2011'),
    ]

    operations = [
        migrations.CreateModel(
            name='Dme_utl_client_customer_group',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('fk_client_id', models.CharField(blank=True, max_length=11, null=True)),
                ('name_lookup', models.CharField(blank=True, max_length=50, null=True)),
                ('group_name', models.CharField(blank=True, max_length=64, null=True)),
                ('z_createdByAccount', models.CharField(blank=True, max_length=64, null=True, verbose_name='Created by account')),
                ('z_createdTimeStamp', models.DateTimeField(default=datetime.datetime.now, verbose_name='Created Timestamp')),
                ('z_modifiedByAccount', models.CharField(blank=True, max_length=64, null=True, verbose_name='Modified by account')),
                ('z_modifiedTimeStamp', models.DateTimeField(default=datetime.datetime.now, verbose_name='Modified Timestamp')),
            ],
            options={
                'db_table': 'dme_utl_client_customer_group',
            },
        ),
    ]
