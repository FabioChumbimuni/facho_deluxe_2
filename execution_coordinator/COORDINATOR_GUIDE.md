# 📋 Guía Completa del Coordinador de Ejecuciones SNMP

## 🎯 ¿Qué es el Coordinador?

El **Coordinador de Ejecuciones** es un sistema inteligente que gestiona y orquesta todas las tareas SNMP (Discovery y GET) en el sistema. Actúa como un "supervisor" que:

- 🔍 **Monitorea** continuamente el estado de todas las OLTs
- 📅 **Planifica** dinámicamente cuándo ejecutar cada tarea
- 🚦 **Prioriza** tareas según importancia (Discovery > GET)
- 🔒 **Previene** colisiones entre tareas de la misma OLT
- ⚡ **Optimiza** el uso de recursos ejecutando tareas inmediatamente cuando es posible
- 🛡️ **Protege** las OLTs de sobrecarga

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                   COORDINATOR LOOP (Celery Beat)             │
│                   Ejecuta cada 5 segundos                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                    DYNAMIC SCHEDULER                         │
│  • Lee SnmpJobHost.next_run_at                              │
│  • Detecta tareas listas                                     │
│  • Verifica si OLT está ocupada                             │
│  • Ejecuta o encola según prioridad                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTION FLOW                            │
│                                                              │
│  OLT LIBRE          │  OLT OCUPADA                          │
│  ↓                  │  ↓                                     │
│  Ejecutar tarea     │  Encolar en Redis                     │
│  de mayor prioridad │  (esperar turno)                      │
│  ↓                  │  ↓                                     │
│  Enviar a Celery    │  Callback ejecuta                     │
│  Worker             │  siguiente INMEDIATAMENTE             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                         CALLBACKS                            │
│  • on_task_completed() → ejecuta siguiente en cola          │
│  • on_task_failed() → maneja errores y continúa            │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Componentes Principales

### 1. **coordinator.py** - El Cerebro
**Función:** Lee y analiza el estado completo del sistema.

```python
class ExecutionCoordinator:
    def get_system_state():
        """
        Lee estado de:
        - SnmpJob (tareas configuradas)
        - SnmpJobHost (próxima ejecución por OLT)
        - OLT (activas/inactivas)
        - Redis (locks, colas, reintentos)
        """
    
    def get_previous_state():
        """
        Lee el estado previo desde Redis
        para detectar cambios
        """
```

**Características:**
- ✅ Calcula hash del estado para detectar cambios
- ✅ Manejo robusto de JSON corrupto en Redis
- ✅ No guarda estado (se calcula dinámicamente)
- ✅ Logging estructurado por OLT

---

### 2. **tasks.py** - El Loop Principal
**Función:** Celery Beat task que ejecuta el loop cada 5 segundos.

```python
@shared_task(bind=True, name='execution_coordinator.tasks.coordinator_loop_task')
def coordinator_loop_task(self):
    """
    Loop principal que:
    1. Auto-corrige desfase de tareas
    2. Lee estado del sistema
    3. Para cada OLT activa:
       - Procesa tareas listas
       - Actualiza cuotas
       - Loguea cambios
    4. Verifica violaciones de cuota (informativo)
    """
```

**Características:**
- ✅ Ejecuta cada 5 segundos
- ✅ Auto-corrección de desfase (Discovery :00, GET :10)
- ✅ Logs solo cuando hay cambios significativos
- ✅ No bloquea si hay errores individuales

---

### 3. **dynamic_scheduler.py** - El Ejecutor
**Función:** Decide qué ejecutar, cuándo y cómo.

#### Métodos Clave:

##### `is_olt_busy()`
Verifica si la OLT está ocupada:
```python
# Checks:
1. lock:execution:olt:{id}        # Ejecutando tarea
2. olt:retrying:{id}               # En proceso de reintento
3. lock:processing_queue:{id}      # Procesando cola (callback)
```

##### `get_ready_tasks()`
Obtiene tareas listas para ejecutar:
```python
# Criterios:
- SnmpJobHost.next_run_at <= now
- Ordena por PRIORIDAD (Discovery=90, GET=40)
- Respeta intervalos configurados
```

