"""
Sistema de Callbacks para Notificar al Coordinator

Cuando una tarea (Discovery o GET) termina, notifica al coordinator
para que ejecute inmediatamente la siguiente tarea en cola
"""

import logging
from redis import Redis
from django.conf import settings
from django.utils import timezone

from .logger import coordinator_logger
from .dynamic_scheduler import DynamicScheduler

logger = logging.getLogger(__name__)
redis_client = Redis.from_url(settings.CELERY_BROKER_URL)


def on_task_completed(olt_id, task_name, task_type, duration_ms, status='SUCCESS'):
    """
    Callback cuando una tarea SNMP termina
    
    Args:
        olt_id: ID de la OLT
        task_name: Nombre de la tarea completada
        task_type: Tipo (descubrimiento o get)
        duration_ms: Duración en milisegundos
        status: Estado final (SUCCESS o FAILED)
    
    Este callback:
    1. Libera el lock de la OLT
    2. Verifica si hay tareas en cola esperando
    3. Ejecuta INMEDIATAMENTE la siguiente tarea de mayor prioridad
    """
    from hosts.models import OLT
    
    try:
        olt = OLT.objects.get(id=olt_id)
        
        # Log de finalización con formato adaptativo
        if duration_ms < 1000:
            time_str = f"{duration_ms}ms"  # Milisegundos para tareas rápidas
        else:
            time_str = f"{duration_ms/1000:.1f}s"  # Segundos para tareas lentas
        
        coordinator_logger.info(
            f"✅ {task_name} completada ({status}) en {time_str}",
            olt=olt,
            event_type='EXECUTION_COMPLETED',
            details={
                'task_name': task_name,
                'task_type': task_type,
                'duration_ms': duration_ms,
                'status': status
            }
        )
        
        # NO liberar lock aquí - ya fue liberado por la tarea que terminó
        # Intentar liberarlo causa: "Cannot release a lock that's no longer owned"
        
        # Verificar si hay tareas en cola
        scheduler = DynamicScheduler(olt_id)
        queue_items = redis_client.lrange(scheduler.queue_key, 0, -1)
        
        if queue_items:
            # Verificar si la siguiente tarea en cola debe respetar desfase
            import json
            next_task = json.loads(queue_items[0])
            
            # Obtener tipo de tarea
            from snmp_jobs.models import SnmpJob
            try:
                job = SnmpJob.objects.get(id=next_task['job_id'])
                
                # Verificar si debe esperar por desfase
                now = timezone.now()
                current_second = now.second
                
                should_wait = False
                if job.job_type == 'get':
                    # GET debe ejecutarse en segundo 10
                    if current_second < 10:
                        should_wait = True
                        wait_seconds = 10 - current_second
                        coordinator_logger.info(
                            f"⏸️ GET en cola esperará {wait_seconds}s para respetar desfase (segundo 10)",
                            olt=olt
                        )
                
                if should_wait:
                    # NO ejecutar ahora, dejar que el coordinator loop lo maneje
                    coordinator_logger.info(
                        f"✓ OLT libre, tarea en cola esperará desfase",
                        olt=olt,
                        event_type='EXECUTION_COMPLETED'
                    )
                else:
                    # LOCK TEMPORAL: Evitar que coordinator loop interfiera mientras procesamos cola
                    processing_key = f"lock:processing_queue:{olt_id}"
                    redis_client.set(processing_key, '1', ex=10)  # 10 segundos
                    
                    # Ejecutar la siguiente INMEDIATAMENTE
                    coordinator_logger.info(
                        f"🔄 Hay {len(queue_items)} tarea(s) en cola, ejecutando siguiente INMEDIATAMENTE",
                        olt=olt,
                        event_type='EXECUTION_STARTED'
                    )
                    
                    executed = scheduler.execute_next_in_queue(olt)
                    
                    # Liberar lock de procesamiento
                    redis_client.delete(processing_key)
                    
                    if executed:
                        coordinator_logger.info(
                            f"▶️ Siguiente tarea iniciada sin demora",
                            olt=olt,
                            event_type='EXECUTION_STARTED'
                        )
                    else:
                        coordinator_logger.info(
                            f"⊘ Siguiente tarea omitida (ya ejecutada recientemente o no disponible)",
                            olt=olt
                        )
            
            except Exception as queue_error:
                logger.error(f"Error procesando cola: {queue_error}")
        else:
            # No hay más tareas en cola
            coordinator_logger.info(
                f"✓ OLT libre, sin tareas pendientes",
                olt=olt,
                event_type='EXECUTION_COMPLETED',
                details={'queue_empty': True}
            )
        
    except OLT.DoesNotExist:
        logger.error(f"OLT {olt_id} no existe")
    except Exception as e:
        logger.error(f"Error en callback de tarea completada: {e}")


def on_task_failed(olt_id, task_name, task_type, error_message):
    """
    Callback cuando una tarea SNMP falla
    
    Similar a on_task_completed pero con manejo de error
    """
    from hosts.models import OLT
    
    try:
        olt = OLT.objects.get(id=olt_id)
        
        coordinator_logger.error(
            f"❌ {task_name} FALLÓ: {error_message[:100]}",
            olt=olt,
            event_type='EXECUTION_FAILED',
            details={
                'task_name': task_name,
                'task_type': task_type,
                'error': error_message
            }
        )
        
        # Liberar lock
        lock_key = f"lock:execution:olt:{olt_id}"
        redis_client.delete(lock_key)
        
        # Intentar ejecutar siguiente en cola
        scheduler = DynamicScheduler(olt_id)
        scheduler.execute_next_in_queue(olt)
        
    except Exception as e:
        logger.error(f"Error en callback de tarea fallida: {e}")

