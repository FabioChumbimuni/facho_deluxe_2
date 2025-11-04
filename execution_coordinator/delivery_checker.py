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
from .logger import coordinator_logger

logger = logging.getLogger(__name__)

# Cliente Celery para inspeccionar tareas
app = Celery('facho_deluxe_v2')
app.config_from_object('django.conf:settings', namespace='CELERY')


def check_pending_deliveries():
    """
    Verifica que tareas PENDING fueron entregadas a Celery
    
    Revisa:
    1. Executions PENDING > 30 segundos
    2. Con celery_task_id asignado
    3. Valida si la tarea existe en Celery
    4. Si no existe o está perdida → marca INTERRUPTED y loguea
    
    Returns:
        dict: Estadísticas de verificación
    """
    now = timezone.now()
    threshold = now - timedelta(seconds=30)
    
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
                # Tarea perdida/huérfana
                lost_tasks.append({
                    'execution_id': execution.id,
                    'olt': execution.olt.abreviatura if execution.olt else 'Unknown',
                    'job': execution.snmp_job.nombre,
                    'age': age,
                    'celery_task_id': execution.celery_task_id
                })
                
                # Marcar como INTERRUPTED
                execution.status = 'INTERRUPTED'
                execution.error_message = f'Tarea perdida: enviada a Celery pero no recogida después de {age}s (saturación del sistema)'
                execution.save(update_fields=['status', 'error_message'])
                
                stats['lost'] += 1
                
                coordinator_logger.warning(
                    f"❌ Tarea perdida detectada: {execution.snmp_job.nombre} en {execution.olt.abreviatura} "
                    f"(ID:{execution.id}, Celery:{execution.celery_task_id[:8]}, edad:{age}s)",
                    olt=execution.olt,
                    event_type='DELIVERY_FAILED',
                    details={
                        'execution_id': execution.id,
                        'celery_task_id': execution.celery_task_id,
                        'age_seconds': age
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

