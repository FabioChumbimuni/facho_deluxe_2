"""
Poller individual: Ejecuta nodos compuestos
"""
from threading import Lock
from datetime import datetime
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Poller:
    """
    Poller individual que ejecuta nodos compuestos
    """
    
    def __init__(self, poller_id: int):
        self.poller_id = poller_id
        self.status = 'FREE'  # FREE, BUSY
        self.current_composite_node = None
        self.current_execution_id = None  # ID de la Execution actual
        self.busy_time = 0.0
        self.total_time = 0.0
        self.tasks_completed = 0
        self.tasks_delayed = 0
        self.lock = Lock()
        self.start_time = timezone.now()
    
    def execute_composite_node(self, composite_node):
        """
        Ejecutar un nodo compuesto (master + encadenados)
        """
        with self.lock:
            self.status = 'BUSY'
            self.current_composite_node = composite_node
            task_start = timezone.now()
        
        try:
            # Ejecutar nodo compuesto (esto crea la Execution y la envía a Celery)
            # La Execution se crea inmediatamente, por lo que el scheduler no la ejecutará de nuevo
            # ✅ Pasar _from_poller=True para indicar que viene de un Poller
            result = composite_node.execute(_from_poller=True)
            
            # ⚠️ IMPORTANTE: No marcar como "completado" inmediatamente
            # La Execution está en PENDING/RUNNING en Celery, no ha terminado realmente
            # El poller solo "envió" la tarea, no la "completó"
            # El poller se marca como FREE para poder recibir otra tarea, pero la Execution sigue corriendo
            
            # Calcular tiempos (tiempo de "envío", no de "ejecución completa")
            task_end = timezone.now()
            execution_time = (task_end - task_start).total_seconds()
            
            # Actualizar métricas
            with self.lock:
                # No incrementar busy_time aquí porque la tarea aún no terminó
                # Solo incrementar cuando la Execution realmente termine (desde callbacks)
                self.total_time = (task_end - self.start_time).total_seconds()
                # No incrementar tasks_completed aquí - se incrementará cuando termine realmente
                
                # ✅ MANTENER POLLER BUSY mientras la Execution esté en PENDING o RUNNING
                # Guardar el execution_id para verificar su estado después
                # result es la Execution creada por composite_node.execute()
                if result:
                    # result es una Execution, tiene atributo id
                    self.current_execution_id = result.id
                    self.status = 'BUSY'  # ✅ EXPLÍCITO: Asegurar que el status sea BUSY
                    # NO marcar como FREE todavía - se marcará cuando la Execution termine
                    # El status seguirá siendo BUSY hasta que el callback lo actualice
                    logger.debug(f"Poller {self.poller_id} guardó execution_id {result.id}, marcado como BUSY")
                else:
                    # Si no hay execution, marcar como FREE (error o caso especial)
                    self.status = 'FREE'
                    self.current_composite_node = None
                    self.current_execution_id = None
                    logger.warning(f"Poller {self.poller_id} no recibió Execution, marcando como FREE")
            
            logger.info(
                f"✅ Poller {self.poller_id} envió nodo compuesto '{composite_node.name}' a Celery "
                f"en {execution_time:.2f}s (Execution creada, ejecutándose en Celery)"
            )
            
            return result
            
        except Exception as e:
            with self.lock:
                self.status = 'FREE'
                self.current_composite_node = None
                self.current_execution_id = None
                composite_node.error_count += 1
            
            logger.error(f"❌ Poller {self.poller_id} error ejecutando nodo compuesto: {e}")
            raise
    
    def get_busy_percentage(self) -> float:
        """Calcular porcentaje de tiempo ocupado"""
        with self.lock:
            if self.total_time == 0:
                return 0.0
            return (self.busy_time / self.total_time) * 100
    
    def get_stats(self, quick_mode: bool = False) -> dict:
        """
        Obtener estadísticas del poller en tiempo real
        
        ✅ IMPORTANTE: Este método muestra el estado ACTUAL del poller basado en:
        1. El current_execution_id guardado (si existe)
        2. Ejecuciones activas en la BD que puedan estar relacionadas
        3. El estado interno del poller
        
        No es sobre historial, es sobre la carga actual del poller.
        """
        # Obtener datos básicos dentro del lock (rápido)
        with self.lock:
            base_status = self.status
            current_node_name = self.current_composite_node.name if self.current_composite_node else None
            current_node_id = self.current_composite_node.id if self.current_composite_node else None
            execution_id = self.current_execution_id
            busy_pct = 0.0
            if self.total_time > 0:
                busy_pct = (self.busy_time / self.total_time) * 100
            
        # ✅ VERIFICAR ESTADO ACTUAL EN TIEMPO REAL (fuera del lock para evitar deadlocks)
        actual_status = base_status
        active_execution = None
        
        # 1. Verificar si hay execution_id guardado
        if execution_id:
            try:
                from executions.models import Execution
                # ✅ OPTIMIZADO: Solo obtener status, no toda la relación (más rápido)
                execution = Execution.objects.only('id', 'status', 'workflow_node_id').get(id=execution_id)
                if execution.status in ['PENDING', 'RUNNING']:
                    # La Execution aún está ejecutándose, poller debe estar BUSY
                    actual_status = 'BUSY'
                    active_execution = execution
                    # Obtener nombre del nodo solo si es necesario
                    if not current_node_name and execution.workflow_node_id:
                        try:
                            from snmp_jobs.models import WorkflowNode
                            node = WorkflowNode.objects.only('name', 'id').get(id=execution.workflow_node_id)
                            current_node_name = node.name
                            current_node_id = node.id
                        except:
                            pass
                elif execution.status in ['SUCCESS', 'FAILED', 'INTERRUPTED']:
                    # La Execution terminó, pero el callback aún no actualizó el poller
                    # Marcar como FREE (el callback lo actualizará pronto)
                    actual_status = 'FREE'
            except Exception as e:
                # Si hay error al obtener la Execution, buscar en la BD
                logger.debug(f"Error verificando Execution {execution_id} para poller {self.poller_id}: {e}")
        
        # 2. Si no hay execution activa y NO es quick_mode, buscar en BD (solo si es necesario)
        # ✅ OPTIMIZADO: En quick_mode, saltamos esta búsqueda costosa para mejorar rendimiento
        if not active_execution and not quick_mode:
            try:
                from executions.models import Execution
                from django.utils import timezone
                from datetime import timedelta
                from zabbix_pollers.tasks import get_poller_manager
                
                pm = get_poller_manager()
                
                # ✅ OPTIMIZADO: Buscar solo ejecuciones con este poller_id en result_summary (más rápido)
                # Usar una consulta directa con JSON field lookup
                try:
                    exec_with_poller = Execution.objects.filter(
                        status__in=['PENDING', 'RUNNING'],
                        workflow_node__isnull=False,
                        result_summary__poller_id=self.poller_id
                    ).select_related('workflow_node').first()
                    
                    if exec_with_poller:
                        active_execution = exec_with_poller
                        actual_status = 'BUSY'
                        current_node_name = exec_with_poller.workflow_node.name if exec_with_poller.workflow_node else None
                        current_node_id = exec_with_poller.workflow_node.id if exec_with_poller.workflow_node else None
                        # Actualizar current_execution_id para mantener consistencia
                        with self.lock:
                            self.current_execution_id = exec_with_poller.id
                        logger.debug(f"✅ Poller {self.poller_id} encontró execution {exec_with_poller.id} por poller_id")
                except Exception as json_error:
                    # Si falla la consulta JSON (puede ser que result_summary no sea JSON en algunos casos)
                    logger.debug(f"Error en consulta JSON para poller {self.poller_id}: {json_error}")
            except Exception as e:
                logger.debug(f"Error buscando ejecuciones activas para poller {self.poller_id}: {e}")
            
        # Retornar estadísticas (tanto para quick_mode como para modo detallado)
            return {
                'poller_id': self.poller_id,
            'status': actual_status,  # Estado actual en tiempo real
                'busy_percentage': busy_pct,
                'tasks_completed': self.tasks_completed,
                'tasks_delayed': self.tasks_delayed,
            'current_node_id': current_node_id,
            'current_node_name': current_node_name,
            'current_execution_id': active_execution.id if active_execution else None,  # Agregar para referencia
            }

