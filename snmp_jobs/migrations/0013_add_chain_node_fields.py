# Generated migration for chain node fields

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('snmp_jobs', '0012_add_workflow_node_execution_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='workflownode',
            name='is_chain_node',
            field=models.BooleanField(
                default=False,
                help_text='Si True, este nodo está en una cadena y se ejecuta después del nodo master'
            ),
        ),
        migrations.AddField(
            model_name='workflownode',
            name='master_node',
            field=models.ForeignKey(
                blank=True,
                help_text='Nodo master de la cadena. Solo los nodos en cadena tienen este campo asignado.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='chain_nodes',
                to='snmp_jobs.workflownode'
            ),
        ),
    ]

