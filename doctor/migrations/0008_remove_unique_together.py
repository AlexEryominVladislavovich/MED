# Generated by Django 5.2.1 on 2025-06-09 11:19

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('doctor', '0007_alter_scheduletemplate_options_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='scheduletemplate',
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name='scheduletemplate',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Создано'),
        ),
    ]
