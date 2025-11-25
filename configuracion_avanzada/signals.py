from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.db import transaction
import logging

from .models import ConfiguracionSistema, ConfiguracionSNMP, ConfiguracionCelery
from .services import ConfiguracionService

logger = logging.getLogger(__name__)


def _clear_config_cache(nombre: str | None = None):
    if nombre:
        cache.delete(f"{ConfiguracionService.CACHE_PREFIX}{nombre}")
    else:
        ConfiguracionService.clear_cache()


def _sync_runtime_settings():
    # Reaplicar sincronización de settings desde configuraciones persistidas
    ConfiguracionService.sync_with_settings()


@receiver(pre_save, sender=ConfiguracionSistema)
def detect_modo_prueba_change(sender, instance: ConfiguracionSistema, **kwargs):
    """
    Detecta cuando cambia el modo_prueba en ConfiguracionSistema
    """
    if instance.pk:
        try:
            old_instance = ConfiguracionSistema.objects.get(pk=instance.pk)
            # Detectar si cambió modo_prueba (de False a True o viceversa)
            if old_instance.modo_prueba != instance.modo_prueba and instance.activo:
                instance._modo_prueba_changed = True
                instance._old_modo_prueba = old_instance.modo_prueba
                instance._new_modo_prueba = instance.modo_prueba
            else:
                instance._modo_prueba_changed = False
        except ConfiguracionSistema.DoesNotExist:
            instance._modo_prueba_changed = False
    else:
        instance._modo_prueba_changed = False