##### `process_ready_tasks()`
Lógica principal de decisión:
```python
if olt_busy:
    if tarea_no_encolada:
        enqueue_task()  # Esperar turno
else:
    _execute_task_now()  # Ejecutar inmediatamente
```

##### `execute_next_in_queue()`
Ejecuta siguiente tarea desde cola (llamado por callback):
```python
1. Sacar primera tarea de Redis
2. Verificar que no se ejecutó recientemente
3. Crear Execution en BD
4. Enviar a Celery
5. Actualizar next_run_at
```

**Características:**
- ✅ Prioridad estricta (Discovery primero)
- ✅ Lock atómico para evitar duplicados
- ✅ Desfase intencional (Discovery :00, GET :10)
- ✅ Actualiza `next_run_at` ANTES de crear ejecución
- ✅ Try/except alrededor de Celery `.delay()`
- ✅ Verifica `last_run_at` para evitar ejecuciones duplicadas

---

### 4. **callbacks.py** - El Notificador
**Función:** Ejecuta tareas inmediatamente cuando termina la anterior.

#### `on_task_completed()`
```python
def on_task_completed(olt_id, task_name, task_type, duration_ms):
    """
    Cuando una tarea termina:
    1. Log con duración adaptativa (ms o s)
    2. Verifica cola de Redis
    3. Si hay tareas esperando:
       - Lock temporal anti-race conditions
       - Ejecuta siguiente INMEDIATAMENTE
    4. Si no hay cola:
       - Log "OLT libre"
    """
```

#### `on_task_failed()`
```python
def on_task_failed(olt_id, task_name, task_type, error_message):
    """
    Cuando una tarea falla:
    1. Log del error
    2. Libera lock
    3. Intenta ejecutar siguiente en cola
    """
```

**Características:**
- ✅ Ejecución inmediata sin esperar al loop
- ✅ Lock temporal `lock:processing_queue:{olt_id}` (10s)
- ✅ No libera lock de ejecución (ya liberado por tarea)
- ✅ Logging detallado de errores

---

### 5. **stagger.py** - Auto-Corrección
**Función:** Corrige el desfase de tareas automáticamente.

```python
def _auto_fix_offset(olt_id):
    """
    Para cada SnmpJobHost de la OLT:
    1. Verifica si next_run_at tiene el segundo correcto
    2. Si no:
       - Discovery → :00 segundos
       - GET → :10 segundos
    3. Guarda cambio en BD
    4. Log solo si hubo corrección
    """
```

**Características:**
- ✅ Ejecuta cada 5 segundos (al inicio del loop)
- ✅ Solo loguea cuando corrige algo
- ✅ No afecta `last_run_at`

---

## 🎮 Flujos de Trabajo

### Flujo 1: Tarea Lista para Ejecutar (OLT Libre)

```
1. Coordinator Loop detecta: SnmpJobHost.next_run_at <= now
2. Verifica: is_olt_busy() → False
3. Ordena tareas por prioridad (Discovery primero)
4. _execute_task_now():
   a. Lock atómico anti-duplicados (5s)
   b. Verifica last_run_at (no ejecutar si < 3s)
   c. Actualiza next_run_at con desfase
   d. Crea Execution en BD (PENDING)
   e. Envía a Celery (.delay)
   f. Log: "▶️ Ejecutando: [nombre] en [OLT] (P90)"
5. Worker recoge tarea y ejecuta
6. Al terminar → on_task_completed()
```

---

### Flujo 2: Tarea Lista pero OLT Ocupada

```
1. Coordinator Loop detecta: SnmpJobHost.next_run_at <= now
2. Verifica: is_olt_busy() → True
   - Lock de ejecución existe
   - O está en reintento
   - O procesando cola
3. Verifica si ya está en cola (evitar duplicados)
4. Si no está:
   a. Encola en Redis: olt:queue:{olt_id}
   b. Guarda: {job_id, job_name, job_type, priority}
   c. Log: "📋 [nombre] encolada en [OLT] (OLT ocupada)"
5. Espera a que termine tarea actual
6. Callback ejecuta siguiente INMEDIATAMENTE
```

---

### Flujo 3: Callback Ejecuta Siguiente en Cola

