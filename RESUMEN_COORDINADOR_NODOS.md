# 📋 RESUMEN COMPLETO: Lo que hace el COORDINADOR (Supervisor) a los NODOS

## 🎯 FUNCIÓN PRINCIPAL
El **Coordinador** es el supervisor que gestiona y orquesta todos los nodos de los workflows de las OLTs. Se ejecuta constantemente (cada 5 segundos) y realiza múltiples funciones para asegurar que los nodos se ejecuten correctamente.

---

## 🔄 FUNCIONES QUE EJECUTA EL COORDINADOR

### 1. **DISTRIBUCIÓN DE EJECUCIONES** (Cada 2 minutos)
**Función:** `distribute_workflow_executions()`

**Qué hace:**
- ✅ Verifica constantemente cómo se ejecutan las OLTs
- ✅ Detecta cuando múltiples OLTs tienen el mismo tiempo de ejecución (mismo minuto)
- ✅ Distribuye las ejecuciones en un rango de hasta 3 minutos (-90 a +90 segundos)
- ✅ Evita que todas las OLTs se ejecuten al mismo tiempo (saturación del CPU)
- ✅ Respeta el intervalo de cada nodo (cada nodo tiene su propio intervalo, no es fijo)
- ✅ Solo distribuye nodos con intervalos >= 15 minutos

**Cómo funciona:**
- Agrupa ejecuciones por minuto objetivo (ej: 16:57:00)
- Si hay múltiples ejecuciones en el mismo minuto, las distribuye uniformemente
- Aplica desfase simétrico: -90, -72, -54, ..., 0, ..., +54, +72, +90 segundos
- Solo actualiza si el cambio es > 30 segundos y el nuevo tiempo está en el futuro
- No redistribuye si la ejecución está a < 60 segundos de ejecutarse

**Lock:** Se ejecuta cada 2 minutos (no cada 5 segundos) usando lock de Redis

---

### 2. **VERIFICACIÓN DE CAPACIDAD DE POLLERS** (Cada 5 segundos)
**Función:** `check_poller_capacity_and_delay()`

**Qué hace:**
- ✅ Detecta ejecuciones RUNNING que duran más de 1 minuto
- ✅ Verifica la capacidad de los pollers (workers de Celery):
  - `discovery_main`: 20 workers
  - `get_poller`: 20 workers
  - `get_main`: 20 workers
- ✅ Si los pollers están saturados (>= 80% capacidad), atrasa ejecuciones
- ✅ Aplica tanto a nodos master como a nodos en cadena
- ✅ Atrasa en 10 segundos por iteración hasta que haya espacio

**Cómo funciona:**
- Cuenta tareas activas en workers de discovery y GET
- Si una ejecución dura > 1 minuto Y los pollers están >= 80% saturados:
  - Busca el siguiente nodo a ejecutar (master o cadena)
  - Atrasa `next_run_at` en 10 segundos
  - Aplica aunque sea nodo en cadena (para evitar pérdidas)
  - Repite hasta que haya espacio en los pollers

---

### 3. **AUTO-REPARACIÓN DE NODOS** (Cada 5 segundos)
**Función:** `get_ready_tasks()` (dentro de `process_ready_tasks()`)

**Qué hace:**
- ✅ Detecta nodos master sin `next_run_at` configurado
- ✅ Los inicializa automáticamente usando `initialize_next_run()`
- ✅ Solo repara nodos master (los nodos en cadena no tienen `next_run_at` por diseño)

**Cómo funciona:**
- Busca nodos habilitados, master, sin `next_run_at`
- Llama a `initialize_next_run()` para calcular el próximo tiempo
- Guarda el `next_run_at` calculado
- Logs: "🔧 Auto-reparación: X WorkflowNode(s) sin next_run_at"

---

### 4. **VERIFICACIÓN DE NODOS LISTOS** (Cada 5 segundos)
**Función:** `get_ready_tasks()`

**Qué hace:**
- ✅ Lee todos los nodos master del workflow de la OLT
- ✅ Filtra nodos con `next_run_at <= now - 30 segundos` (margen de seguridad)
- ✅ Verifica que el nodo pueda ejecutarse (`can_execute_now()`)
- ✅ Verifica que NO haya ejecución PENDING o RUNNING para el nodo
- ✅ Ordena por prioridad (descubrimiento=90, GET=40)
- ✅ Solo incluye nodos con OID (directo o desde template_node)

