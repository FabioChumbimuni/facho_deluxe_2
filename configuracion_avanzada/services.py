from django.core.cache import cache
from django.conf import settings
from .models import ConfiguracionSistema, ConfiguracionSNMP, ConfiguracionCelery
import logging

logger = logging.getLogger(__name__)


class ConfiguracionService:
    """
    Servicio para gestionar configuraciones del sistema
    """
    
    CACHE_PREFIX = 'config_'
    CACHE_TIMEOUT = 300  # 5 minutos
    
    @classmethod
    def get_config(cls, nombre, default=None, use_cache=True):
        """
        Obtener una configuración por nombre
        
        Args:
            nombre (str): Nombre de la configuración
            default: Valor por defecto si no existe
            use_cache (bool): Usar cache o no
            
        Returns:
            Valor de la configuración convertido al tipo correcto
        """
        cache_key = f"{cls.CACHE_PREFIX}{nombre}"
        
        if use_cache:
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
        
        try:
            config = ConfiguracionSistema.objects.get(
                nombre=nombre, 
                activo=True
            )
            valor = config.get_valor_typed()
            
            # Guardar en cache
            if use_cache:
                cache.set(cache_key, valor, cls.CACHE_TIMEOUT)
            
            return valor
        except ConfiguracionSistema.DoesNotExist:
            logger.warning(f"Configuración '{nombre}' no encontrada, usando valor por defecto: {default}")
            return default
    
    @classmethod
    def set_config(cls, nombre, valor, tipo='string', categoria='general', descripcion=''):
        """
        Crear o actualizar una configuración
        
        Args:
            nombre (str): Nombre de la configuración
            valor: Valor a establecer
            tipo (str): Tipo de dato
            categoria (str): Categoría
            descripcion (str): Descripción
            
        Returns:
            ConfiguracionSistema: Objeto creado/actualizado
        """
        config, created = ConfiguracionSistema.objects.get_or_create(
            nombre=nombre,
            defaults={
                'tipo': tipo,
                'categoria': categoria,
                'descripcion': descripcion,
                'activo': True
            }
        )
        
        config.set_valor_typed(valor)
        config.save()
        
        # Limpiar cache
        cache_key = f"{cls.CACHE_PREFIX}{nombre}"
        cache.delete(cache_key)
        
        logger.info(f"Configuración '{nombre}' {'creada' if created else 'actualizada'}: {valor}")
        return config
    
    @classmethod
    def get_snmp_config(cls, tipo_operacion='descubrimiento', nombre=None):
        """
        Obtener configuración SNMP para un tipo de operación específico
        
        Args:
            tipo_operacion (str): Tipo de operación ('descubrimiento', 'get', 'bulk', etc.)
            nombre (str): Nombre específico de configuración (opcional)
            
        Returns:
            dict: Configuración SNMP
        """
        try:
            if nombre:
                # Si se especifica nombre, buscarlo directamente
                config = ConfiguracionSNMP.objects.get(nombre=nombre, activo=True)
            else:
                # Usar el método estático para obtener config por tipo
                config = ConfiguracionSNMP.get_config_for_tipo(tipo_operacion)
            
            if config:
                return {
                    'timeout': config.timeout,
                    'retries': config.reintentos,
                    'community': config.comunidad,
                    'version': config.version
                }
        except ConfiguracionSNMP.DoesNotExist:
            logger.warning(f"Configuración SNMP '{nombre or tipo_operacion}' no encontrada, usando valores por defecto")
        
        # Valores por defecto
        return {
            'timeout': 10 if tipo_operacion == 'descubrimiento' else 5,
            'retries': 0 if tipo_operacion == 'descubrimiento' else 2,
            'community': 'public',
            'version': '2c'
        }
    
    @classmethod
    def get_celery_config(cls, cola):
        """
        Obtener configuración Celery para una cola específica
        
        Args:
            cola (str): Nombre de la cola
            
        Returns:
            dict: Configuración Celery
        """
        try:
            config = ConfiguracionCelery.objects.get(cola=cola, activo=True)
            return {
                'concurrency': config.concurrencia,
                'timeout': config.timeout_tarea,
                'retries': config.reintentos_tarea
            }
        except ConfiguracionCelery.DoesNotExist:
            logger.warning(f"Configuración Celery para cola '{cola}' no encontrada, usando valores por defecto")
            return {
                'concurrency': 1,
                'timeout': 300,
                'retries': 0
            }
    
    @classmethod
    def clear_cache(cls, nombre=None):
        """
        Limpiar cache de configuraciones
        
        Args:
            nombre (str): Nombre específico a limpiar, None para limpiar todo
        """
        if nombre:
            cache_key = f"{cls.CACHE_PREFIX}{nombre}"
            cache.delete(cache_key)
            logger.info(f"Cache limpiado para configuración: {nombre}")
        else:
            # Limpiar todas las configuraciones del cache
            configs = ConfiguracionSistema.objects.filter(activo=True)
            for config in configs:
                cache_key = f"{cls.CACHE_PREFIX}{config.nombre}"
                cache.delete(cache_key)
            logger.info("Cache limpiado para todas las configuraciones")
    
    @classmethod
    def get_all_configs(cls, categoria=None):
        """
        Obtener todas las configuraciones activas
        
        Args:
            categoria (str): Filtrar por categoría
            
        Returns:
            dict: Diccionario con todas las configuraciones
        """
        queryset = ConfiguracionSistema.objects.filter(activo=True)
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        
        configs = {}
        for config in queryset:
            configs[config.nombre] = config.get_valor_typed()
        
        return configs
    
    @classmethod
    def sync_with_settings(cls):
        """
        Presentación únicamente: no modificar settings desde BD
        """
        logger.info("sync_with_settings: modo presentación, no se modifica settings en tiempo de ejecución")


