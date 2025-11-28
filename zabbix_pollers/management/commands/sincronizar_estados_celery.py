"""
Comando para sincronizar el estado de ejecuciones con el estado real de Celery

Las ejecuciones pueden quedar en PENDING aunque las tareas de Celery ya terminaron
si los callbacks no se ejecutaron correctamente. Este comando sincroniza los estados.
"""

from django.core.management.base import BaseCommand
from executions.models import Execution
from django.utils import timezone
from datetime import timedelta
from celery.result import AsyncResult
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sincroniza el estado de ejecuciones PENDING con el estado real de las tareas de Celery'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin hacer cambios',
        )
        parser.add_argument(
            '--max-age-minutes',
            type=int,
            default=5,
            help='Solo sincronizar ejecuciones más antiguas que X minutos (default: 5)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_age_minutes = options['max_age_minutes']
        
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("SINCRONIZACIÓN DE ESTADOS: CELERY → EXECUTION"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        
        # Buscar ejecuciones PENDING con celery_task_id
        cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
        pending_executions = Execution.objects.filter(
            status='PENDING',
            celery_task_id__isnull=False,
            created_at__lt=cutoff_time
        ).select_related('workflow_node', 'olt')
        
        total = pending_executions.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS(f"\n✅ No hay ejecuciones PENDING con celery_task_id (más antiguas que {max_age_minutes} minutos)"))
            return
        
        self.stdout.write(f"\n📊 Encontradas {total} ejecuciones para sincronizar")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n🔍 MODO DRY-RUN: No se harán cambios"))
        
        updated_success = 0
        updated_failed = 0
        still_pending = 0
        
        for exec in pending_executions:
            workflow_node = exec.workflow_node.name if exec.workflow_node else 'N/A'
            olt = exec.olt.abreviatura if exec.olt else 'N/A'
            age_minutes = (timezone.now() - exec.created_at).total_seconds() / 60
            
            if not exec.celery_task_id:
                continue
            
            result = AsyncResult(exec.celery_task_id)
            
            if result.ready():
                if result.successful():
                    # Tarea completada exitosamente
                    if dry_run:
                        self.stdout.write(f"   ID {exec.id} ({workflow_node} | {olt}): Se actualizaría a SUCCESS")
                    else:
                        exec.status = 'SUCCESS'
                        if not exec.finished_at:
                            exec.finished_at = timezone.now()
                        exec.save(update_fields=['status', 'finished_at'])
                        self.stdout.write(self.style.SUCCESS(f"   ✅ ID {exec.id}: Actualizada a SUCCESS"))
                    updated_success += 1
                else:
                    # Tarea falló
                    error_msg = str(result.info) if result.info else "Tarea falló en Celery"
                    if dry_run:
                        self.stdout.write(f"   ID {exec.id} ({workflow_node} | {olt}): Se actualizaría a FAILED - {error_msg}")
                    else:
                        exec.status = 'FAILED'
                        exec.error_message = error_msg[:500]  # Limitar longitud
                        if not exec.finished_at:
                            exec.finished_at = timezone.now()
                        exec.save(update_fields=['status', 'error_message', 'finished_at'])
                        self.stdout.write(self.style.ERROR(f"   ❌ ID {exec.id}: Actualizada a FAILED - {error_msg}"))
                    updated_failed += 1
            else:
                # Tarea aún en ejecución
                self.stdout.write(f"   ⏳ ID {exec.id} ({workflow_node} | {olt}): Aún en ejecución (estado: {result.state})")
                still_pending += 1
        
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        if dry_run:
            self.stdout.write(self.style.WARNING(f"🔍 DRY-RUN: {total} ejecuciones se sincronizarían"))
            self.stdout.write(f"   - SUCCESS: {updated_success}")
            self.stdout.write(f"   - FAILED: {updated_failed}")
            self.stdout.write(f"   - Aún PENDING: {still_pending}")
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Sincronizadas: {updated_success + updated_failed}"))
            self.stdout.write(self.style.SUCCESS(f"   - SUCCESS: {updated_success}"))
            if updated_failed > 0:
                self.stdout.write(self.style.ERROR(f"   - FAILED: {updated_failed}"))
            if still_pending > 0:
                self.stdout.write(f"   - Aún PENDING: {still_pending}")
        self.stdout.write(self.style.SUCCESS("=" * 70))

