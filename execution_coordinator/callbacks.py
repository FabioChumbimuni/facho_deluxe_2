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


def update_workflow_node_on_completion(execution_id, status):
    """
    Actualiza los campos del WorkflowNode cuando una ejecución termina
    
    Args:
        execution_id: ID de la ejecución
        status: Estado final (SUCCESS o FAILED)
    """
    from executions.models import Execution
    from django.utils import timezone
    
    try:
        execution = Execution.objects.select_related('workflow_node').get(id=execution_id)
        
        if execution.workflow_node:
            now = timezone.now()
            
            # SIEMPRE actualizar last_run_at cuando termina (SUCCESS, FAILED o INTERRUPTED)
            execution.workflow_node.last_run_at = now
            
            if status == 'SUCCESS':
                execution.workflow_node.last_success_at = now
            elif status == 'FAILED':
                execution.workflow_node.last_failure_at = now
            # INTERRUPTED también actualiza last_run_at para indicar que terminó
            
            execution.workflow_node.save(update_fields=['last_success_at', 'last_failure_at', 'last_run_at'])
            
            logger.debug(
                f"✅ WorkflowNode {execution.workflow_node.id} actualizado: "
                f"last_success_at={execution.workflow_node.last_success_at}, "
                f"last_failure_at={execution.workflow_node.last_failure_at}"
            )
    except Execution.DoesNotExist:
        logger.warning(f"Execution {execution_id} no existe para actualizar WorkflowNode")
    except Exception as e:
        logger.error(f"Error actualizando WorkflowNode desde execution {execution_id}: {e}")