# Funciones de conveniencia para uso en otras partes del sistema
def get_snmp_timeout(tipo_operacion='descubrimiento'):
    """
    Obtener timeout SNMP para un tipo de operación específico.
    
    Args:
        tipo_operacion: 'descubrimiento', 'get', 'bulk', 'table', o 'general'
    """
    # 1) ConfiguracionSNMP específica para el tipo o general
    config = ConfiguracionSNMP.get_config_for_tipo(tipo_operacion)
    if config:
        return config.timeout
    
    # 2) ConfiguracionSistema
    value = ConfiguracionService.get_config('snmp_timeout_global', None)
    if value is not None:
        return value
    
    # 3) Default
    return 5

def get_snmp_retries(tipo_operacion='descubrimiento'):
    """
    Obtener reintentos SNMP para un tipo de operación específico.
    
    Args:
        tipo_operacion: 'descubrimiento', 'get', 'bulk', 'table', o 'general'
    """
    # 1) ConfiguracionSNMP específica para el tipo o general
    config = ConfiguracionSNMP.get_config_for_tipo(tipo_operacion)
    if config:
        return config.reintentos
    
    # 2) ConfiguracionSistema
    value = ConfiguracionService.get_config('snmp_retries_global', None)
    if value is not None:
        return value
    
    # 3) Default
    return 0

def get_dispatcher_interval():
    """Obtener intervalo del dispatcher"""
    return ConfiguracionService.get_config('dispatcher_interval', 10)

def get_max_concurrent_executions():
    """Obtener máximo de ejecuciones concurrentes"""
    return ConfiguracionService.get_config('max_concurrent_executions', 50)

def get_log_level():
    """Obtener nivel de logging"""
    return ConfiguracionService.get_config('log_level', 'INFO')

def is_retry_system_enabled():
    """Verificar si el sistema de reintentos está habilitado"""
    return ConfiguracionService.get_config('enable_retry_system', True)
