# Generated by Django 3.2.19 on 2024-08-06 04:47

from django.db import migrations
import django.db.models.manager


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0069_auto_20240806_1427"),
    ]

    operations = [
        migrations.AlterModelManagers(
            name="unregistereduser",
            managers=[
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
    ]
