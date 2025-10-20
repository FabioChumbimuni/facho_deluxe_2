from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.conf import settings

from .models import ConfiguracionSistema, ConfiguracionSNMP, ConfiguracionCelery
from .services import ConfiguracionService


def _clear_config_cache(nombre: str | None = None):
    if nombre:
        cache.delete(f"{ConfiguracionService.CACHE_PREFIX}{nombre}")
    else:
        ConfiguracionService.clear_cache()


def _sync_runtime_settings():
    # Reaplicar sincronización de settings desde configuraciones persistidas
    ConfiguracionService.sync_with_settings()


@receiver(post_save, sender=ConfiguracionSistema)
def configuracion_sistema_saved(sender, instance: ConfiguracionSistema, **kwargs):
    _clear_config_cache(instance.nombre)
    _sync_runtime_settings()


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