**Cómo funciona:**
- Filtra: `enabled=True`, `is_chain_node=False`, `next_run_at <= safe_time`
- Verifica dependencias y que no haya ejecuciones duplicadas
- Determina tipo (descubrimiento/GET) desde el OID
- Retorna lista ordenada por prioridad

---

### 5. **PROCESAMIENTO DE TAREAS LISTAS** (Cada 5 segundos)
**Función:** `process_ready_tasks()`

**Qué hace:**
- ✅ Procesa nodos listos para ejecutar
- ✅ Verifica si la OLT está ocupada (1 ejecución a la vez por OLT)
- ✅ Si OLT ocupada: encola todos los nodos (NO SE PIERDEN)
- ✅ Si OLT libre: ejecuta el nodo de mayor prioridad
- ✅ Encola el resto para ejecutar después
- ✅ Verifica capacidad de Celery antes de ejecutar

**Cómo funciona:**
1. Obtiene nodos listos (`get_ready_tasks()`)
2. Verifica si OLT está ocupada (`is_olt_busy()`)
3. Si ocupada: encola todos en Redis (cola por OLT)
4. Si libre: ejecuta el primero (mayor prioridad) con `_execute_task_now()`
5. Encola el resto para ejecutar cuando termine el primero

**Logs:** "📞 WORKFLOW → COORDINADOR: X nodo(s) listo(s)..."

---

### 6. **VERIFICACIÓN DE CAPACIDAD DE CELERY** (Antes de ejecutar)
**Función:** `_check_celery_capacity()`

**Qué hace:**
- ✅ Verifica si hay capacidad en Celery para ejecutar una tarea
- ✅ Límites: 20 ejecuciones PENDING por tipo (descubrimiento o GET)
- ✅ Si está saturado, encola la tarea (NO SE PIERDE)

**Cómo funciona:**
- Cuenta ejecuciones PENDING del mismo tipo
- Si `pending_count >= 20`: retorna False (saturado)
- Si `pending_count < 20`: retorna True (hay capacidad)

---

### 7. **EJECUCIÓN DE TAREAS** (Cuando hay capacidad)
**Función:** `_execute_task_now()`

**Qué hace:**
- ✅ Ejecuta una tarea INMEDIATAMENTE si hay capacidad
- ✅ Verifica que NO haya ejecución PENDING o RUNNING para el nodo
- ✅ Usa lock atómico para evitar duplicados
- ✅ Actualiza `next_run_at` ANTES de crear ejecución
- ✅ Aplica distribución de tiempo (desfase por OLT ID)
- ✅ Crea Execution en BD (PENDING)
- ✅ Envía a Celery (`.delay()`)
- ✅ Actualiza `last_run_at` del WorkflowNode

**Cómo funciona:**
1. Obtiene WorkflowNode
2. Verifica OID (directo o desde template_node)
3. Busca/crea SnmpJob y SnmpJobHost (compatibilidad legacy)
4. Verifica capacidad de Celery
5. Verifica que no haya ejecución duplicada
6. Lock atómico (5 segundos)
7. Verifica `last_run_at` (no ejecutar si < 3 segundos)
8. Calcula y actualiza `next_run_at` (con distribución si es descubrimiento)
9. Crea Execution (PENDING)
10. Envía a Celery
11. Actualiza `last_run_at`

**Distribución aplicada:**
- Para descubrimiento con intervalo >= 15 min:
  - Alinea a minutos :12, :27, :42, :57
  - Aplica desfase único por OLT ID (-90 a +90 segundos)
  - Distribuye para evitar saturación

---

### 8. **GESTIÓN DE COLAS** (Cuando OLT está ocupada)
**Función:** `enqueue_task()` y `execute_next_in_queue()`

**Qué hace:**
- ✅ Encola tareas cuando la OLT está ocupada
- ✅ Usa Redis para almacenar cola por OLT
- ✅ Ordena por prioridad (mayor primero)
- ✅ Ejecuta siguiente en cola cuando termina una ejecución

**Cómo funciona:**
- Cola en Redis: `queue:olt:{olt_id}:pending`
- Almacena: `workflow_node_id`, `node_name`, `job_type`, `priority`
- Cuando termina una ejecución, el callback ejecuta `execute_next_in_queue()`
- Toma la tarea de mayor prioridad y la ejecuta