```
1. Tarea termina en worker
2. Worker llama: on_task_completed(olt_id, ...)
3. Callback verifica: olt:queue:{olt_id}
4. Si hay tareas:
   a. Lock temporal: lock:processing_queue:{olt_id} (10s)
   b. Saca primera tarea de cola (LPOP)
   c. Verifica last_run_at < 3s (evitar duplicados)
   d. Actualiza next_run_at con desfase
   e. Crea Execution en BD
   f. Envía a Celery
   g. Log: "▶️ Ejecutando INMEDIATAMENTE: [nombre] en [OLT]"
   h. Libera lock temporal
5. Nueva tarea ejecuta sin esperar 5s del loop
```

---

### Flujo 4: Tarea Falla y Entra en Reintento

```
1. Tarea falla en worker (timeout, error SNMP, etc.)
2. Worker:
   a. Marca Execution como FAILED
   b. Crea lock: olt:retrying:{olt_id} (10 minutos)
   c. Encola reintento en discovery_retry/get_retry
3. Coordinator Loop:
   a. Detecta: olt:retrying:{olt_id} existe
   b. Log: "🛑 OLT [id] ([nombre]) EN REINTENTO - bloqueada"
   c. NO ejecuta ni encola nuevas tareas
4. Después de 30s: worker ejecuta reintento
5. Si reintento exitoso:
   a. Libera olt:retrying:{olt_id}
   b. Callback ejecuta siguiente en cola
6. Si falla todos los reintentos:
   a. Marca como FAILED final
   b. Libera lock
   c. Sistema reanuda coordinación normal
```

---

## 🔒 Sistema de Locks en Redis

### 1. **Lock de Ejecución**
```redis
Key: lock:execution:olt:{olt_id}
TTL: 600 segundos (10 minutos)
Propósito: Indica que la OLT está ejecutando una tarea
Creado por: Worker al iniciar tarea
Liberado por: Worker al terminar tarea
```

### 2. **Lock de Creación**
```redis
Key: lock:create_execution:{olt_id}:{job_id}
TTL: 5 segundos
Propósito: Evitar crear la misma ejecución dos veces
Creado por: Coordinator antes de crear Execution
Liberado por: Coordinator después de enviar a Celery
```

### 3. **Lock de Reintento**
```redis
Key: olt:retrying:{olt_id}
TTL: 600 segundos (10 minutos)
Propósito: Bloquear OLT mientras está en proceso de reintento
Creado por: Worker al fallar tarea
Liberado por: Worker al completar reintento (éxito o fallo final)
```

### 4. **Lock de Procesamiento de Cola**
```redis
Key: lock:processing_queue:{olt_id}
TTL: 10 segundos
Propósito: Evitar race conditions entre callback y coordinator loop
Creado por: Callback al procesar cola
Liberado por: Callback al terminar de procesar
```

---

## 📋 Cola de Tareas en Redis

### Estructura:
```redis
Key: olt:queue:{olt_id}
Type: LIST (FIFO)
TTL: None (persiste hasta que se procese)
```

### Formato de cada item:
```json
{
  "job_id": 28,
  "job_name": "Descripción OID",
  "job_type": "get",
  "priority": 40,
  "enqueued_at": "2025-10-27T12:15:38"
}
```

### Operaciones:
- **RPUSH**: Agregar tarea al final (coordinator)
- **LPOP**: Sacar tarea del inicio (callback)
- **LRANGE**: Ver todas las tareas (monitoring)

---

## ⏱️ Desfase Intencional

### ¿Por qué?
Para **minimizar colisiones naturales** entre Discovery y GET que tienen el mismo intervalo.

### Configuración:
```python
# Discovery
next_time = next_time.replace(second=0, microsecond=0)
# Ejemplo: 12:05:00, 12:10:00, 12:15:00

# GET
next_time = next_time.replace(second=10, microsecond=0)
# Ejemplo: 12:05:10, 12:10:10, 12:15:10
```

### Auto-corrección:
Cada 5 segundos, `_auto_fix_offset()` revisa todas las OLTs y corrige desviaciones.

---

## 📊 Telemetría en Vivo

### Propósito:
Monitorear el estado del scheduler en tiempo real apoyándonos en métricas vivas en lugar de cuotas históricas.

