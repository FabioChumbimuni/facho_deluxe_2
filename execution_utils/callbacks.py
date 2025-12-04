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
# DESACTIVADO: DynamicScheduler eliminado - ahora se usa el sistema de pollers Zabbix
# from .dynamic_scheduler import DynamicScheduler

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
    from datetime import timedelta
    
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
            
            # ✅ ACTUALIZAR next_run_at solo si es un nodo MASTER (no encadenado)
            # Los nodos encadenados no tienen next_run_at
            if not execution.workflow_node.is_chain_node and execution.workflow_node.interval_seconds:
                # Calcular siguiente ejecución: ahora + intervalo
                execution.workflow_node.next_run_at = now + timedelta(seconds=execution.workflow_node.interval_seconds)
                execution.workflow_node.save(update_fields=['last_success_at', 'last_failure_at', 'last_run_at', 'next_run_at'])
                logger.debug(
                    f"✅ WorkflowNode {execution.workflow_node.id} (MASTER) actualizado: "
                    f"next_run_at={execution.workflow_node.next_run_at}, "
                    f"last_run_at={execution.workflow_node.last_run_at}"
                )
            else:
                # Nodo encadenado: solo actualizar last_run_at
                execution.workflow_node.save(update_fields=['last_success_at', 'last_failure_at', 'last_run_at'])
                logger.debug(
                    f"✅ WorkflowNode {execution.workflow_node.id} (encadenado) actualizado: "
                    f"last_run_at={execution.workflow_node.last_run_at}"
                )
            
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
    2. Actualiza métricas de pollers si la ejecución fue creada por el sistema de pollers
    3. Libera el lock de la OLT
    4. Verifica si hay tareas en cola esperando
    5. Ejecuta INMEDIATAMENTE la siguiente tarea de mayor prioridad
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
                
                # ✅ ACTUALIZAR MÉTRICAS DE POLLERS si la ejecución fue creada por el sistema de pollers
                # Las ejecuciones creadas por pollers tienen workflow_node y poller_id en result_summary
                if workflow_node:
                    try:
                        from zabbix_pollers.tasks import get_poller_manager
                        poller_manager = get_poller_manager()
                        
                        # ✅ CORREGIDO: Buscar el poller que realmente ejecutó esta tarea usando poller_id
                        poller_id = None
                        if execution.result_summary and isinstance(execution.result_summary, dict):
                            poller_id = execution.result_summary.get('poller_id')
                        
                        target_poller = None
                        if poller_id is not None and poller_manager.pollers:
                            # Buscar el poller específico que ejecutó esta tarea
                            for poller in poller_manager.pollers:
                                if poller.poller_id == poller_id:
                                    target_poller = poller
                                    break
                        
                        # Si no se encontró por poller_id, usar el que tiene current_execution_id
                        if not target_poller and poller_manager.pollers:
                            for poller in poller_manager.pollers:
                                if poller.current_execution_id == execution_id:
                                    target_poller = poller
                                    break
                        
                        # Si aún no se encontró, usar el que menos tareas haya completado (fallback)
                        if not target_poller and poller_manager.pollers:
                            target_poller = min(poller_manager.pollers, key=lambda p: p.tasks_completed)
                        
                        if target_poller:
                            # Actualizar métricas del poller que realmente ejecutó la tarea
                            with target_poller.lock:
                                if status == 'SUCCESS':
                                    target_poller.tasks_completed += 1
                                    # Actualizar busy_time con la duración real
                                    if duration_ms:
                                        target_poller.busy_time += (duration_ms / 1000.0)  # Convertir ms a segundos
                                elif status == 'FAILED':
                                    # También contar fallos como tareas procesadas
                                    target_poller.tasks_completed += 1
                                    if duration_ms:
                                        target_poller.busy_time += (duration_ms / 1000.0)
                                
                                # Actualizar total_time
                                now = timezone.now()
                                target_poller.total_time = (now - target_poller.start_time).total_seconds()
                                
                                # ✅ MEJORADO: Liberar poller de forma más robusta
                                # Verificar múltiples condiciones para asegurar que se libere correctamente
                                should_free = False
                                reason = ""
                                
                                # Condición 1: current_execution_id coincide exactamente
                                if target_poller.current_execution_id == execution_id:
                                    # Verificar que la ejecución realmente terminó (doble verificación)
                                    try:
                                        exec_check = Execution.objects.only('status').get(id=execution_id)
                                        if exec_check.status in ['SUCCESS', 'FAILED', 'INTERRUPTED']:
                                            should_free = True
                                            reason = f"current_execution_id coincide y execution terminó ({exec_check.status})"
                                    except Execution.DoesNotExist:
                                        # La ejecución no existe, liberar de todas formas
                                        should_free = True
                                        reason = f"current_execution_id coincide pero execution {execution_id} no existe"
                                
                                # ✅ CRÍTICO: Si el poller está BUSY pero no tiene current_execution_id válido, liberarlo
                                # Esto previene que los pollers queden bloqueados permanentemente
                                if target_poller.status == 'BUSY' and not should_free:
                                    # Verificar si la ejecución asociada realmente terminó
                                    if target_poller.current_execution_id:
                                        try:
                                            exec_check = Execution.objects.only('status').get(id=target_poller.current_execution_id)
                                            if exec_check.status in ['SUCCESS', 'FAILED', 'INTERRUPTED']:
                                                should_free = True
                                                reason = f"poller BUSY pero execution {target_poller.current_execution_id} terminó ({exec_check.status})"
                                        except Execution.DoesNotExist:
                                            # La ejecución no existe, liberar el poller
                                            should_free = True
                                            reason = f"execution {target_poller.current_execution_id} no existe en BD"
                                    else:
                                        # No tiene execution_id pero está BUSY, liberarlo
                                        should_free = True
                                        reason = "poller BUSY sin current_execution_id"
                                
                                if should_free:
                                    old_status = target_poller.status
                                    old_execution_id = target_poller.current_execution_id
                                    target_poller.status = 'FREE'
                                    target_poller.current_composite_node = None
                                    target_poller.current_execution_id = None
                                    logger.info(
                                        f"✅ Poller {target_poller.poller_id} liberado: {reason} "
                                        f"(status: {old_status}→FREE, execution_id: {old_execution_id}→None)"
                                    )
                            
                            logger.debug(
                                f"✅ Poller {target_poller.poller_id} actualizado: "
                                f"tasks_completed={target_poller.tasks_completed}, "
                                f"busy_time={target_poller.busy_time:.2f}s, "
                                f"status={target_poller.status}"
                            )
                    except Exception as poller_error:
                        # No es crítico si falla la actualización de métricas de pollers
                        logger.debug(f"Error actualizando métricas de pollers: {poller_error}")
                        
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
        
        # ✅ DESACTIVADO: DynamicScheduler eliminado - ahora se usa el sistema de pollers Zabbix
        # Los nodos en cadena se ejecutarán automáticamente por el scheduler de pollers
        # cuando detecte que el nodo master terminó
        
        # ✅ WORKFLOW → POLLERS: El workflow usa el sistema de pollers Zabbix para ejecutar items en cadena
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
                # ✅ CRÍTICO: Usar lock de Redis para evitar ejecuciones duplicadas del nodo encadenado
                # Múltiples callbacks pueden ejecutarse simultáneamente cuando el master termina
                from redis import Redis
                from django.conf import settings
                from redis.lock import Lock as RedisLock
                
                redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
                # Lock específico para este master y su primer nodo encadenado
                first_chain_node = chain_nodes.first()
                lock_key = f"lock:chain_execution:master:{workflow_node.id}:chain:{first_chain_node.id}"
                lock = RedisLock(redis_client, lock_key, timeout=30)  # 30 segundos timeout
                
                # Intentar adquirir lock (timeout de 0 = no bloquear)
                if not lock.acquire(blocking=False):
                    # Otro callback ya está ejecutando este nodo encadenado
                    coordinator_logger.debug(
                        f"🔒 Lock activo para ejecución de nodo encadenado '{first_chain_node.name}' "
                        f"después de master '{workflow_node.name}', otro callback ya lo está procesando (OLT {olt.abreviatura})",
                        olt=olt
                    )
                    return
                
                try:
                    coordinator_logger.info(
                        f"📞 WORKFLOW → COORDINADOR: Master '{workflow_node.name}' completado, ejecutando {chain_nodes.count()} nodo(s) en cadena (OLT {olt.abreviatura} - independiente)",
                        olt=olt,
                        event_type='CHAIN_STARTED'
                    )
                    
                    # Ejecutar el primer nodo de la cadena (mayor prioridad)
                    
                    # ✅ Verificar que el nodo en cadena tenga OID (directo o desde template_node)
                    oid_check = first_chain_node.oid or (first_chain_node.template_node.oid if first_chain_node.template_node else None)
                    if not oid_check:
                        coordinator_logger.warning(
                            f"⏸️ Nodo en cadena '{first_chain_node.name}' no tiene OID asociado, no se puede ejecutar",
                            olt=olt
                        )
                        return
                    
                    # ✅ CRÍTICO: Verificar PRIMERO que NO haya ejecución PENDING o RUNNING para este nodo en cadena
                    # Esto debe hacerse ANTES de can_execute_now() para evitar condiciones de carrera
                    from executions.models import Execution
                    existing_execution = Execution.objects.filter(
                        workflow_node=first_chain_node,
                        status__in=['PENDING', 'RUNNING']
                    ).first()
                    
                    if existing_execution:
                        coordinator_logger.debug(
                            f"🔒 Nodo en cadena '{first_chain_node.name}' ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, "
                            f"omitiendo (evita duplicados) - OLT {olt.abreviatura}",
                            olt=olt
                        )
                        return  # Salir inmediatamente, no intentar ejecutar
                    
                    # Ahora verificar que el nodo pueda ejecutarse (incluye verificación de plantilla activa)
                    can_execute, reason = first_chain_node.can_execute_now()
                    
                    if not can_execute:
                        coordinator_logger.debug(
                            f"⏸️ Nodo en cadena '{first_chain_node.name}' no puede ejecutarse: {reason} - OLT {olt.abreviatura}",
                            olt=olt
                        )
                        return  # Salir si no puede ejecutarse
                    
                    # Si llegamos aquí, can_execute es True
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
                        return
                    
                    # ✅ DOBLE VERIFICACIÓN: Re-verificar que no haya ejecución PENDING o RUNNING para el nodo de cadena
                    # Esto es una verificación adicional después de todas las validaciones del master
                    existing_execution = Execution.objects.filter(
                        workflow_node=first_chain_node,
                        status__in=['PENDING', 'RUNNING']
                    ).first()
                    
                    if existing_execution:
                        coordinator_logger.debug(
                            f"🔒 Nodo en cadena '{first_chain_node.name}' ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, "
                            f"omitiendo (doble verificación) - OLT {olt.abreviatura}",
                            olt=olt
                        )
                        return
                    
                    # ✅ DESACTIVADO: DynamicScheduler eliminado
                    # Los nodos en cadena se ejecutarán automáticamente por el scheduler de pollers Zabbix
                    # cuando detecte que el nodo master terminó y el next_run_at esté listo
                    try:
                        from zabbix_pollers.tasks import get_poller_manager
                        from zabbix_pollers.composite_node import CompositeNode
                        from snmp_jobs.models import WorkflowNode
                        
                        poller_manager = get_poller_manager()
                        
                        # Crear nodo compuesto para el primer nodo de la cadena
                        # (solo el primer nodo, los demás se ejecutarán cuando este termine)
                        master_node = WorkflowNode.objects.select_related('workflow', 'workflow__olt').get(id=first_chain_node.id)
                        # Para nodos en cadena, el "master" es el nodo en cadena mismo
                        composite_node = CompositeNode(master_node, [], master_node.workflow, olt)
                        
                        # ✅ CRÍTICO: Intentar asignar directamente (sin verificar is_olt_busy primero)
                        # porque el master ya terminó, la OLT debería estar libre
                        # Si la OLT está ocupada, assign_node() lo encolará automáticamente
                        try:
                            poller_manager.assign_node(composite_node)
                            coordinator_logger.info(
                                f"📞 WORKFLOW → POLLERS: Primer nodo de cadena '{node.name}' asignado/encolado (OLT {olt.abreviatura})",
                                olt=olt,
                                event_type='CHAIN_NODE_STARTED'
                            )
                        except Exception as assign_error:
                            # Si falla la asignación, encolar directamente
                            poller_manager.queue.put(composite_node)
                            coordinator_logger.warning(
                                f"⚠️ WORKFLOW → POLLERS: Error asignando nodo de cadena '{node.name}', encolado directamente (OLT {olt.abreviatura}): {assign_error}",
                                olt=olt,
                                event_type='TASK_ADDED'
                            )
                    except Exception as e:
                        logger.warning(f"Error asignando nodo en cadena a pollers: {e}")
                finally:
                    # Liberar lock después de procesar
                    try:
                        # Verificar si el lock todavía es propiedad de este proceso antes de liberarlo
                        # Esto evita el error "Cannot release a lock that's no longer owned"
                        if lock.owned():
                            lock.release()
                    except Exception:
                        pass  # Ignorar errores al liberar lock (normal si expiró o fue liberado)
        
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
                
                # ✅ CRÍTICO: Usar lock de Redis para evitar ejecuciones duplicadas del siguiente nodo
                from redis import Redis
                from django.conf import settings
                from redis.lock import Lock as RedisLock
                
                redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
                # Lock específico para este siguiente nodo en cadena
                lock_key = f"lock:chain_execution:chain:{next_node.id}"
                lock = RedisLock(redis_client, lock_key, timeout=30)  # 30 segundos timeout
                
                # Intentar adquirir lock (timeout de 0 = no bloquear)
                if not lock.acquire(blocking=False):
                    # Otro callback ya está ejecutando este siguiente nodo
                    coordinator_logger.debug(
                        f"🔒 Lock activo para ejecución de siguiente nodo en cadena '{next_node.name}', "
                        f"otro callback ya lo está procesando (OLT {olt.abreviatura})",
                        olt=olt
                    )
                    return
                
                try:
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
                            
                        # ✅ DESACTIVADO: DynamicScheduler eliminado
                        # Los nodos en cadena se ejecutarán automáticamente por el scheduler de pollers Zabbix
                        try:
                            from zabbix_pollers.tasks import get_poller_manager
                            from zabbix_pollers.composite_node import CompositeNode
                            from snmp_jobs.models import WorkflowNode
                            
                            poller_manager = get_poller_manager()
                            
                            # Crear nodo compuesto para el siguiente nodo en la cadena
                            next_master = WorkflowNode.objects.select_related('workflow', 'workflow__olt').get(id=next_node.id)
                            composite_node = CompositeNode(next_master, [], next_master.workflow, olt)
                            
                            # Intentar asignar a un poller
                            if poller_manager.has_free_poller():
                                poller_manager.assign_node(composite_node)
                                coordinator_logger.info(
                                    f"📞 WORKFLOW → POLLERS: Siguiente nodo de cadena '{next_node.name}' asignado a poller (OLT {olt.abreviatura})",
                                    olt=olt,
                                    event_type='CHAIN_NODE_STARTED'
                                )
                            else:
                                # No hay pollers libres, encolar en el sistema de pollers
                                poller_manager.queue.put(composite_node)
                                coordinator_logger.info(
                                    f"📞 WORKFLOW → POLLERS: Siguiente nodo de cadena '{next_node.name}' encolado en sistema de pollers (OLT {olt.abreviatura})",
                                    olt=olt,
                                    event_type='TASK_ADDED'
                                )
                        except Exception as e:
                            logger.warning(f"Error asignando siguiente nodo en cadena a pollers: {e}")
                    else:
                        coordinator_logger.debug(
                            f"⏸️ Siguiente nodo de cadena no puede ejecutarse: {reason}",
                            olt=olt
                        )
                finally:
                    # Liberar lock después de procesar
                    try:
                        # Verificar si el lock todavía es propiedad de este proceso antes de liberarlo
                        # Esto evita el error "Cannot release a lock that's no longer owned"
                        if lock.owned():
                            lock.release()
                    except Exception:
                        pass  # Ignorar errores al liberar lock (normal si expiró o fue liberado)
            else:
                coordinator_logger.info(
                    f"✓ Cadena completada: '{workflow_node.name}' fue el último nodo",
                    olt=olt,
                    event_type='CHAIN_COMPLETED'
                )
        
        # ✅ DESACTIVADO: DynamicScheduler eliminado
        # El sistema de pollers Zabbix maneja la cola automáticamente
        # No es necesario procesar cola aquí, el scheduler de pollers lo hace cada segundo
        
    except OLT.DoesNotExist:
        logger.error(f"OLT {olt_id} no existe")
    except Exception as e:
        logger.error(f"Error en callback de tarea completada: {e}")


