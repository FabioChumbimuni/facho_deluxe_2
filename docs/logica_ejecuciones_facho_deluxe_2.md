# 🔄 Lógica de Ejecuciones - Facho Deluxe v2

## 📋 Tabla de Contenidos

1. [Introducción](#introducción)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Workflows y su Funcionamiento](#workflows-y-su-funcionamiento)
4. [Relación con OIDs](#relación-con-oids)
5. [Sistema de Ejecución](#sistema-de-ejecución)
6. [Coordinador de Ejecuciones](#coordinador-de-ejecuciones)
7. [Prioridades y Orden de Ejecución](#prioridades-y-orden-de-ejecución)
8. [Prevención de Saturación](#prevención-de-saturación)
9. [Flujos Detallados](#flujos-detallados)
10. [Integración con Celery](#integración-con-celery)

---

## 🎯 Introducción

Facho Deluxe v2 implementa un sistema complejo de gestión de workflows SNMP que permite ejecutar tareas de descubrimiento y monitoreo sobre múltiples OLTs de manera coordinada, eficiente y sin saturar el sistema.

### Conceptos Clave

- **Workflow**: Conjunto de nodos (tareas) que se ejecutan sobre una OLT específica
- **Nodo**: Tarea individual dentro de un workflow (ej: descubrimiento de ONUs, GET de estado)
- **OID**: Identificador SNMP que define qué operación realizar (descubrimiento o GET)
- **Coordinador**: Sistema inteligente que gestiona la ejecución de tareas
- **Celery**: Sistema de colas de tareas asíncronas

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                    DJANGO BACKEND                                │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                 │
│  │  WorkflowTemplate │───▶│  WorkflowTemplate│                 │
│  │   (Plantilla)     │    │      Node        │                 │
│  └────────┬──────────┘    └────────┬─────────┘                 │
│           │                        │                            │
│           │                        ▼                            │
│           │              ┌──────────────────┐                  │
│           │              │      OID          │                  │
│           │              │  (descubrimiento/ │                  │
│           │              │      get)         │                  │
│           │              └───────────────────┘                  │
│           │                        │                            │
│           ▼                        │                            │
│  ┌──────────────────┐             │                            │
│  │  OLTWorkflow     │◀────────────┘                            │
│  │  (Instancia)     │                                            │
│  └────────┬─────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                            │
│  │  WorkflowNode    │                                            │
│  │  (Tarea real)    │                                            │
│  └────────┬─────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                            │
│  │  SnmpJob         │                                            │
│  │  SnmpJobHost     │                                            │
│  └────────┬─────────┘                                            │
└───────────┼──────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│              EXECUTION COORDINATOR                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Coordinator Loop (Celery Beat - cada 5 segundos)        │   │
│  │  • Lee estado de todas las OLTs activas                  │   │
│  │  • Detecta cambios (hash comparison)                     │   │
│  │  • Procesa tareas listas                                 │   │
│  └───────────────┬──────────────────────────────────────────┘   │
│                  │                                               │
│                  ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Dynamic Scheduler                                        │   │
│  │  • Identifica tareas con next_run_at <= now              │   │
│  │  • Verifica si OLT está ocupada                          │   │
│  │  • Ordena por prioridad                                  │   │
│  │  • Ejecuta o encola                                      │   │
│  └───────────────┬──────────────────────────────────────────┘   │
│                  │                                               │
│                  ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Redis Queue (olt:queue:{olt_id})                        │   │
│  │  • Almacena tareas pendientes por OLT                    │   │
│  │  • Ordenadas por prioridad                               │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────┬───────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CELERY WORKERS                                │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Discovery    │  │ GET Main     │  │ Coordinator  │          │
│  │ Queue        │  │ Queue        │  │ Queue        │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                  │                   │
│         ▼                 ▼                  ▼                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Workers ejecutan tareas SNMP                            │   │
│  │  • discovery_main_task                                   │   │
│  │  • get_main_task                                         │   │
│  │  • coordinator_loop_task                                 │   │
│  └───────────────┬──────────────────────────────────────────┘   │
│                  │                                               │
│                  ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Callbacks                                                │   │
│  │  • on_task_completed() → ejecuta siguiente en cola      │   │
│  │  • on_task_failed() → maneja errores                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 📦 Workflows y su Funcionamiento

### ¿Qué es un Workflow?

Un **Workflow** es una colección de nodos (tareas) que se ejecutan sobre una OLT específica. Es similar a las plantillas de Zabbix: defines una plantilla con múltiples items y luego la aplicas a múltiples hosts (OLTs).

### Componentes de un Workflow

#### 1. **WorkflowTemplate** (Plantilla)
- Define la estructura reutilizable de un workflow
- Contiene múltiples `WorkflowTemplateNode`
- Se puede aplicar a múltiples OLTs
- Ejemplo: "MA5800 Discovery Básico"

#### 2. **WorkflowTemplateNode** (Nodo de Plantilla)
- Define una tarea dentro de la plantilla
- **Depende directamente de un OID** (no de TaskTemplate)
- Contiene:
  - `key`: Identificador único del nodo (ej: "discovery.onus")
  - `oid`: OID SNMP que define marca, modelo y tipo de operación
  - `interval_seconds`: Intervalo de ejecución
  - `priority`: Prioridad de ejecución (1-100)
  - `enabled`: Si está habilitado o no
  - `parameters`: Parámetros adicionales en JSON

#### 3. **OLTWorkflow** (Instancia de Workflow)
- Instancia específica de un workflow para una OLT
- Se crea automáticamente al aplicar una plantilla
- Contiene múltiples `WorkflowNode`

#### 4. **WorkflowNode** (Nodo Real)
- Tarea real que se ejecuta en una OLT específica
- Puede estar vinculado a un `WorkflowTemplateNode` (si viene de plantilla)
- O ser un nodo custom (creado manualmente)
- Se convierte en `SnmpJob` y `SnmpJobHost` para ejecución

### Flujo de Creación de Workflow

```
1. Usuario crea WorkflowTemplate
   └─ Nombre: "MA5800 Discovery Básico"
   
2. Usuario agrega WorkflowTemplateNode a la plantilla
   └─ key: "discovery.onus"
   └─ oid: OID de descubrimiento (ej: 1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1)
   └─ interval_seconds: 180
   └─ priority: 1 (descubrimiento tiene prioridad 1)
   
3. Usuario aplica plantilla a OLTs
   └─ Selecciona OLTs: SMP-10, SMP-11, SMP-12
   └─ Sistema crea OLTWorkflow para cada OLT
   └─ Sistema crea WorkflowNode para cada WorkflowTemplateNode
   
4. Sistema convierte WorkflowNode en SnmpJob + SnmpJobHost
   └─ WorkflowNode → SnmpJob (plantilla de tarea)
   └─ WorkflowNode → SnmpJobHost (instancia por OLT)
   └─ SnmpJobHost.next_run_at se calcula automáticamente
```

---

## 🔗 Relación con OIDs

### Dependencia Directa de OIDs

**IMPORTANTE**: Los nodos de workflow **dependen directamente de OIDs**, no de TaskTemplates.

#### ¿Qué es un OID?

Un **OID** (Object Identifier) define:
- **Marca**: Fabricante (Huawei, ZTE, etc.)
- **Modelo**: Modelo específico (MA5800, C320, etc.)
- **Espacio**: Tipo de operación
  - `descubrimiento`: Para descubrir elementos (ONUs, puertos, etc.)
  - `get`: Para obtener valores específicos (estado, métricas, etc.)
- **OID SNMP**: El identificador real (ej: `1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1`)

#### Flujo de Selección de TaskTemplate

Cuando se crea un `WorkflowNode` desde un `WorkflowTemplateNode`:

```
1. WorkflowTemplateNode tiene un OID asignado
   └─ oid.espacio = "descubrimiento" o "get"
   
2. Sistema busca TaskTemplate apropiado:
   └─ Si espacio == "descubrimiento":
      → Busca TaskFunction con function_type = "descubrimiento"
      → Busca TaskTemplate con esa función
   └─ Si espacio == "get":
      → Busca TaskFunction con function_type = "get"
      → Busca TaskTemplate con esa función
   
3. TaskTemplate encontrado se asigna al WorkflowNode
   └─ WorkflowNode.template = TaskTemplate
   └─ Este TaskTemplate define qué función Python ejecutar
```

### Ejemplo Práctico

```
OID: 1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1
├─ Marca: Huawei
├─ Modelo: MA5800
├─ Espacio: descubrimiento
└─ Nombre: "Discovery ONUs"

WorkflowTemplateNode:
├─ key: "discovery.onus"
├─ oid: [OID anterior]
├─ interval_seconds: 180
└─ priority: 1

Al crear WorkflowNode:
├─ Busca TaskTemplate con función "descubrimiento"
├─ Encuentra: "Discovery Huawei MA5800"
└─ Asigna: WorkflowNode.template = TaskTemplate
```

---

## ⚙️ Sistema de Ejecución

### Ejecución Individual vs Grupal

#### Ejecución Individual

Cada **WorkflowNode** se ejecuta **independientemente**:

- Cada nodo tiene su propio `interval_seconds`
- Cada nodo tiene su propio `priority`
- Cada nodo se convierte en un `SnmpJob` separado
- Cada `SnmpJob` tiene múltiples `SnmpJobHost` (uno por OLT)

**Ejemplo**:
```
Workflow "SMP-10" tiene 3 nodos:
├─ Nodo 1: Discovery ONUs (interval: 180s, priority: 1)
├─ Nodo 2: GET Estado ONUs (interval: 60s, priority: 3)
└─ Nodo 3: GET Métricas (interval: 300s, priority: 3)

Cada uno se ejecuta independientemente según su intervalo.
```

#### Ejecución por OLT

Aunque los nodos son independientes, **el coordinador los ejecuta de forma coordinada**:

- Solo **una tarea SNMP pesada por OLT a la vez**
- Si una OLT está ocupada, las demás tareas se encolan
- El coordinador gestiona las colas por OLT

### Conversión de WorkflowNode a SnmpJob

```
WorkflowNode (definición)
    │
    ├─ Se convierte en SnmpJob (plantilla)
    │  └─ SnmpJob.nombre = WorkflowNode.name
    │  └─ SnmpJob.oid = WorkflowNode.template_node.oid
    │  └─ SnmpJob.interval_seconds = WorkflowNode.interval_seconds
    │  └─ SnmpJob.job_type = OID.espacio (descubrimiento/get)
    │
    └─ Se crea SnmpJobHost por cada OLT
       └─ SnmpJobHost.olt = OLT específica
       └─ SnmpJobHost.next_run_at = calculado automáticamente
       └─ SnmpJobHost.enabled = WorkflowNode.enabled
```

---

## 🎮 Coordinador de Ejecuciones

### ¿Qué es el Coordinador?

El **Execution Coordinator** es el "cerebro" del sistema que:

1. **Monitorea** continuamente el estado de todas las OLTs
2. **Planifica** dinámicamente cuándo ejecutar cada tarea
3. **Prioriza** tareas según importancia
4. **Previene** colisiones entre tareas
5. **Optimiza** el uso de recursos

### Componentes del Coordinador

#### 1. **Coordinator Loop** (`coordinator_loop_task`)

- **Ejecuta cada 5 segundos** (Celery Beat)
- **Lee el estado** de todas las OLTs activas
- **Detecta cambios** comparando hashes de estado
- **Procesa tareas listas** mediante Dynamic Scheduler

```python
@shared_task(queue='coordinator', bind=True)
def coordinator_loop_task(self):
    """
    Loop principal que se ejecuta cada 5 segundos
    """
    active_olts = OLT.objects.filter(habilitar_olt=True)
    
    for olt in active_olts:
        # 1. Auto-corregir desfases
        _auto_fix_offset(olt.id)
        
        # 2. Leer estado actual
        coordinator = ExecutionCoordinator(olt.id)
        current_state = coordinator.get_system_state()
        
        # 3. Procesar tareas listas
        scheduler = DynamicScheduler(olt.id)
        tasks_processed = scheduler.process_ready_tasks(olt)
```

#### 2. **Dynamic Scheduler** (`dynamic_scheduler.py`)

- **Identifica tareas listas**: `SnmpJobHost.next_run_at <= now`
- **Verifica si OLT está ocupada**: `is_olt_busy()`
- **Ordena por prioridad**: Discovery (90) > GET (40)
- **Ejecuta o encola**: Según disponibilidad

#### 3. **Execution Coordinator** (`coordinator.py`)

- **Lee estado completo** del sistema
- **Calcula hashes** para detección rápida de cambios
- **Gestiona estado anterior** para comparación

### Flujo del Coordinador

```
Cada 5 segundos:
│
├─ 1. Para cada OLT activa:
│  │
│  ├─ 2. Auto-corregir desfases de tiempo
│  │  └─ Discovery → :00 segundos
│  │  └─ GET → :10 segundos
│  │
│  ├─ 3. Leer estado actual
│  │  └─ SnmpJobHost habilitados
│  │  └─ Executions en curso
│  │  └─ Cola Redis
│  │
│  ├─ 4. Detectar cambios (hash comparison)
│  │  └─ Si hay cambios → reformular plan
│  │
│  └─ 5. Procesar tareas listas
│     └─ Dynamic Scheduler
│        ├─ Obtener tareas con next_run_at <= now
│        ├─ Ordenar por prioridad
│        ├─ Verificar si OLT está ocupada
│        └─ Ejecutar o encolar
```

---

## 🎯 Prioridades y Orden de Ejecución

### Sistema de Prioridades

Las tareas tienen **prioridades numéricas** (1-100):

| Prioridad | Tipo de Tarea | Descripción |
|-----------|---------------|-------------|
| **90** | Discovery | Descubrimiento de elementos (ONUs, puertos) |
| **40** | GET | Obtención de valores específicos |
| **30** | WALK | Recorrido de árbol SNMP |
| **50** | Otros | Tareas misceláneas |

### Cálculo de Prioridad

La prioridad se calcula automáticamente según el tipo de job:

```python
def calculate_priority(job_type):
    if job_type == 'descubrimiento':
        return 90  # Máxima prioridad
    elif job_type == 'get':
        return 40  # Prioridad media
    elif job_type == 'walk':
        return 30  # Prioridad baja
    else:
        return 50  # Default
```

### Orden de Ejecución

1. **Discovery siempre primero**: Si hay tareas de descubrimiento listas, se ejecutan antes que GET
2. **GET espera**: Si hay discovery en curso o pendiente, GET se encola
3. **Orden dentro del mismo tipo**: Por nombre (alfabético)

**Ejemplo**:
```
Tareas listas para OLT SMP-10:
├─ Discovery ONUs (P90) → Ejecuta PRIMERO
├─ GET Estado ONU-1 (P40) → Encolada (hay discovery)
├─ GET Estado ONU-2 (P40) → Encolada
└─ Discovery Puertos (P90) → Ejecuta DESPUÉS del primero

Orden de ejecución:
1. Discovery ONUs
2. Discovery Puertos
3. GET Estado ONU-1
4. GET Estado ONU-2
```

---

## 🛡️ Prevención de Saturación

### Mecanismos de Protección

#### 1. **Límite de Capacidad por Tipo**

El sistema verifica la capacidad de Celery antes de ejecutar:

```python
CAPACITY_LIMITS = {
    'descubrimiento': 25,  # Máximo 25 Discovery PENDING
    'get': 25             # Máximo 25 GET PENDING
}

def _check_celery_capacity(job_type):
    pending_count = Execution.objects.filter(
        status='PENDING',
        snmp_job__job_type=job_type
    ).count()
    
    if pending_count >= CAPACITY_LIMITS[job_type]:
        return False  # Sistema saturado
    return True
```

#### 2. **Una Tarea por OLT**

- Solo **una tarea SNMP pesada por OLT a la vez**
- Si OLT está ocupada, otras tareas se encolan en Redis
- Cola por OLT: `olt:queue:{olt_id}`

#### 3. **Locks Anti-Duplicados**

- Lock atómico de 5 segundos antes de ejecutar
- Previene ejecuciones duplicadas
- Verifica `last_run_at` (no ejecutar si < 3 segundos)

#### 4. **Desfases de Tiempo**

- **Discovery**: Se ejecuta en `:00` segundos (ej: 10:00:00, 10:03:00)
- **GET**: Se ejecuta en `:10` segundos (ej: 10:00:10, 10:01:10)
- Evita colisiones entre tipos de tareas

### Flujo de Prevención

```
Tarea lista para ejecutar:
│
├─ 1. Verificar capacidad Celery
│  └─ Si saturado → Encolar
│
├─ 2. Verificar si OLT está ocupada
│  └─ Si ocupada → Encolar en Redis
│
├─ 3. Verificar lock anti-duplicados
│  └─ Si existe lock → Skip
│
├─ 4. Verificar last_run_at
│  └─ Si < 3 segundos → Skip
│
└─ 5. Ejecutar
   └─ Crear Execution (PENDING)
   └─ Enviar a Celery
   └─ Actualizar next_run_at con desfase
```

---

## 🔄 Flujos Detallados

### Flujo 1: Tarea Lista - OLT Libre

```
1. Coordinator Loop detecta:
   └─ SnmpJobHost.next_run_at <= now
   └─ Ejemplo: 10:00:00 <= 10:00:05

2. Dynamic Scheduler obtiene tareas listas:
   └─ Ordena por prioridad (Discovery primero)
   └─ Ejemplo: [Discovery ONUs (P90), GET Estado (P40)]

3. Verifica si OLT está ocupada:
   └─ is_olt_busy() → False
   └─ No hay Execution RUNNING
   └─ No hay lock de ejecución

4. Verifica capacidad Celery:
   └─ _check_celery_capacity('descubrimiento') → True
   └─ Hay menos de 25 Discovery PENDING

5. Ejecuta tarea:
   ├─ Lock atómico (5s): lock:execution:{olt_id}:{job_id}
   ├─ Verifica last_run_at (no < 3s)
   ├─ Actualiza next_run_at:
   │  └─ Discovery → now + interval + desfase :00
   │  └─ Ejemplo: 10:00:05 + 180s = 10:03:05 → 10:03:00
   ├─ Crea Execution (PENDING)
   ├─ Envía a Celery: discovery_main_task.delay(...)
   └─ Log: "▶️ Ejecutando: Discovery ONUs en SMP-10 (P90)"

6. Worker Celery ejecuta:
   └─ discovery_main_task recoge tarea
   └─ Ejecuta SNMP walk/GET
   └─ Actualiza Execution (SUCCESS/FAILED)

7. Callback ejecuta:
   └─ on_task_completed() verifica cola
   └─ Si hay tareas → ejecuta siguiente INMEDIATAMENTE
```

### Flujo 2: Tarea Lista - OLT Ocupada

```
1. Coordinator Loop detecta:
   └─ SnmpJobHost.next_run_at <= now
   └─ Ejemplo: GET Estado (10:00:10 <= 10:00:15)

2. Dynamic Scheduler obtiene tareas listas:
   └─ Ordena por prioridad
   └─ Ejemplo: [GET Estado (P40)]

3. Verifica si OLT está ocupada:
   └─ is_olt_busy() → True
   └─ Hay Execution RUNNING (Discovery en curso)

4. Verifica si ya está en cola:
   └─ Redis: olt:queue:{olt_id}
   └─ Si no está → Encolar

5. Encola en Redis:
   ├─ Redis.lpush(olt:queue:{olt_id}, {
   │  ├─ job_id: 123,
   │  ├─ job_name: "GET Estado",
   │  ├─ job_type: "get",
   │  └─ priority: 40
   │  })
   └─ Log: "📋 GET Estado encolada en SMP-10 (OLT ocupada)"

6. Espera a que termine tarea actual:
   └─ Discovery termina → on_task_completed()
   └─ Callback verifica cola
   └─ Ejecuta siguiente INMEDIATAMENTE
```

### Flujo 3: Callback Ejecuta Siguiente

```
1. Tarea termina en Worker:
   └─ discovery_main_task completa
   └─ Execution.status = SUCCESS

2. Worker llama callback:
   └─ on_task_completed(olt_id, execution_id, ...)

3. Callback verifica cola Redis:
   └─ Redis.lrange(olt:queue:{olt_id}, 0, -1)
   └─ Si hay tareas → procesar

4. Lock temporal:
   └─ lock:processing_queue:{olt_id} (10s)
   └─ Previene procesamiento simultáneo

5. Obtiene siguiente tarea:
   └─ Redis.rpop(olt:queue:{olt_id})
   └─ Ordena por prioridad (si hay múltiples)

6. Ejecuta siguiente:
   └─ _execute_task_now(task_info, olt)
   └─ Crea Execution (PENDING)
   └─ Envía a Celery
   └─ Log: "▶️ Ejecutando siguiente: GET Estado en SMP-10 (P40)"

7. Si hay más tareas:
   └─ Repite desde paso 5
   └─ Hasta que cola esté vacía
```

### Flujo 4: Saturación del Sistema

```
1. Coordinator intenta ejecutar:
   └─ Tarea lista: Discovery ONUs

2. Verifica capacidad Celery:
   └─ _check_celery_capacity('descubrimiento')
   └─ Pending count = 25 (límite alcanzado)

3. Sistema saturado:
   └─ Log: "⚠️ Sistema saturado: 25 tareas descubrimiento PENDING"
   └─ NO ejecuta
   └─ Espera a que termine alguna tarea

4. Próximo loop (5 segundos después):
   └─ Vuelve a verificar capacidad
   └─ Si hay espacio → ejecuta
```

---

## 🔧 Integración con Celery

### ¿Qué es Celery?

**Celery** es un sistema de colas de tareas distribuidas que permite ejecutar tareas de forma asíncrona en workers separados.

### Configuración de Celery

```python
# core/settings.py

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

CELERY_TASK_ROUTES = {
    'snmp_jobs.tasks.discovery_main_task': {'queue': 'discovery_main'},
    'snmp_jobs.tasks.discovery_retry_task': {'queue': 'discovery_retry'},
    'snmp_get.tasks.get_main_task': {'queue': 'get_main'},
    'snmp_get.tasks.get_retry_task': {'queue': 'get_retry'},
    'execution_coordinator.tasks.coordinator_loop_task': {'queue': 'coordinator'},
}

CELERY_WORKER_CONCURRENCY = 20
```

### Colas de Celery

| Cola | Propósito | Workers |
|------|-----------|---------|
| `discovery_main` | Tareas de descubrimiento principales | 5-10 |
| `discovery_retry` | Reintentos de descubrimiento | 2-3 |
| `get_main` | Tareas GET principales | 5-10 |
| `get_retry` | Reintentos GET | 2-3 |
| `coordinator` | Loop del coordinador | 1 |

### Flujo con Celery

```
1. Coordinador decide ejecutar tarea:
   └─ _execute_task_now()
   └─ Crea Execution (PENDING)

2. Envía a Celery:
   └─ discovery_main_task.delay(snmp_job_id, olt_id, execution_id)
   └─ Celery encola en redis://localhost:6379/0

3. Worker Celery recoge tarea:
   └─ Worker escucha cola 'discovery_main'
   └─ Recoge tarea de Redis
   └─ Ejecuta función discovery_main_task()

4. Worker ejecuta SNMP:
   └─ Conecta a OLT
   └─ Ejecuta SNMP walk/GET
   └─ Procesa resultados
   └─ Guarda en BD

5. Worker actualiza Execution:
   └─ Execution.status = SUCCESS/FAILED
   └─ Execution.finished_at = now()

6. Worker llama callback:
   └─ on_task_completed(olt_id, execution_id, ...)
   └─ Callback ejecuta siguiente en cola
```

### Ventajas de Celery

1. **Escalabilidad**: Múltiples workers pueden ejecutar tareas en paralelo
2. **Resiliencia**: Si un worker falla, otra tarea puede tomar su lugar
3. **Priorización**: Colas separadas permiten priorizar tipos de tareas
4. **Monitoreo**: Celery Flower permite monitorear workers y tareas

---

## 📊 Resumen de Dependencias

### Jerarquía de Dependencias

```
WorkflowTemplate (Plantilla)
    │
    ├─ WorkflowTemplateNode (Nodo de plantilla)
    │  │
    │  └─ OID (Dependencia directa)
    │     ├─ Define marca
    │     ├─ Define modelo
    │     └─ Define espacio (descubrimiento/get)
    │        │
    │        └─ TaskFunction (según espacio)
    │           └─ TaskTemplate (función a ejecutar)
    │
    └─ Aplicado a OLTs
       │
       └─ OLTWorkflow (Instancia)
          │
          └─ WorkflowNode (Nodo real)
             │
             └─ SnmpJob (Plantilla de tarea)
                │
                └─ SnmpJobHost (Instancia por OLT)
                   │
                   └─ Execution (Ejecución real)
                      │
                      └─ Celery Task
                         └─ Worker ejecuta SNMP
```

### Dependencias Clave

1. **WorkflowTemplateNode → OID**: Directa y obligatoria
2. **OID → TaskTemplate**: Indirecta (según espacio)
3. **WorkflowNode → SnmpJob**: Conversión automática
4. **SnmpJobHost → Execution**: Una ejecución por vez
5. **Execution → Celery Task**: Envío asíncrono

---

## 🎓 Conclusión

El sistema de workflows de Facho Deluxe v2 es un sistema complejo pero bien estructurado que:

- ✅ **Separa responsabilidades**: Plantillas vs Instancias
- ✅ **Depende de OIDs**: Define operaciones de forma centralizada
- ✅ **Coordina ejecuciones**: Evita colisiones y saturación
- ✅ **Prioriza tareas**: Discovery siempre primero
- ✅ **Escala con Celery**: Múltiples workers ejecutan en paralelo
- ✅ **Previene saturación**: Límites de capacidad y colas por OLT

Este diseño permite gestionar cientos de OLTs con miles de tareas SNMP de forma eficiente y coordinada.

---

## 📚 Referencias

- `snmp_jobs/models.py`: Modelos de workflows y tareas
- `snmp_jobs/services/workflow_template_service.py`: Lógica de aplicación de plantillas
- `execution_coordinator/coordinator.py`: Coordinador principal
- `execution_coordinator/dynamic_scheduler.py`: Scheduler dinámico
- `execution_coordinator/callbacks.py`: Callbacks de ejecución
- `execution_coordinator/COORDINATOR_GUIDE.md`: Guía detallada del coordinador