### Fuentes clave:
- `CoordinatorEvent`: registra cada decisión (enqueue, delay, interrupción, auto-reparación).
- `Execution`: provee el estado actual de cada tarea (PENDING, RUNNING, etc.).
- Dashboard en `/coordinator/dashboard/`: visualiza filas activas por OLT, colisiones y eventos recientes.

### Métricas principales:
- Conteos globales de tareas pendientes/ejecutándose.
- Tareas listas por OLT y detección de colisiones (< 60s).
- Últimas ejecuciones por tarea (hora, duración, estado).

---



## 📈 Modelo de Datos

### SnmpJob (Template)
```python
nombre = "Descubrimiento Huawei"
job_type = "descubrimiento"  # o "get"
interval_seconds = 300       # 5 minutos
priority = 90                # Discovery > GET
habilitado = True
```

### SnmpJobHost (Instancia por OLT)
```python
snmp_job = ForeignKey(SnmpJob)
olt = ForeignKey(OLT)
next_run_at = DateTimeField()   # ← EL COORDINADOR LEE ESTO
last_run_at = DateTimeField()
```

### Execution (Registro de ejecución)
```python
snmp_job = ForeignKey(SnmpJob)
olt = ForeignKey(OLT)
status = "PENDING/RUNNING/SUCCESS/FAILED/INTERRUPTED"
attempt = IntegerField()         # Número de reintento
worker_name = CharField()        # Qué worker la ejecutó
created_at = DateTimeField()
started_at = DateTimeField()
completed_at = DateTimeField()
duration_ms = IntegerField()
error_message = TextField()
```

---

## 🔍 Logging y Monitoreo

### Logs del Coordinator
**Ubicación:** `/opt/facho_deluxe_2/logs/coordinator/main.log`

#### Mensajes Clave:

**Ejecución de tarea:**
```
▶️ Ejecutando: Descubrimiento Huawei en SMP-10 (P90)
▶️ Ejecutando INMEDIATAMENTE: Descripción OID en NEW_LO-15 (desde cola)
```

**OLT ocupada:**
```
⏸️ OLT 26 (CAMP2-11) ejecutando tarea
📋 Descripción OID encolada en SMP-10 (OLT ocupada, ejecutará cuando termine actual)
```

**OLT bloqueada:**
```
🛑 OLT 28 (PTP-17) EN REINTENTO - bloqueada (expira en 581s)
```

**Finalización:**
```
✅ Descubrimiento Huawei completada (SUCCESS) en 18.5s
✅ Descripción OID completada (SUCCESS) en 42ms
✓ OLT libre, sin tareas pendientes
```

**Cambios detectados:**
```
🔄 Cambios detectados en SMP-10
🚀 2 tarea(s) lista(s) procesada(s) en NEW_LO-15
```

**Errores:**
```
❌ Error enviando tarea a Celery: [detalle]
❌ Error procesando cola: [detalle]
```

---

## 🚨 Resolución de Problemas

### Problema 1: Ejecuciones PENDING atascadas

**Síntoma:** Ejecución creada pero nunca ejecuta (`worker_name = None`)

**Causas:**
1. Worker GET/Discovery no está corriendo
2. Saturación momentánea de Celery
3. Error al enviar a Celery (ahora capturado)

**Solución:**
```bash
# Verificar workers
sudo supervisorctl status facho_deluxe_v2:celery_worker_*

# Ver ejecuciones huérfanas
python manage.py shell
>>> from executions.models import Execution
>>> Execution.objects.filter(status='PENDING', created_at__lt=now-2min)

# El cleanup job las marca automáticamente como INTERRUPTED
```

---

### Problema 2: Tareas se ejecutan dos veces

**Síntoma:** Dos ejecuciones casi simultáneas de la misma tarea

**Causas:**
1. Race condition entre coordinator loop y callback
2. Lock atómico no funcionó

**Solución:**
- ✅ **Lock atómico de creación** (5s)
- ✅ **Verificación de `last_run_at`** (< 3s rechaza)
- ✅ **Actualización de `next_run_at` ANTES** de crear ejecución
- ✅ **Lock de procesamiento de cola** (10s)

---

### Problema 3: Tareas no respetan intervalo