@receiver(post_save, sender=ConfiguracionSistema)
def configuracion_sistema_saved(sender, instance: ConfiguracionSistema, **kwargs):
    _clear_config_cache(instance.nombre)
    _sync_runtime_settings()
    
    # Si cambió el modo_prueba, cancelar todas las ejecuciones y recalcular next_run_at
    if hasattr(instance, '_modo_prueba_changed') and instance._modo_prueba_changed:
        from executions.models import Execution
        from snmp_jobs.models import WorkflowNode
        from datetime import timedelta
        import pytz
        
        def cancel_and_recalculate_executions():
            try:
                modo_anterior = instance._old_modo_prueba
                modo_nuevo = instance._new_modo_prueba
                now = timezone.now()
                peru_tz = pytz.timezone('America/Lima')
                
                logger.info(
                    f"🔄 Cambio de modo detectado: {'PRUEBA' if modo_anterior else 'PRODUCCIÓN'} → "
                    f"{'PRUEBA' if modo_nuevo else 'PRODUCCIÓN'}, abortando ejecuciones y recalculando tiempos..."
                )
                
                # 1. Abortar todas las ejecuciones PENDING y RUNNING
                pending_executions = Execution.objects.filter(
                    status__in=['PENDING', 'RUNNING']
                )
                
                canceled_count = pending_executions.update(
                    status='INTERRUPTED',
                    finished_at=now,
                    error_message=f"Cambio de modo: {'PRUEBA' if modo_anterior else 'PRODUCCIÓN'} → {'PRUEBA' if modo_nuevo else 'PRODUCCIÓN'}"
                )
                
                if canceled_count > 0:
                    logger.info(f"✅ {canceled_count} ejecución(es) abortada(s) por cambio de modo")
                else:
                    logger.info("ℹ️ No había ejecuciones para abortar")
                
                # 2. Recalcular next_run_at para todos los nodos habilitados
                # Solo recalcular nodos master/normales (NO nodos en cadena)
                # Solo recalcular nodos con intervalo >= 300s (5 minutos)
                workflow_nodes = WorkflowNode.objects.filter(
                    enabled=True,
                    is_chain_node=False,  # Solo nodos master/normales
                    interval_seconds__gte=300  # Solo nodos con intervalo >= 5 minutos
                ).select_related('workflow', 'workflow__olt', 'template_node', 'template_node__template')
                
                recalculated_count = 0
                skipped_count = 0
                
                for node in workflow_nodes:
                    # Verificar que la plantilla esté activa (si tiene plantilla)
                    if node.template_node and node.template_node.template:
                        if not node.template_node.template.is_active:
                            skipped_count += 1
                            continue
                    
                    interval_seconds = node.interval_seconds or 900
                    
                    # Calcular próxima ejecución desde el momento de activación/desactivación + intervalo
                    # Nada se ejecuta de inmediato, siempre después de su intervalo
                    next_run = now + timedelta(seconds=interval_seconds)
                    next_run_peru = timezone.localtime(next_run, peru_tz)
                    
                    # Actualizar next_run_at y resetear last_run_at
                    old_next_run = node.next_run_at
                    node.next_run_at = next_run
                    node.last_run_at = None  # Resetear para recalcular desde ahora
                    node.save(update_fields=['next_run_at', 'last_run_at'])
                    recalculated_count += 1
                    
                    # Log detallado del motivo del recálculo
                    old_time_str = "N/A"
                    if old_next_run:
                        old_time_peru = timezone.localtime(old_next_run, peru_tz)
                        old_time_str = old_time_peru.strftime('%H:%M:%S')
                    
                    logger.info(
                        f"   ✅ Nodo '{node.name}' (OLT: {node.workflow.olt.abreviatura}) "
                        f"recalculado: {old_time_str} → {next_run_peru.strftime('%H:%M:%S')} PERÚ "
                        f"(intervalo: {interval_seconds//60}min, desde cambio de modo: {timezone.localtime(now, peru_tz).strftime('%H:%M:%S')})",
                        extra={
                            'node_id': node.id,
                            'node_name': node.name,
                            'olt_abreviatura': node.workflow.olt.abreviatura,
                            'interval_seconds': interval_seconds,
                            'old_next_run': old_next_run.isoformat() if old_next_run else None,
                            'new_next_run': next_run.isoformat(),
                            'mode_change_time': now.isoformat(),
                            'reason': 'modo_prueba_changed_recalculate_from_change_time'
                        }
                    )
                
                logger.info(
                    f"✅ Total: {recalculated_count} nodo(s) recalculado(s), {skipped_count} nodo(s) omitido(s) "
                    f"(plantilla desactivada o intervalo < 300s) por cambio de modo prueba"
                )
                
            except Exception as e:
                logger.error(f"❌ Error abortando ejecuciones y recalculando tiempos al cambiar modo: {e}", exc_info=True)
        
        transaction.on_commit(cancel_and_recalculate_executions)


@receiver(post_delete, sender=ConfiguracionSistema)
def configuracion_sistema_deleted(sender, instance: ConfiguracionSistema, **kwargs):
    _clear_config_cache(instance.nombre)
    _sync_runtime_settings()


@receiver(post_save, sender=ConfiguracionSNMP)
def configuracion_snmp_saved(sender, instance: ConfiguracionSNMP, **kwargs):
    # Invalidar claves relacionadas
    _clear_config_cache('snmp_timeout_global')
    _clear_config_cache('snmp_retries_global')
    _sync_runtime_settings()


@receiver(post_delete, sender=ConfiguracionSNMP)
def configuracion_snmp_deleted(sender, instance: ConfiguracionSNMP, **kwargs):
    _clear_config_cache('snmp_timeout_global')
    _clear_config_cache('snmp_retries_global')
    _sync_runtime_settings()


@receiver(post_save, sender=ConfiguracionCelery)
def configuracion_celery_saved(sender, instance: ConfiguracionCelery, **kwargs):
    _clear_config_cache('dispatcher_interval')
    _sync_runtime_settings()


@receiver(post_delete, sender=ConfiguracionCelery)
def configuracion_celery_deleted(sender, instance: ConfiguracionCelery, **kwargs):
    _clear_config_cache('dispatcher_interval')
    _sync_runtime_settings()


