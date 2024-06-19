from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0369_auto_20240226_2245"),
    ]

    operations = [
        migrations.AddField(
            model_name="supplierinvoice",
            name="dme_added_amt",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supplierinvoice",
            name="fp_inv_total_mass_kg",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supplierinvoice",
            name="fpinv_total_cbm",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supplierinvoice",
            name="fpinv_total_cbm_kg",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
