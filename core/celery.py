import os
from celery import Celery

# Establecer la variable de entorno para las configuraciones de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Crear la instancia de Celery
app = Celery('facho_deluxe_v2')

# Usar la configuración de Django para Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# Cargar tareas automáticamente desde todos los archivos tasks.py registrados
app.autodiscover_tasks()

# Importar explícitamente módulos con tareas que no se llaman tasks.py
# Esto asegura que las tareas se registren correctamente en Celery
try:
    import snmp_get.cleanup_tasks  # noqa: F401
except ImportError:
    pass  # El módulo puede no existir en algunos entornos

# Configuración de colas optimizada (5 colas especializadas)
app.conf.task_routes = {
    'snmp_jobs.tasks.discovery_main_task': {'queue': 'discovery_main'},
    'snmp_jobs.tasks.discovery_retry_task': {'queue': 'discovery_retry'},
    'snmp_jobs.tasks.discovery_manual_task': {'queue': 'discovery_manual'},  # Máxima prioridad
    'snmp_jobs.tasks.dispatcher_check_and_enqueue': {'queue': 'discovery_main'},
    'snmp_jobs.tasks.cleanup_old_executions_task': {'queue': 'cleanup'},
    # Tareas de ODF Management
    'odf_management.tasks.sync_single_olt_ports': {'queue': 'odf_sync'},
    'odf_management.tasks.sync_scheduled_olts': {'queue': 'odf_sync'},
    'odf_management.tasks.cleanup_old_sync_logs': {'queue': 'cleanup'},
    # Tareas de sincronización masiva batch
    'odf_management.tasks.sync_all_odf_hilos': {'queue': 'odf_sync'},
    'odf_management.tasks.sync_odf_hilos_for_olt': {'queue': 'odf_sync'},
}

# Configuración de workers por cola (4 colas especializadas)
app.conf.task_default_queue = 'discovery_main'
app.conf.task_default_exchange = 'discovery_main'
app.conf.task_default_routing_key = 'discovery_main'

# Configuración de reintentos
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True
app.conf.task_serializer = 'json'
app.conf.result_serializer = 'json'
app.conf.accept_content = ['json']

# Configuración de timeouts
app.conf.task_soft_time_limit = 300  # 5 minutos
app.conf.task_time_limit = 600       # 10 minutos

# Configuración de beat (scheduler) - Se toma de settings.py
# app.conf.beat_schedule se carga automáticamente desde CELERY_BEAT_SCHEDULE en settings.py

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