def on_task_completed(olt_id, task_name, task_type, duration_ms, status='SUCCESS', execution_id=None):
    """
    Callback cuando una tarea SNMP termina
    
    Args:
        olt_id: ID de la OLT
        task_name: Nombre de la tarea completada
        task_type: Tipo (descubrimiento o get)
        duration_ms: Duración en milisegundos
        status: Estado final (SUCCESS o FAILED)
        execution_id: ID de la ejecución (opcional, para actualizar WorkflowNode)
    
    Este callback:
    1. Actualiza WorkflowNode si la ejecución tiene uno asociado
    2. Libera el lock de la OLT
    3. Verifica si hay tareas en cola esperando
    4. Ejecuta INMEDIATAMENTE la siguiente tarea de mayor prioridad
    """
    from hosts.models import OLT
    
    try:
        # Actualizar WorkflowNode si hay execution_id
        workflow_node = None
        if execution_id:
            from executions.models import Execution
            try:
                execution = Execution.objects.select_related('workflow_node').get(id=execution_id)
                workflow_node = execution.workflow_node
            except Execution.DoesNotExist:
                pass
            
            update_workflow_node_on_completion(execution_id, status)
        
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
        
        scheduler = DynamicScheduler(olt_id)
        
        # ✅ WORKFLOW → COORDINADOR: El workflow llama al coordinador para ejecutar items en cadena
        # Cada OLT funciona de manera independiente, no se combinan con el resto
        coordinator_logger.info(
            f"📞 WORKFLOW → COORDINADOR: Nodo '{workflow_node.name if workflow_node else 'Unknown'}' completado ({status}) en OLT {olt.abreviatura}",
            olt=olt,
            event_type='WORKFLOW_TO_COORDINATOR',
            details={
                'workflow_node_id': workflow_node.id if workflow_node else None,
                'status': status,
                'execution_id': execution_id
            }
        )
        
        # ✅ NUEVO: Ejecución en cadena automática
        # Si el nodo que terminó es un master (SUCCESS o FAILED), ejecutar nodos en cadena
        # IMPORTANTE: Los nodos en cadena se ejecutan cuando el master termina, no solo cuando tiene éxito
        # Los items en cadena son los únicos que dependen del master, los GET independientes NO esperan
        if workflow_node and status in ['SUCCESS', 'FAILED'] and not workflow_node.is_chain_node:
            # Es un nodo master, buscar nodos en su cadena
            chain_nodes = workflow_node.get_chain_nodes()
            
            if chain_nodes.exists():
                coordinator_logger.info(
                    f"📞 WORKFLOW → COORDINADOR: Master '{workflow_node.name}' completado, ejecutando {chain_nodes.count()} nodo(s) en cadena (OLT {olt.abreviatura} - independiente)",
                    olt=olt,
                    event_type='CHAIN_STARTED'
                )
                
                # Ejecutar el primer nodo de la cadena (mayor prioridad)
                first_chain_node = chain_nodes.first()
                
                # ✅ Verificar que el nodo en cadena tenga OID (directo o desde template_node)
                oid_check = first_chain_node.oid or (first_chain_node.template_node.oid if first_chain_node.template_node else None)
                if not oid_check:
                    coordinator_logger.warning(
                        f"⏸️ Nodo en cadena '{first_chain_node.name}' no tiene OID asociado, no se puede ejecutar",
                        olt=olt
                    )
                    return
                
                can_execute, reason = first_chain_node.can_execute_now()
                
                # ✅ CRÍTICO: Verificar que NO haya ejecución PENDING o RUNNING para este nodo en cadena
                from executions.models import Execution
                existing_execution = Execution.objects.filter(
                    workflow_node=first_chain_node,
                    status__in=['PENDING', 'RUNNING']
                ).first()
                
                if existing_execution:
                    coordinator_logger.warning(
                        f"⏸️ Nodo en cadena '{first_chain_node.name}' ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, omitiendo",
                        olt=olt
                    )
                    can_execute = False
                    reason = f"Ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}"
                
                if can_execute:
                    # ✅ CRÍTICO: Verificar que el nodo maestro haya terminado COMPLETAMENTE
                    # Esto es especialmente importante para discovery que procesa archivos y escribe en BD
                    from executions.models import Execution
                    import time
                    
                    # Re-verificar el estado de la ejecución del nodo maestro desde la BD
                    master_execution = None
                    if execution_id:
                        try:
                            master_execution = Execution.objects.select_related('workflow_node', 'snmp_job').get(id=execution_id)
                        except Execution.DoesNotExist:
                            pass
                    
                    # Si tenemos la ejecución del master, verificar que esté completamente terminada
                    if master_execution:
                        # Verificar que el estado sea final (SUCCESS, FAILED o INTERRUPTED)
                        if master_execution.status not in ['SUCCESS', 'FAILED', 'INTERRUPTED']:
                            coordinator_logger.warning(
                                f"⏸️ Nodo maestro '{workflow_node.name}' aún no ha terminado (estado: {master_execution.status}), esperando...",
                                olt=olt
                            )
                            return
                        
                        # Verificar que finished_at esté establecido
                        if not master_execution.finished_at:
                            coordinator_logger.warning(
                                f"⏸️ Nodo maestro '{workflow_node.name}' no tiene finished_at establecido, esperando...",
                                olt=olt
                            )
                            return
                        
                        # Para discovery, verificar que el procesamiento haya terminado
                        # Si es discovery y tiene result_summary, verificar que tenga los datos procesados
                        if master_execution.snmp_job and master_execution.snmp_job.job_type == 'descubrimiento':
                            if not master_execution.result_summary:
                                coordinator_logger.warning(
                                    f"⏸️ Nodo maestro discovery '{workflow_node.name}' no tiene result_summary, esperando procesamiento...",
                                    olt=olt
                                )
                                return
                            
                            # Verificar que el procesamiento haya terminado (tiene datos de procesamiento)
                            result_summary = master_execution.result_summary
                            if isinstance(result_summary, dict):
                                # Verificar que tenga indicadores de procesamiento completado
                                # Para discovery, debe tener total_found o new_index_created
                                if 'total_found' not in result_summary and 'new_index_created' not in result_summary:
                                    # Esperar un momento y re-verificar (máximo 3 intentos, 1 segundo cada uno)
                                    max_retries = 3
                                    for retry in range(max_retries):
                                        time.sleep(1)
                                        master_execution.refresh_from_db()
                                        if master_execution.result_summary and isinstance(master_execution.result_summary, dict):
                                            if 'total_found' in master_execution.result_summary or 'new_index_created' in master_execution.result_summary:
                                                break
                                    else:
                                        # Si después de los reintentos aún no tiene datos, omitir
                                        coordinator_logger.warning(
                                            f"⏸️ Nodo maestro discovery '{workflow_node.name}' aún procesando datos después de {max_retries} intentos, omitiendo nodo de cadena",
                                            olt=olt
                                        )
                                        return
                    
                    # Preparar task_info para el nodo en cadena
                    from snmp_jobs.models import WorkflowNode
                    node = first_chain_node
                    
                    # Determinar tipo y prioridad desde el OID (directo o desde template_node)
                    oid = node.oid or (node.template_node.oid if node.template_node else None)
                    if oid:
                        if oid.espacio == 'descubrimiento':
                            job_type = 'descubrimiento'
                            priority = node.priority or 90
                        else:
                            job_type = 'get'
                            priority = node.priority or 40
                    else:
                        # Sin OID, no se puede ejecutar
                        coordinator_logger.warning(
                            f"⏸️ Nodo en cadena '{node.name}' no tiene OID asociado, no se puede ejecutar",
                            olt=olt
                        )
                        can_execute = False
                        reason = "Nodo no tiene OID asociado"
                    
                    if not can_execute:
                        return
                    
                    task_info = {
                        'workflow_node_id': node.id,
                        'node_name': node.name,
                        'node_key': node.key,
                        'job_type': job_type,
                        'priority': priority,
                        'interval_seconds': node.interval_seconds,
                        'is_chain_node': True,
                        'master_node_id': node.master_node.id if node.master_node else None,
                    }
                    
                    # Re-verificar que no haya ejecución PENDING o RUNNING para el nodo de cadena
                    existing_execution = Execution.objects.filter(
                        workflow_node=first_chain_node,
                        status__in=['PENDING', 'RUNNING']
                    ).first()
                    
                    if existing_execution:
                        coordinator_logger.warning(
                            f"⏸️ Nodo en cadena '{first_chain_node.name}' ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, omitiendo",
                            olt=olt
                        )
                        return
                    
                    # ✅ CRÍTICO: Verificar si OLT está libre (solo 1 nodo a la vez por OLT)
                    # Cada OLT es independiente, no se combina con otras OLTs
                    if not scheduler.is_olt_busy():
                        # Verificar capacidad de Celery
                        if scheduler._check_celery_capacity(job_type):
                            # ✅ WORKFLOW → COORDINADOR: Ejecutar item en cadena inmediatamente
                            executed = scheduler._execute_task_now(task_info, olt)
                            if executed:
                                coordinator_logger.info(
                                    f"📞 WORKFLOW → COORDINADOR: Primer nodo de cadena '{node.name}' ejecutado INMEDIATAMENTE (OLT {olt.abreviatura} libre)",
                                    olt=olt,
                                    event_type='CHAIN_NODE_STARTED'
                                )
                            else:
                                # Si no se pudo ejecutar, encolar (NO SE PIERDE)
                                scheduler.enqueue_task(task_info)
                                coordinator_logger.info(
                                    f"📞 WORKFLOW → COORDINADOR: Primer nodo de cadena '{node.name}' ENCOLADO (OLT {olt.abreviatura} - NO SE PIERDE)",
                                    olt=olt,
                                    event_type='TASK_ADDED'
                                )
                        else:
                            # Celery saturado, encolar (NO SE PIERDE)
                            scheduler.enqueue_task(task_info)
                            coordinator_logger.info(
                                f"📞 WORKFLOW → COORDINADOR: Primer nodo de cadena '{node.name}' ENCOLADO (Celery saturado - OLT {olt.abreviatura} - NO SE PIERDE)",
                                olt=olt,
                                event_type='TASK_ADDED'
                            )
                    else:
                        # OLT ocupada (tiene 1 nodo ejecutándose), encolar (NO SE PIERDE)
                        scheduler.enqueue_task(task_info)
                        coordinator_logger.info(
                            f"📞 WORKFLOW → COORDINADOR: Primer nodo de cadena '{node.name}' ENCOLADO (OLT {olt.abreviatura} ocupada - NO SE PIERDE)",
                            olt=olt,
                            event_type='TASK_ADDED'
                        )
                else:
                    coordinator_logger.warning(
                        f"⏸️ Primer nodo de cadena no puede ejecutarse: {reason}",
                        olt=olt
                    )
        
        # Si el nodo que terminó está en cadena (SUCCESS o FAILED), ejecutar el siguiente nodo de la cadena
        elif workflow_node and status in ['SUCCESS', 'FAILED'] and workflow_node.is_chain_node and workflow_node.master_node:
            master = workflow_node.master_node
            chain_nodes = master.get_chain_nodes()
            
            # Encontrar el siguiente nodo en la cadena
            # Los nodos en cadena están ordenados por prioridad (mayor primero), luego por id
            # Necesitamos encontrar el siguiente después del actual
            all_chain_nodes = list(chain_nodes)
            current_index = None
            
            for i, node in enumerate(all_chain_nodes):
                if node.id == workflow_node.id:
                    current_index = i
                    break
            
            if current_index is not None and current_index < len(all_chain_nodes) - 1:
                # Hay un siguiente nodo en la cadena
                next_node = all_chain_nodes[current_index + 1]
                coordinator_logger.info(
                    f"📞 WORKFLOW → COORDINADOR: Nodo en cadena '{workflow_node.name}' completado, ejecutando siguiente '{next_node.name}' (OLT {olt.abreviatura} - independiente)",
                    olt=olt,
                    event_type='CHAIN_NEXT'
                )
                can_execute, reason = next_node.can_execute_now()
                
                # ✅ CRÍTICO: Verificar que NO haya ejecución PENDING o RUNNING para este nodo en cadena
                from executions.models import Execution
                existing_execution = Execution.objects.filter(
                    workflow_node=next_node,
                    status__in=['PENDING', 'RUNNING']
                ).first()
                
                if existing_execution:
                    coordinator_logger.warning(
                        f"⏸️ Siguiente nodo en cadena '{next_node.name}' ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, omitiendo",
                        olt=olt
                    )
                    can_execute = False
                    reason = f"Ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}"
                
                if can_execute:
                    # ✅ CRÍTICO: Verificar que el nodo anterior (en cadena) haya terminado COMPLETAMENTE
                    from executions.models import Execution
                    import time
                    
                    # Re-verificar el estado de la ejecución del nodo anterior desde la BD
                    previous_execution = None
                    if execution_id:
                        try:
                            previous_execution = Execution.objects.select_related('workflow_node', 'snmp_job').get(id=execution_id)
                        except Execution.DoesNotExist:
                            pass
                    
                    # Si tenemos la ejecución del nodo anterior, verificar que esté completamente terminada
                    if previous_execution:
                        # Verificar que el estado sea final (SUCCESS, FAILED o INTERRUPTED)
                        if previous_execution.status not in ['SUCCESS', 'FAILED', 'INTERRUPTED']:
                            coordinator_logger.warning(
                                f"⏸️ Nodo anterior en cadena '{workflow_node.name}' aún no ha terminado (estado: {previous_execution.status}), esperando...",
                                olt=olt
                            )
                            return
                        
                        # Verificar que finished_at esté establecido
                        if not previous_execution.finished_at:
                            coordinator_logger.warning(
                                f"⏸️ Nodo anterior en cadena '{workflow_node.name}' no tiene finished_at establecido, esperando...",
                                olt=olt
                            )
                            return
                        
                        # Para discovery, verificar que el procesamiento haya terminado
                        if previous_execution.snmp_job and previous_execution.snmp_job.job_type == 'descubrimiento':
                            if not previous_execution.result_summary:
                                coordinator_logger.warning(
                                    f"⏸️ Nodo anterior discovery '{workflow_node.name}' no tiene result_summary, esperando procesamiento...",
                                    olt=olt
                                )
                                return
                            
                            # Verificar que el procesamiento haya terminado
                            result_summary = previous_execution.result_summary
                            if isinstance(result_summary, dict):
                                if 'total_found' not in result_summary and 'new_index_created' not in result_summary:
                                    # Esperar un momento y re-verificar (máximo 3 intentos, 1 segundo cada uno)
                                    max_retries = 3
                                    for retry in range(max_retries):
                                        time.sleep(1)
                                        previous_execution.refresh_from_db()
                                        if previous_execution.result_summary and isinstance(previous_execution.result_summary, dict):
                                            if 'total_found' in previous_execution.result_summary or 'new_index_created' in previous_execution.result_summary:
                                                break
                                    else:
                                        # Si después de los reintentos aún no tiene datos, omitir
                                        coordinator_logger.warning(
                                            f"⏸️ Nodo anterior discovery '{workflow_node.name}' aún procesando datos después de {max_retries} intentos, omitiendo siguiente nodo",
                                            olt=olt
                                        )
                                        return
                    
                    # Preparar task_info
                    node = next_node
                    
                    # Determinar tipo y prioridad desde el OID (directo o desde template_node)
                    oid = node.oid or (node.template_node.oid if node.template_node else None)
                    if oid:
                        if oid.espacio == 'descubrimiento':
                            job_type = 'descubrimiento'
                            priority = node.priority or 90
                        else:
                            job_type = 'get'
                            priority = node.priority or 40
                    else:
                        # Sin OID, no se puede ejecutar
                        coordinator_logger.warning(
                            f"⏸️ Nodo en cadena '{node.name}' no tiene OID asociado, no se puede ejecutar",
                            olt=olt
                        )
                        can_execute = False
                        reason = "Nodo no tiene OID asociado"
                    
                    if not can_execute:
                        return
                    
                    # Re-verificar que no haya ejecución PENDING o RUNNING para el siguiente nodo
                    existing_execution = Execution.objects.filter(
                        workflow_node=next_node,
                        status__in=['PENDING', 'RUNNING']
                    ).first()
                    
                    if existing_execution:
                        coordinator_logger.warning(
                            f"⏸️ Siguiente nodo en cadena '{next_node.name}' ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, omitiendo",
                            olt=olt
                        )
                        return
                        
                    # Preparar task_info para el siguiente nodo en cadena
                        task_info = {
                        'workflow_node_id': next_node.id,
                        'node_name': next_node.name,
                        'node_key': next_node.key,
                            'job_type': job_type,
                            'priority': priority,
                        'interval_seconds': next_node.interval_seconds,
                            'is_chain_node': True,
                        'master_node_id': next_node.master_node.id if next_node.master_node else None,
                        }
                        
                    # ✅ CRÍTICO: Verificar si OLT está libre (solo 1 nodo a la vez por OLT)
                    # Cada OLT es independiente, no se combina con otras OLTs
                        if not scheduler.is_olt_busy():
                            # Verificar capacidad de Celery
                            if scheduler._check_celery_capacity(job_type):
                            # ✅ WORKFLOW → COORDINADOR: Ejecutar siguiente nodo en cadena inmediatamente
                                executed = scheduler._execute_task_now(task_info, olt)
                                if executed:
                                    coordinator_logger.info(
                                    f"📞 WORKFLOW → COORDINADOR: Siguiente nodo de cadena '{next_node.name}' EJECUTADO INMEDIATAMENTE (OLT {olt.abreviatura} libre)",
                                        olt=olt,
                                        event_type='CHAIN_NODE_STARTED'
                                    )
                            else:
                                # Si no se pudo ejecutar, encolar (NO SE PIERDE)
                                scheduler.enqueue_task(task_info)
                                coordinator_logger.info(
                                    f"📞 WORKFLOW → COORDINADOR: Siguiente nodo de cadena '{next_node.name}' ENCOLADO (no se pudo ejecutar - NO SE PIERDE) en OLT {olt.abreviatura}",
                                    olt=olt,
                                    event_type='TASK_ADDED'
                                )
                        else:
                            # Celery saturado, encolar (NO SE PIERDE)
                            scheduler.enqueue_task(task_info)
                            coordinator_logger.info(
                                f"📞 WORKFLOW → COORDINADOR: Siguiente nodo de cadena '{next_node.name}' ENCOLADO (Celery saturado - OLT {olt.abreviatura} - NO SE PIERDE)",
                                olt=olt,
                                event_type='TASK_ADDED'
                            )
                    else:
                        # OLT ocupada, encolar (NO SE PIERDE)
                        scheduler.enqueue_task(task_info)
                        coordinator_logger.info(
                            f"📞 WORKFLOW → COORDINADOR: Siguiente nodo de cadena '{next_node.name}' ENCOLADO (OLT {olt.abreviatura} ocupada - NO SE PIERDE)",
                                olt=olt,
                                event_type='TASK_ADDED'
                            )
                else:
                    coordinator_logger.debug(
                        f"⏸️ Siguiente nodo de cadena no puede ejecutarse: {reason}",
                        olt=olt
                    )
            else:
                coordinator_logger.info(
                    f"✓ Cadena completada: '{workflow_node.name}' fue el último nodo",
                    olt=olt,
                    event_type='CHAIN_COMPLETED'
                )
        
        # Verificar si hay tareas en cola (además de las cadenas)
        queue_items = redis_client.lrange(scheduler.queue_key, 0, -1)
        
        if queue_items:
            # LOCK TEMPORAL: Evitar que coordinator loop interfiera mientras procesamos cola
            processing_key = f"lock:processing_queue:{olt_id}"
            redis_client.set(processing_key, '1', ex=10)  # 10 segundos
            
            try:
                # Ejecutar la siguiente desde cola
                coordinator_logger.info(
                    f"🔄 Hay {len(queue_items)} tarea(s) en cola, ejecutando siguiente INMEDIATAMENTE",
                    olt=olt,
                    event_type='EXECUTION_STARTED'
                )
                
                executed = scheduler.execute_next_in_queue(olt)
                
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
                coordinator_logger.error(
                    f"❌ Error procesando cola: {queue_error}",
                    olt=olt,
                    event_type='EXECUTION_ERROR'
                )
            
            finally:
                # Liberar lock de procesamiento
                redis_client.delete(processing_key)
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

