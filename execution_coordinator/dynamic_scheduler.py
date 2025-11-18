"""
Scheduler Dinámico con Ejecución Inmediata

Estrategia:
1. Cuando una tarea termina → Ejecuta INMEDIATAMENTE la siguiente en cola
2. NO espera horarios fijos, aprovecha tiempo libre
3. Mantiene cuotas por hora (ej: 3 ejecuciones de Discovery/hora)
4. Prioriza Discovery sobre GET
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from redis import Redis
from django.conf import settings
import json

from .logger import coordinator_logger

logger = logging.getLogger(__name__)
redis_client = Redis.from_url(settings.CELERY_BROKER_URL)


class DynamicScheduler:
    """
    Scheduler que ejecuta tareas inmediatamente cuando hay recursos disponibles
    """
    
    def __init__(self, olt_id):
        self.olt_id = olt_id
        self.lock_key = f"lock:execution:olt:{olt_id}"
        self.queue_key = f"queue:olt:{olt_id}:pending"
    
    def is_olt_busy(self, log_reason=False):
        """
        Verifica si la OLT está ocupada ejecutando una tarea, en reintento, o procesando cola
        
        Args:
            log_reason: Si True, loguea la razón por la que está ocupada
        """
        from hosts.models import OLT
        
        # Verificar lock de ejecución
        lock_data = redis_client.get(self.lock_key)
        if lock_data is not None:
            if log_reason:
                olt = OLT.objects.get(id=self.olt_id)
                coordinator_logger.info(
                    f"⏸️ OLT {self.olt_id} ({olt.abreviatura}) ejecutando tarea",
                    olt=olt
                )
            return True
        
        # Verificar si está en reintento
        retry_key = f"olt:retrying:{self.olt_id}"
        if redis_client.exists(retry_key):
            ttl = redis_client.ttl(retry_key)
            if log_reason:
                olt = OLT.objects.get(id=self.olt_id)
                coordinator_logger.warning(
                    f"🛑 OLT {self.olt_id} ({olt.abreviatura}) EN REINTENTO - bloqueada (expira en {ttl}s)",
                    olt=olt
                )
            return True
        
        # Verificar si está procesando cola (callback ejecutando siguiente tarea)
        processing_key = f"lock:processing_queue:{self.olt_id}"
        if redis_client.exists(processing_key):
            if log_reason:
                coordinator_logger.info(
                    f"⏸️ OLT {self.olt_id} procesando cola",
                    olt=OLT.objects.get(id=self.olt_id)
                )
            return True
        
        return False
    
    def get_ready_tasks(self):
        """
        Obtiene tareas que están listas para ejecutar (next_run_at <= now)
        ORDENADAS POR PRIORIDAD (Discovery primero, GET después)
        
        IMPORTANTE: Usa SnmpJobHost.next_run_at (POR OLT) no SnmpJob.next_run_at (global)
        
        INCLUYE AUTO-REPARACIÓN: Si encuentra JobHosts sin next_run_at, los inicializa
        """
        from snmp_jobs.models import SnmpJob, SnmpJobHost
        
        now = timezone.now()
        
        # AUTO-REPARACIÓN: Detectar y corregir JobHosts sin next_run_at
        broken_job_hosts = SnmpJobHost.objects.filter(
            olt_id=self.olt_id,
            enabled=True,
            snmp_job__enabled=True,
            next_run_at__isnull=True  # ← Sin programar
        ).select_related('snmp_job')
        
        if broken_job_hosts.exists():
            coordinator_logger.warning(
                f"🔧 Auto-reparación: {broken_job_hosts.count()} JobHost(s) sin next_run_at en OLT {self.olt_id}",
                olt=None
            )
            
            for jh in broken_job_hosts:
                # Inicializar usando el método del modelo
                jh.initialize_next_run(is_new=True)
                jh.save(update_fields=['next_run_at'])
                
                coordinator_logger.info(
                    f"✅ Auto-reparado: {jh.snmp_job.nombre} → next_run_at inicializado",
                    olt=None
                )
        
        # CAMBIO CRÍTICO: Usar SnmpJobHost.next_run_at en vez de SnmpJob.next_run_at
        # Esto permite que cada OLT tenga su propio horario independiente
        
        # IMPORTANTE: Solo ejecutar tareas que provienen de workflows vinculados a plantillas activas
        # Obtener todos los WorkflowNodes activos de esta OLT que están vinculados a plantillas
        from snmp_jobs.models import WorkflowNode, OLTWorkflow, WorkflowTemplateLink, WorkflowTemplateNode
        
        # Obtener workflows de esta OLT que están vinculados a plantillas activas
        workflows_with_templates = OLTWorkflow.objects.filter(
            olt_id=self.olt_id,
            is_active=True
        ).filter(
            template_links__template__is_active=True
        ).distinct()
        
        # Obtener los WorkflowNodes de estos workflows que están vinculados a plantillas
        workflow_nodes = WorkflowNode.objects.filter(
            workflow__in=workflows_with_templates,
            enabled=True,
            template_node__isnull=False  # Solo nodos que vienen de plantillas
        ).select_related('template_node', 'template_node__oid')
        
        # Obtener los OIDs y tipos de operación de estos nodos de plantilla
        # Un SnmpJob debe tener el mismo OID y tipo de operación para ser considerado válido
        valid_oid_ids = set()
        for wn in workflow_nodes:
            if wn.template_node and wn.template_node.oid:
                valid_oid_ids.add(wn.template_node.oid.id)
        
        # Si no hay OIDs válidos, no hay tareas que ejecutar
        if not valid_oid_ids:
            return []
        
        # Filtrar job_hosts para SOLO incluir tareas con OIDs de workflows vinculados a plantillas
        job_hosts = SnmpJobHost.objects.filter(
            olt_id=self.olt_id,
            enabled=True,
            snmp_job__enabled=True,
            snmp_job__oid_id__in=valid_oid_ids,  # ← SOLO tareas con OIDs de plantillas activas
            next_run_at__lte=now,  # ← AHORA USA SnmpJobHost.next_run_at
            next_run_at__isnull=False  # Solo los que tienen next_run_at
        ).select_related('snmp_job', 'snmp_job__oid')
        
        ready_tasks = []
        for jh in job_hosts:
            job = jh.snmp_job
            
            # Calcular prioridad CORRECTAMENTE
            if job.job_type == 'descubrimiento':
                priority = 90
            elif job.job_type == 'get':
                priority = 40
            elif job.job_type == 'walk':
                priority = 30
            else:
                priority = 50
            
            ready_tasks.append({
                'job_id': job.id,
                'job_host_id': jh.id,
                'job_name': job.nombre,
                'job_type': job.job_type,
                'priority': priority,
                'next_run_at': jh.next_run_at.isoformat() if jh.next_run_at else None,  # ← De SnmpJobHost
            })
        
        # CRÍTICO: Ordenar por prioridad descendente
        # Discovery (90) SIEMPRE antes que GET (40)
        ready_tasks.sort(key=lambda t: (-t['priority'], t['job_name']))
        
        return ready_tasks

    def _has_discovery_job(self):
        from snmp_jobs.models import SnmpJobHost
        return SnmpJobHost.objects.filter(
            olt_id=self.olt_id,
            enabled=True,
            snmp_job__enabled=True,
            snmp_job__job_type='descubrimiento'
        ).exists()

    def _has_pending_or_running_discovery(self):
        from executions.models import Execution
        statuses = [
            Execution.STATUS_PENDING,
            Execution.STATUS_RUNNING,
        ]
        return Execution.objects.filter(
            olt_id=self.olt_id,
            snmp_job__job_type='descubrimiento',
            status__in=statuses
        ).exists()
    
    def enqueue_task(self, task_info):
        """
        Encola una tarea para ejecución posterior
        """
        queue_data = {
            'job_id': task_info['job_id'],
            'job_host_id': task_info['job_host_id'],
            'job_name': task_info['job_name'],
            'job_type': task_info['job_type'],
            'priority': task_info['priority'],
            'enqueued_at': timezone.now().isoformat(),  # Ya está como string ISO
        }
        
        # Agregar a cola con orden de prioridad
        # rpush = al final (FIFO dentro de misma prioridad)
        redis_client.rpush(self.queue_key, json.dumps(queue_data))
        redis_client.expire(self.queue_key, 3600)  # Expirar en 1 hora
    
    def execute_next_in_queue(self, olt):
        """
        Ejecuta la siguiente tarea en cola INMEDIATAMENTE
        
        Returns:
            bool: True si ejecutó una tarea, False si no había nada
        """
        from snmp_jobs.models import SnmpJob, SnmpJobHost
        from executions.models import Execution
        
        # Obtener todas las tareas en cola
        queue_items = redis_client.lrange(self.queue_key, 0, -1)
        
        if not queue_items:
            return False  # Cola vacía
        
        # Parsear y ordenar por prioridad
        tasks_in_queue = []
        for item in queue_items:
            try:
                task_data = json.loads(item)
                tasks_in_queue.append(task_data)
            except:
                continue
        
        if not tasks_in_queue:
            return False
        
        # Ordenar por prioridad
        tasks_in_queue.sort(key=lambda t: t['priority'], reverse=True)
        
        # Tomar la de mayor prioridad
        next_task = tasks_in_queue[0]
        
        # Remover de cola temporalmente
        redis_client.lrem(self.queue_key, 1, json.dumps(next_task))
        
        # Ejecutar INMEDIATAMENTE
        try:
            job = SnmpJob.objects.get(id=next_task['job_id'])
            job_host = SnmpJobHost.objects.get(id=next_task['job_host_id'])
            
            # ✅ NUEVO: Verificar capacidad de Celery ANTES de ejecutar
            if not self._check_celery_capacity(job.job_type):
                # Sistema saturado, devolver a la cola
                redis_client.lpush(self.queue_key, json.dumps(next_task))
                logger.warning(f"⏸️ Sistema saturado, {job.nombre} regresa a cola")
                return False
            
            # VERIFICAR: ¿La OLT está en proceso de reintento?
            retry_key = f"olt:retrying:{self.olt_id}"
            is_retrying = redis_client.exists(retry_key)
            
            if is_retrying:
                logger.info(f"🛑 OLT {self.olt_id} EN REINTENTO - bloqueada, omitiendo cola")
                return False
            
            # VERIFICAR: ¿La OLT está ocupada?
            olt_lock_key = f"lock:execution:olt:{self.olt_id}"
            olt_is_busy = redis_client.exists(olt_lock_key)
            
            if olt_is_busy:
                logger.info(f"⏸️ OLT {self.olt_id} ocupada, esperando...")
                return False
            
            # LOCK ATÓMICO: Evitar crear la misma ejecución dos veces
            execution_lock_key = f"lock:create_execution:{self.olt_id}:{job.id}"
            lock_acquired = redis_client.set(execution_lock_key, '1', nx=True, ex=5)
            
            if not lock_acquired:
                logger.warning(f"⚠️ Lock no disponible para {job.nombre} desde cola, omitiendo")
                return False
            
            # Verificar last_run_at del SnmpJobHost
            if job_host.last_run_at:
                time_since_last = (timezone.now() - job_host.last_run_at).total_seconds()
                if time_since_last < 3:
                    logger.warning(f"⚠️ {job.nombre} se ejecutó hace {time_since_last:.1f}s desde cola, omitiendo")
                    redis_client.delete(execution_lock_key)
                    return False
            
            # ACTUALIZAR next_run_at ANTES de crear ejecución
            now = timezone.now()
            interval_seconds = job.interval_seconds or 300
            next_time = now + timedelta(seconds=interval_seconds)
            
            # DESFASE INTENCIONAL según tipo de tarea
            if job.job_type == 'descubrimiento':
                next_time = next_time.replace(second=0, microsecond=0)
            elif job.job_type == 'get':
                next_time = next_time.replace(second=10, microsecond=0)
            
            job_host.next_run_at = next_time
            job_host.last_run_at = now
            job_host.save(update_fields=['next_run_at', 'last_run_at'])
            
            # Liberar lock ANTES de crear ejecución
            redis_client.delete(execution_lock_key)
            
            # Crear ejecución
            execution = Execution.objects.create(
                snmp_job=job,
                job_host=job_host,
                olt_id=self.olt_id,
                status='PENDING',
                attempt=0
            )
            
            # Encolar en Celery según tipo
            celery_task_id = None
            try:
                if job.job_type == 'descubrimiento':
                    from snmp_jobs.tasks import discovery_main_task
                    result = discovery_main_task.delay(job.id, self.olt_id, execution.id)
                    celery_task_id = result.id
                    logger.debug(f"Discovery task enqueued: {result.id}")
                elif job.job_type == 'get':
                    from snmp_get.tasks import get_main_task
                    result = get_main_task.delay(job.id, self.olt_id, execution.id)
                    celery_task_id = result.id
                    logger.debug(f"GET task enqueued: {result.id}")
                
                # Guardar celery_task_id para tracking
                if celery_task_id:
                    execution.celery_task_id = celery_task_id
                    execution.save(update_fields=['celery_task_id'])
                    coordinator_logger.debug(
                        f"📤 Tarea enviada a Celery: {celery_task_id}",
                        olt=olt,
                        details={'celery_task_id': celery_task_id, 'execution_id': execution.id}
                    )
                
            except Exception as celery_error:
                logger.error(f"❌ Error enviando tarea a Celery: {celery_error}")
                execution.status = 'FAILED'
                execution.error_message = f"Error encolando en Celery: {celery_error}"
                execution.save(update_fields=['status', 'error_message'])
                return False
            
            coordinator_logger.info(
                f"▶️ Ejecutando INMEDIATAMENTE: {next_task['job_name']} en {olt.abreviatura} (desde cola)",
                olt=olt,
                event_type='EXECUTION_STARTED',
                details={
                    'task_name': next_task['job_name'],
                    'task_type': next_task['job_type'],
                    'priority': next_task.get('priority', 50),
                    'from_queue': True,
                    'execution_id': execution.id
                }
            )
            
            # next_run_at ya fue actualizado ANTES de crear ejecución
            
            return True
            
        except Exception as e:
            logger.error(f"Error ejecutando tarea desde cola: {e}")
            return False
    
    def process_ready_tasks(self, olt):
        """
        Procesa tareas listas para ejecutar RESPETANDO INTERVALOS
        
        LÓGICA CRÍTICA:
        1. Solo ejecuta si next_run_at <= now (respeta intervalo)
        2. Si OLT ocupada → encola para ejecutar DESPUÉS
        3. Si OLT libre → ejecuta la de mayor prioridad
        4. Cuando termina una tarea, el callback ejecuta la siguiente en cola
        
        IMPORTANTE: 
        - NO ejecuta todo corrido
        - RESPETA el intervalo configurado (20 min = 3 veces/hora)
        - Solo optimiza el ORDEN de ejecución cuando hay colisión
        """
        ready_tasks = self.get_ready_tasks()
        
        if not ready_tasks:
            return 0  # No hay tareas listas (next_run_at > now)
        
        # Verificar si OLT está ocupada (loguea razón si hay tareas listas)
        is_busy = self.is_olt_busy(log_reason=True)
        
        if is_busy:
            # OLT ocupada, encolar TODAS las tareas listas para ejecución posterior
            for task in ready_tasks:
                # Verificar si ya está en cola
                queue_items = redis_client.lrange(self.queue_key, 0, -1)
                already_queued = any(
                    json.loads(item).get('job_id') == task['job_id'] 
                    for item in queue_items
                )
                
                if not already_queued:
                    self.enqueue_task(task)
                    
                    coordinator_logger.info(
                        f"📋 {task['job_name']} encolada en {olt.abreviatura} (OLT ocupada, ejecutará cuando termine actual)",
                        olt=olt,
                        event_type='TASK_ADDED',
                        details=task
                    )
            
            return 0  # No ejecutó nada, solo encoló
        
        else:
            # OLT libre, ejecutar la de MAYOR PRIORIDAD
            first_task = ready_tasks[0]
            
            # Encolar el resto (se ejecutarán cuando termine la primera)
            for task in ready_tasks[1:]:
                # Verificar si ya está en cola
                queue_items = redis_client.lrange(self.queue_key, 0, -1)
                already_queued = any(
                    json.loads(item).get('job_id') == task['job_id'] 
                    for item in queue_items
                )
                
                if not already_queued:
                    self.enqueue_task(task)
            
            # Ejecutar la primera
            executed = self._execute_task_now(first_task, olt)
            
            if executed:
                return 1  # Ejecutó 1 tarea
            else:
                return 0
    
    def _check_celery_capacity(self, job_type):
        """
        Verifica si hay capacidad en Celery para ejecutar una tarea
        
        Args:
            job_type: 'descubrimiento' o 'get'
        
        Returns:
            bool: True si hay capacidad, False si está saturado
        """
        from executions.models import Execution
        
        # Límites de capacidad por tipo de tarea
        CAPACITY_LIMITS = {
            'descubrimiento': 25,  # Máximo 25 Discovery PENDING
            'get': 25             # Máximo 25 GET PENDING
        }
        
        limit = CAPACITY_LIMITS.get(job_type, 20)
        
        # Contar ejecuciones PENDING del mismo tipo
        pending_count = Execution.objects.filter(
            status='PENDING',
            snmp_job__job_type=job_type
        ).count()
        
        if pending_count >= limit:
            logger.warning(f"⚠️ Sistema saturado: {pending_count} tareas {job_type} PENDING (límite: {limit})")
            return False
        
        return True
    
    def _execute_task_now(self, task_info, olt):
        """
        Ejecuta una tarea INMEDIATAMENTE (si hay capacidad en Celery)
        
        Returns:
            bool: True si se ejecutó correctamente
        """
        from snmp_jobs.models import SnmpJob, SnmpJobHost
        from executions.models import Execution
        
        try:
            job = SnmpJob.objects.get(id=task_info['job_id'])
            job_host = SnmpJobHost.objects.get(id=task_info['job_host_id'])

            # Si existe una tarea de descubrimiento configurada para esta OLT,
            # los GET deben esperar hasta que no haya descubrimientos pendientes o en curso.
            if job.job_type == 'get' and self._has_discovery_job():
                if self._has_pending_or_running_discovery():
                    # Devolver a la cola si aún no está en ella
                    queue_items = redis_client.lrange(self.queue_key, 0, -1)
                    already_queued = any(
                        json.loads(item).get('job_id') == task_info['job_id']
                        for item in queue_items
                    )
                    if not already_queued:
                        self.enqueue_task(task_info)
                    coordinator_logger.info(
                        f"⏸️ {job.nombre} espera a que finalice Discovery en {olt.abreviatura}",
                        olt=olt,
                        event_type='WAITING',
                        details={
                            'reason': 'pending_discovery',
                            'execution_blocked_job_id': job.id,
                            'olt_id': self.olt_id,
                        }
                    )
                    return False
            
            # ✅ NUEVO: Verificar capacidad de Celery ANTES de crear ejecución
            if not self._check_celery_capacity(job.job_type):
                # Sistema saturado, mantener en cola del coordinador
                coordinator_logger.warning(
                    f"⏸️ Sistema saturado, manteniendo {task_info['job_name']} en cola interna",
                    olt=olt,
                    event_type='CAPACITY_EXCEEDED',
                    details={'job_type': job.job_type}
                )
                # NO eliminar de la cola, se reintentará en el siguiente loop
                return False
            
            # VERIFICAR: ¿La OLT está en proceso de reintento?
            retry_key = f"olt:retrying:{self.olt_id}"
            is_retrying = redis_client.exists(retry_key)
            
            if is_retrying:
                logger.info(f"🛑 OLT {self.olt_id} EN REINTENTO - bloqueada, omitiendo {job.nombre}")
                return False
            
            # VERIFICAR: ¿La OLT está ocupada ejecutando otra tarea?
            olt_lock_key = f"lock:execution:olt:{self.olt_id}"
            olt_is_busy = redis_client.exists(olt_lock_key)
            
            if olt_is_busy:
                logger.info(f"⏸️ OLT {self.olt_id} ocupada, encolando {job.nombre}")
                # Encolar para ejecutar cuando termine la tarea actual
                self.enqueue_task(task_info)
                return False
            
            # LOCK ATÓMICO: Evitar crear la misma ejecución dos veces
            execution_lock_key = f"lock:create_execution:{self.olt_id}:{job.id}"
            lock_acquired = redis_client.set(execution_lock_key, '1', nx=True, ex=5)
            
            if not lock_acquired:
                logger.warning(f"⚠️ Lock no disponible para {job.nombre}, omitiendo")
                return False
            
            # Verificar last_run_at del SnmpJobHost
            if job_host.last_run_at:
                time_since_last = (timezone.now() - job_host.last_run_at).total_seconds()
                if time_since_last < 3:
                    logger.warning(f"⚠️ {job.nombre} se ejecutó hace {time_since_last:.1f}s, omitiendo")
                    redis_client.delete(execution_lock_key)
                    return False
            
            # ACTUALIZAR next_run_at ANTES de crear ejecución
            now = timezone.now()
            interval_seconds = job.interval_seconds or 300
            next_time = now + timedelta(seconds=interval_seconds)
            
            # DESFASE INTENCIONAL según tipo de tarea
            if job.job_type == 'descubrimiento':
                next_time = next_time.replace(second=0, microsecond=0)
            elif job.job_type == 'get':
                next_time = next_time.replace(second=10, microsecond=0)
            
            job_host.next_run_at = next_time
            job_host.last_run_at = now
            job_host.save(update_fields=['next_run_at', 'last_run_at'])
            
            # Liberar lock ANTES de crear ejecución
            redis_client.delete(execution_lock_key)
            
            # Crear ejecución
            execution = Execution.objects.create(
                snmp_job=job,
                job_host=job_host,
                olt_id=self.olt_id,
                status='PENDING',
                attempt=0
            )
            
            # Encolar en Celery según tipo
            celery_task_id = None
            try:
                if job.job_type == 'descubrimiento':
                    from snmp_jobs.tasks import discovery_main_task
                    result = discovery_main_task.delay(job.id, self.olt_id, execution.id)
                    celery_task_id = result.id
                    logger.debug(f"Discovery task enqueued: {result.id}")
                elif job.job_type == 'get':
                    from snmp_get.tasks import get_main_task
                    result = get_main_task.delay(job.id, self.olt_id, execution.id)
                    celery_task_id = result.id
                    logger.debug(f"GET task enqueued: {result.id}")
                
                # Guardar celery_task_id para tracking
                if celery_task_id:
                    execution.celery_task_id = celery_task_id
                    execution.save(update_fields=['celery_task_id'])
                    coordinator_logger.debug(
                        f"📤 Tarea enviada a Celery: {celery_task_id}",
                        olt=olt,
                        details={'celery_task_id': celery_task_id, 'execution_id': execution.id}
                    )
                
            except Exception as celery_error:
                logger.error(f"❌ Error enviando tarea a Celery: {celery_error}")
                execution.status = 'FAILED'
                execution.error_message = f"Error encolando en Celery: {celery_error}"
                execution.save(update_fields=['status', 'error_message'])
                return False
            
            coordinator_logger.info(
                f"▶️ Ejecutando: {task_info['job_name']} en {olt.abreviatura} (P{task_info['priority']})",
                olt=olt,
                event_type='EXECUTION_STARTED',
                details={**task_info, 'execution_id': execution.id}
            )
            
            # next_run_at ya fue actualizado ANTES de crear la ejecución
            # para evitar detecciones duplicadas
            
            return True
            
        except Exception as e:
            logger.error(f"Error ejecutando tarea: {e}")
            return False
    
    def on_task_completed(self, olt):
        """
        Callback cuando una tarea termina
        Ejecuta INMEDIATAMENTE la siguiente en cola si hay
        """
        # Ejecutar siguiente en cola
        executed = self.execute_next_in_queue(olt)
        
        if executed:
            coordinator_logger.info(
                f"✅ Tarea completada, ejecutando siguiente INMEDIATAMENTE",
                olt=olt,
                event_type='EXECUTION_STARTED'
            )
        else:
            coordinator_logger.info(
                f"✅ Tarea completada, OLT libre (sin tareas en cola)",
                olt=olt,
                event_type='EXECUTION_COMPLETED'
            )