---

### 9. **EJECUCIÓN DE NODOS EN CADENA** (Cuando master termina)
**Función:** `on_task_completed()` en `callbacks.py`

**Qué hace:**
- ✅ Cuando un nodo master termina (SUCCESS o FAILED), ejecuta nodos en cadena
- ✅ Verifica que el master haya terminado completamente
- ✅ Para discovery, verifica que tenga `result_summary` procesado
- ✅ Ejecuta el primer nodo de la cadena inmediatamente
- ✅ Cuando un nodo en cadena termina, ejecuta el siguiente en la cadena

**Cómo funciona:**
1. Master termina → busca nodos en cadena (`get_chain_nodes()`)
2. Verifica que el master terminó completamente (estado, `finished_at`, `result_summary`)
3. Ejecuta primer nodo de cadena si OLT está libre y hay capacidad
4. Si no puede ejecutar, encola (NO SE PIERDE)
5. Cuando nodo en cadena termina → ejecuta siguiente en cadena
6. Cuando último nodo en cadena termina → cadena completada

**Logs:** "📞 WORKFLOW → COORDINADOR: Master completado, ejecutando X nodo(s) en cadena..."

---

### 10. **ACTUALIZACIÓN DE NEXT_RUN_AT** (Después de ejecutar)
**Función:** `_execute_task_now()` (dentro del método)

**Qué hace:**
- ✅ Calcula `next_run_at` desde el momento actual + intervalo del nodo
- ✅ Para descubrimiento con intervalo >= 15 min:
  - Alinea a minutos :12, :27, :42, :57
  - Aplica desfase único por OLT ID para distribución
- ✅ Para nodos en cadena: NO actualiza `next_run_at` (se ejecutan secuencialmente)

**Cómo funciona:**
- Si es nodo en cadena: `next_run_at = None`, solo actualiza `last_run_at`
- Si es nodo master: `next_run_at = now + interval_seconds`
- Aplica distribución si es descubrimiento >= 15 min
- Guarda en BD antes de crear ejecución

---

### 11. **VERIFICACIÓN DE ENTREGAS A CELERY** (Cada 30 segundos)
**Función:** `check_pending_deliveries()` en `delivery_checker.py`

**Qué hace:**
- ✅ Verifica que tareas PENDING fueron entregadas a Celery
- ✅ Detecta tareas "perdidas" (enviadas pero no recogidas)
- ✅ Si una tarea está PENDING > 300 segundos (5 minutos) y no está en Celery:
  - Verifica si el sistema está saturado
  - Si NO está saturado: marca como INTERRUPTED y reencola
  - Si está saturado: espera (no marca como perdida)

**Cómo funciona:**
- Busca ejecuciones PENDING > 300 segundos con `celery_task_id`
- Verifica en Celery (active, reserved, scheduled)
- Si no está en Celery Y sistema NO saturado: marca INTERRUPTED
- Si es discovery: reencola automáticamente
- Si es GET: bloquea OLT temporalmente

---

### 12. **AUTO-CORRECCIÓN DE DESFASE** (Cada 5 segundos)
**Función:** `_auto_fix_offset()` en `tasks.py`

**Qué hace:**
- ✅ Verifica y corrige automáticamente el desfase de tareas legacy (SnmpJobHost)
- ✅ Desfase esperado:
  - Discovery: segundo 00
  - GET: segundo 10

**Cómo funciona:**
- Lee todos los SnmpJobHost de la OLT
- Verifica si el segundo de `next_run_at` es el esperado
- Si no: corrige ajustando solo el segundo
- Logs solo si corrige algo

---

### 13. **VERIFICACIÓN DE ESTADO DE OLT** (Cada 5 segundos)
**Función:** `is_olt_busy()`

**Qué hace:**
- ✅ Verifica si la OLT está ocupada ejecutando un nodo
- ✅ Solo permite 1 ejecución a la vez por OLT
- ✅ El sistema puede ejecutar nodos de diferentes OLTs simultáneamente (hasta 20 OLTs)

**Cómo funciona:**
- Cuenta ejecuciones RUNNING o PENDING en la OLT
- Si `running_count >= 1`: OLT ocupada
- Si `running_count == 0`: OLT libre

---