def on_task_failed(olt_id, task_name, task_type, error_message, execution_id=None):
    """
    Callback cuando una tarea SNMP falla
    
    Similar a on_task_completed pero con manejo de error
    También libera pollers asociados a la ejecución fallida
    ✅ CRÍTICO: Actualiza next_run_at del WorkflowNode para evitar ejecuciones duplicadas
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
                'error': error_message,
                'execution_id': execution_id
            }
        )
        
        # ✅ CRÍTICO: Actualizar next_run_at del WorkflowNode si existe
        # Esto evita que el scheduler cree nuevas ejecuciones inmediatamente
        if execution_id:
            try:
                update_workflow_node_on_completion(execution_id, 'FAILED')
            except Exception as update_error:
                logger.warning(f"⚠️ Error actualizando WorkflowNode en on_task_failed: {update_error}")
        
        # ✅ MEJORADO: Liberar poller asociado a la ejecución fallida
        if execution_id:
            try:
                from executions.models import Execution
                from zabbix_pollers.tasks import get_poller_manager
                
                execution = Execution.objects.select_related('workflow_node').get(id=execution_id)
                
                if execution.workflow_node:
                    poller_manager = get_poller_manager()
                    
                    # Buscar poller asociado
                    poller_id = None
                    if execution.result_summary and isinstance(execution.result_summary, dict):
                        poller_id = execution.result_summary.get('poller_id')
                    
                    target_poller = None
                    if poller_id is not None:
                        for poller in poller_manager.pollers:
                            if poller.poller_id == poller_id:
                                target_poller = poller
                                break
                    
                    # Si no se encontró por poller_id, buscar por current_execution_id
                    if not target_poller:
                        for poller in poller_manager.pollers:
                            if poller.current_execution_id == execution_id:
                                target_poller = poller
                                break
                    
                    if target_poller:
                        with target_poller.lock:
                            old_status = target_poller.status
                            old_execution_id = target_poller.current_execution_id
                            target_poller.status = 'FREE'
                            target_poller.current_composite_node = None
                            target_poller.current_execution_id = None
                            logger.info(
                                f"✅ Poller {target_poller.poller_id} liberado después de fallo: "
                                f"execution {execution_id} falló "
                                f"(status: {old_status}→FREE, execution_id: {old_execution_id}→None)"
                            )
            except Exception as poller_error:
                logger.debug(f"Error liberando poller después de fallo: {poller_error}")
        
        # Liberar lock
        lock_key = f"lock:execution:olt:{olt_id}"
        redis_client.delete(lock_key)
        
        # ✅ DESACTIVADO: DynamicScheduler eliminado
        # El sistema de pollers Zabbix maneja la cola automáticamente
        
    except Exception as e:
        logger.error(f"Error en callback de tarea fallida: {e}")

