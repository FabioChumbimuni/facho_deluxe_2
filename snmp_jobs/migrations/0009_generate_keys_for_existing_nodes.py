# snmp_jobs/migrations/0009_generate_keys_for_existing_nodes.py
from django.db import migrations
import re


def generate_keys_for_existing_nodes(apps, schema_editor):
    """Genera keys para nodos existentes que no tienen key"""
    WorkflowNode = apps.get_model('snmp_jobs', 'WorkflowNode')
    
    nodes = WorkflowNode.objects.filter(key__isnull=True)
    
    for node in nodes:
        # Generar key basada en nombre y tipo
        name_lower = node.name.lower().replace(' ', '.')
        # Limpiar caracteres especiales
        name_clean = re.sub(r'[^a-z0-9.]', '', name_lower)
        
        # Agregar intervalo si es posible
        interval_min = node.interval_seconds // 60
        if interval_min > 0:
            key = f"{name_clean}.{interval_min}min"
        else:
            key = f"{name_clean}.{node.interval_seconds}s"
        
        # Asegurar unicidad dentro del workflow
        base_key = key
        counter = 1
        while WorkflowNode.objects.filter(workflow=node.workflow, key=key).exclude(id=node.id).exists():
            key = f"{base_key}.{counter}"
            counter += 1
        
        node.key = key
        node.save(update_fields=['key'])


def reverse_generate_keys(apps, schema_editor):
    """No hacer nada al revertir"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('snmp_jobs', '0008_add_workflow_templates_and_keys'),
    ]

    operations = [
        migrations.RunPython(generate_keys_for_existing_nodes, reverse_generate_keys),
    ]