### 14. **LOGS Y MONITOREO** (Constante)
**Función:** `coordinator_logger` en todos los métodos

**Qué hace:**
- ✅ Registra todas las acciones del coordinador
- ✅ Logs estructurados con información de OLT, nodo, tiempos, etc.
- ✅ Eventos: `WORKFLOW_TO_COORDINADOR`, `EXECUTION_DISTRIBUTED`, `EXECUTION_DELAYED`, etc.

**Tipos de logs:**
- `📞 WORKFLOW → COORDINADOR`: Cuando el workflow llama al coordinador
- `🔄 COORDINADOR: Distribución`: Cuando distribuye ejecuciones
- `⏱️ COORDINADOR: Atrasando`: Cuando atrasa por saturación de pollers
- `📊 COORDINADOR: Distribuidas`: Resumen de distribuciones
- `✅ Auto-reparado`: Cuando repara nodos sin `next_run_at`

---

## 📊 RESUMEN DE FRECUENCIAS

| Función | Frecuencia | Descripción |
|---------|-----------|-------------|
| `coordinator_loop_task` | Cada 5 segundos | Loop principal |
| `distribute_workflow_executions` | Cada 2 minutos | Distribución de ejecuciones |
| `check_poller_capacity_and_delay` | Cada 5 segundos | Verificación de pollers |
| `process_ready_tasks` | Cada 5 segundos | Procesamiento de nodos listos |
| `check_pending_deliveries` | Cada 30 segundos | Verificación de entregas |
| `_auto_fix_offset` | Cada 5 segundos | Corrección de desfase |

---

## 🎯 PRINCIPIOS FUNDAMENTALES

1. **Cada OLT es independiente**: No se combinan ejecuciones entre OLTs
2. **Solo 1 nodo a la vez por OLT**: Previene colisiones
3. **NO SE PIERDEN TAREAS**: Todas se encolan si no se pueden ejecutar
4. **Respeta intervalos**: Cada nodo mantiene su intervalo configurado
5. **Prioridad estricta**: Discovery (90) antes que GET (40)
6. **Distribución inteligente**: Evita saturación del CPU
7. **Verificación constante**: Pollers, capacidad, entregas, etc.

---

## 🔄 FLUJO COMPLETO DE UN NODO

```
1. Nodo activado → initialize_next_run() → next_run_at = now + intervalo
2. Coordinador verifica cada 5s → get_ready_tasks()
3. Si next_run_at <= now - 30s → nodo listo
4. Verifica is_olt_busy() → OLT ocupada o libre?
5. Si ocupada → enqueue_task() → cola Redis
6. Si libre → _check_celery_capacity() → hay capacidad?
7. Si saturado → enqueue_task() → cola Redis
8. Si hay capacidad → _execute_task_now()
9. Actualiza next_run_at (con distribución si aplica)
10. Crea Execution (PENDING)
11. Envía a Celery (.delay())
12. Worker recoge y ejecuta
13. Al terminar → on_task_completed()
14. Si es master → ejecuta nodos en cadena
15. Si hay cola → execute_next_in_queue()
16. Ciclo continúa...
```

---

## ⚠️ PROTECCIONES IMPLEMENTADAS

1. **Lock atómico**: Evita ejecuciones duplicadas
2. **Margen de seguridad**: 30 segundos para evitar ejecuciones inmediatas
3. **Verificación de duplicados**: No ejecuta si ya hay PENDING/RUNNING
4. **Verificación de last_run_at**: No ejecuta si < 3 segundos desde última ejecución
5. **Protección de ejecuciones inminentes**: No redistribuye si < 60 segundos
6. **Verificación de capacidad**: No ejecuta si Celery saturado
7. **Verificación de pollers**: Atrasa si pollers saturados
8. **Verificación de entregas**: Detecta tareas perdidas

---

## 📝 NOTAS IMPORTANTES

- **Nodos en cadena**: NO tienen `next_run_at`, se ejecutan después del master
- **Nodos master**: Tienen `next_run_at` y se ejecutan según intervalo
- **GET independientes**: NO esperan por descubrimientos
- **Items en cadena**: Dependen del master, se ejecutan secuencialmente
- **Distribución**: Solo para descubrimiento con intervalo >= 15 min
- **Cada OLT funciona de manera independiente**: No se combinan con otras OLTs