**Síntoma:** Se ejecutan antes de tiempo o muy seguido

**Causas:**
1. `next_run_at` no se actualizó correctamente
2. Catch-up de tareas perdidas

**Solución:**
```python
# El coordinator SIEMPRE actualiza next_run_at:
next_time = now + timedelta(seconds=interval_seconds)

# NO hay catch-up:
# Si una tarea no se ejecutó a las 12:00, 
# la próxima será 12:05, NO 12:00 + todas las perdidas
```

---

### Problema 4: Discovery y GET chocan

**Síntoma:** Discovery ejecutando y GET intenta ejecutar

**Causas:**
1. Desfase no aplicado
2. Auto-corrección no funcionando

**Solución:**
```bash
# Aplicar desfase manualmente
python manage.py aplicar_desfase

# Verificar auto-corrección en logs
grep "Corrigiendo desfase" logs/coordinator/main.log

# Debe estar activa cada 5 segundos
```

---

### Problema 5: OLT bloqueada permanentemente

**Síntoma:** "OLT EN REINTENTO" por más de 10 minutos

**Causas:**
1. Worker de reintentos no corriendo
2. Redis lock corrupto

**Solución:**
```bash
# Verificar lock en Redis
redis-cli
> GET olt:retrying:26
> TTL olt:retrying:26  # Debe ser < 600s

# Si está corrupto, eliminar manualmente
> DEL olt:retrying:26

# Verificar worker de reintentos
sudo supervisorctl status facho_deluxe_v2:celery_worker_discovery
```

---

### Problema 6: Logs spam "Cambios detectados"

**Síntoma:** Log se llena con "Cambios detectados" constantemente

**Causas:**
1. Estado cambia en cada loop
2. Criterio muy sensible

**Solución (ya implementado):**
```python
# Solo loguea si:
1. Hay tareas activas (has_active_tasks)
2. Y hubo cambios reales (tasks_added o tasks_removed)
```

---

## ⚙️ Configuración

### Celery Beat Schedule
```python
# core/settings.py
CELERY_BEAT_SCHEDULE = {
    'coordinator-loop': {
        'task': 'execution_coordinator.tasks.coordinator_loop_task',
        'schedule': 5.0,  # Cada 5 segundos
        'options': {
            'queue': 'coordinator',
            'expires': 4.0,  # Expira antes del siguiente
        }
    },
}
```

### Workers en Supervisor
```ini
# /etc/supervisor/conf.d/facho_deluxe_v2.conf

[program:celery_coordinator]
command=/opt/facho_deluxe_2/venv/bin/celery -A core worker
    --queue=coordinator
    --concurrency=2
    --loglevel=WARNING

[program:celery_worker_discovery]
command=/opt/facho_deluxe_2/venv/bin/celery -A core worker
    --queue=discovery_main,discovery_retry
    --concurrency=15
    --loglevel=INFO

[program:celery_worker_get]
command=/opt/facho_deluxe_2/venv/bin/celery -A core worker
    --queue=get_main,get_poller,get_retry
    --concurrency=15
    --loglevel=INFO
```

---

## 📚 Comandos Django Útiles

### Aplicar desfase manualmente
```bash
python manage.py aplicar_desfase
```

### Ver estado de una OLT
```bash
python manage.py shell
>>> from snmp_jobs.models import SnmpJobHost
>>> from hosts.models import OLT
>>> olt = OLT.objects.get(abreviatura='SMP-10')
>>> for jh in SnmpJobHost.objects.filter(olt=olt):
...     print(f"{jh.snmp_job.nombre}: next={jh.next_run_at}")
```

### Limpiar ejecuciones huérfanas
```bash
python manage.py shell
>>> from executions.models import Execution
>>> from django.utils import timezone
>>> from datetime import timedelta
>>> old = Execution.objects.filter(
...     status='PENDING',
...     created_at__lt=timezone.now() - timedelta(minutes=2)
... )
>>> old.update(status='INTERRUPTED', error_message='Huérfana')
```

### Ver cuotas de la última hora
```bash
python manage.py shell
>>> from execution_coordinator.models import CoordinatorEvent
>>> CoordinatorEvent.objects.filter(
...     hour_start__gte=timezone.now() - timedelta(hours=1)
... ).values('olt__abreviatura', 'snmp_job__nombre', 'status', 'actual_count', 'expected_count')
```

