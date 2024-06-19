# Generated by Django 2.1.2 on 2024-01-24 02:11

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0362_auto_20240108_1323'),
    ]

    operations = [
        migrations.CreateModel(
            name='DME_Tokens',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('token_type', models.CharField(blank=True, default=None, max_length=32, null=True)),
                ('token', models.CharField(blank=True, default=None, max_length=128, null=True)),
                ('email', models.CharField(blank=True, default=None, max_length=32, null=True)),
                ('api_booking_quote_id', models.IntegerField(blank=True, null=True)),
                ('vx_freight_provider', models.CharField(blank=True, default=None, max_length=128, null=True)),
                ('booking_id', models.IntegerField(blank=True, default=None, null=True)),
                ('z_createdTimeStamp', models.DateTimeField(auto_now_add=True, null=True, verbose_name='Created Timestamp')),
                ('z_expiredTimeStamp', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'dme_tokens',
            },
        ),
    ]
