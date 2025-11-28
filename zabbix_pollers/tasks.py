"""
Tareas Celery del sistema de Pollers Zabbix
Reemplaza execution_coordinator.tasks.coordinator_loop_task
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

# Singleton del PollerManager (se inicializa una vez)
_poller_manager = None
_scheduler = None


def get_poller_manager():
    """Obtener instancia singleton del PollerManager"""
    global _poller_manager
    if _poller_manager is None:
        from .poller_manager import PollerManager
        _poller_manager = PollerManager(start_pollers=10)  # Configurable
    return _poller_manager


def get_scheduler():
    """Obtener instancia singleton del Scheduler"""
    global _scheduler
    if _scheduler is None:
        from .scheduler import ZabbixScheduler
        poller_manager = get_poller_manager()
        _scheduler = ZabbixScheduler(poller_manager)
    return _scheduler


@shared_task(
    queue='zabbix_scheduler', 
    bind=True, 
    name='zabbix_pollers.tasks.zabbix_scheduler_loop_task',
    soft_time_limit=5,  # ✅ REDUCIDO AÚN MÁS: 5 segundos máximo (debe ser muy rápido)
    time_limit=10,  # ✅ REDUCIDO AÚN MÁS: 10 segundos hard limit (evitar timeouts)
    ignore_result=True  # No necesitamos guardar el resultado
)
def zabbix_scheduler_loop_task(self):
    """
    Loop principal del scheduler Zabbix
    Reemplaza coordinator_loop_task
    
    Se ejecuta cada 1 segundo (configurado en Celery Beat)
    Ejecuta UNA iteración del scheduler (no un loop infinito)
    
    IMPORTANTE: Esta tarea debe ejecutarse rápidamente (< 1 segundo).
    Si toma más tiempo, hay un problema de rendimiento.
    
    ⚠️ LOGS: Solo loguea cuando hay actividad o problemas, no cada iteración normal.
    """
    try:
        scheduler = get_scheduler()
        # Log cada 10 iteraciones para verificar que se está ejecutando
        if scheduler.loop_count % 10 == 0:
            logger.info(f"🔄 Scheduler ejecutándose (iteración {scheduler.loop_count})")
        
        # Ejecutar una iteración del scheduler (no el loop completo)
        scheduler.scheduler_iteration()
        # No loguear éxito normal - solo errores o situaciones anómalas
    except Exception as e:
        # No relanzar SoftTimeLimitExceeded, solo loguear
        if 'SoftTimeLimitExceeded' in str(type(e).__name__):
            logger.warning(f"⏱️ Scheduler iteration excedió tiempo límite (30s). Esto no debería pasar normalmente.")
        else:
            logger.error(f"❌ Error en zabbix_scheduler_loop_task: {e}", exc_info=True)
        # No relanzar para que Celery Beat continúe programando la siguiente ejecución

