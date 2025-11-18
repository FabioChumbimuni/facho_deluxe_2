# snmp_get/cleanup_tasks.py
"""
Tareas de limpieza para el sistema GET
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task(queue='cleanup')
def cleanup_interrupted_executions(max_age_minutes=30):
    """
    Limpia ejecuciones INTERRUPTED antiguas.
    
    Ejecuciones INTERRUPTED que tienen más de X minutos se marcan como FAILED
    para que no se ejecuten cuando se reinician los workers.
    
    Args:
        max_age_minutes: Edad máxima en minutos (default: 30)
    """
    from executions.models import Execution
    
    logger.info(f"🧹 Iniciando limpieza de ejecuciones INTERRUPTED (más de {max_age_minutes} minutos)")
    
    cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
    
    # Buscar ejecuciones INTERRUPTED antiguas
    interrupted_executions = Execution.objects.filter(
        status='INTERRUPTED',
        created_at__lt=cutoff_time
    )
    
    total = interrupted_executions.count()
    
    if total == 0:
        logger.info("✅ No hay ejecuciones INTERRUPTED antiguas para limpiar")
        return {'status': 'success', 'cleaned': 0}
    
    # Actualizar a FAILED
    updated = interrupted_executions.update(
        status='FAILED',
        error_message='Ejecución interrumpida por reinicio de workers (auto-limpieza)',
        finished_at=timezone.now()
    )
    
    logger.info(f"✅ Limpiadas {updated} ejecuciones INTERRUPTED antiguas")
    
    return {
        'status': 'success',
        'cleaned': updated,
        'cutoff_time': cutoff_time.isoformat()
    }


@shared_task(queue='cleanup')
def cancel_pending_executions_for_disabled_jobs():
    """
    Cancela ejecuciones PENDING para tareas que están deshabilitadas.
    
    Si una tarea GET está deshabilitada, cualquier ejecución PENDING
    se marca como INTERRUPTED para evitar que se ejecute.
    """
    from executions.models import Execution
    from snmp_jobs.models import SnmpJob
    
    logger.info("🧹 Verificando ejecuciones PENDING de tareas GET deshabilitadas")
    
    # Buscar tareas GET deshabilitadas
    disabled_get_jobs = SnmpJob.objects.filter(
        job_type='get',
        enabled=False
    )
    
    if not disabled_get_jobs.exists():
        logger.info("✅ No hay tareas GET deshabilitadas")
        return {'status': 'success', 'cancelled': 0}
    
    # Buscar ejecuciones PENDING de esas tareas
    pending_executions = Execution.objects.filter(
        snmp_job__in=disabled_get_jobs,
        status='PENDING'
    )
    
    total = pending_executions.count()
    
    if total == 0:
        logger.info("✅ No hay ejecuciones PENDING de tareas deshabilitadas")
        return {'status': 'success', 'cancelled': 0}
    
    # Cancelar ejecuciones
    cancelled = pending_executions.update(
        status='INTERRUPTED',
        error_message='Tarea deshabilitada - Ejecución cancelada',
        finished_at=timezone.now()
    )
    
    logger.info(f"✅ Canceladas {cancelled} ejecuciones PENDING de tareas deshabilitadas")
    
    return {
        'status': 'success',
        'cancelled': cancelled
    }


@shared_task(queue='cleanup')
def cleanup_old_pending_executions(max_age_minutes=10):
    """
    Limpia ejecuciones PENDING muy antiguas que probablemente están atascadas.
    
    Si una ejecución está en estado PENDING por más de X minutos, probablemente
    está atascada o nunca se procesó. Se marca como INTERRUPTED.
    
    Args:
        max_age_minutes: Edad máxima en minutos antes de marcar como INTERRUPTED (default: 10)
    """
    from executions.models import Execution
    
    logger.info(f"🧹 Iniciando limpieza de ejecuciones PENDING antiguas (más de {max_age_minutes} minutos)")
    
    cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
    
    # Buscar ejecuciones PENDING antiguas
    old_pending_executions = Execution.objects.filter(
        status='PENDING',
        created_at__lt=cutoff_time
    ).select_related('snmp_job', 'olt')
    
    total = old_pending_executions.count()
    
    if total == 0:
        logger.info("✅ No hay ejecuciones PENDING antiguas para limpiar")
        return {'status': 'success', 'cleaned': 0}
    
    # Mostrar detalles antes de limpiar
    for e in old_pending_executions[:10]:
        age_minutes = (timezone.now() - e.created_at).total_seconds() / 60
        logger.info(f"  ⚠️ Ejecución PENDING antigua: ID {e.id} - {e.snmp_job.nombre if e.snmp_job else 'N/A'} - OLT: {e.olt.abreviatura if e.olt else 'N/A'} - Edad: {age_minutes:.1f} min")
    
    # Actualizar a INTERRUPTED
    updated = old_pending_executions.update(
        status='INTERRUPTED',
        error_message=f'Ejecución PENDING atascada (más de {max_age_minutes} minutos sin procesar) - Auto-limpieza',
        finished_at=timezone.now()
    )
    
    logger.info(f"✅ Limpiadas {updated} ejecuciones PENDING antiguas (marcadas como INTERRUPTED)")
    
    return {
        'status': 'success',
        'cleaned': updated,
        'cutoff_time': cutoff_time.isoformat()
    }

