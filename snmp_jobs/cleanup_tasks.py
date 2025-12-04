# snmp_jobs/cleanup_tasks.py
"""
Tareas de limpieza para ejecuciones PENDING que tienen tareas fallidas en Celery
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from celery.result import AsyncResult
from django.conf import settings
from celery import Celery
import os

logger = logging.getLogger(__name__)


@shared_task(queue='cleanup')
def sync_pending_executions_with_celery(max_age_minutes=5):
    """
    Sincroniza ejecuciones PENDING con el estado real de las tareas en Celery.
    
    Si una ejecución está en PENDING pero su tarea de Celery ya falló,
    actualiza la ejecución a FAILED con el mensaje de error correspondiente.
    
    Args:
        max_age_minutes: Solo verificar ejecuciones con más de X minutos (default: 5)
    """
    from executions.models import Execution
    from configuracion_avanzada.services import get_snmp_timeout, get_snmp_retries
    
    logger.info(f"🧹 Iniciando sincronización de ejecuciones PENDING con Celery (más de {max_age_minutes} minutos)")
    
    cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
    
    # Buscar ejecuciones PENDING antiguas con celery_task_id
    pending_executions = Execution.objects.filter(
        status='PENDING',
        celery_task_id__isnull=False,
        created_at__lt=cutoff_time
    ).select_related('snmp_job', 'olt', 'workflow_node')
    
    total = pending_executions.count()
    
    if total == 0:
        logger.info("✅ No hay ejecuciones PENDING antiguas para verificar")
        return {'status': 'success', 'checked': 0, 'updated': 0}
    
    logger.info(f"📊 Verificando {total} ejecución(es) PENDING con tareas de Celery")
    
    # Crear instancia de Celery para consultar
    app = Celery('facho_deluxe_2')
    app.config_from_object('django.conf:settings', namespace='CELERY')
    
    updated_count = 0
    checked_count = 0
    
    for execution in pending_executions:
        checked_count += 1
        try:
            result = app.AsyncResult(execution.celery_task_id)
            
            # Si la tarea está lista y falló
            if result.ready() and not result.successful():
                error_info = result.info if result.info else "Tarea falló en Celery"
                
                # Determinar tipo de operación
                job_type = 'descubrimiento'
                if execution.snmp_job:
                    job_type = execution.snmp_job.job_type or 'descubrimiento'
                
                # Obtener configuración SNMP
                snmp_timeout = get_snmp_timeout(job_type)
                snmp_retries = get_snmp_retries(job_type)
                
                # Construir mensaje detallado si es timeout
                is_timeout = 'TimeLimitExceeded' in str(error_info) or 'timeout' in str(error_info).lower()
                
                if is_timeout:
                    detailed_message = (
                        f"SNMP se quedó colgado - La consulta SNMP no respondió dentro del tiempo límite. "
                        f"Configuración SNMP aplicada: timeout={snmp_timeout}s, reintentos={snmp_retries}. "
                        f"Se realizó el intento inicial y {snmp_retries} reintento(s) adicional(es) sin éxito. "
                        f"La tarea fue cancelada por Celery después de exceder el límite de tiempo (180s)."
                    )
                else:
                    detailed_message = f"Tarea falló en Celery: {error_info}"
                
                # Actualizar ejecución
                execution.status = 'FAILED'
                execution.error_message = detailed_message
                execution.finished_at = timezone.now()
                if not execution.started_at:
                    execution.started_at = execution.created_at
                if execution.started_at and execution.finished_at:
                    execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                execution.save()
                
                # Actualizar WorkflowNode si existe
                if execution.workflow_node:
                    try:
                        # Usar register_failure si existe, sino usar schedule_next_run directamente
                        if hasattr(execution.workflow_node, 'register_failure'):
                            execution.workflow_node.register_failure()
                        else:
                            # Actualizar manualmente
                            now = timezone.now()
                            execution.workflow_node.last_run_at = now
                            execution.workflow_node.last_failure_at = now
                            execution.workflow_node.consecutive_failures = (execution.workflow_node.consecutive_failures or 0) + 1
                            execution.workflow_node.schedule_next_run(reference=now, commit=True)
                        logger.info(f"✅ WorkflowNode {execution.workflow_node.id} actualizado")
                    except Exception as node_error:
                        logger.warning(f"⚠️ Error actualizando WorkflowNode {execution.workflow_node.id}: {node_error}")
                
                # Llamar callback para asegurar actualización completa
                try:
                    from execution_utils.callbacks import on_task_failed
                    job_name = execution.snmp_job.nombre if execution.snmp_job else (execution.workflow_node.name if execution.workflow_node else 'Unknown')
                    job_type_callback = execution.snmp_job.job_type if execution.snmp_job else 'descubrimiento'
                    on_task_failed(
                        olt_id=execution.olt.id,
                        task_name=job_name,
                        task_type=job_type_callback,
                        error_message=detailed_message,
                        execution_id=execution.id
                    )
                except Exception as callback_error:
                    logger.warning(f"⚠️ Error en callback on_task_failed: {callback_error}")
                
                updated_count += 1
                logger.info(f"✅ Ejecución {execution.id} actualizada a FAILED (tarea falló en Celery)")
                
        except Exception as e:
            logger.error(f"❌ Error verificando ejecución {execution.id}: {e}")
    
    logger.info(f"✅ Sincronización completada: {checked_count} verificada(s), {updated_count} actualizada(s)")
    
    return {
        'status': 'success',
        'checked': checked_count,
        'updated': updated_count
    }

