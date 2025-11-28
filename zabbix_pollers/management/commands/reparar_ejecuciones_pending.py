"""
Comando para reparar ejecuciones PENDING que no tienen celery_task_id

Estas ejecuciones se crearon pero nunca se enviaron a Celery, por lo que
quedan en PENDING indefinidamente. Este comando las repara enviándolas a Celery.
"""

from django.core.management.base import BaseCommand
from executions.models import Execution
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Repara ejecuciones PENDING que no tienen celery_task_id enviándolas a Celery'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin hacer cambios',
        )
        parser.add_argument(
            '--max-age-minutes',
            type=int,
            default=60,
            help='Solo reparar ejecuciones más antiguas que X minutos (default: 60)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        max_age_minutes = options['max_age_minutes']
        
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("REPARACIÓN DE EJECUCIONES PENDING SIN CELERY_TASK_ID"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        
        # Buscar ejecuciones PENDING sin celery_task_id
        cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
        pending_executions = Execution.objects.filter(
            status='PENDING',
            celery_task_id__isnull=True,
            created_at__lt=cutoff_time
        ).select_related('snmp_job', 'olt', 'workflow_node')
        
        total = pending_executions.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS(f"\n✅ No hay ejecuciones PENDING sin celery_task_id (más antiguas que {max_age_minutes} minutos)"))
            return
        
        self.stdout.write(f"\n📊 Encontradas {total} ejecuciones para reparar")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n🔍 MODO DRY-RUN: No se harán cambios"))
        
        repaired = 0
        failed = 0
        
        for exec in pending_executions:
            workflow_node = exec.workflow_node.name if exec.workflow_node else 'N/A'
            olt = exec.olt.abreviatura if exec.olt else 'N/A'
            age_minutes = (timezone.now() - exec.created_at).total_seconds() / 60
            
            self.stdout.write(f"\n   ID {exec.id}: {workflow_node} | OLT: {olt} ({age_minutes:.1f} min)")
            
            if not exec.snmp_job:
                self.stdout.write(self.style.ERROR(f"      ❌ No hay SnmpJob asociado, marcando como FAILED"))
                if not dry_run:
                    exec.status = 'FAILED'
                    exec.error_message = "No hay SnmpJob asociado"
                    exec.finished_at = timezone.now()
                    exec.save(update_fields=['status', 'error_message', 'finished_at'])
                failed += 1
                continue
            
            # Determinar tipo de job
            job_type = exec.snmp_job.job_type if exec.snmp_job.job_type else 'descubrimiento'
            
            if dry_run:
                self.stdout.write(f"      🔍 Se enviaría a Celery ({job_type})")
            else:
                try:
                    if job_type == 'descubrimiento':
                        from snmp_jobs.tasks import discovery_main_task
                        result = discovery_main_task.delay(exec.snmp_job.id, exec.olt.id, exec.id)
                    elif job_type == 'get':
                        from snmp_get.tasks import get_main_task
                        result = get_main_task.delay(exec.snmp_job.id, exec.olt.id, exec.id)
                    else:
                        raise ValueError(f"Tipo de job desconocido: {job_type}")
                    
                    exec.celery_task_id = result.id
                    exec.save(update_fields=['celery_task_id'])
                    self.stdout.write(self.style.SUCCESS(f"      ✅ Enviada a Celery (Task: {result.id})"))
                    repaired += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"      ❌ Error: {e}"))
                    logger.error(f"Error reparando Execution {exec.id}: {e}", exc_info=True)
                    # Marcar como FAILED
                    exec.status = 'FAILED'
                    exec.error_message = f"Error al reparar: {str(e)}"
                    exec.finished_at = timezone.now()
                    exec.save(update_fields=['status', 'error_message', 'finished_at'])
                    failed += 1
        
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
        if dry_run:
            self.stdout.write(self.style.WARNING(f"🔍 DRY-RUN: {total} ejecuciones se repararían"))
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Reparadas: {repaired}"))
            if failed > 0:
                self.stdout.write(self.style.ERROR(f"❌ Fallidas: {failed}"))
        self.stdout.write(self.style.SUCCESS("=" * 70))

