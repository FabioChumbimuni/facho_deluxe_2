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
    
    @staticmethod
    def distribute_workflow_executions():
        """
        ✅ COORDINADOR: Distribuye ejecuciones de workflows con hora base variable y ventana de ±3 minutos
        
        LÓGICA:
        1. Hora base variable: Se recalcula desde la última ejecución real (last_run_at + interval_seconds)
        2. Ventana de variación: ±180 segundos (±3 minutos) desde la hora base
        3. Verificación de colisiones: Si hay >5 nodos en mismo minuto, redistribuir
        4. Ejecución anticipada: Si no hay ejecuciones en próximo minuto, puede ejecutar hasta 3 min antes
        5. Protección de cuota: Verificar máximo de ejecuciones por hora (60/intervalo)
        
        IMPORTANTE:
        - Solo distribuye nodos master/normales (NO nodos en cadena)
        - Se ejecuta cada 2 minutos para evitar cambios constantes
        - Margen de 30 segundos entre nodos es suficiente (óptimo hasta 5 nodos simultáneos)
        """
        from snmp_jobs.models import WorkflowNode, OLTWorkflow
        from hosts.models import OLT
        from django.utils import timezone
        from datetime import timedelta
        import pytz
        from redis import Redis
        from django.conf import settings
        from executions.models import Execution
        
        redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
        peru_tz = pytz.timezone('America/Lima')
        now_utc = timezone.now()
        
        # ✅ CRÍTICO: Solo ejecutar cada 2 minutos para evitar cambios constantes
        distribution_lock_key = "lock:distribution:workflow_executions"
        lock_acquired = redis_client.set(distribution_lock_key, '1', nx=True, ex=120)  # 2 minutos
        
        if not lock_acquired:
            return 0
        
        # Obtener todas las OLTs habilitadas
        olts = OLT.objects.filter(habilitar_olt=True).order_by('id')
        
        # Obtener todos los nodos master/normales con next_run_at
        all_nodes = []
        for olt in olts:
            try:
                workflow = OLTWorkflow.objects.get(olt=olt, is_active=True)
                nodes = WorkflowNode.objects.filter(
                    workflow=workflow,
                    enabled=True,
                    is_chain_node=False,  # Solo nodos master/normales
                    next_run_at__isnull=False
                ).select_related('workflow__olt')
                
                for node in nodes:
                    # Calcular hora base desde última ejecución real
                    # Si no hay last_run_at, usar next_run_at como referencia
                    if node.last_run_at:
                        # Hora base = última ejecución + intervalo
                        base_time = node.last_run_at + timedelta(seconds=node.interval_seconds or 900)
                    else:
                        # Si no hay last_run_at, usar next_run_at como hora base
                        base_time = node.next_run_at
                    
                    all_nodes.append({
                        'node': node,
                        'olt': olt,
                        'base_time': base_time,  # Hora base de referencia
                        'current_next_run': node.next_run_at,  # Hora actual configurada
                        'interval_seconds': node.interval_seconds or 900
                    })
            except OLTWorkflow.DoesNotExist:
                continue
        
        if not all_nodes:
            return 0
        
        # Agrupar ejecuciones por minuto objetivo (redondeado)
        executions_by_minute = {}
        
        for node_info in all_nodes:
            base_time_peru = timezone.localtime(node_info['base_time'], peru_tz)
            minute_key = base_time_peru.strftime('%H:%M')
            
            if minute_key not in executions_by_minute:
                executions_by_minute[minute_key] = []
            
            executions_by_minute[minute_key].append(node_info)
        
        distributed_count = 0
        early_execution_count = 0
        
        # ✅ LÍMITE GLOBAL: Máximo 6 ejecuciones por minuto (distribuidas en ventana de ±3 minutos)
        # Esto evita saturación masiva del sistema
        MAX_EXECUTIONS_PER_MINUTE = 6
        
        # Procesar cada minuto
        for minute_key, executions in executions_by_minute.items():
            # Si hay más de MAX_EXECUTIONS_PER_MINUTE nodos en el mismo minuto, redistribuir
            if len(executions) > MAX_EXECUTIONS_PER_MINUTE:
                # Ordenar por OLT ID para distribución consistente
                executions.sort(key=lambda x: x['olt'].id)
                
                # Distribuir en rango de ±180 segundos (±3 minutos)
                for idx, exec_info in enumerate(executions):
                    base_time_peru = timezone.localtime(exec_info['base_time'], peru_tz)
                    base_time_rounded = base_time_peru.replace(second=0, microsecond=0)
                    
                    # Calcular desfase: distribuir uniformemente en rango de 360 segundos (6 minutos)
                    # Pero limitar a ±180 segundos desde la hora base
                    total_executions = len(executions)
                    if total_executions == 1:
                        stagger_seconds = 0
                    else:
                        # Distribuir uniformemente: -180, -144, ..., 0, ..., +144, +180
                        position = idx / (total_executions - 1) if total_executions > 1 else 0.5
                        stagger_seconds = int((position * 360) - 180)  # Rango: -180 a +180
                    
                    new_time_peru = base_time_rounded + timedelta(seconds=stagger_seconds)
                    
                    # Convertir a UTC
                    if timezone.is_naive(new_time_peru):
                        new_time_peru = peru_tz.localize(new_time_peru)
                    new_time_utc = new_time_peru.astimezone(pytz.UTC)
                    
                    # Solo actualizar si el cambio es significativo (> 30 segundos) y está en el futuro
                    time_diff = abs((new_time_utc - exec_info['current_next_run']).total_seconds())
                    time_until_execution = (exec_info['current_next_run'] - now_utc).total_seconds()
                    
                    if time_diff > 30 and new_time_utc > now_utc and time_until_execution > 60:
                        node = exec_info['node']
                        old_time = node.next_run_at
                        node.next_run_at = new_time_utc
                        node.save(update_fields=['next_run_at'])
                        distributed_count += 1
                        
                        interval_min = exec_info['interval_seconds'] // 60
                        coordinator_logger.debug(
                            f"🔄 COORDINADOR: Distribución por colisión - OLT {exec_info['olt'].abreviatura} "
                            f"nodo '{node.name}' (intervalo: {interval_min}min) ajustado {stagger_seconds:+d}s "
                            f"({timezone.localtime(old_time, peru_tz).strftime('%H:%M:%S')} → {new_time_peru.strftime('%H:%M:%S')}) "
                            f"[{len(executions)} nodos en {minute_key}]",
                            olt=exec_info['olt'],
                            event_type='EXECUTION_DISTRIBUTED',
                            details={
                                'node_id': node.id,
                                'old_time': old_time.isoformat(),
                                'new_time': new_time_utc.isoformat(),
                                'stagger_seconds': stagger_seconds,
                                'minute_key': minute_key,
                                'total_in_minute': total_executions,
                                'interval_seconds': exec_info['interval_seconds'],
                                'reason': 'collision_avoidance'
                            }
                        )
            
            # Verificar ejecución anticipada para nodos con pocas colisiones (≤5 nodos)
            elif len(executions) <= 5:
                for exec_info in executions:
                    node = exec_info['node']
                    base_time = exec_info['base_time']
                    current_next_run = exec_info['current_next_run']
                    interval_seconds = exec_info['interval_seconds']
                    
                    # ✅ LÓGICA SIMPLIFICADA: Sin cuota, solo respeta intervalo
                    # El coordinador puede ajustar ±3 minutos para evitar colisiones
                    
                    # Verificar si puede ejecutarse anticipadamente (hasta 3 min antes)
                    # Revisar todas las próximas ejecuciones en el próximo minuto
                    next_minute_start = now_utc + timedelta(minutes=1)
                    next_minute_end = next_minute_start + timedelta(minutes=1)
                    
                    # Buscar ejecuciones programadas en el próximo minuto (excluyendo este nodo)
                    conflicting_executions = WorkflowNode.objects.filter(
                        enabled=True,
                        is_chain_node=False,
                        next_run_at__gte=next_minute_start,
                        next_run_at__lt=next_minute_end
                    ).exclude(id=node.id).count()
                    
                    # Si no hay ejecuciones en el próximo minuto, puede anticipar
                    if conflicting_executions == 0:
                        # Calcular tiempo anticipado (hasta 3 min antes de la hora base)
                        early_time = base_time - timedelta(seconds=180)  # 3 minutos antes
                        
                        # Solo anticipar si:
                        # 1. El tiempo anticipado está en el futuro (no retroceder)
                        # 2. El tiempo anticipado está al menos 1 minuto en el futuro
                        # 3. No excede el máximo de ejecuciones por hora
                        if early_time > now_utc + timedelta(minutes=1) and early_time < current_next_run:
                            # Verificar que no haya colisiones en el tiempo anticipado
                            early_time_start = early_time - timedelta(seconds=30)
                            early_time_end = early_time + timedelta(seconds=30)
                            
                            collisions = WorkflowNode.objects.filter(
                                enabled=True,
                                is_chain_node=False,
                                next_run_at__gte=early_time_start,
                                next_run_at__lt=early_time_end
                            ).exclude(id=node.id).count()
                            
                            if collisions == 0:
                                old_time = node.next_run_at
                                node.next_run_at = early_time
                                node.save(update_fields=['next_run_at'])
                                early_execution_count += 1
                                
                                interval_min = interval_seconds // 60
                                coordinator_logger.debug(
                                    f"⏰ COORDINADOR: Ejecución anticipada - OLT {exec_info['olt'].abreviatura} "
                                    f"nodo '{node.name}' (intervalo: {interval_min}min) anticipado 3min "
                                    f"({timezone.localtime(old_time, peru_tz).strftime('%H:%M:%S')} → {timezone.localtime(early_time, peru_tz).strftime('%H:%M:%S')})",
                                    olt=exec_info['olt'],
                                    event_type='EXECUTION_EARLY',
                                    details={
                                        'node_id': node.id,
                                        'old_time': old_time.isoformat(),
                                        'new_time': early_time.isoformat(),
                                        'interval_seconds': interval_seconds,
                                        'reason': 'early_execution_no_conflicts'
                                    }
                                )
        
        total_changes = distributed_count + early_execution_count
        if total_changes > 0:
            coordinator_logger.info(
                f"📊 COORDINADOR: Distribuidas {distributed_count} ejecución(es) por colisión, "
                f"{early_execution_count} anticipada(s) (total: {total_changes})",
                event_type='DISTRIBUTION_COMPLETE',
                details={
                    'distributed_count': distributed_count,
                    'early_execution_count': early_execution_count,
                    'total_changes': total_changes
                }
            )
        
        return total_changes
    
    def is_olt_busy(self, log_reason=False):
        """
        Verifica si la OLT está ocupada ejecutando un nodo.
        Solo permite 1 ejecución a la vez por OLT, pero el sistema puede ejecutar
        nodos de diferentes OLTs simultáneamente (hasta 20 OLTs diferentes).
        
        Args:
            log_reason: Si True, loguea la razón por la que está ocupada
        
        Returns:
            bool: True si la OLT está ocupada (tiene al menos 1 ejecución), False si está libre
        """
        from hosts.models import OLT
        from executions.models import Execution
        
        # ✅ NUEVO: Ya no se usan locks de reintento a nivel de tarea
        # Los reintentos se manejan a nivel de configuración SNMP (ConfiguracionSNMP)
        
        # Verificar si hay al menos 1 ejecución RUNNING o PENDING en esta OLT
        # Solo 1 nodo a la vez por OLT
        running_count = Execution.objects.filter(
            olt_id=self.olt_id,
            status__in=['RUNNING', 'PENDING']
        ).count()
        
        if running_count >= 1:
            if log_reason:
                olt = OLT.objects.get(id=self.olt_id)
                coordinator_logger.debug(
                    f"⏸️ OLT {self.olt_id} ({olt.abreviatura}) tiene {running_count} nodo(s) ejecutándose",
                    olt=olt
                )
            return True
        
        return False
    
    def get_running_nodes_count(self):
        """
        Obtiene el número de nodos actualmente ejecutándose (RUNNING o PENDING) en esta OLT.
        
        Returns:
            int: Número de ejecuciones en curso
        """
        from executions.models import Execution
        
        return Execution.objects.filter(
            olt_id=self.olt_id,
            status__in=['RUNNING', 'PENDING']
        ).count()
    
    def get_ready_tasks(self):
        """
        Obtiene tareas que están listas para ejecutar (next_run_at <= now)
        ORDENADAS POR PRIORIDAD (Discovery primero, GET después)
        
        IMPORTANTE: Usa SnmpJobHost.next_run_at (POR OLT) no SnmpJob.next_run_at (global)
        
        INCLUYE AUTO-REPARACIÓN: Si encuentra JobHosts sin next_run_at, los inicializa
        """
        from snmp_jobs.models import SnmpJob, SnmpJobHost
        
        now = timezone.now()
        
        # CAMBIO CRÍTICO: Leer directamente de WorkflowNode, NO de SnmpJobHost (legacy)
        # Cada OLT tiene su workflow independiente con nodos que se ejecutan según su intervalo
        from snmp_jobs.models import WorkflowNode, OLTWorkflow
        
        # Obtener el workflow de esta OLT
        try:
            workflow = OLTWorkflow.objects.get(olt_id=self.olt_id, is_active=True)
        except OLTWorkflow.DoesNotExist:
            return []  # No hay workflow para esta OLT
        
        # AUTO-REPARACIÓN: Detectar y corregir nodos sin next_run_at
        # IMPORTANTE: 
        # - NO reparar nodos en cadena (no tienen next_run_at por diseño)
        # - NO reparar nodos cuya plantilla está desactivada (next_run_at=None es intencional)
        broken_nodes = WorkflowNode.objects.filter(
            workflow=workflow,
            enabled=True,
            is_chain_node=False,  # Solo reparar nodos normales/master
            next_run_at__isnull=True
        ).select_related('template_node', 'template_node__template')
        
        if broken_nodes.exists():
            # Filtrar nodos que pueden ser reparados:
            # - Nodos sin plantilla (pueden ser reparados)
            # - Nodos con plantilla activa (pueden ser reparados)
            # - Nodos con plantilla desactivada (NO reparar, next_run_at=None es intencional)
            repairable_nodes = []
            
            for node in broken_nodes:
                # Verificar si la plantilla está activa
                if node.template_node and node.template_node.template:
                    if not node.template_node.template.is_active:
                        # Plantilla desactivada: NO reparar (next_run_at=None es intencional)
                        # No loguear: es el comportamiento esperado
                        continue
                
                # Nodo sin plantilla o con plantilla activa: puede ser reparado
                repairable_nodes.append(node)
            
            if repairable_nodes:
                coordinator_logger.warning(
                    f"🔧 Auto-reparación: {len(repairable_nodes)} WorkflowNode(s) sin next_run_at en OLT {self.olt_id}",
                    olt=workflow.olt
                )
                
                for node in repairable_nodes:
                    # Inicializar usando el método del modelo
                    node.initialize_next_run()
                    node.save(update_fields=['next_run_at'])
                    
                    coordinator_logger.info(
                        f"✅ Auto-reparado: {node.name} → next_run_at inicializado ({node.interval_seconds}s)",
                        olt=workflow.olt
                    )
        
        # ✅ NUEVA LÓGICA: Ventana de ±3 minutos desde hora base
        # Un nodo puede ejecutarse si:
        # 1. next_run_at <= now (ya pasó su hora programada)
        # 2. O está dentro de la ventana de ±3 minutos desde la hora base Y no hay ejecuciones en próximo minuto
        
        # Obtener nodos que están en su hora programada o antes
        safety_margin = timedelta(seconds=30)  # Margen de seguridad para evitar ejecutar inmediatamente al activar
        safe_time = now - safety_margin
        
        # Obtener nodos que están listos (next_run_at <= safe_time)
        from django.db import models as db_models
        nodes_at_time = WorkflowNode.objects.filter(
            workflow=workflow,
            enabled=True,
            is_chain_node=False,  # SOLO nodos normales/master, NO nodos en cadena
            next_run_at__lte=safe_time,
            next_run_at__isnull=False
        ).filter(
            db_models.Q(oid__isnull=False) | db_models.Q(template_node__oid__isnull=False)
        ).select_related('oid', 'template_node', 'template_node__oid', 'template', 'workflow__olt', 'master_node')
        
        # Obtener nodos que pueden ejecutarse anticipadamente (dentro de ventana de ±3 minutos)
        # Solo si no hay ejecuciones en el próximo minuto
        from executions.models import Execution
        next_minute_start = now + timedelta(minutes=1)
        next_minute_end = next_minute_start + timedelta(minutes=1)
        
        # Contar ejecuciones programadas en el próximo minuto
        executions_in_next_minute = WorkflowNode.objects.filter(
            enabled=True,
            is_chain_node=False,
            next_run_at__gte=next_minute_start,
            next_run_at__lt=next_minute_end
        ).count()
        
        # Si no hay ejecuciones en el próximo minuto, considerar ejecución anticipada
        early_nodes = []
        if executions_in_next_minute == 0:
            # Buscar nodos que están dentro de la ventana de ±3 minutos desde su hora base
            # Hora base = last_run_at + interval_seconds (o next_run_at si no hay last_run_at)
            for node in WorkflowNode.objects.filter(
                workflow=workflow,
                enabled=True,
                is_chain_node=False,
                next_run_at__isnull=False
            ).filter(
                db_models.Q(oid__isnull=False) | db_models.Q(template_node__oid__isnull=False)
            ).select_related('oid', 'template_node', 'template_node__oid', 'template', 'workflow__olt', 'master_node'):
                
                # Calcular hora base
                if node.last_run_at:
                    base_time = node.last_run_at + timedelta(seconds=node.interval_seconds or 900)
                else:
                    base_time = node.next_run_at
                
                # Verificar si está dentro de la ventana de ±3 minutos
                window_start = base_time - timedelta(seconds=180)  # 3 minutos antes
                window_end = base_time + timedelta(seconds=180)    # 3 minutos después
                
                # Si next_run_at está dentro de la ventana Y está en el futuro (pero cerca)
                if window_start <= node.next_run_at <= window_end and node.next_run_at > now:
                    # Verificar que no haya ejecución PENDING o RUNNING
                    existing_execution = Execution.objects.filter(
                        workflow_node=node,
                        status__in=['PENDING', 'RUNNING']
                    ).first()
                    
                    if not existing_execution:
                        # Verificar que no haya colisiones en el tiempo de ejecución anticipada
                        execution_time = node.next_run_at
                        collision_window_start = execution_time - timedelta(seconds=30)
                        collision_window_end = execution_time + timedelta(seconds=30)
                        
                        collisions = WorkflowNode.objects.filter(
                            enabled=True,
                            is_chain_node=False,
                            next_run_at__gte=collision_window_start,
                            next_run_at__lt=collision_window_end
                        ).exclude(id=node.id).count()
                        
                        # Solo anticipar si no hay colisiones (≤5 nodos es óptimo)
                        if collisions <= 5:
                            early_nodes.append(node)
        
        # Combinar nodos listos y nodos anticipados
        all_ready_nodes = list(nodes_at_time) + early_nodes
        
        # Eliminar duplicados (por si un nodo está en ambas listas)
        seen_ids = set()
        unique_ready_nodes = []
        for node in all_ready_nodes:
            if node.id not in seen_ids:
                seen_ids.add(node.id)
                unique_ready_nodes.append(node)
        all_ready_nodes = unique_ready_nodes
        
        ready_tasks = []
        for node in all_ready_nodes:
            # Verificar si el nodo puede ejecutarse ahora (dependencias, cadenas, etc.)
            can_execute, reason = node.can_execute_now(now)
            
            if not can_execute:
                # Log solo si es importante (no spam)
                if "Dependencia" in reason or "Master" in reason:
                    coordinator_logger.debug(
                        f"⏸️ Nodo '{node.name}' esperando: {reason}",
                        olt=workflow.olt
                    )
                continue
            
            # ✅ CRÍTICO: Verificar que NO haya ejecución PENDING o RUNNING para este nodo
            # Esto previene ejecuciones duplicadas (especialmente importante para nodos normales)
            from executions.models import Execution
            existing_execution = Execution.objects.filter(
                workflow_node=node,
                status__in=['PENDING', 'RUNNING']
            ).first()
            
            if existing_execution:
                coordinator_logger.debug(
                    f"⏸️ Nodo '{node.name}' ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, omitiendo",
                    olt=workflow.olt
                )
                continue  # Omitir este nodo, ya tiene ejecución
            
            # ✅ LÓGICA SIMPLIFICADA: Los nodos se ejecutan según su intervalo
            # El coordinador puede ajustar ±3 minutos para evitar colisiones
            # NO hay límite de cuota por hora, solo respeta el intervalo configurado
            
            # ✅ POSTERGAR SI HAY NODOS RUNNING DEL MISMO TIPO
            # Determinar tipo de operación desde el OID (directo o desde template_node)
            oid = node.oid or (node.template_node.oid if node.template_node else None)
            if oid:
                if oid.espacio == 'descubrimiento':
                    job_type = 'descubrimiento'
                    priority = 90
                else:
                    job_type = 'get'
                    priority = 40
            else:
                # Fallback: usar prioridad del nodo
                job_type = 'get'
                priority = node.priority or 50
            
            # Verificar si hay ejecuciones RUNNING del mismo tipo en esta OLT
            # Si hay, postergar esta ejecución para evitar saturación
            running_same_type = Execution.objects.filter(
                olt_id=self.olt_id,
                status='RUNNING',
                snmp_job__job_type=job_type
            ).count()
            
            # ✅ POSTERGAR SI HAY NODOS RUNNING DEL MISMO TIPO
            # Si hay ejecución RUNNING del mismo tipo, postergar esta ejecución
            # (solo 1 nodo a la vez por OLT, pero podemos tener múltiples OLTs ejecutando)
            if running_same_type > 0:
                coordinator_logger.debug(
                    f"⏸️ Nodo '{node.name}' postergado: hay {running_same_type} ejecución(es) RUNNING del tipo '{job_type}'",
                    olt=workflow.olt
                )
                continue  # Postergar este nodo hasta que termine la ejecución RUNNING
            
            # Para ordenamiento: incluir timestamp de next_run_at para detectar colisiones
            next_run_timestamp = node.next_run_at.timestamp() if node.next_run_at else 0
            
            ready_tasks.append({
                'workflow_node_id': node.id,
                'node_name': node.name,
                'node_key': node.key,
                'job_type': job_type,
                'priority': priority,
                'interval_seconds': node.interval_seconds,
                'oid_id': node.template_node.oid.id if node.template_node and node.template_node.oid else None,
                'template_node_id': node.template_node.id if node.template_node else None,
                'next_run_at': node.next_run_at.isoformat() if node.next_run_at else None,
                'next_run_timestamp': next_run_timestamp,  # Para detectar colisiones de tiempo
                'is_chain_node': False,  # Ya no incluimos nodos en cadena aquí (solo desde callbacks)
                'master_node_id': None,  # Ya no incluimos nodos en cadena aquí
            })
        
        # Ordenar por prioridad (mayor primero), luego por timestamp (colisiones de tiempo)
        # Si hay colisión de tiempo (mismo intervalo), se ejecuta primero el de mayor prioridad
        ready_tasks.sort(key=lambda t: (t['next_run_timestamp'], -t['priority'], -t['workflow_node_id']), reverse=False)
        
        return ready_tasks

    def _has_discovery_job(self):
        """
        Verifica si hay nodos de descubrimiento en el workflow de esta OLT
        (nuevo sistema independiente, no usa SnmpJobHost legacy)
        """
        from snmp_jobs.models import WorkflowNode, OLTWorkflow
        
        try:
            workflow = OLTWorkflow.objects.get(olt_id=self.olt_id, is_active=True)
            return WorkflowNode.objects.filter(
                workflow=workflow,
                enabled=True,
                template_node__oid__espacio='descubrimiento'
            ).exists()
        except OLTWorkflow.DoesNotExist:
            return False

    def _has_pending_or_running_discovery(self):
        """
        Verifica si hay ejecuciones de descubrimiento pendientes o en curso
        (nuevo sistema independiente, verifica por workflow_node)
        """
        from executions.models import Execution
        from snmp_jobs.models import WorkflowNode, OLTWorkflow
        
        try:
            workflow = OLTWorkflow.objects.get(olt_id=self.olt_id, is_active=True)
            discovery_nodes = WorkflowNode.objects.filter(
                workflow=workflow,
                enabled=True,
                template_node__oid__espacio='descubrimiento'
            )
            
            statuses = [
                Execution.STATUS_PENDING,
                Execution.STATUS_RUNNING,
            ]
            return Execution.objects.filter(
                olt_id=self.olt_id,
                workflow_node__in=discovery_nodes,
                status__in=statuses
            ).exists()
        except OLTWorkflow.DoesNotExist:
            return False
    
    def enqueue_task(self, task_info):
        """
        Encola una tarea para ejecución posterior
        (nuevo sistema: usa workflow_node_id en lugar de job_id/job_host_id)
        """
        queue_data = {
            'workflow_node_id': task_info.get('workflow_node_id'),  # ← NUEVO sistema
            'node_name': task_info.get('node_name', task_info.get('job_name', 'Unknown')),
            'job_type': task_info['job_type'],
            'priority': task_info['priority'],
            'enqueued_at': timezone.now().isoformat(),
        }
        
        # Agregar a cola con orden de prioridad
        # rpush = al final (FIFO dentro de misma prioridad)
        redis_client.rpush(self.queue_key, json.dumps(queue_data))
        redis_client.expire(self.queue_key, 3600)  # Expirar en 1 hora
    
    def execute_next_in_queue(self, olt):
        """
        Ejecuta la siguiente tarea en cola INMEDIATAMENTE
        (nuevo sistema: usa WorkflowNode directamente)
        
        Returns:
            bool: True si ejecutó una tarea, False si no había nada
        """
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
        
        # Ejecutar INMEDIATAMENTE usando el nuevo sistema
        # Si tiene workflow_node_id, usar _execute_task_now directamente
        if 'workflow_node_id' in next_task:
            return self._execute_task_now(next_task, olt)
        
        # Compatibilidad con sistema legacy (si hay job_id/job_host_id)
        # Esto no debería ocurrir en el nuevo sistema, pero lo mantenemos por seguridad
        logger.warning(f"⚠️ Tarea en cola con formato legacy, usando _execute_task_now con adaptación")
        return self._execute_task_now(next_task, olt)
    
    def process_ready_tasks(self, olt):
        """
        Procesa nodos listos para ejecutar RESPETANDO INTERVALOS Y PRIORIDADES.
        Solo 1 nodo a la vez por OLT, pero el sistema puede ejecutar nodos de diferentes
        OLTs simultáneamente (hasta 20 OLTs diferentes ejecutando nodos al mismo tiempo).
        
        LÓGICA CRÍTICA:
        1. Solo ejecuta si next_run_at <= now (respeta intervalo) o si es nodo en cadena
        2. Si OLT ocupada (tiene 1 ejecución) → encola para ejecutar DESPUÉS
        3. Si OLT libre → ejecuta 1 nodo (el de mayor prioridad)
        4. Si hay colisiones de tiempo (mismo intervalo), ejecuta primero el de mayor prioridad
        5. Cuando termina un nodo master, el callback ejecuta sus nodos en cadena secuencialmente
        6. Cuando termina cualquier nodo, el callback ejecuta la siguiente en cola
        
        IMPORTANTE: 
        - NO ejecuta todo corrido
        - RESPETA el intervalo configurado (20 min = 3 veces/hora)
        - Optimiza el ORDEN de ejecución cuando hay colisión de tiempo usando prioridad
        - Solo verifica que nodo/plantilla/host estén activos (is_executable)
        - Solo 1 nodo a la vez por OLT
        - El sistema puede ejecutar nodos de hasta 20 OLTs diferentes simultáneamente
        """
        ready_tasks = self.get_ready_tasks()
        
        if not ready_tasks:
            return 0  # No hay nodos listos (next_run_at > now)
        
        # ✅ WORKFLOW → COORDINADOR: El workflow tiene nodos listos, llama al coordinador
        from hosts.models import OLT
        olt = OLT.objects.get(id=self.olt_id)
        coordinator_logger.info(
            f"📞 WORKFLOW → COORDINADOR: {len(ready_tasks)} nodo(s) listo(s) en OLT {olt.abreviatura} (independiente)",
            olt=olt,
            event_type='WORKFLOW_TO_COORDINATOR',
            details={
                'ready_tasks_count': len(ready_tasks),
                'tasks': [{'name': t.get('node_name'), 'type': t.get('job_type'), 'priority': t.get('priority')} for t in ready_tasks[:5]]
            }
        )
        
        # Verificar si OLT está ocupada (tiene al menos 1 ejecución)
        # Cada OLT es independiente, solo 1 nodo a la vez por OLT
        is_busy = self.is_olt_busy(log_reason=True)
        
        if is_busy:
            # OLT ocupada, encolar TODOS los nodos listos para ejecución posterior
            # Ordenados por prioridad (ya vienen ordenados de get_ready_tasks)
            # ✅ IMPORTANTE: NO SE PIERDEN, se encolan y se ejecutarán cuando la OLT esté libre
            for task in ready_tasks:
                # Verificar si ya está en cola
                queue_items = redis_client.lrange(self.queue_key, 0, -1)
                already_queued = any(
                    json.loads(item).get('workflow_node_id') == task.get('workflow_node_id')
                    for item in queue_items
                )
                
                if not already_queued:
                    self.enqueue_task(task)
                    
                    coordinator_logger.info(
                        f"📞 WORKFLOW → COORDINADOR: Nodo '{task.get('node_name', 'Unknown')}' ENCOLADO en OLT {olt.abreviatura} (OLT ocupada - NO SE PIERDE)",
                        olt=olt,
                        event_type='TASK_ADDED',
                        details=task
                    )
            
            return 0  # No ejecutó nada, solo encoló (NO SE PIERDEN)
        
        else:
            # OLT libre, ejecutar el nodo de MAYOR PRIORIDAD
            # Los nodos ya vienen ordenados por prioridad de get_ready_tasks()
            first_task = ready_tasks[0]
            
            # Verificar capacidad de Celery antes de ejecutar
            if not self._check_celery_capacity(first_task['job_type']):
                # Celery saturado, encolar todos los nodos (NO SE PIERDEN)
                coordinator_logger.info(
                    f"📞 WORKFLOW → COORDINADOR: Celery saturado, encolando {len(ready_tasks)} nodo(s) en OLT {olt.abreviatura} (NO SE PIERDEN)",
                    olt=olt,
                    event_type='CAPACITY_EXCEEDED'
                )
                for task in ready_tasks:
                    queue_items = redis_client.lrange(self.queue_key, 0, -1)
                    already_queued = any(
                        json.loads(item).get('workflow_node_id') == task.get('workflow_node_id')
                        for item in queue_items
                    )
                    
                    if not already_queued:
                        self.enqueue_task(task)
                return 0
            
            # Encolar el resto (se ejecutarán cuando termine el primero)
            # Respetando el orden de prioridad
            for task in ready_tasks[1:]:
                # Verificar si ya está en cola
                queue_items = redis_client.lrange(self.queue_key, 0, -1)
                already_queued = any(
                    json.loads(item).get('workflow_node_id') == task.get('workflow_node_id')
                    for item in queue_items
                )
                
                if not already_queued:
                    self.enqueue_task(task)
            
            # Ejecutar el primero (mayor prioridad) - solo 1 nodo a la vez por OLT
            # ✅ WORKFLOW → COORDINADOR: Ejecutar nodo de mayor prioridad
            executed = self._execute_task_now(first_task, olt)
            
            if executed:
                coordinator_logger.info(
                    f"📞 WORKFLOW → COORDINADOR: Nodo '{first_task.get('node_name', 'Unknown')}' EJECUTADO en OLT {olt.abreviatura}",
                    olt=olt,
                    event_type='TASK_EXECUTED',
                    details=first_task
                )
                return 1  # Ejecutó 1 nodo
            else:
                # Si no se pudo ejecutar, encolar (NO SE PIERDE)
                self.enqueue_task(first_task)
                coordinator_logger.info(
                    f"📞 WORKFLOW → COORDINADOR: Nodo '{first_task.get('node_name', 'Unknown')}' ENCOLADO (no se pudo ejecutar - NO SE PIERDE) en OLT {olt.abreviatura}",
                    olt=olt,
                    event_type='TASK_ADDED',
                    details=first_task
                )
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
        
        # Límites de capacidad por tipo de nodo
        # Permite que hasta 20 OLTs diferentes ejecuten nodos simultáneamente
        # (1 nodo por OLT = hasta 20 nodos simultáneos del mismo tipo)
        CAPACITY_LIMITS = {
            'descubrimiento': 20,  # Máximo 20 Discovery PENDING (1 por OLT, hasta 20 OLTs)
            'get': 20             # Máximo 20 GET PENDING (1 por OLT, hasta 20 OLTs)
        }
        
        limit = CAPACITY_LIMITS.get(job_type, 20)
        
        # Contar ejecuciones PENDING del mismo tipo
        pending_count = Execution.objects.filter(
            status='PENDING',
            snmp_job__job_type=job_type
        ).count()
        
        if pending_count >= limit:
            logger.debug(f"⏸️ Sistema con capacidad limitada: {pending_count} nodos {job_type} PENDING (límite: {limit})")
            return False
        
        return True
    
    @staticmethod
    def check_poller_capacity_and_delay():
        """
        ✅ LÓGICA AVANZADA: Verifica capacidad de pollers y atrasa ejecuciones si están saturados
        
        Si hay ejecuciones que duran más de 1 minuto y los pollers están saturados,
        atrasa las siguientes ejecuciones en 10 segundos hasta que haya espacio.
        
        Aplica tanto a nodos master como a nodos en cadena (GET o descubrimiento).
        A pesar de ser cadena, se atrasa si los pollers están saturados.
        """
        from snmp_jobs.models import WorkflowNode, OLTWorkflow
        from hosts.models import OLT
        from executions.models import Execution
        from django.utils import timezone
        from datetime import timedelta
        from celery import Celery
        from django.conf import settings
        import pytz
        
        peru_tz = pytz.timezone('America/Lima')
        now_utc = timezone.now()
        
        # Obtener inspector de Celery
        app = Celery('facho_deluxe_v2')
        app.config_from_object('django.conf:settings', namespace='CELERY')
        inspector = app.control.inspect()
        
        try:
            # Obtener tareas activas en workers
            active_tasks = inspector.active() or {}
            reserved_tasks = inspector.reserved() or {}
            
            # Contar tareas por tipo y cola (verificar workers específicos)
            discovery_active = 0
            get_poller_active = 0
            get_main_active = 0
            
            # Contar tareas en workers de discovery
            for worker_name, worker_tasks in active_tasks.items():
                if 'discovery' in worker_name.lower():
                    if isinstance(worker_tasks, list):
                        discovery_active += len(worker_tasks)
            
            for worker_name, worker_tasks in reserved_tasks.items():
                if 'discovery' in worker_name.lower():
                    if isinstance(worker_tasks, list):
                        discovery_active += len(worker_tasks)
            
            # Contar tareas en workers de GET
            for worker_name, worker_tasks in active_tasks.items():
                if 'get' in worker_name.lower():
                    if isinstance(worker_tasks, list):
                        if 'poller' in worker_name.lower():
                            get_poller_active += len(worker_tasks)
                        else:
                            get_main_active += len(worker_tasks)
            
            for worker_name, worker_tasks in reserved_tasks.items():
                if 'get' in worker_name.lower():
                    if isinstance(worker_tasks, list):
                        if 'poller' in worker_name.lower():
                            get_poller_active += len(worker_tasks)
                        else:
                            get_main_active += len(worker_tasks)
            
            # Límites de capacidad de pollers
            # get_poller: 20 workers (concurrency)
            # discovery_main: 20 workers (concurrency)
            POLLER_CAPACITY = {
                'descubrimiento': 20,
                'get_poller': 20,
                'get_main': 20
            }
            
            # Verificar ejecuciones RUNNING que duran más de 1 minuto
            long_running = Execution.objects.filter(
                status='RUNNING',
                started_at__lt=now_utc - timedelta(minutes=1)
            ).select_related('snmp_job', 'workflow_node', 'olt', 'workflow_node__workflow')
            
            delayed_count = 0
            
            for execution in long_running:
                job_type = execution.snmp_job.job_type if execution.snmp_job else None
                workflow_node = execution.workflow_node
                
                if not workflow_node or not job_type:
                    continue
                
                # Determinar si necesita atrasar según tipo y saturación de pollers
                needs_delay = False
                poller_type = None
                poller_usage = 0
                
                if job_type == 'descubrimiento':
                    poller_usage = discovery_active
                    if discovery_active >= POLLER_CAPACITY['descubrimiento'] * 0.8:  # 80% de capacidad
                        needs_delay = True
                        poller_type = 'descubrimiento'
                elif job_type == 'get':
                    # Para GET, verificar pollers primero (más crítico)
                    poller_usage = get_poller_active
                    if get_poller_active >= POLLER_CAPACITY['get_poller'] * 0.8:  # 80% de capacidad
                        needs_delay = True
                        poller_type = 'get_poller'
                    elif get_main_active >= POLLER_CAPACITY['get_main'] * 0.8:
                        needs_delay = True
                        poller_type = 'get_main'
                        poller_usage = get_main_active
                
                if needs_delay:
                    # Buscar el siguiente nodo a ejecutar (master o cadena)
                    try:
                        workflow = execution.workflow_node.workflow if execution.workflow_node.workflow else OLTWorkflow.objects.get(olt=execution.olt, is_active=True)
                        
                        next_node = None
                        
                        # Si es un nodo en cadena, buscar el siguiente en la cadena
                        if workflow_node.is_chain_node and workflow_node.master_node:
                            chain_nodes = workflow_node.master_node.get_chain_nodes()
                            all_chain_nodes = list(chain_nodes)
                            current_index = None
                            
                            for i, node in enumerate(all_chain_nodes):
                                if node.id == workflow_node.id:
                                    current_index = i
                                    break
                            
                            if current_index is not None and current_index < len(all_chain_nodes) - 1:
                                # Hay siguiente nodo en cadena
                                next_node = all_chain_nodes[current_index + 1]
                        
                        # Si no hay siguiente en cadena, buscar siguiente nodo master del workflow
                        if not next_node:
                            next_nodes = WorkflowNode.objects.filter(
                                workflow=workflow,
                                enabled=True,
                                is_chain_node=False,
                                next_run_at__isnull=False,
                                next_run_at__gt=now_utc
                            ).order_by('next_run_at')[:1]
                            
                            if next_nodes.exists():
                                next_node = next_nodes.first()
                        
                        # Si aún no hay siguiente, buscar primer nodo en cadena pendiente
                        if not next_node:
                            # Buscar nodos en cadena que dependen del master actual
                            if workflow_node.is_chain_node and workflow_node.master_node:
                                # Ya estamos en cadena, no hay más
                                pass
                            else:
                                # Buscar nodos en cadena que dependen de este master
                                chain_nodes = WorkflowNode.objects.filter(
                                    workflow=workflow,
                                    enabled=True,
                                    is_chain_node=True,
                                    master_node=workflow_node
                                ).order_by('priority', 'id')[:1]
                                
                                if chain_nodes.exists():
                                    next_node = chain_nodes.first()
                        
                        if next_node and next_node.next_run_at:
                            # Atrasar en 10 segundos (aunque sea nodo en cadena)
                            new_next_run = next_node.next_run_at + timedelta(seconds=10)
                            old_next_run = next_node.next_run_at
                            next_node.next_run_at = new_next_run
                            next_node.save(update_fields=['next_run_at'])
                            delayed_count += 1
                            
                            node_type = "cadena" if next_node.is_chain_node else "master"
                            coordinator_logger.info(
                                f"⏱️ COORDINADOR: Atrasando ejecución - OLT {execution.olt.abreviatura} "
                                f"nodo '{next_node.name}' ({node_type}) +10s (pollers {poller_type} al {int(poller_usage / POLLER_CAPACITY.get(poller_type, 20) * 100)}% capacidad)",
                                olt=execution.olt,
                                event_type='EXECUTION_DELAYED',
                                details={
                                    'node_id': next_node.id,
                                    'node_type': node_type,
                                    'old_time': old_next_run.isoformat(),
                                    'new_time': new_next_run.isoformat(),
                                    'delay_seconds': 10,
                                    'poller_type': poller_type,
                                    'poller_usage': poller_usage,
                                    'poller_capacity': POLLER_CAPACITY.get(poller_type, 20),
                                    'reason': 'poller_saturated',
                                    'long_running_execution_id': execution.id
                                }
                            )
                    except Exception as e:
                        logger.warning(f"Error atrasando ejecución para OLT {execution.olt_id}: {e}", exc_info=True)
            
            if delayed_count > 0:
                coordinator_logger.info(
                    f"⏱️ COORDINADOR: Atrasadas {delayed_count} ejecución(es) por saturación de pollers "
                    f"(Discovery: {discovery_active}/{POLLER_CAPACITY['descubrimiento']}, "
                    f"GET Poller: {get_poller_active}/{POLLER_CAPACITY['get_poller']}, "
                    f"GET Main: {get_main_active}/{POLLER_CAPACITY['get_main']})",
                    event_type='DELAYS_APPLIED',
                    details={
                        'delayed_count': delayed_count,
                        'discovery_active': discovery_active,
                        'get_poller_active': get_poller_active,
                        'get_main_active': get_main_active
                    }
                )
            
            return delayed_count
            
        except Exception as e:
            logger.error(f"Error verificando capacidad de pollers: {e}", exc_info=True)
            return 0
    
    def _execute_task_now(self, task_info, olt):
        """
        Ejecuta una tarea INMEDIATAMENTE (si hay capacidad en Celery)
        
        IMPORTANTE: Ahora trabaja con WorkflowNode directamente, no con SnmpJobHost (legacy)
        
        Returns:
            bool: True si se ejecutó correctamente
        """
        from snmp_jobs.models import SnmpJob, SnmpJobHost, WorkflowNode
        from executions.models import Execution
        
        try:
            # Obtener el WorkflowNode (nuevo sistema independiente)
            workflow_node = WorkflowNode.objects.select_related(
                'template_node', 'template_node__oid', 'workflow__olt'
            ).get(id=task_info['workflow_node_id'])
            
            # Obtener el OID (puede venir directamente del nodo o desde template_node)
            oid = workflow_node.oid or (workflow_node.template_node.oid if workflow_node.template_node else None)
            if not oid:
                logger.warning(
                    f"⏸️ WorkflowNode {workflow_node.id} ('{workflow_node.name}') no tiene OID asociado, "
                    f"omitido (los nodos sin OID no se ejecutan automáticamente)"
                )
                return False
            
            # Buscar o crear SnmpJob para compatibilidad con tareas Celery existentes
            # Las tareas Celery todavía esperan snmp_job_id
            job, job_created = SnmpJob.objects.get_or_create(
                oid=oid,
                job_type=task_info['job_type'],
                defaults={
                    'nombre': f"[Workflow] {workflow_node.name}",
                    'descripcion': f"Generado automáticamente desde WorkflowNode {workflow_node.key}",
                    'marca': olt.marca,  # Usar marca de la OLT
                    'interval_seconds': workflow_node.interval_seconds,
                    'enabled': True,
                }
            )
            
            # Buscar o crear SnmpJobHost para compatibilidad (legacy)
            job_host, host_created = SnmpJobHost.objects.get_or_create(
                snmp_job=job,
                olt=olt,
                defaults={
                    'enabled': True,
                }
            )

            # ✅ BLOQUEO ELIMINADO: Ya no se bloquea GET por Discovery pendiente
            # La prioridad se respeta en la cola, pero no se bloquea la ejecución de tareas específicas
            # Solo se verifica que el nodo/plantilla/host estén activos (is_executable)
            
            # ✅ NUEVO: Verificar capacidad de Celery ANTES de crear ejecución
            if not self._check_celery_capacity(job.job_type):
                # Sistema saturado, mantener en cola del coordinador
                coordinator_logger.warning(
                    f"⏸️ Sistema saturado, manteniendo {workflow_node.name} en cola interna",
                    olt=olt,
                    event_type='CAPACITY_EXCEEDED',
                    details={'job_type': job.job_type}
                )
                # NO eliminar de la cola, se reintentará en el siguiente loop
                return False
            
            # ✅ NUEVO: Ya no se verifican locks de reintento a nivel de tarea
            # Los reintentos se manejan a nivel de configuración SNMP (ConfiguracionSNMP)
            
            # Ya no verificamos lock individual - permitimos múltiples ejecuciones simultáneas por OLT
            # La verificación de capacidad se hace en process_ready_tasks() y is_olt_busy()
            
            # ✅ CRÍTICO: Verificar que NO haya otra ejecución PENDING o RUNNING para este nodo
            existing_execution = Execution.objects.filter(
                workflow_node=workflow_node,
                status__in=['PENDING', 'RUNNING']
            ).first()
            
            if existing_execution:
                logger.warning(
                    f"⚠️ {workflow_node.name} ya tiene ejecución {existing_execution.id} en estado {existing_execution.status}, omitiendo"
                )
                return False
            
            # LOCK ATÓMICO: Evitar crear la misma ejecución dos veces
            execution_lock_key = f"lock:create_execution:{self.olt_id}:{workflow_node.id}"
            lock_acquired = redis_client.set(execution_lock_key, '1', nx=True, ex=5)
            
            if not lock_acquired:
                logger.warning(f"⚠️ Lock no disponible para {workflow_node.name}, omitiendo")
                return False
            
            # Verificar last_run_at del WorkflowNode (nuevo sistema)
            if workflow_node.last_run_at:
                time_since_last = (timezone.now() - workflow_node.last_run_at).total_seconds()
                if time_since_last < 3:
                    logger.warning(f"⚠️ {workflow_node.name} se ejecutó hace {time_since_last:.1f}s, omitiendo")
                    redis_client.delete(execution_lock_key)
                    return False
            
            # ACTUALIZAR next_run_at del WorkflowNode ANTES de crear ejecución
            # IMPORTANTE: Usar el intervalo del nodo, no del job
            # Los nodos en cadena NO tienen intervalo (se ejecutan después del master)
            now = timezone.now()
            
            if workflow_node.is_chain_node:
                # Nodos en cadena no tienen next_run_at (se ejecutan secuencialmente)
                # Solo actualizar last_run_at
                workflow_node.last_run_at = now
                workflow_node.save(update_fields=['last_run_at'])
                
                # Para compatibilidad legacy, usar intervalo del master o default
                master_interval = workflow_node.master_node.interval_seconds if workflow_node.master_node else 300
                job_host.next_run_at = None  # Nodos en cadena no tienen next_run_at
                job_host.last_run_at = now
                job_host.save(update_fields=['last_run_at'])
            else:
                # Nodo normal o master: calcular next_run_at con hora base variable
                interval_seconds = workflow_node.interval_seconds or 300
                
                # ✅ LÓGICA SIMPLIFICADA: Sin cuota, solo respeta intervalo
                # Hora base = última ejecución + intervalo (o ahora + intervalo si no hay última ejecución)
                if workflow_node.last_run_at:
                    base_time = workflow_node.last_run_at + timedelta(seconds=interval_seconds)
                else:
                    base_time = now + timedelta(seconds=interval_seconds)
                
                # ✅ VENTANA DE VARIACIÓN: ±180 segundos (±3 minutos) desde la hora base
                # El coordinador puede variar dentro de esta ventana para evitar colisiones
                # Por defecto, usar la hora base (sin variación)
                next_time = base_time
                
                # Verificar colisiones: buscar otros nodos que se ejecuten en el mismo minuto
                # (margen de 30 segundos es suficiente, óptimo hasta 5 nodos simultáneos)
                import pytz
                peru_tz = pytz.timezone('America/Lima')
                base_time_peru = timezone.localtime(base_time, peru_tz)
                
                # Buscar colisiones en el rango de ±30 segundos desde la hora base
                collision_window_start = base_time - timedelta(seconds=30)
                collision_window_end = base_time + timedelta(seconds=30)
                
                # Contar nodos que se ejecutan en esta ventana (excluyendo este nodo)
                # Solo contar nodos master/normales (NO nodos en cadena)
                from snmp_jobs.models import WorkflowNode
                collisions = WorkflowNode.objects.filter(
                    enabled=True,
                    is_chain_node=False,
                    next_run_at__gte=collision_window_start,
                    next_run_at__lt=collision_window_end
                ).exclude(id=workflow_node.id).count()
                
                # Si hay colisiones (>5 nodos en mismo minuto), ajustar horario
                if collisions > 5:
                    # Calcular desfase para evitar colisión
                    # Distribuir en rango de ±180 segundos desde la hora base
                    # Usar OLT ID para distribución consistente
                    olt_id_hash = olt.id % 20
                    stagger_seconds = (olt_id_hash * 9) - 90  # Rango: -90 a +90 segundos
                    
                    # Aplicar desfase
                    next_time = base_time + timedelta(seconds=stagger_seconds)
                    
                    # Asegurar que el tiempo ajustado esté en el futuro
                    if next_time <= now:
                        next_time = base_time
                    
                    coordinator_logger.debug(
                        f"🔄 COORDINADOR: Ajuste por colisión - OLT {olt.abreviatura} "
                        f"nodo '{workflow_node.name}' ajustado {stagger_seconds:+d}s "
                        f"({timezone.localtime(base_time, peru_tz).strftime('%H:%M:%S')} → {timezone.localtime(next_time, peru_tz).strftime('%H:%M:%S')}) "
                        f"[{collisions} colisiones]",
                        olt=olt,
                        event_type='EXECUTION_ADJUSTED',
                        details={
                            'node_id': workflow_node.id,
                            'base_time': base_time.isoformat(),
                            'adjusted_time': next_time.isoformat(),
                            'stagger_seconds': stagger_seconds,
                            'collisions': collisions,
                            'reason': 'collision_avoidance'
                        }
                    )
                
                # Actualizar WorkflowNode (nuevo sistema independiente)
                workflow_node.next_run_at = next_time
                workflow_node.last_run_at = now
                workflow_node.save(update_fields=['next_run_at', 'last_run_at'])
                
                # También actualizar SnmpJobHost para compatibilidad (legacy)
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
                workflow_node=workflow_node,  # ✅ CRÍTICO: Asignar workflow_node para tracking
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
                f"▶️ Ejecutando: {workflow_node.name} (WorkflowNode) en {olt.abreviatura} (P{task_info['priority']})",
                olt=olt,
                event_type='EXECUTION_STARTED',
                details={**task_info, 'execution_id': execution.id, 'workflow_node_id': workflow_node.id}
            )
            
            # next_run_at ya fue actualizado ANTES de crear la ejecución
            # para evitar detecciones duplicadas
            
            # ✅ NUEVO: Si es un nodo master, preparar nodos en cadena para ejecución
            # Los nodos en cadena se ejecutarán automáticamente cuando el master termine
            # (se maneja en callbacks.py)
            
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

