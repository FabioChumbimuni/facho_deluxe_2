"""
Coordinador Inteligente de Ejecuciones SNMP

Este módulo implementa el loop continuo que:
- Lee el estado completo del sistema
- Detecta cambios en tareas/OLTs
- Reformula planes dinámicamente
- Gestiona cuotas y prioridades
- Previene colisiones entre tareas
"""

import hashlib
import json
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from redis import Redis
from django.conf import settings

from .logger import CoordinatorLogger
from .models import QuotaTracker, CoordinatorLog

# Logger específico del coordinator
logger = CoordinatorLogger('coordinator_loop')

# Cliente Redis
redis_client = Redis.from_url(settings.CELERY_BROKER_URL)


class ExecutionCoordinator:
    """
    Coordinador de ejecuciones para una OLT específica
    """
    
    def __init__(self, olt_id):
        self.olt_id = olt_id
        self.state_key = f"coordinator:state:olt:{olt_id}"
        self.plan_key = f"coordinator:plan:olt:{olt_id}"
    
    def get_system_state(self):
        """
        Lee el estado COMPLETO del sistema para esta OLT
        
        Returns:
            dict: Estado completo con OLT, tareas, ejecuciones, locks, colas, etc.
        """
        from snmp_jobs.models import SnmpJob, SnmpJobHost
        from executions.models import Execution
        from hosts.models import OLT
        
        try:
            # 1. Estado de la OLT
            olt = OLT.objects.get(id=self.olt_id)
            olt_state = {
                'enabled': olt.habilitar_olt,
                'ip': olt.ip_address,
                'abreviatura': olt.abreviatura,
                'comunidad': olt.comunidad,
            }
            
            # 2. Tareas asociadas a esta OLT
            job_hosts = SnmpJobHost.objects.filter(
                olt_id=self.olt_id,
                enabled=True
            ).select_related('snmp_job', 'snmp_job__oid')
            
            tasks_state = []
            for jh in job_hosts:
                job = jh.snmp_job
                
                # Solo tareas habilitadas
                if not job.enabled:
                    continue
                
                # IMPORTANTE: Usar SnmpJobHost.next_run_at (POR OLT)
                tasks_state.append({
                    'job_id': job.id,
                    'job_host_id': jh.id,
                    'job_name': job.nombre,
                    'job_type': job.job_type,
                    'enabled': job.enabled,
                    'interval_raw': job.interval_raw,
                    'interval_seconds': job.interval_seconds,
                    'next_run_at': jh.next_run_at.isoformat() if jh.next_run_at else None,  # ← De SnmpJobHost
                    'last_run_at': jh.last_run_at.isoformat() if jh.last_run_at else None,  # ← De SnmpJobHost
                    'priority': self._get_task_priority(job.job_type),
                    'oid': job.oid.oid if job.oid else None,
                    'oid_espacio': job.oid.espacio if job.oid else None,
                })
            
            # 3. Ejecuciones activas
            active_executions = list(Execution.objects.filter(
                olt_id=self.olt_id,
                status__in=['RUNNING', 'PENDING']
            ).select_related('snmp_job').values(
                'id', 'status', 'snmp_job_id', 'snmp_job__job_type',
                'snmp_job__nombre', 'started_at', 'created_at', 'attempt'
            ))
            
            # 4. Estado de locks
            lock_status = redis_client.get(f"lock:execution:olt:{self.olt_id}")
            try:
                lock_state = json.loads(lock_status) if lock_status else None
            except json.JSONDecodeError:
                lock_state = None
            
            # 5. Cola de espera
            queue_items = redis_client.lrange(
                f"queue:olt:{self.olt_id}:pending", 0, -1
            )
            queue_state = []
            for item in queue_items:
                try:
                    queue_state.append(json.loads(item))
                except json.JSONDecodeError:
                    pass  # Ignorar items corruptos
            
            # 6. Quota trackers de la hora actual
            current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
            quota_trackers = list(QuotaTracker.objects.filter(
                olt_id=self.olt_id,
                period_start=current_hour
            ).values(
                'task_type', 'quota_required', 'quota_completed',
                'quota_failed', 'quota_pending', 'status'
            ))
            
            return {
                'timestamp': timezone.now().isoformat(),
                'olt': olt_state,
                'tasks': tasks_state,
                'executions': active_executions,
                'lock': lock_state,
                'queue': queue_state,
                'quotas': quota_trackers,
            }
            
        except OLT.DoesNotExist:
            logger.error(f"OLT {self.olt_id} no existe", details={'olt_id': self.olt_id})
            return None
        except json.JSONDecodeError as e:
            # Estado corrupto en Redis - auto-corregido, no es crítico
            logger.warning(f"Estado corrupto en Redis para OLT {self.olt_id}, ignorando")
            return None
        except Exception as e:
            logger.error(f"Error leyendo estado para OLT {self.olt_id}: {e}", details={'error': str(e)})
            return None
    
    def _get_task_priority(self, job_type):
        """Retorna prioridad numérica por tipo de tarea"""
        priorities = {
            'descubrimiento': 90,
            'get': 40,
            'walk': 30,
            'table': 20,
            'bulk': 10,
        }
        return priorities.get(job_type, 50)
    
    def calculate_state_hash(self, state):
        """
        Calcula hash SHA256 del estado para detectar cambios
        """
        if not state:
            return None
        
        # Excluir timestamp y datos volátiles del hash
        state_copy = state.copy()
        state_copy.pop('timestamp', None)
        state_copy.pop('executions', None)  # Las ejecuciones cambian constantemente
        
        # Serializar y hashear
        state_json = json.dumps(state_copy, sort_keys=True)
        return hashlib.sha256(state_json.encode()).hexdigest()
    
    def detect_changes(self, current_state, previous_state):
        """
        Detecta cambios específicos entre dos estados
        
        Returns:
            dict: Información sobre cambios detectados
        """
        if not previous_state:
            return {'type': 'initial', 'changes': []}
        
        if not current_state:
            return {'type': 'error', 'changes': []}
        
        changes = []
        
        try:
            # 1. Detectar cambios en tareas
            prev_tasks = {t['job_id']: t for t in previous_state.get('tasks', [])}
            curr_tasks = {t['job_id']: t for t in current_state.get('tasks', [])}
            
            # Tareas nuevas (agregadas o habilitadas)
            new_task_ids = set(curr_tasks.keys()) - set(prev_tasks.keys())
            for task_id in new_task_ids:
                task = curr_tasks[task_id]
                changes.append({
                    'type': 'task_added',
                    'task_id': task_id,
                    'task_name': task['job_name'],
                    'task_type': task['job_type'],
                    'action_required': 'add_to_plan'
                })
            
            # Tareas eliminadas (deshabilitadas o removidas)
            removed_task_ids = set(prev_tasks.keys()) - set(curr_tasks.keys())
            for task_id in removed_task_ids:
                task = prev_tasks[task_id]
                changes.append({
                    'type': 'task_removed',
                    'task_id': task_id,
                    'task_name': task['job_name'],
                    'task_type': task['job_type'],
                    'action_required': 'remove_from_plan'
                })
            
            # Tareas modificadas
            for task_id in set(prev_tasks.keys()) & set(curr_tasks.keys()):
                prev_task = prev_tasks[task_id]
                curr_task = curr_tasks[task_id]
                
                if prev_task['interval_seconds'] != curr_task['interval_seconds']:
                    changes.append({
                        'type': 'task_interval_changed',
                        'task_id': task_id,
                        'task_name': curr_task['job_name'],
                        'old_interval': prev_task['interval_seconds'],
                        'new_interval': curr_task['interval_seconds'],
                        'action_required': 'recalculate_quota'
                    })
            
            # 2. Detectar cambios en OLT
            prev_olt = previous_state.get('olt', {})
            curr_olt = current_state.get('olt', {})
            
            if prev_olt.get('enabled') != curr_olt.get('enabled'):
                if curr_olt.get('enabled'):
                    changes.append({
                        'type': 'olt_enabled',
                        'action_required': 'resume_executions'
                    })
                else:
                    changes.append({
                        'type': 'olt_disabled',
                        'action_required': 'abort_all_executions'
                    })
            
        except Exception as e:
            logger.error(f"Error detectando cambios: {e}", details={'error': str(e)})
        
        return {
            'type': 'changes_detected' if changes else 'no_changes',
            'count': len(changes),
            'changes': changes
        }
    
    def handle_changes(self, changes_info):
        """
        Maneja los cambios detectados ejecutando las acciones necesarias
        """
        if changes_info['type'] in ['initial', 'no_changes', 'error']:
            return
        
        changes = changes_info['changes']
        
        if not changes:
            return
        
        from hosts.models import OLT
        
        try:
            olt = OLT.objects.get(id=self.olt_id)
        except OLT.DoesNotExist:
            return
        
        logger.info(
            f"🔄 {len(changes)} cambio(s) detectado(s) en {olt.abreviatura}",
            olt=olt,
            event_type='STATE_CHANGE',
            details={'changes_count': len(changes)}
        )
        
        for change in changes:
            action = change.get('action_required')
            
            try:
                if action == 'remove_from_plan':
                    self._handle_task_removed(change, olt)
                
                elif action == 'add_to_plan':
                    self._handle_task_added(change, olt)
                
                elif action == 'recalculate_quota':
                    self._handle_quota_recalculation(change, olt)
                
                elif action == 'abort_all_executions':
                    self._handle_olt_disabled(olt)
                
                elif action == 'resume_executions':
                    self._handle_olt_enabled(olt)
                    
            except Exception as e:
                logger.error(
                    f"Error manejando cambio {action}: {e}",
                    olt=olt,
                    details={'change': change, 'error': str(e)}
                )
    
    def check_and_apply_stagger(self, current_state, olt):
        """
        Verifica si hay colisiones y aplica desfase automático
        
        Args:
            current_state: Estado actual del sistema
            olt: Objeto OLT
        """
        from .stagger import CollisionDetector
        
        tasks = current_state.get('tasks', [])
        
        if len(tasks) <= 1:
            return  # No hay posibles colisiones con 1 sola tarea
        
        # Detectar y aplicar desfase
        detector = CollisionDetector(self.olt_id)
        adjusted = detector.apply_stagger(tasks, olt)
        
        return adjusted
    
    def _handle_task_removed(self, change, olt):
        """Maneja cuando una tarea se deshabilita"""
        from executions.models import Execution
        from snmp_jobs.models import SnmpJob
        
        task_id = change['task_id']
        task_name = change['task_name']
        
        logger.log_task_removed(task_name, olt=olt, details=change)
        
        # Abortar ejecuciones pendientes
        aborted = Execution.objects.filter(
            snmp_job_id=task_id,
            olt_id=self.olt_id,
            status='PENDING'
        ).update(
            status='INTERRUPTED',
            finished_at=timezone.now(),
            error_message='Tarea deshabilitada por usuario'
        )
        
        if aborted > 0:
            logger.info(f"  🛑 {aborted} ejecución(es) abortada(s)", olt=olt)
        
        # Remover de cola de espera
        self._remove_from_queue(task_id)
        
        # Ajustar cuota
        self._adjust_quota_for_removed_task(task_id, change['task_type'])
    
    def _handle_task_added(self, change, olt):
        """Maneja cuando una tarea se habilita o crea"""
        from snmp_jobs.models import SnmpJob
        
        task_id = change['task_id']
        task_name = change['task_name']
        
        logger.log_task_added(task_name, olt=olt, details=change)
        
        # Crear QuotaTracker para esta tarea
        job = SnmpJob.objects.get(id=task_id)
        self._create_quota_tracker(job, change['task_type'])
    
    def _handle_quota_recalculation(self, change, olt):
        """Maneja cuando cambia el intervalo de una tarea"""
        logger.log_plan_adjusted(olt, "Intervalo de tarea modificado", details=change)
        # La lógica de recálculo se implementará después
    
    def _handle_olt_disabled(self, olt):
        """Maneja cuando se deshabilita la OLT"""
        from snmp_jobs.models import SnmpJob
        
        logger.log_olt_disabled(olt)
        
        # Abortar TODO
        SnmpJob.abort_pending_executions_for_olt(
            self.olt_id,
            reason="OLT deshabilitada por usuario"
        )
        
        # Limpiar locks y colas
        redis_client.delete(f"lock:execution:olt:{self.olt_id}")
        redis_client.delete(f"queue:olt:{self.olt_id}:pending")
    
    def _handle_olt_enabled(self, olt):
        """Maneja cuando se habilita la OLT"""
        logger.log_olt_enabled(olt)
        # La lógica de reactivación se implementará después
    
    def _remove_from_queue(self, task_id):
        """Remueve una tarea de la cola de espera"""
        queue_key = f"queue:olt:{self.olt_id}:pending"
        queue_items = redis_client.lrange(queue_key, 0, -1)
        
        for item in queue_items:
            try:
                task_data = json.loads(item)
                if task_data.get('id') == task_id:
                    redis_client.lrem(queue_key, 1, item)
            except:
                continue
    
    def _adjust_quota_for_removed_task(self, task_id, task_type):
        """Ajusta la cuota cuando se remueve una tarea"""
        current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        
        tracker = QuotaTracker.objects.filter(
            olt_id=self.olt_id,
            task_type=task_type,
            period_start=current_hour
        ).first()
        
        if tracker:
            tracker.quota_required = tracker.quota_completed
            tracker.status = 'ADJUSTED'
            tracker.save()
    
    def _create_quota_tracker(self, job, task_type):
        """Crea un QuotaTracker para una tarea nueva"""
        current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        
        interval_seconds = job.interval_seconds or 3600
        quota = max(1, 3600 // interval_seconds)
        
        QuotaTracker.objects.get_or_create(
            olt_id=self.olt_id,
            task_type=task_type,
            period_start=current_hour,
            defaults={
                'period_end': current_hour + timedelta(hours=1),
                'quota_required': quota,
                'quota_pending': quota,
                'status': 'IN_PROGRESS'
            }
        )
    
    def save_state(self, state):
        """
        Guarda el estado actual en Redis
        DESHABILITADO: Causa errores de JSON concurrentes sin beneficio real
        """
        # El estado se calcula dinámicamente cada vez desde la BD
        # No es necesario guardarlo en Redis
        pass
    
    def get_previous_state(self):
        """
        Obtiene el estado anterior desde Redis
        Si hay error de JSON, limpia la clave corrupta automáticamente
        """
        try:
            previous_state_json = redis_client.get(self.state_key)
            if not previous_state_json:
                return None
            
            # Intentar parsear JSON
            return json.loads(previous_state_json)
            
        except json.JSONDecodeError as e:
            # Estado corrupto, limpiar y continuar
            logger.warning(f"Estado corrupto en Redis para OLT {self.olt_id}, limpiando: {e}")
            redis_client.delete(self.state_key)
            return None
        except Exception as e:
            logger.error(f"Error leyendo estado previo para OLT {self.olt_id}: {e}")
            return None

