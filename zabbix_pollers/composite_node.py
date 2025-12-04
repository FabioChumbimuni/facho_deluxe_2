"""
CompositeNode: Representa un nodo compuesto (master + encadenados)

Un nodo master con sus encadenados cuenta como UN SOLO NODO.
Aunque sean 7 nodos, si están encadenados cuentan como 1.
La demora de ejecución incluye todos los encadenados.
"""
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class CompositeNode:
    """
    Representa un nodo compuesto: master + encadenados
    Cuenta como UN SOLO NODO aunque tenga múltiples encadenados
    """
    
    def __init__(self, master, chain_nodes, workflow, olt):
        """
        Args:
            master: WorkflowNode master (tiene nextcheck)
            chain_nodes: Lista de WorkflowNode encadenados (no tienen nextcheck)
            workflow: OLTWorkflow al que pertenece
            olt: OLT asociada
        """
        self.master = master
        self.chain_nodes = chain_nodes or []
        self.workflow = workflow
        self.olt = olt
        
        # Propiedades del master (usadas para scheduling)
        self.id = master.id
        self.name = master.name
        self.nextcheck = master.next_run_at
        self.lastcheck = master.last_run_at
        self.interval_seconds = master.interval_seconds or 300
        self.priority = master.priority or 50
        self.enabled = master.enabled
        
        # Estado
        self.delayed = False
        self.delay_time = 0.0
        self.execution_time = 0.0
        self.error_count = 0
    
    def __repr__(self):
        chain_count = len(self.chain_nodes)
        return f"CompositeNode(master={self.master.name}, chain_nodes={chain_count}, olt={self.olt.abreviatura})"
    
    def calculate_delay(self, now):
        """Calcular delay si nextcheck ya pasó"""
        if self.nextcheck and self.nextcheck < now:
            self.delay_time = (now - self.nextcheck).total_seconds()
            if self.delay_time > self.interval_seconds:
                self.delayed = True
        else:
            self.delay_time = 0.0
            self.delayed = False
    
    def execute(self, _from_poller=False):
        """
        Ejecuta el nodo compuesto: master primero, luego encadenados secuencialmente
        La demora total incluye todos los encadenados
        
        ✅ RESPETA MODO PRUEBA: El modo prueba se maneja automáticamente
        en las tareas de Celery (discovery_main_task, get_main_task).
        Si modo_prueba=True, las ejecuciones se simulan sin consultas SNMP reales.
        
        ⚠️ PROTECCIÓN: Este método SOLO puede ser llamado desde un Poller.
        Cualquier otro intento de llamarlo directamente lanzará una excepción.
        
        Args:
            _from_poller: Flag interno que indica que la llamada viene de un Poller.
                         NO debe ser usado directamente desde fuera del módulo zabbix_pollers.
        
        Returns:
            Resultado de la ejecución del master
        """
        # ✅ PROTECCIÓN: Solo permitir ejecución desde Poller
        if not _from_poller:
            import inspect
            stack = inspect.stack()
            # Verificar que la llamada viene de poller.py
            caller_file = stack[1].filename if len(stack) > 1 else ''
            if 'poller.py' not in caller_file:
                raise RuntimeError(
                    f"❌ composite_node.execute() solo puede ser llamado desde un Poller. "
                    f"Llamado desde: {caller_file}. "
                    f"Usa poller_manager.assign_node() en su lugar."
                )
        
        from executions.models import Execution
        from snmp_jobs.tasks import discovery_main_task, discovery_manual_task
        from snmp_get.tasks import get_main_task
        
        # Verificar modo prueba (solo para logging)
        from configuracion_avanzada.models import ConfiguracionSistema
        is_modo_prueba = ConfiguracionSistema.is_modo_prueba()
        modo_str = "🧪 MODO PRUEBA" if is_modo_prueba else "▶️"
        
        start_time = timezone.now()
        master_result = None
        
        try:
            # 1. Ejecutar SOLO el master
            # Los nodos encadenados se ejecutarán automáticamente cuando el master termine
            # mediante los callbacks en execution_coordinator/callbacks.py
            logger.info(f"{modo_str} Ejecutando nodo compuesto: master '{self.master.name}' (ID: {self.master.id})")
            logger.info(f"   → Los {len(self.chain_nodes)} nodo(s) encadenado(s) se ejecutarán automáticamente cuando el master termine")
            master_result = self._execute_node(self.master)
            
            # ⚠️ NO ejecutar encadenados aquí - se ejecutarán automáticamente desde los callbacks
            # cuando el master termine. Esto garantiza el orden correcto: master primero, luego encadenados.
            
            end_time = timezone.now()
            self.execution_time = (end_time - start_time).total_seconds()
            
            # ⚠️ NO actualizar next_run_at aquí porque las tareas son asíncronas
            # El next_run_at se actualizará cuando la Execution del MASTER realmente termine
            # en los callbacks de Celery (execution_coordinator/callbacks.py)
            # Esto evita que el nodo se ejecute constantemente antes de que termine realmente
            
            logger.info(f"✅ Nodo master enviado a Celery en {self.execution_time:.2f}s")
            logger.info(f"   → Los encadenados se ejecutarán automáticamente cuando el master termine")
            logger.info(f"   → next_run_at se actualizará cuando la Execution del master termine")
            
            return master_result
            
        except Exception as e:
            logger.error(f"❌ Error ejecutando nodo compuesto: {e}")
            self.error_count += 1
            raise
    
    def _execute_node(self, node):
        """
        Ejecuta un nodo individual (master o encadenado)
        Crea Execution y envía a Celery según el tipo
        
        NOTA: Esta función crea la Execution y la envía a Celery, pero NO espera
        a que termine. El poller considera que el nodo está "ejecutándose" cuando
        la Execution está en estado PENDING o RUNNING.
        """
        from executions.models import Execution
        from snmp_jobs.models import SnmpJob, SnmpJobHost
        
        # ✅ CRÍTICO: Verificar que el nodo pueda ejecutarse ANTES de crear Execution
        # Esto verifica: OLT habilitada, workflow activo, nodo habilitado
        # ⚠️ IMPORTANTE: Para ejecuciones manuales, omitir validación de plantilla y next_run_at
        # - La plantilla inactiva solo afecta ejecuciones automáticas, no manuales
        # - next_run_at puede estar en el futuro, pero queremos ejecutar manualmente ahora
        can_execute, reason = node.can_execute_now(skip_template_check=True, skip_next_run_check=True)
        if not can_execute:
            logger.warning(
                f"  ⏸️ Nodo '{node.name}' no puede ejecutarse: {reason}, abortando ejecución"
            )
            raise ValueError(f"Nodo '{node.name}' no puede ejecutarse: {reason}")
        
        # Obtener OID
        oid = node.oid
        if not oid and node.template_node:
            oid = node.template_node.oid
        
        if not oid:
            raise ValueError(f"Nodo {node.name} (ID: {node.id}) no tiene OID asociado")
        
        # Determinar job_type desde el OID
        # Si espacio es 'descubrimiento' → job_type='descubrimiento'
        # Cualquier otro espacio (descripcion, mac, plan_onu, etc.) → job_type='get'
        if oid.espacio == 'descubrimiento':
            job_type = 'descubrimiento'
        else:
            job_type = 'get'  # Todos los demás son GETs
        
        # Crear/obtener SnmpJob
        job, _ = SnmpJob.objects.get_or_create(
            oid=oid,
            job_type=job_type,
            defaults={
                'nombre': f"[Workflow] {node.name}",
                'descripcion': f"Generado desde WorkflowNode {node.key}",
                'marca': self.olt.marca,
                'interval_seconds': node.interval_seconds or 300,
                'enabled': True,
            }
        )
        
        # Crear/obtener SnmpJobHost
        job_host, _ = SnmpJobHost.objects.get_or_create(
            snmp_job=job,
            olt=self.olt,
            defaults={'enabled': True}
        )
        
        # ✅ CRÍTICO: Usar lock de Redis para evitar ejecuciones duplicadas
        # Esto previene condiciones de carrera donde múltiples threads intentan crear la misma Execution
        from redis import Redis
        from django.conf import settings
        from redis.lock import Lock as RedisLock
        
        redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
        lock_key = f"lock:execution:workflow_node:{node.id}"
        lock = RedisLock(redis_client, lock_key, timeout=300)  # 5 minutos timeout
        
        # Intentar adquirir lock (timeout de 0 = no bloquear)
        if not lock.acquire(blocking=False):
            # Ya hay otra ejecución en curso para este nodo
            existing = Execution.objects.filter(
                workflow_node=node,
                status__in=['PENDING', 'RUNNING']
            ).order_by('-created_at').first()
            if existing:
                # ✅ MEJORADO: Mensaje más claro - el lock está activo porque hay una ejecución
                logger.debug(
                    f"  🔒 Lock activo para nodo '{node.name}': Execution {existing.id} en estado {existing.status}, "
                    f"reutilizando (evita duplicados)"
                )
                return existing
            else:
                # ✅ MEJORADO: Si no hay ejecución pero el lock está activo, puede ser un lock huérfano
                # Intentar liberar el lock y continuar (solo si somos los dueños)
                try:
                    # Verificar si el lock todavía es propiedad de este proceso antes de liberarlo
                    if lock.owned():
                        lock.release()
                        logger.debug(
                            f"  🔓 Lock huérfano liberado para nodo '{node.name}', continuando con nueva ejecución"
                        )
                    else:
                        logger.debug(
                            f"  ⚠️ Lock para nodo '{node.name}' no es propiedad de este proceso, continuando"
                        )
                except Exception:
                    # El lock ya fue liberado o no existe, continuar normalmente
                    logger.debug(
                        f"  ⚠️ No se pudo liberar lock para nodo '{node.name}' pero no hay Execution activa, "
                        f"continuando (lock puede estar en otro proceso o haber expirado)"
                    )
        
        try:
            # Verificar nuevamente si ya existe una Execution (doble verificación)
            existing = Execution.objects.filter(
                workflow_node=node,
                status__in=['PENDING', 'RUNNING']
            ).first()
            
            if existing:
                # ✅ MEJORADO: Mensaje más claro - se detectó una ejecución existente (doble verificación)
                logger.debug(
                    f"  ✅ Execution {existing.id} ya existe para nodo '{node.name}' (estado: {existing.status}), "
                    f"reutilizando (evita duplicados)"
                )
                return existing
            
            # Crear Execution
            execution = Execution.objects.create(
                snmp_job=job,
                job_host=job_host,
                olt_id=self.olt.id,
                workflow_node=node,
                status='PENDING',
                attempt=0
            )
            
            # ✅ IMPORTANTE: Guardar inmediatamente para que el scheduler la vea
            execution.save()
            logger.info(f"  → Execution {execution.id} creada y guardada (status: PENDING, OLT: {self.olt.abreviatura})")
        finally:
            # Liberar lock después de crear la Execution
            try:
                # Verificar si el lock todavía es propiedad de este proceso antes de liberarlo
                # Esto evita el error "Cannot release a lock that's no longer owned"
                if lock.owned():
                    lock.release()
            except Exception:
                pass  # Ignorar errores al liberar lock (normal si expiró o fue liberado)
        
        # Enviar a Celery según tipo
        try:
            if job_type == 'descubrimiento':
                from snmp_jobs.tasks import discovery_main_task
                result = discovery_main_task.delay(job.id, self.olt.id, execution.id)
                execution.celery_task_id = result.id
                execution.save(update_fields=['celery_task_id'])
                logger.info(f"  → Enviado a Celery (discovery): Execution {execution.id}, Task {result.id}")
            elif job_type == 'get':
                from snmp_get.tasks import get_main_task
                result = get_main_task.delay(job.id, self.olt.id, execution.id)
                execution.celery_task_id = result.id
                execution.save(update_fields=['celery_task_id'])
                logger.info(f"  → Enviado a Celery (get): Execution {execution.id}, Task {result.id}")
            else:
                raise ValueError(f"Tipo de job desconocido: {job_type}")
        except Exception as e:
            # Si falla al enviar a Celery, marcar la Execution como FAILED
            logger.error(f"  ❌ Error al enviar Execution {execution.id} a Celery: {e}", exc_info=True)
            execution.status = 'FAILED'
            execution.error_message = f"Error al enviar a Celery: {str(e)}"
            execution.finished_at = timezone.now()
            execution.save(update_fields=['status', 'error_message', 'finished_at'])
            raise  # Re-lanzar para que el poller lo maneje
        
        return execution

