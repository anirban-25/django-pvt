# Generated by Django 2.1.2 on 2021-03-31 01:29

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0246_auto_20210319_0259"),
    ]

    operations = [
        migrations.AddField(
            model_name="bok_1_headers",
            name="b_081_b_pu_auto_pack",
            field=models.BooleanField(default=None, null=True),
        ),
    ]