---

## 🎓 Conceptos Clave

### 1. SnmpJob como "Template"
`SnmpJob` define **QUÉ** hacer y **cada cuánto**, pero NO cuándo exactamente.

### 2. SnmpJobHost como "Instancia"
`SnmpJobHost` tiene el `next_run_at` específico para cada OLT.

### 3. Coordinator como "Supervisor"
Lee `SnmpJobHost.next_run_at` y decide dinámicamente qué ejecutar.

### 4. Callbacks como "Optimizador"
Ejecutan tareas inmediatamente sin esperar el loop de 5s.

### 5. Locks como "Guardián"
Previenen race conditions y ejecuciones duplicadas.

### 6. Desfase como "Prevención"
Reduce colisiones naturales entre tipos de tareas.

### 7. Cola como "Buffer"
Guarda tareas que esperan turno, respetando orden de llegada dentro de cada OLT.

---

## 📈 Métricas y KPIs

### 1. Tasa de Éxito
```
Objetivo: > 95%
Medición: SUCCESS / (SUCCESS + FAILED)
```

### 2. Cumplimiento de Cuota
```
Objetivo: 80-120%
Medición: actual_count / expected_count
```

### 3. Tiempo de Cola
```
Objetivo: < 30 segundos
Medición: execution.started_at - enqueued_at
```

### 4. Ejecuciones Huérfanas
```
Objetivo: < 1%
Medición: INTERRUPTED / TOTAL
```

### 5. Duración Promedio
```
Discovery: 5-20 segundos
GET: 50-500 ms
```

---

## 🚀 Roadmap Futuro

### ✅ Implementado
- [x] Coordinación inteligente
- [x] Sistema de prioridades
- [x] Desfase automático
- [x] Ejecución inmediata via callbacks
- [x] Locks anti-race conditions
- [x] Auto-corrección de desfase
- [x] Logging mejorado
- [x] Manejo de errores de Celery

### 🔮 Posibles Mejoras
- [ ] Dashboard en tiempo real más avanzado
- [ ] Alertas automáticas (email/Slack) por fallos
- [ ] Historial de rendimiento por OLT
- [ ] Predicción de carga y auto-ajuste de concurrencia
- [ ] API REST para control externo
- [ ] Modo "mantenimiento" por OLT
- [ ] Prioridad dinámica basada en SLA

---

## 📞 Soporte y Depuración

### Logs Importantes
```bash
# Coordinator
tail -f /opt/facho_deluxe_2/logs/coordinator/main.log

# Discovery Worker
tail -f /opt/facho_deluxe_2/logs/celery_worker_discovery.log

# GET Worker
tail -f /opt/facho_deluxe_2/logs/celery_worker_get.log

# Celery Beat
tail -f /opt/facho_deluxe_2/logs/celery_beat.log
```

### Verificar Estado del Sistema
```bash
# Supervisor
sudo supervisorctl status facho_deluxe_v2:

# Redis
redis-cli KEYS "lock:*"
redis-cli KEYS "olt:*"

# Colas Celery
redis-cli LLEN discovery_main
redis-cli LLEN get_main
```

### Reiniciar Componentes
```bash
# Solo coordinator
sudo supervisorctl restart facho_deluxe_v2:celery_coordinator

# Todos los workers
sudo supervisorctl restart facho_deluxe_v2:

# Celery Beat
sudo supervisorctl restart facho_deluxe_v2:celery_beat
```

---

## 🎯 Conclusión

El **Coordinador de Ejecuciones** es un sistema robusto y auto-gestionado que:

✅ **Maximiza** la utilización de recursos  
✅ **Minimiza** colisiones entre tareas  
✅ **Protege** las OLTs de sobrecarga  
✅ **Optimiza** tiempos de ejecución  
✅ **Auto-corrige** desviaciones  
✅ **Monitorea** cumplimiento de objetivos  

**Es 100% autónomo** y solo requiere que `SnmpJob` y `OLT` estén configurados correctamente.

---

**Última actualización:** 27 de Octubre, 2025  
**Versión:** 2.0 - Sistema de Coordinación Inteligente

