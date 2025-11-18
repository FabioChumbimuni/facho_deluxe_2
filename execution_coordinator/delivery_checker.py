"""
Sistema de Verificación de Entrega de Tareas a Celery

Este módulo verifica que las tareas enviadas a Celery fueron realmente
recogidas por los workers. Si una tarea está PENDING por > 30 segundos
y no aparece en Celery, se marca como INTERRUPTED y se reenvía.
"""

import logging
from datetime import timedelta
from django.utils import timezone
from celery import Celery
from django.conf import settings

from executions.models import Execution
from .event_utils import create_execution_event
from .logger import coordinator_logger
from redis import Redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Cliente Celery para inspeccionar tareas
app = Celery('facho_deluxe_v2')
app.config_from_object('django.conf:settings', namespace='CELERY')

redis_client = Redis.from_url(settings.CELERY_BROKER_URL)


def check_pending_deliveries():
    """
    Verifica que tareas PENDING fueron entregadas a Celery
    
    Revisa:
    1. Executions PENDING > 90 segundos (aumentado para evitar falsos positivos)
    2. Con celery_task_id asignado
    3. Valida si la tarea existe en Celery
    4. Si no existe Y el sistema NO está saturado → marca INTERRUPTED
    5. Si está saturado → ESPERA (no cancela)
    
    Returns:
        dict: Estadísticas de verificación
    """
    now = timezone.now()
    threshold = now - timedelta(seconds=90)  # Aumentado de 30s a 90s
    
    # Buscar PENDING antiguas con celery_task_id
    pending_execs = Execution.objects.filter(
        status='PENDING',
        created_at__lt=threshold,
        celery_task_id__isnull=False
    ).select_related('olt', 'snmp_job')
    
    if not pending_execs.exists():
        return {
            'checked': 0,
            'lost': 0,
            'requeued': 0
        }
    
    lost_tasks = []
    stats = {
        'checked': pending_execs.count(),
        'lost': 0,
        'requeued': 0
    }
    
    # Obtener inspector de Celery
    inspector = app.control.inspect()
    
    try:
        # Tareas activas en todos los workers
        active_tasks = inspector.active() or {}
        # Tareas reservadas (en cola del worker)
        reserved_tasks = inspector.reserved() or {}
        # Tareas programadas
        scheduled_tasks = inspector.scheduled() or {}
        
        # Crear set de todos los task_ids conocidos por Celery
        all_celery_task_ids = set()
        
        for tasks_dict in [active_tasks, reserved_tasks, scheduled_tasks]:
            for worker_tasks in tasks_dict.values():
                if isinstance(worker_tasks, list):
                    for task in worker_tasks:
                        if isinstance(task, dict) and 'id' in task:
                            all_celery_task_ids.add(task['id'])
        
        # Verificar cada ejecución PENDING
        for execution in pending_execs:
            age = int((now - execution.created_at).total_seconds())
            
            # ¿Celery tiene la tarea?
            if execution.celery_task_id not in all_celery_task_ids:
                # VERIFICAR: ¿El sistema está saturado?
                # Si está saturado, es normal que la tarea espere en cola
                # NO debemos marcarla como INTERRUPTED, debe ESPERAR
                
                job_type = execution.snmp_job.job_type
                pending_same_type = Execution.objects.filter(
                    status='PENDING',
                    snmp_job__job_type=job_type
                ).count()
                
                # Límites de saturación
                SATURATION_THRESHOLD = {
                    'descubrimiento': 20,
                    'get': 20
                }
                
                is_saturated = pending_same_type >= SATURATION_THRESHOLD.get(job_type, 15)
                
                if is_saturated:
                    # Sistema saturado, la tarea debe ESPERAR
                    coordinator_logger.info(
                        f"⏸️ Tarea esperando: {execution.snmp_job.nombre} en {execution.olt.abreviatura} "
                        f"(edad:{age}s, {pending_same_type} {job_type} PENDING en sistema)",
                        olt=execution.olt,
                        event_type='TASK_WAITING',
                        details={
                            'execution_id': execution.id,
                            'age_seconds': age,
                            'pending_count': pending_same_type
                        }
                    )
                    # NO marcar como INTERRUPTED, dejar que espere
                    continue
                
                # Sistema NO saturado pero tarea no fue recogida → realmente perdida
                lost_tasks.append({
                    'execution_id': execution.id,
                    'olt': execution.olt.abreviatura if execution.olt else 'Unknown',
                    'job': execution.snmp_job.nombre,
                    'age': age,
                    'celery_task_id': execution.celery_task_id
                })
                
                # Marcar como INTERRUPTED
                execution.status = 'INTERRUPTED'
                execution.error_message = f'Tarea perdida: enviada a Celery pero no recogida después de {age}s (sistema NO saturado)'
                execution.save(update_fields=['status', 'error_message'])
                interruption_details = {
                    'execution_id': execution.id,
                    'celery_task_id': execution.celery_task_id,
                    'age_seconds': age,
                    'pending_same_type': pending_same_type,
                }
                create_execution_event(
                    event_type='EXECUTION_INTERRUPTED',
                    execution=execution,
                    decision='ABORT',
                    source='DELIVERY_CHECKER',
                    reason=execution.error_message,
                    details=interruption_details,
                )
                
                stats['lost'] += 1
                
                coordinator_logger.log_execution_interrupted(
                    execution.snmp_job.nombre if execution.snmp_job else 'SNMP Job',
                    execution.error_message,
                    olt=execution.olt,
                    details=interruption_details,
                )

                job = execution.snmp_job
                if job and job.job_type == 'descubrimiento':
                    try:
                        new_execution = Execution.objects.create(
                            snmp_job=execution.snmp_job,
                            job_host=execution.job_host,
                            olt=execution.olt,
                            status='PENDING',
                            attempt=execution.attempt + 1,
                            requested_by=execution.requested_by,
                        )
                        from snmp_jobs.tasks import discovery_main_task
                        task_result = discovery_main_task.delay(job.id, execution.olt.id, new_execution.id)

                        create_execution_event(
                            event_type='REQUEUED',
                            execution=new_execution,
                            decision='REQUEUE',
                            source='DELIVERY_CHECKER',
                            reason='Reencolada tras detectar tarea perdida',
                            details={
                                'original_execution': execution.id,
                                'new_execution': new_execution.id,
                                'celery_task_id': task_result.id if task_result else None,
                            }
                        )
                        coordinator_logger.info(
                            f"🔁 Reencolada ejecución {new_execution.id} tras perder {execution.id}",
                            olt=execution.olt,
                            event_type='REQUEUED',
                            details={
                                'original_execution': execution.id,
                                'new_execution': new_execution.id,
                                'attempt': new_execution.attempt,
                                'celery_task_id': task_result.id if task_result else None,
                            }
                        )
                        retry_key = f"olt:retrying:{execution.olt_id}"
                        redis_client.set(retry_key, '1', ex=180)
                    except Exception as requeue_error:
                        coordinator_logger.error(
                            f"❌ Error reencolando ejecución después de pérdida: {requeue_error}",
                            olt=execution.olt,
                            event_type='EXECUTION_FAILED',
                            details={'execution_id': execution.id, 'error': str(requeue_error)}
                        )
                else:
                    retry_key = f"olt:retrying:{execution.olt_id}"
                    redis_client.set(retry_key, '1', ex=360)
                    coordinator_logger.warning(
                        f"🛑 OLT {execution.olt.abreviatura if execution.olt else execution.olt_id} bloqueada tras pérdida de GET",
                        olt=execution.olt,
                        event_type='EXECUTION_ABORTED',
                        details={
                            'execution_id': execution.id,
                            'snmp_job_id': job.id if job else None,
                            'reason': 'lost_get_execution',
                            'retry_key': retry_key
                        }
                    )
    
    except Exception as e:
        logger.error(f"Error verificando entregas a Celery: {e}")
        return stats
    
    # Logging de resumen
    if stats['lost'] > 0:
        coordinator_logger.warning(
            f"📦 Verificación de entregas: {stats['checked']} revisadas, {stats['lost']} perdidas",
            event_type='DELIVERY_CHECK',
            details=stats
        )
    
    return stats


