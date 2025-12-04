"""
Comando para verificar el estado de una ejecución y revisar logs relacionados
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from executions.models import Execution
from pathlib import Path
import re
from datetime import timedelta


class Command(BaseCommand):
    help = 'Verifica el estado de una ejecución y busca información en los logs'

    def add_arguments(self, parser):
        parser.add_argument(
            'execution_id',
            type=int,
            help='ID de la ejecución a verificar'
        )
        parser.add_argument(
            '--logs',
            action='store_true',
            help='Buscar información en los logs de coordinator'
        )

    def handle(self, *args, **options):
        execution_id = options['execution_id']
        check_logs = options['logs']
        
        try:
            execution = Execution.objects.get(id=execution_id)
        except Execution.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Ejecución {execution_id} no encontrada'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\n📊 INFORMACIÓN DE EJECUCIÓN {execution_id}'))
        self.stdout.write('=' * 70)
        
        # Información básica
        self.stdout.write(f'🆔 ID: {execution.id}')
        self.stdout.write(f'📡 OLT: {execution.olt.abreviatura if execution.olt else "N/A"} ({execution.olt.ip_address if execution.olt else "N/A"})')
        self.stdout.write(f'📋 Job: {execution.snmp_job.nombre if execution.snmp_job else "N/A"}')
        if execution.workflow_node:
            self.stdout.write(f'🔄 Nodo Workflow: {execution.workflow_node.name} (ID: {execution.workflow_node.id})')
        self.stdout.write(f'📊 Estado: {execution.status}')
        self.stdout.write(f'🔄 Intento: {execution.attempt}')
        self.stdout.write(f'👷 Worker: {execution.worker_name or "N/A"}')
        self.stdout.write(f'🆔 Task ID: {execution.celery_task_id or "N/A"}')
        
        # Tiempos
        self.stdout.write('\n⏰ TIEMPOS:')
        self.stdout.write(f'   Creada: {execution.created_at}')
        if execution.started_at:
            self.stdout.write(f'   Iniciada: {execution.started_at}')
        else:
            self.stdout.write(f'   Iniciada: ⏳ PENDIENTE')
        
        if execution.finished_at:
            self.stdout.write(f'   Finalizada: {execution.finished_at}')
            if execution.started_at:
                duration = execution.finished_at - execution.started_at
                self.stdout.write(f'   Duración: {duration.total_seconds():.2f} segundos ({execution.duration_ms}ms)')
        else:
            self.stdout.write(f'   Finalizada: ⏳ EN PROGRESO')
            if execution.started_at:
                elapsed = timezone.now() - execution.started_at
                self.stdout.write(f'   ⚠️ Tiempo transcurrido: {elapsed.total_seconds():.2f} segundos ({elapsed.total_seconds()/60:.2f} minutos)')
            else:
                waiting = timezone.now() - execution.created_at
                self.stdout.write(f'   ⏳ Tiempo esperando: {waiting.total_seconds():.2f} segundos ({waiting.total_seconds()/60:.2f} minutos)')
        
        # Verificar si está demorando demasiado
        if execution.status == 'RUNNING' and execution.started_at:
            elapsed = timezone.now() - execution.started_at
            if elapsed.total_seconds() > 300:  # Más de 5 minutos
                self.stdout.write(self.style.WARNING(f'\n⚠️ ADVERTENCIA: La ejecución lleva más de 5 minutos ejecutándose'))
                self.stdout.write(self.style.WARNING(f'   Esto puede indicar un problema de rendimiento o timeout'))
        elif execution.status == 'PENDING':
            waiting = timezone.now() - execution.created_at
            if waiting.total_seconds() > 60:  # Más de 1 minuto esperando
                self.stdout.write(self.style.WARNING(f'\n⚠️ ADVERTENCIA: La ejecución lleva más de 1 minuto esperando'))
                self.stdout.write(self.style.WARNING(f'   Esto puede indicar que no hay workers disponibles o la cola está saturada'))
        
        # Error si existe
        if execution.error_message:
            self.stdout.write(self.style.ERROR(f'\n❌ ERROR: {execution.error_message}'))
        
        # Buscar en logs si se solicita
        if check_logs:
            self.stdout.write('\n📋 BUSCANDO EN LOGS...')
            self.stdout.write('=' * 70)
            
            # Buscar en logs de coordinator
            log_dir = Path('logs/coordinator')
            if log_dir.exists():
                log_file = log_dir / 'main.log'
                if log_file.exists():
                    self.stdout.write(f'🔍 Buscando en: {log_file}')
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            # Buscar líneas relacionadas con esta ejecución
                            found_lines = []
                            for i, line in enumerate(lines):
                                if (str(execution_id) in line or 
                                    (execution.olt and execution.olt.abreviatura in line) or
                                    (execution.celery_task_id and execution.celery_task_id in line)):
                                    found_lines.append((i+1, line.strip()))
                            
                            if found_lines:
                                self.stdout.write(f'\n✅ Encontradas {len(found_lines)} líneas relevantes:')
                                # Mostrar últimas 20 líneas
                                for line_num, line in found_lines[-20:]:
                                    self.stdout.write(f'   [{line_num}] {line}')
                            else:
                                self.stdout.write(self.style.WARNING('   No se encontraron líneas relevantes en los logs'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'   Error leyendo logs: {e}'))
                else:
                    self.stdout.write(self.style.WARNING(f'   Archivo de log no encontrado: {log_file}'))
            else:
                self.stdout.write(self.style.WARNING(f'   Directorio de logs no encontrado: {log_dir}'))
        
        self.stdout.write('\n' + '=' * 70)

