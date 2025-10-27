# Generated manually to remove ExecutionPlan model

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('execution_coordinator', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ExecutionPlan',
        ),
    ]

