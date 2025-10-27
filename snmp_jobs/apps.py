from django.apps import AppConfig


class SnmpJobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'snmp_jobs'
    
    def ready(self):
        """Importar signals cuando la app esté lista"""
        import snmp_jobs.signals