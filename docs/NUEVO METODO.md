Perfecto 🔥, acá te dejo el **prompt completo** listo para que lo uses en tu proyecto (sin pseudocódigo, todo implementable con Django + Celery + PostgreSQL).

---

# Prompt: Sincronización masiva `odf_hilos` ↔ `zabbix_port_data`

**Contexto:**

* Base de datos: PostgreSQL
* Framework: Django
* Scheduler: Celery
* Tablas involucradas: `odf_hilos`, `odf`, `zabbix_port_data`

**Objetivo:**
Sincronizar en batch los estados de `odf_hilos` con `zabbix_port_data` por OLT, usando SQL nativo para máxima eficiencia.

---

### 1. Task Celery para sincronizar todas las OLT

```python
# tasks.py
from celery import shared_task
from .models import Olt
from .tasks import sync_odf_hilos_for_olt

@shared_task
def sync_all_odf_hilos():
    """
    Lanza subtareas de sincronización por cada OLT registrada.
    """
    for olt_id in Olt.objects.values_list("id", flat=True):
        sync_odf_hilos_for_olt.delay(olt_id)
```

---

### 2. Task Celery por OLT con SQL batch

```python
# tasks.py
from celery import shared_task
from django.db import connection
from django.utils import timezone

@shared_task
def sync_odf_hilos_for_olt(olt_id):
    """
    Sincroniza los registros de odf_hilos con zabbix_port_data para una OLT específica.
    """
    now = timezone.now()

    with connection.cursor() as cursor:
        # 1️⃣ Marcar como presentes en Zabbix
        cursor.execute("""
            UPDATE odf_hilos h
            SET en_zabbix = TRUE,
                estado = CASE WHEN z.disponible THEN 'enabled' ELSE 'disabled' END,
                zabbix_port_id = z.id,
                updated_at = %s
            FROM zabbix_port_data z
            JOIN odf o ON o.id = h.odf_id
            WHERE o.olt_id = %s
              AND h.slot = z.slot
              AND h.port = z.port
              AND z.olt_id = o.olt_id;
        """, [now, olt_id])

        # 2️⃣ Marcar como ausentes (no existen en Zabbix)
        cursor.execute("""
            UPDATE odf_hilos h
            SET en_zabbix = FALSE,
                estado = 'disabled',
                zabbix_port_id = NULL,
                updated_at = %s
            FROM odf o
            WHERE o.id = h.odf_id
              AND o.olt_id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM zabbix_port_data z
                  WHERE z.olt_id = o.olt_id
                    AND z.slot = h.slot
                    AND z.port = h.port
              );
        """, [now, olt_id])
```

---

### 3. Scheduler Celery Beat

Agrega en tu configuración Celery Beat para que corra cada 5 minutos:

```python
# celery.py o configuración de beat_schedule
from celery.schedules import crontab

app.conf.beat_schedule = {
    'sync-odf-hilos-every-5min': {
        'task': 'miapp.tasks.sync_all_odf_hilos',
        'schedule': crontab(minute='*/5'),
    },
}
```

---

### 4. Índices necesarios en PostgreSQL

```sql
CREATE INDEX idx_zabbix_port_data_lookup
    ON zabbix_port_data (olt_id, slot, port);

CREATE INDEX idx_odf_hilos_lookup
    ON odf_hilos (odf_id, slot, port);

CREATE INDEX idx_odf_olt
    ON odf (olt_id);
```

---

### 5. Flujo de ejecución

1. Cada 5 min Celery Beat dispara `sync_all_odf_hilos`.
2. Se crean subtareas por OLT → `sync_odf_hilos_for_olt(olt_id)`.
3. Cada subtarea ejecuta **2 queries batch** en PostgreSQL:

   * `UPDATE` con `JOIN` → marca como presentes en Zabbix.
   * `UPDATE` con `NOT EXISTS` → marca como ausentes.
4. Se actualizan `en_zabbix`, `estado`, `zabbix_port_id`, `updated_at`.
5. Todo el proceso es paralelo y escalable.

---

⚡ Con este prompt:

* 500 OLT (~120k filas) → solo 1000 queries en total (2 por OLT).
* Escalable a miles de OLT con workers Celery.
* 100% eficiente en PostgreSQL gracias a índices.

---

¿Quieres que además te arme un **query de auditoría** para verificar qué hilos están en `odf_hilos` pero nunca aparecieron en `zabbix_port_data` (huérfanos)?
