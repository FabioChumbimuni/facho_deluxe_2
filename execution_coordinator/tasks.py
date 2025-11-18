"""
Tareas Celery del Coordinator

- coordinator_loop_task: Loop principal que se ejecuta cada 5 segundos
- check_delivery_task: Verifica que tareas fueron entregadas a Celery (cada 30s)
- cleanup_old_coordinator_logs: Limpieza de logs antiguos
"""

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

from .coordinator import ExecutionCoordinator
from .logger import coordinator_logger
from .delivery_checker import check_pending_deliveries

logger = logging.getLogger(__name__)


def _auto_fix_offset(olt_id):
    """
    Verifica y corrige automáticamente el desfase de tareas
    
    DESFASE ESPERADO:
    - Discovery: segundo 00
    - GET:       segundo 10
    
    Esta función se ejecuta cada vez que el coordinator procesa una OLT,
    garantizando que el desfase siempre esté correcto sin intervención manual.
    """
    from snmp_jobs.models import SnmpJobHost
    
    # Obtener tareas de esta OLT que necesitan corrección
    job_hosts = SnmpJobHost.objects.filter(
        olt_id=olt_id,
        enabled=True,
        snmp_job__enabled=True,
        next_run_at__isnull=False
    ).select_related('snmp_job')
    
    corrected = 0
    
    for jh in job_hosts:
        current_second = jh.next_run_at.second
        expected_second = 0 if jh.snmp_job.job_type == 'descubrimiento' else 10
        
        # Si el segundo NO es el esperado, corregir
        if current_second != expected_second:
            # Mantener la fecha/hora pero ajustar el segundo
            jh.next_run_at = jh.next_run_at.replace(second=expected_second, microsecond=0)
            jh.save(update_fields=['next_run_at'])
            corrected += 1
    
    if corrected > 0:
        logger.info(f"🔧 Auto-corrección: {corrected} tarea(s) ajustadas en OLT {olt_id}")


@shared_task(queue='coordinator', bind=True)
def coordinator_loop_task(self):
    """
    Loop principal del coordinator
    Se ejecuta cada 5 segundos para todas las OLTs activas
    
    Este es el corazón del sistema de coordinación que:
    1. Lee el estado de cada OLT activa
    2. Detecta cambios (tareas habilitadas/deshabilitadas, etc.)
    3. Reformula planes dinámicamente
    4. Gestiona prioridades y telemetría
    """
    from hosts.models import OLT
    
    # Obtener solo OLTs habilitadas
    active_olts = OLT.objects.filter(habilitar_olt=True)
    
    # Solo log si no hay OLTs (situación anormal)
    if not active_olts.exists():
        return
    
    changes_detected = False
    
    for olt in active_olts:
        try:
            # VERIFICAR Y CORREGIR DESFASE AUTOMÁTICAMENTE
            _auto_fix_offset(olt.id)
            
            coordinator = ExecutionCoordinator(olt.id)
            
            # 1. Leer estado actual
            current_state = coordinator.get_system_state()
            
            if not current_state:
                continue
            
            # 2. Obtener estado anterior
            previous_state = coordinator.get_previous_state()
            
            # 3. Calcular hashes para detección rápida de cambios
            current_hash = coordinator.calculate_state_hash(current_state)
            previous_hash = coordinator.calculate_state_hash(previous_state) if previous_state else None
            
            # 4. SCHEDULER DINÁMICO: Procesar tareas listas
            # CRÍTICO: Se ejecuta SIEMPRE en cada loop (no solo cuando hay cambios)
            # Esto garantiza:
            # - Auto-reparación de JobHosts sin next_run_at (cada 5s)
            # - Ejecución de tareas listas aunque no haya cambios de estado
            from .dynamic_scheduler import DynamicScheduler
            
            scheduler = DynamicScheduler(olt.id)
            tasks_processed = scheduler.process_ready_tasks(olt)
            
            if tasks_processed > 0:
                coordinator_logger.info(
                    f"🚀 {tasks_processed} tarea(s) lista(s) procesada(s) en {olt.abreviatura}",
                    olt=olt,
                    event_type='EXECUTION_STARTED',
                    details={'tasks_count': tasks_processed}
                )
            
            # 5. Detectar y manejar cambios de estado si los hay
            has_active_tasks = current_state.get('tasks', [])
            
            if current_hash != previous_hash and has_active_tasks:
                changes_detected = True
                
                # Detectar cambios específicos
                changes_info = coordinator.detect_changes(current_state, previous_state)
                
                # Solo loguear si hay cambios SIGNIFICATIVOS (tareas agregadas/removidas)
                if changes_info.get('tasks_added') or changes_info.get('tasks_removed'):
                    coordinator_logger.info(
                        f"🔄 Cambios detectados en {olt.abreviatura}",
                        olt=olt,
                        event_type='STATE_CHANGE'
                    )
                
                # Manejar los cambios
                coordinator.handle_changes(changes_info)
            
            # 6. Guardar estado actual (siempre, para tener timestamp actualizado)
            coordinator.save_state(current_state)
            
        except Exception as e:
            coordinator_logger.error(
                f"Error en coordinator loop para OLT {olt.id}: {e}",
                olt=olt,
                details={'error': str(e), 'olt_id': olt.id}
            )
            continue


