# Generated by Django 5.1.1 on 2024-10-06 08:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ta_support_app', '0003_data_datetime'),
    ]

    operations = [
        migrations.AlterField(
            model_name='data',
            name='transcript',
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name='data',
            name='transcript_diarize',
            field=models.TextField(null=True),
        ),
    ]
