# snmp_get/admin.py
from django.contrib import admin

# Esta app no tiene modelos propios, solo tareas Celery
# Las configuraciones GET se manejan desde snmp_jobs.SnmpJob con job_type='get'