@shared_task(queue='coordinator', bind=True)
def check_quota_violations_task(self):
    """
    Tarea legacy mantenida para compatibilidad con configuraciones antiguas.
    El sistema de cuotas ya no está activo, así que simplemente registramos el llamado.
    """
    coordinator_logger.info(
        "check_quota_violations_task ignorada (sistema de cuotas desactivado)",
        event_type='STATE_UPDATED',
        details={'task': 'check_quota_violations_task'}
    )
    return {
        'status': 'skipped',
        'reason': 'quota system disabled'
    }


@shared_task(queue='cleanup', bind=True)
def cleanup_old_coordinator_logs_task(self, days_old=7):
    """
    Limpia logs del coordinator más antiguos que X días
    Se ejecuta diariamente
    """
    from .models import CoordinatorLog
    
    cutoff_date = timezone.now() - timedelta(days=days_old)
    
    deleted_count, _ = CoordinatorLog.objects.filter(
        timestamp__lt=cutoff_date
    ).delete()
    
    if deleted_count > 0:
        coordinator_logger.info(
            f"🧹 Limpieza de logs: {deleted_count} registros eliminados (más de {days_old} días)",
            event_type='STATE_CHANGE'
        )
    
    return {
        'status': 'success',
        'deleted_count': deleted_count,
        'cutoff_date': cutoff_date.isoformat()
    }


@shared_task(bind=True, name='execution_coordinator.tasks.check_delivery_task')
def check_delivery_task(self):
    """
    Verifica que tareas PENDING fueron entregadas a Celery
    
    Ejecuta cada 30 segundos para detectar tareas "perdidas" que:
    - Se crearon en la BD
    - Se enviaron a Celery (.delay())
    - Pero nunca fueron recogidas por un worker
    
    Si una tarea está PENDING > 30s y no aparece en Celery:
    - La marca como INTERRUPTED
    - Loguea el problema
    - Las estadísticas se usan para monitoreo
    """
    try:
        stats = check_pending_deliveries()
        
        # Solo loguear si hay pérdidas o si se revisaron tareas
        if stats['lost'] > 0:
            coordinator_logger.warning(
                f"⚠️ Verificación de entregas: {stats['lost']} de {stats['checked']} tareas perdidas",
                event_type='DELIVERY_CHECK',
                details=stats
            )
        # Si checked > 0 pero lost == 0, todo está bien (no loguear)
        
        # Retornar stats para monitoreo pero sin logging automático de Celery
        # (el loglevel WARNING ya filtra los INFO de Celery)
        return stats
        
    except Exception as e:
        logger.error(f"Error en check_delivery_task: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }

