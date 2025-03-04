# Generated by Django 2.1.2 on 2024-02-26 22:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0368_auto_20240226_0933"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierinvoice",
            name="rec_200_Supplier_approvedToInvoice_YD_YS_NO_TR",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="supplierinvoice",
            name="si_13_Service",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="supplierinvoice",
            name="si_18_0_Markup",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supplierinvoice",
            name="x09_fp_charge_description",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
    ]
