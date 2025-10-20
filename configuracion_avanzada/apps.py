from django.apps import AppConfig


class ConfiguracionAvanzadaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'configuracion_avanzada'
    verbose_name = 'Configuración Avanzada'

    def ready(self):
        # Registrar señales para limpiar caché y sincronizar settings
        from . import signals  # noqa: F401
