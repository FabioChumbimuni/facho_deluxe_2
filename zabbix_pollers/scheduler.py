"""
Scheduler Zabbix: Loop principal que identifica nodos listos cada 1 segundo
Reemplaza al coordinator_loop_task
"""
import time
import logging
from django.utils import timezone
from typing import List

from .poller_manager import PollerManager
from .composite_node import CompositeNode

logger = logging.getLogger(__name__)


class ZabbixScheduler:
    """
    Scheduler estilo Zabbix que reemplaza al coordinador
    
    Funcionamiento:
    - Loop cada 1 segundo
    - Identifica nodos listos (nextcheck <= now)
    - Agrupa nodos master + encadenados = 1 nodo compuesto
    - Calcula delay y marca como delayed
    - Envía a PollerManager
    """
    
    def __init__(self, poller_manager: PollerManager):
        self.poller_manager = poller_manager
        self.running = False
        self.loop_count = 0
    
    def scheduler_iteration(self):
        """
        Ejecutar UNA iteración del scheduler
        Se llama cada 1 segundo desde Celery Beat
        
        Reemplaza coordinator_loop_task
        
        IMPORTANTE: Esta función debe ejecutarse rápidamente (< 1 segundo).
        Si toma más tiempo, hay un problema de rendimiento.
        """
        try:
            now = timezone.now()
            self.loop_count += 1
            
            # 1. Identificar nodos listos (solo masters, los encadenados no tienen nextcheck)
            ready_nodes = self._get_ready_nodes(now)
            
            # 2. Agrupar nodos master + encadenados como nodos compuestos
            composite_nodes = self._group_chain_nodes(ready_nodes, now)
            
            # 3. Ordenar por prioridad (delayed primero, mayor delay primero, mayor prioridad primero)
            composite_nodes.sort(key=lambda n: (
                not n.delayed,      # Delayed primero (False < True)
                -n.delay_time,      # Mayor delay primero
                -n.priority         # Mayor prioridad primero
            ))
            
            # 4. Asignar a pollers o encolar (TODOS los nodos deben ejecutarse, NUNCA omitir)
            assigned = 0
            queued = 0
            
            # Solo loguear si hay nodos para procesar
            if composite_nodes:
                logger.info(f"📊 Iteración {self.loop_count}: {len(composite_nodes)} nodo(s) compuesto(s) listo(s)")
            
            # ✅ CRÍTICO: TODOS los nodos deben ejecutarse, nunca omitir
            # Procesar todos los nodos, asignando a pollers o encolando
            for composite_node in composite_nodes:
                # ✅ OPTIMIZACIÓN: Verificar si hay poller libre antes de intentar asignar
                has_free = self.poller_manager.has_free_poller()
                
                if has_free:
                    try:
                        self.poller_manager.assign_node(composite_node)
                        assigned += 1
                        logger.debug(f"✅ Nodo compuesto '{composite_node.name}' asignado a poller (OLT: {composite_node.olt.abreviatura})")
                    except Exception as e:
                        logger.warning(f"⚠️ Error asignando nodo '{composite_node.name}': {e}")
                        # ✅ CRÍTICO: Si falla la asignación, ENCOLAR (nunca perder)
                        self.poller_manager.queue.put(composite_node)
                        queued += 1
                        logger.debug(f"📥 Nodo compuesto '{composite_node.name}' encolado después de error (OLT: {composite_node.olt.abreviatura})")
                else:
                    # ✅ CRÍTICO: Si no hay poller libre, ENCOLAR (nunca perder)
                    self.poller_manager.queue.put(composite_node)
                    queued += 1
                    logger.debug(f"📥 Nodo compuesto '{composite_node.name}' encolado (OLT: {composite_node.olt.abreviatura})")
            
            if assigned > 0 or queued > 0:
                logger.debug(f"  → {assigned} asignado(s), {queued} encolado(s)")
            
            # 5. Procesar cola cuando hay pollers libres
            # ✅ AUMENTADO: Procesar más nodos de la cola para que los encadenados se ejecuten más rápido
            processed_from_queue = self.poller_manager.process_queue(max_nodes=10)
            if processed_from_queue > 0:
                logger.debug(f"  → {processed_from_queue} procesado(s) desde cola")
            
            # 6. Log de saturación si aplica (solo cada 10 iteraciones para no saturar logs)
            if self.loop_count % 10 == 0 and self.poller_manager.is_saturated():
                stats = self.poller_manager.get_stats()
                # ✅ MEJORADO: Mensaje más descriptivo con explicación
                busy_pct = stats['busy_percentage']
                queue_size = stats['queue_size']
                busy_pollers = stats['busy_pollers']
                total_pollers = stats['total_pollers']
                
                # Determinar razón de saturación
                reasons = []
                if busy_pct > 75:
                    reasons.append(f"busy={busy_pct:.1f}%")
                if queue_size > self.poller_manager.start_pollers * 2:
                    reasons.append(f"cola={queue_size} (límite: {self.poller_manager.start_pollers * 2})")
                if busy_pollers == total_pollers and queue_size > 0:
                    reasons.append(f"todos los pollers ocupados ({busy_pollers}/{total_pollers}) con {queue_size} en cola")
                
                reason_str = " | ".join(reasons) if reasons else "desconocida"
                logger.warning(
                    f"⚠️ Sistema saturado: {reason_str}"
                )
            
        except Exception as e:
            logger.error(f"❌ Error en scheduler iteration: {e}", exc_info=True)
    
    def scheduler_loop(self):
        """
        Loop infinito del scheduler (para uso directo, no desde Celery)
        DEPRECADO: Usar scheduler_iteration() desde Celery Beat
        """
        logger.warning("⚠️ scheduler_loop() está deprecado. Usar scheduler_iteration() desde Celery Beat")
        self.running = True
        
        while self.running:
            self.scheduler_iteration()
            time.sleep(1)
    
    def _get_ready_nodes(self, now):
        """
        Identificar nodos listos (nextcheck <= now)
        Incluye:
        1. Nodos master con next_run_at <= now
        2. Nodos encadenados cuyo master haya terminado recientemente (sin next_run_at)
        
        ✅ RESPETA MODO PRUEBA: El modo prueba se maneja automáticamente
        en las tareas de Celery (discovery_main_task, get_main_task),
        pero el scheduler puede continuar ejecutando normalmente.
        
        ⚠️ EXCLUYE nodos que ya tienen una Execution en estado PENDING o RUNNING
        para evitar ejecuciones duplicadas.
        """
        from snmp_jobs.models import WorkflowNode, OLTWorkflow
        from hosts.models import OLT
        from executions.models import Execution
        from datetime import timedelta
        
        # ✅ OPTIMIZACIÓN: Obtener IDs de OLTs con ejecuciones activas de una vez
        busy_olt_ids = set(
            Execution.objects.filter(
                status__in=['PENDING', 'RUNNING']
            ).values_list('olt_id', flat=True).distinct()
        )
        
        # ✅ OPTIMIZACIÓN: Obtener IDs de nodos con ejecuciones activas de una vez
        busy_node_ids = set(
            Execution.objects.filter(
                status__in=['PENDING', 'RUNNING'],
                workflow_node__isnull=False
            ).values_list('workflow_node_id', flat=True).distinct()
        )
        
        # ✅ NUEVO: Obtener nodos encadenados cuyo master haya terminado recientemente
        # Buscar masters que terminaron en los últimos 5 minutos y tienen nodos encadenados
        recent_master_finish = now - timedelta(minutes=5)
        recent_master_execs = Execution.objects.filter(
            workflow_node__is_chain_node=False,
            status__in=['SUCCESS', 'FAILED'],
            finished_at__gte=recent_master_finish
        ).select_related('workflow_node').values_list('workflow_node_id', flat=True).distinct()
        
        # Obtener nodos encadenados de estos masters que no tienen ejecuciones activas
        ready_chain_nodes = []
        if recent_master_execs:
            from django.db.models import Q
            ready_chain_nodes = WorkflowNode.objects.filter(
                is_chain_node=True,
                master_node_id__in=recent_master_execs,
                enabled=True,
                workflow__is_active=True  # ✅ CORREGIDO: Usar is_active en lugar de enabled
            ).exclude(
                id__in=busy_node_ids
            ).select_related('workflow', 'workflow__olt', 'master_node')
            
            # ✅ CRÍTICO: NO agregar nodos encadenados aquí - el callback los ejecuta automáticamente
            # Si los agregamos aquí, se ejecutarán dos veces: una por el callback y otra por el scheduler
            # El callback ya tiene locks de Redis para evitar duplicados, pero es mejor evitar conflictos
            # Dejamos que solo el callback ejecute nodos encadenados
            verified_chain_nodes = []
            # Comentado: El callback maneja la ejecución de nodos encadenados automáticamente
            # ready_chain_nodes = verified_chain_nodes
            ready_chain_nodes = []  # ✅ DESACTIVADO: Solo el callback ejecuta nodos encadenados
        
        # Obtener workflows activos (excluyendo OLTs eliminadas)
        active_workflows = OLTWorkflow.objects.filter(
            is_active=True,
            olt__is_deleted=False  # ✅ Excluir workflows de OLTs eliminadas
        ).select_related('olt')
        
        ready_nodes = []
        for workflow in active_workflows:
            # ✅ OPTIMIZACIÓN: Saltar workflows de OLTs ocupadas
            if workflow.olt_id in busy_olt_ids:
                continue
            
            # Solo nodos master (no encadenados) que están listos
            nodes = WorkflowNode.objects.filter(
                workflow=workflow,
                enabled=True,
                is_chain_node=False,  # Solo masters
                next_run_at__lte=now,
                next_run_at__isnull=False
            ).select_related('workflow__olt', 'template_node', 'oid')
            
            # Filtrar nodos que ya tienen una Execution en ejecución
            for node in nodes:
                # ✅ OPTIMIZACIÓN: Verificar en memoria en lugar de consulta BD
                if node.id in busy_node_ids:
                    continue
                
                # ✅ CRÍTICO: Verificar que el nodo pueda ejecutarse (incluye verificación de plantilla activa)
                # Esto verifica: OLT habilitada, workflow activo, plantilla activa (si aplica), nodo habilitado
                if not node.can_execute_now()[0]:
                    continue
                
                # ✅ OPTIMIZACIÓN: Ya verificamos que la OLT no está ocupada arriba
                ready_nodes.append(node)
        
        # ✅ DESACTIVADO: Los nodos encadenados se ejecutan automáticamente por el callback
        # cuando el master termina. No los agregamos aquí para evitar ejecuciones duplicadas.
        # El callback tiene locks de Redis para prevenir duplicados, pero es mejor evitar conflictos.
        # if ready_chain_nodes:
        #     ready_nodes.extend(ready_chain_nodes)
        #     logger.debug(f"✅ Agregados {len(ready_chain_nodes)} nodo(s) encadenado(s) listo(s) (master terminó)")
        
        return ready_nodes
    
    def _group_chain_nodes(self, nodes, now):
        """
        Agrupa nodos master + encadenados como nodos compuestos
        
        Un nodo master con 6 encadenados = 1 nodo compuesto
        La demora de ejecución incluye todos los encadenados
        
        ✅ NUEVO: También maneja nodos encadenados individuales (sin master en la lista)
        que se ejecutan después de que su master terminó. Estos se tratan como
        nodos compuestos individuales donde el encadenado actúa como su propio "master".
        """
        composite_nodes = []
        processed_master_ids = set()
        processed_chain_ids = set()
        
        for node in nodes:
            if node.id in processed_master_ids or node.id in processed_chain_ids:
                continue
            
            # ✅ NUEVO: Si es un nodo encadenado sin su master en la lista,
            # crear un nodo compuesto individual (el encadenado es su propio "master")
            if node.is_chain_node:
                # Crear nodo compuesto donde el encadenado actúa como master
                composite = CompositeNode(
                    master=node,  # El encadenado es su propio master para ejecución
                    chain_nodes=[],  # No tiene más encadenados
                    workflow=node.workflow,
                    olt=node.workflow.olt
                )
                composite.calculate_delay(now)
                composite_nodes.append(composite)
                processed_chain_ids.add(node.id)
                logger.debug(f"✅ Nodo encadenado '{node.name}' agrupado como nodo compuesto individual (master terminó)")
                continue
            
            # Es un nodo master, obtener sus encadenados
            # Obtener nodos encadenados habilitados
            chain_nodes = node.chain_nodes.filter(enabled=True).order_by('priority', 'id')
            
            # Crear nodo compuesto
            composite = CompositeNode(
                master=node,
                chain_nodes=list(chain_nodes),
                workflow=node.workflow,
                olt=node.workflow.olt
            )
            
            # Calcular delay
            composite.calculate_delay(now)
            
            composite_nodes.append(composite)
            processed_master_ids.add(node.id)
            
            # Marcar encadenados como procesados (no se procesan por separado)
            for chain_node in chain_nodes:
                processed_chain_ids.add(chain_node.id)
        
        return composite_nodes
    
    def stop(self):
        """Detener el scheduler"""
        self.running = False
        logger.info("⏹️ Zabbix Scheduler detenido")