def get_celery_task_state(celery_task_id):
    """
    Obtiene el estado de una tarea específica en Celery
    
    Args:
        celery_task_id: ID de la tarea en Celery
    
    Returns:
        str: Estado de la tarea (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED, etc.)
             o None si no se puede determinar
    """
    try:
        from celery.result import AsyncResult
        result = AsyncResult(celery_task_id, app=app)
        return result.state
    except Exception as e:
        logger.error(f"Error obteniendo estado de tarea {celery_task_id}: {e}")
        return None


def verify_single_execution(execution_id):
    """
    Verifica una ejecución específica
    
    Args:
        execution_id: ID de la ejecución a verificar
    
    Returns:
        dict: Estado de la verificación
    """
    try:
        execution = Execution.objects.select_related('olt', 'snmp_job').get(id=execution_id)
        
        if not execution.celery_task_id:
            return {
                'status': 'no_celery_id',
                'message': 'No se asignó celery_task_id'
            }
        
        # Verificar en Celery
        celery_state = get_celery_task_state(execution.celery_task_id)
        
        return {
            'status': 'checked',
            'celery_state': celery_state,
            'execution_status': execution.status,
            'match': execution.status.lower() == celery_state.lower() if celery_state else False
        }
        
    except Execution.DoesNotExist:
        return {
            'status': 'not_found',
            'message': f'Execution {execution_id} no existe'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

