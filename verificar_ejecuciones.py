#!/usr/bin/env python
"""Script para verificar estado de ejecuciones de OLTs"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from hosts.models import OLT
from snmp_jobs.models import OLTWorkflow, WorkflowNode
from executions.models import Execution
from django.utils import timezone
from datetime import timedelta

print("=" * 80)
print("VERIFICACIÓN DE EJECUCIONES DE OLTs")
print("=" * 80)
print()

# 1. Estado de todas las OLTs
print("1️⃣ ESTADO DE TODAS LAS OLTs HABILITADAS")
print("-" * 80)
olts = OLT.objects.filter(habilitar_olt=True).order_by('abreviatura')
print(f"Total OLTs habilitadas: {olts.count()}\n")

for olt in olts:
    workflow = OLTWorkflow.objects.filter(olt=olt, is_active=True).first()
    if workflow:
        nodes = WorkflowNode.objects.filter(workflow=workflow, enabled=True)
        execs_24h = Execution.objects.filter(olt=olt, created_at__gte=timezone.now() - timedelta(hours=24)).count()
        execs_running = Execution.objects.filter(olt=olt, status__in=['PENDING', 'RUNNING']).count()
        status = "✅"
    else:
        nodes = WorkflowNode.objects.none()
        execs_24h = 0
        execs_running = 0
        status = "❌"
    
    print(f"{status} {olt.abreviatura:15} | Workflow: {'Sí':3} | Nodos: {nodes.count():2} | Ejecs 24h: {execs_24h:3} | Running: {execs_running:2}")

print()

# 2. Ejecuciones programadas para las 10:50
print("2️⃣ EJECUCIONES PROGRAMADAS PARA LAS 10:50")
print("-" * 80)
nodes_1050 = WorkflowNode.objects.filter(
    next_run_at__hour=10,
    next_run_at__minute=50,
    enabled=True,
    workflow__is_active=True
).select_related('workflow__olt').order_by('next_run_at')

if nodes_1050.exists():
    print(f"Total nodos programados a las 10:50: {nodes_1050.count()}\n")
    for node in nodes_1050:
        print(f"  {node.next_run_at.strftime('%Y-%m-%d %H:%M:%S')} - {node.workflow.olt.abreviatura} - {node.name}")
else:
    print("❌ No hay ejecuciones programadas exactamente a las 10:50\n")

print()

# 3. Próximas ejecuciones
print("3️⃣ PRÓXIMAS 20 EJECUCIONES")
print("-" * 80)
now = timezone.now()
next_execs = WorkflowNode.objects.filter(
    next_run_at__gte=now,
    enabled=True,
    workflow__is_active=True
).select_related('workflow__olt').order_by('next_run_at')[:20]

if next_execs.exists():
    print(f"Total próximas ejecuciones: {next_execs.count()}\n")
    for node in next_execs:
        time_str = node.next_run_at.strftime('%Y-%m-%d %H:%M:%S')
        print(f"  {time_str} - {node.workflow.olt.abreviatura:15} - {node.name}")
else:
    print("❌ No hay ejecuciones programadas\n")

print()

# 4. OLTs sin workflow
print("4️⃣ OLTs SIN WORKFLOW ACTIVO (NO GENERAN EJECUCIONES)")
print("-" * 80)
workflows_activos = OLTWorkflow.objects.filter(is_active=True)
olt_ids_con_workflow = set(workflows_activos.values_list('olt_id', flat=True))
olts_sin_workflow = [olt for olt in olts if olt.id not in olt_ids_con_workflow]

if olts_sin_workflow:
    print(f"Total: {len(olts_sin_workflow)} OLTs sin workflow activo\n")
    for olt in olts_sin_workflow:
        print(f"  ❌ {olt.abreviatura} (ID: {olt.id})")
    print("\n⚠️ Estas OLTs NO aparecerán en el historial porque no tienen workflows activos.")
    print("   Para que generen ejecuciones, necesitas aplicar una plantilla de workflow a estas OLTs.")
else:
    print("✅ Todas las OLTs tienen workflows activos\n")

print()
print("=" * 80)

