"""
Poller Manager: Gestiona múltiples pollers paralelos con protección OLT
"""
from threading import Thread, Lock
from typing import List, Optional
from django.utils import timezone
import logging

from .poller import Poller
from .node_queue import NodeQueue
from .composite_node import CompositeNode

logger = logging.getLogger(__name__)


class PollerManager:
    """
    Gestiona múltiples pollers paralelos estilo Zabbix
    Con protección OLT (1 nodo a la vez por OLT)
    """
    
    def __init__(self, start_pollers: int = 10):
        self.start_pollers = start_pollers
        self.pollers: List[Poller] = []
        self.queue = NodeQueue()
        self.lock = Lock()
        
        # Crear pollers
        for i in range(start_pollers):
            poller = Poller(poller_id=i)
            self.pollers.append(poller)
        
        logger.info(f"✅ PollerManager inicializado con {start_pollers} pollers")
    
    def has_free_poller(self) -> bool:
        """
        Verificar si hay poller libre
        
        ✅ OPTIMIZADO: Verificación rápida sin consultas pesadas a BD.
        Usa el estado interno del poller y solo verifica BD si es necesario.
        """
        with self.lock:
            for poller in self.pollers:
                # Verificación rápida: estado interno del poller
                if poller.status == 'FREE':
                    # Verificación adicional rápida: solo si tiene execution_id, verificar en BD
                    if poller.current_execution_id:
                        try:
                            from executions.models import Execution
                            exec = Execution.objects.only('status').get(id=poller.current_execution_id)
                            if exec.status not in ['PENDING', 'RUNNING']:
                                # Execution terminó, poller está libre
                                return True
                            # Execution aún activa, poller ocupado
                            continue
                        except:
                            # Execution no existe, poller está libre
                            return True
                    else:
                        # No tiene execution_id, poller está libre
                        return True
            return False
    
    def get_free_poller(self) -> Optional[Poller]:
        """
        Obtener un poller libre
        
        ✅ OPTIMIZADO: Verificación rápida sin consultas pesadas a BD.
        Usa el estado interno del poller y solo verifica BD si es necesario.
        """
        with self.lock:
            for poller in self.pollers:
                # Verificación rápida: estado interno del poller
                if poller.status == 'FREE':
                    # Verificación adicional rápida: solo si tiene execution_id, verificar en BD
                    if poller.current_execution_id:
                        try:
                            from executions.models import Execution
                            exec = Execution.objects.only('status').get(id=poller.current_execution_id)
                            if exec.status not in ['PENDING', 'RUNNING']:
                                # Execution terminó, poller está libre
                                return poller
                            # Execution aún activa, poller ocupado
                            continue
                        except:
                            # Execution no existe, poller está libre
                            return poller
                    else:
                        # No tiene execution_id, poller está libre
                        return poller
            return None
    
    def is_olt_busy(self, olt_id: int) -> bool:
        """
        ✅ PROTECCIÓN OLT: Verificar si OLT ya tiene un nodo ejecutándose
        Solo 1 nodo a la vez por OLT para evitar saturación
        
        OPTIMIZADO: Usa only('id') para reducir carga de datos
        """
        from executions.models import Execution
        # Usar only('id') para reducir la carga de datos de la consulta
        running = Execution.objects.filter(
            olt_id=olt_id,
            status__in=['RUNNING', 'PENDING']
        ).only('id').exists()  # Solo necesitamos saber si existe, no los datos completos
        return running
    
    def assign_node(self, composite_node: CompositeNode):
        """
        Asignar nodo compuesto a poller libre, respetando límite de 1 por OLT
        """
        olt_id = composite_node.olt.id
        
        # ✅ PROTECCIÓN OLT: Verificar si OLT ya tiene un nodo ejecutándose
        if self.is_olt_busy(olt_id):
            logger.debug(f"⏸️ OLT {composite_node.olt.abreviatura} ocupada, encolando nodo compuesto '{composite_node.name}'")
            self.queue.put(composite_node)
            return
        
        # OLT libre, intentar asignar a poller libre
        poller = self.get_free_poller()
        if poller:
            # Ejecutar nodo compuesto y cuando termine, procesar cola de esa OLT
            thread = Thread(
                target=self._execute_and_process_queue,
                args=(poller, composite_node, olt_id),
                daemon=True
            )
            thread.start()
            logger.info(f"▶️ Poller {poller.poller_id} asignado a nodo compuesto '{composite_node.name}' (OLT: {composite_node.olt.abreviatura})")
        else:
            # No hay poller libre, encolar
            logger.debug(f"📋 No hay poller libre, encolando nodo compuesto '{composite_node.name}'")
            self.queue.put(composite_node)
    
    def _execute_and_process_queue(self, poller: Poller, composite_node: CompositeNode, olt_id: int):
        """
        Ejecutar nodo compuesto y después procesar siguiente nodo de esa OLT en cola
        
        ⚠️ IMPORTANTE: Esta función se ejecuta en un thread separado.
        La Execution se crea dentro de composite_node.execute(), y debe guardarse
        inmediatamente para que el scheduler la vea en la siguiente iteración.
        """
        try:
            # Ejecutar nodo compuesto (esto crea la Execution y la envía a Celery)
            # La Execution se crea y guarda inmediatamente en _execute_node()
            execution = poller.execute_composite_node(composite_node)
            
            # ✅ Verificar que la Execution se creó correctamente
            if execution:
                from executions.models import Execution as ExecutionModel
                try:
                    # ✅ GUARDAR POLLER_ID EN LA EXECUTION para tracking en tiempo real
                    # Esto permite ver qué poller está ejecutando qué, incluso si se pierde el current_execution_id
                    execution_obj = ExecutionModel.objects.get(id=execution.id)
                    if not hasattr(execution_obj, 'result_summary') or execution_obj.result_summary is None:
                        execution_obj.result_summary = {}
                    
                    # Guardar poller_id en result_summary para tracking
                    if isinstance(execution_obj.result_summary, dict):
                        execution_obj.result_summary['poller_id'] = poller.poller_id
                        execution_obj.save(update_fields=['result_summary'])
                        logger.debug(f"✅ Poller {poller.poller_id} asociado con Execution {execution.id}")
                    
                    logger.debug(f"✅ Execution {execution.id} verificada en BD para nodo '{composite_node.name}'")
                except ExecutionModel.DoesNotExist:
                    logger.error(f"❌ Execution {execution.id if execution else 'None'} no encontrada en BD después de crear")
        except Exception as e:
            logger.error(f"❌ Error ejecutando nodo compuesto '{composite_node.name}': {e}", exc_info=True)
        finally:
            # Cuando termina, verificar si hay más nodos de esta OLT en cola
            self._process_queue_for_olt(olt_id)
    
    def _process_queue_for_olt(self, olt_id: int):
        """
        Procesar siguiente nodo compuesto de una OLT específica desde la cola
        """
        # Buscar siguiente nodo de esta OLT en cola
        next_node = None
        temp_nodes = []
        
        # Revisar cola y encontrar nodo de esta OLT
        while not self.queue.empty():
            node = self.queue.get()
            if node and node.olt.id == olt_id and next_node is None:
                next_node = node
            elif node:
                temp_nodes.append(node)
        
        # Devolver nodos que no son de esta OLT a la cola
        for node in temp_nodes:
            self.queue.put(node)
        
        # Si hay siguiente nodo de esta OLT y OLT está libre, ejecutarlo
        if next_node and not self.is_olt_busy(olt_id):
            poller = self.get_free_poller()
            if poller:
                thread = Thread(
                    target=self._execute_and_process_queue,
                    args=(poller, next_node, olt_id),
                    daemon=True
                )
                thread.start()
                logger.info(f"▶️ Procesando siguiente nodo de OLT {next_node.olt.abreviatura} desde cola: '{next_node.name}'")
            else:
                # No hay poller libre, devolver a cola
                self.queue.put(next_node)
    
    def process_queue(self, max_nodes=20):
        """
        Procesar nodos de la cola cuando hay pollers libres
        Se llama periódicamente desde el scheduler
        
        ✅ CRÍTICO: Este método debe procesar TODOS los nodos posibles de la cola.
        No debe omitir ningún nodo, todos deben ejecutarse eventualmente.
        
        Args:
            max_nodes: Máximo número de nodos a procesar en una iteración (evita bloqueos)
        """
        processed = 0
        # ✅ CRÍTICO: Procesar hasta max_nodes nodos, pero SIEMPRE intentar procesar todos los posibles
        while self.has_free_poller() and not self.queue.empty() and processed < max_nodes:
            try:
                composite_node = self.queue.get()
                if composite_node:
                    # ✅ CRÍTICO: assign_node() encolará si no puede asignar (OLT ocupada o sin poller libre)
                    # Esto garantiza que ningún nodo se pierda
                    self.assign_node(composite_node)
                    processed += 1
                    logger.debug(f"📤 Procesando nodo desde cola: '{composite_node.name}' (OLT: {composite_node.olt.abreviatura})")
            except Exception as e:
                logger.warning(f"⚠️ Error procesando nodo desde cola: {e}", exc_info=True)
                # ✅ CRÍTICO: Si hay error, NO romper el loop, continuar con el siguiente nodo
                # Esto garantiza que se procesen todos los nodos posibles
                continue
        
        if processed > 0:
            logger.debug(f"📊 Procesados {processed} nodo(s) desde cola (restantes en cola: {self.queue.qsize()})")
        
        return processed
    
    def get_busy_percentage(self) -> float:
        """Calcular porcentaje promedio de busy"""
        with self.lock:
            if not self.pollers:
                return 0.0
            # Calcular busy_percentage directamente para cada poller (sin llamar a get_busy_percentage para evitar deadlock)
            total_busy = 0.0
            for p in self.pollers:
                if p.total_time == 0:
                    busy_pct = 0.0
                else:
                    busy_pct = (p.busy_time / p.total_time) * 100
                total_busy += busy_pct
            return total_busy / len(self.pollers)
    
    def is_saturated(self) -> bool:
        """
        Detectar saturación estilo Zabbix
        
        ✅ MEJORADO: Verificación más precisa basada en estado real de pollers
        - Busy > 75%: Sistema saturado (basado en tiempo ocupado)
        - Cola > (StartPollers * 2): Sistema colapsado (más de 20 nodos esperando)
        - Todos los pollers ocupados Y cola > 0: Sistema saturado (no hay capacidad)
        """
        busy_pct = self.get_busy_percentage()
        queue_size = self.queue.qsize()
        
        # Obtener conteo real de pollers ocupados (no solo status interno)
        stats = self.get_stats()
        busy_pollers = stats['busy_pollers']
        total_pollers = stats['total_pollers']
        
        # Condición 1: Porcentaje de tiempo ocupado > 75%
        if busy_pct > 75:
            return True
        
        # Condición 2: Cola muy grande (> 2x número de pollers)
        if queue_size > self.start_pollers * 2:
            return True
        
        # ✅ NUEVA Condición 3: Todos los pollers ocupados Y hay cola
        # Esto indica que el sistema está al 100% de capacidad y hay tareas esperando
        if busy_pollers == total_pollers and queue_size > 0:
            return True
        
        return False
    
    def get_stats(self) -> dict:
        """
        Obtener estadísticas del PollerManager
        
        ✅ MEJORADO: Verificación más precisa del estado de los pollers
        Verifica ejecuciones activas en BD para determinar estado real
        """
        with self.lock:
            # ✅ MEJORADO: Verificar estado real de cada poller basado en ejecuciones activas
            from executions.models import Execution
            
            # Contar pollers libres y ocupados basado en estado real
            free_count = 0
            busy_count = 0
            
            # Obtener ejecuciones activas por poller_id para verificación
            active_executions_by_poller = {}
            try:
                active_execs = Execution.objects.filter(
                    status__in=['PENDING', 'RUNNING'],
                    workflow_node__isnull=False,
                    result_summary__isnull=False
                ).only('id', 'result_summary')
                
                for exec_obj in active_execs:
                    if exec_obj.result_summary and isinstance(exec_obj.result_summary, dict):
                        poller_id = exec_obj.result_summary.get('poller_id')
                        if poller_id is not None:
                            if poller_id not in active_executions_by_poller:
                                active_executions_by_poller[poller_id] = []
                            active_executions_by_poller[poller_id].append(exec_obj.id)
            except Exception as e:
                logger.debug(f"Error obteniendo ejecuciones activas para stats: {e}")
            
            # Verificar cada poller
            for p in self.pollers:
                is_really_busy = False
                
                # Verificar 1: Estado interno
                if p.status == 'BUSY':
                    is_really_busy = True
                
                # Verificar 2: Tiene current_execution_id y la ejecución está activa
                if p.current_execution_id:
                    try:
                        exec_check = Execution.objects.only('status').get(id=p.current_execution_id)
                        if exec_check.status in ['PENDING', 'RUNNING']:
                            is_really_busy = True
                        else:
                            # La ejecución terminó pero el poller no se liberó, corregir
                            with p.lock:
                                p.status = 'FREE'
                                p.current_execution_id = None
                                p.current_composite_node = None
                            logger.debug(f"✅ Poller {p.poller_id} corregido: execution {p.current_execution_id} terminó pero estaba BUSY")
                    except Execution.DoesNotExist:
                        # La ejecución no existe, liberar poller
                        with p.lock:
                            p.status = 'FREE'
                            p.current_execution_id = None
                            p.current_composite_node = None
                        logger.debug(f"✅ Poller {p.poller_id} corregido: execution {p.current_execution_id} no existe")
                
                # Verificar 3: Tiene ejecuciones activas asociadas por poller_id
                if p.poller_id in active_executions_by_poller:
                    is_really_busy = True
                
                if is_really_busy:
                    busy_count += 1
                else:
                    free_count += 1
            
            # Calcular busy_percentage directamente (sin llamar a get_busy_percentage para evitar deadlock)
            if not self.pollers:
                busy_pct = 0.0
            else:
                total_busy = 0.0
                for p in self.pollers:
                    if p.total_time == 0:
                        p_busy_pct = 0.0
                    else:
                        p_busy_pct = (p.busy_time / p.total_time) * 100
                    total_busy += p_busy_pct
                busy_pct = total_busy / len(self.pollers)
            
            queue_size = self.queue.qsize()
            is_saturated = busy_pct > 75 or queue_size > self.start_pollers * 2
            
            # ✅ CONTAR EJECUCIONES REALES: Sumar ejecuciones con workflow_node que terminaron
            # Esto da un número más preciso que solo contar desde los pollers
            total_tasks_from_pollers = sum(p.tasks_completed for p in self.pollers)
            total_tasks_from_executions = 0
            
            try:
                from django.utils import timezone
                from datetime import timedelta
                
                # Contar ejecuciones con workflow_node que terminaron (últimas 24 horas)
                last_24h = timezone.now() - timedelta(hours=24)
                total_tasks_from_executions = Execution.objects.filter(
                    workflow_node__isnull=False,
                    status__in=['SUCCESS', 'FAILED'],
                    finished_at__gte=last_24h
                ).count()
            except Exception as e:
                # Si falla, usar solo el contador de pollers
                logger.debug(f"Error contando ejecuciones: {e}")
                total_tasks_from_executions = total_tasks_from_pollers
            
            # Usar el máximo entre ambos para tener el número más preciso
            total_tasks_completed = max(total_tasks_from_pollers, total_tasks_from_executions)
            
            return {
                'total_pollers': len(self.pollers),
                'free_pollers': free_count,  # ✅ Usar conteo verificado
                'busy_pollers': busy_count,  # ✅ Usar conteo verificado
                'busy_percentage': busy_pct,
                'queue_size': queue_size,
                'is_saturated': is_saturated,
                'is_overload': self.queue.is_overload(),
                'total_tasks_completed': total_tasks_completed,
                'total_tasks_delayed': sum(p.tasks_delayed for p in self.pollers),
            }

