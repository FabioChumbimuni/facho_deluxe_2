"""
Comando de gestión para listar todas las futuras ejecuciones de workflows
"""
from django.core.management.base import BaseCommand
from snmp_jobs.models import WorkflowNode, OLTWorkflow
from hosts.models import OLT
from django.utils import timezone
from datetime import timedelta
import pytz


class Command(BaseCommand):
    help = 'Lista todas las futuras ejecuciones programadas de todos los workflows'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Número máximo de ejecuciones a mostrar (default: 50)'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['table', 'json', 'csv'],
            default='table',
            help='Formato de salida (default: table)'
        )

    def handle(self, *args, **options):
        peru_tz = pytz.timezone('America/Lima')
        now = timezone.now()
        now_peru = timezone.localtime(now, peru_tz)
        limit = options['limit']
        output_format = options['format']

        # Obtener todos los workflows activos
        workflows = OLTWorkflow.objects.filter(is_active=True).select_related('olt').order_by('olt__abreviatura')

        all_executions = []

        for workflow in workflows:
            olt = workflow.olt
            if not olt or not olt.habilitar_olt:
                continue

            # Obtener todos los nodos del workflow (solo master/normales, no chain)
            nodes = WorkflowNode.objects.filter(
                workflow=workflow,
                enabled=True,
                is_chain_node=False,
                next_run_at__isnull=False
            ).select_related('template_node', 'template_node__template').order_by('next_run_at')

            for node in nodes:
                next_run_peru = timezone.localtime(node.next_run_at, peru_tz)
                time_until = (node.next_run_at - now).total_seconds()

                # Calcular tiempo relativo
                if time_until < 0:
                    relative_time = f'Hace {int(abs(time_until) // 60)} min'
                    status = '⚠️ PASADO'
                elif time_until < 60:
                    relative_time = f'En {int(time_until)} seg'
                    status = '🔴 INMINENTE'
                elif time_until < 300:
                    relative_time = f'En {int(time_until // 60)} min'
                    status = '🟡 PRÓXIMO'
                elif time_until < 3600:
                    relative_time = f'En {int(time_until // 60)} min'
                    status = '🟢 PROGRAMADO'
                else:
                    hours = int(time_until // 3600)
                    mins = int((time_until % 3600) // 60)
                    relative_time = f'En {hours}h {mins}m'
                    status = '🔵 FUTURO'

                interval_min = node.interval_seconds // 60 if node.interval_seconds else 0
                template_name = node.template_node.template.name if node.template_node and node.template_node.template else 'N/A'

                all_executions.append({
                    'olt': olt.abreviatura,
                    'olt_id': olt.id,
                    'workflow_id': workflow.id,
                    'node_id': node.id,
                    'node_name': node.name,
                    'template': template_name,
                    'interval_minutes': interval_min,
                    'next_run_at': next_run_peru.strftime('%H:%M:%S'),
                    'next_run_date': next_run_peru.strftime('%Y-%m-%d'),
                    'next_run_datetime': next_run_peru.strftime('%Y-%m-%d %H:%M:%S'),
                    'relative_time': relative_time,
                    'status': status,
                    'time_until_seconds': int(time_until)
                })

        # Ordenar por próxima ejecución
        all_executions.sort(key=lambda x: x['time_until_seconds'])
        all_executions = all_executions[:limit]

        if output_format == 'json':
            import json
            self.stdout.write(json.dumps(all_executions, indent=2, ensure_ascii=False))
        elif output_format == 'csv':
            import csv
            import sys
            if all_executions:
                writer = csv.DictWriter(sys.stdout, fieldnames=all_executions[0].keys())
                writer.writeheader()
                writer.writerows(all_executions)
        else:  # table
            self.stdout.write(f'\n📅 Futuras Ejecuciones de Workflows')
            self.stdout.write(f'Hora actual: {now_peru.strftime("%Y-%m-%d %H:%M:%S")} PERÚ')
            self.stdout.write('=' * 120)
            self.stdout.write('')

            if all_executions:
                # Encabezados
                header = f"{'OLT':<10} {'Workflow':<10} {'Nodo':<25} {'Template':<20} {'Intervalo':<10} {'Próxima':<10} {'Fecha':<8} {'Relativo':<12} {'Estado':<12}"
                self.stdout.write(header)
                self.stdout.write('-' * 120)

                for exec in all_executions:
                    row = f"{exec['olt']:<10} {exec['workflow_id']:<10} {exec['node_name'][:25]:<25} {exec['template'][:20]:<20} {exec['interval_minutes']} min{'':<5} {exec['next_run_at']:<10} {exec['next_run_date'][5:]:<8} {exec['relative_time']:<12} {exec['status']:<12}"
                    self.stdout.write(row)

                self.stdout.write('')
                self.stdout.write(f'Total: {len(all_executions)} ejecuciones programadas (mostrando {min(limit, len(all_executions))} de {len(all_executions)})')
            else:
                self.stdout.write('No hay ejecuciones programadas')

