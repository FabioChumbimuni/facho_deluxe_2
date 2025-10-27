# Diagrama de Base de Datos - Facho Deluxe v2

## Actualizado: 2025-10-21

## 📊 Nuevas Tablas del Sistema de Coordinación

### execution_coordinator App

#### **quota_tracker**
Rastrea el cumplimiento de cuotas por OLT y tipo de tarea.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | BigInt | PK |
| olt_id | ForeignKey | Referencia a hosts.OLT |
| task_type | CharField(50) | Tipo: 'discovery', 'get_descripcion', etc. |
| period_start | DateTime | Inicio del período (hora) |
| period_end | DateTime | Fin del período |
| quota_required | Integer | Ejecuciones requeridas en el período |
| quota_completed | Integer | Ejecuciones completadas |
| quota_failed | Integer | Ejecuciones fallidas |
| quota_skipped | Integer | Ejecuciones omitidas |
| quota_pending | Integer | Ejecuciones pendientes |
| total_duration_ms | BigInteger | Tiempo total consumido (ms) |
| avg_duration_ms | Integer | Duración promedio (ms) |
| status | CharField(20) | IN_PROGRESS, COMPLETED, PARTIAL, FAILED, etc. |
| created_at | DateTime | Fecha creación |
| updated_at | DateTime | Fecha actualización |

**Índices:**
- (olt_id, period_start)
- status
- UNIQUE (olt_id, task_type, period_start)

---

#### **quota_violations**
Registro de violaciones de cuota.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | BigInt | PK |
| olt_id | ForeignKey | Referencia a hosts.OLT |
| period_start | DateTime | Inicio del período |
| period_end | DateTime | Fin del período |
| report | JSON | Reporte completo de la violación |
| severity | CharField(20) | LOW, MEDIUM, HIGH, CRITICAL |
| notified | Boolean | Si se notificó |
| notified_at | DateTime | Cuándo se notificó |
| created_at | DateTime | Fecha creación |

**Índices:**
- (olt_id, created_at)
- severity
- notified

---

#### **coordinator_logs**
Log detallado de todas las acciones del coordinator.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | BigInt | PK |
| olt_id | ForeignKey | Referencia a hosts.OLT (nullable) |
| event_type | CharField(30) | TASK_ADDED, PLAN_ADJUSTED, etc. |
| level | CharField(10) | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| message | Text | Mensaje descriptivo |
| details | JSON | Datos adicionales |
| timestamp | DateTime | Fecha/hora del evento |

**Índices:**
- (olt_id, timestamp)
- (event_type, timestamp)
- (level, timestamp)

---

#### **execution_plans**
Planes de ejecución generados por el coordinator.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | BigInt | PK |
| olt_id | ForeignKey | Referencia a hosts.OLT |
| period_start | DateTime | Inicio del período |
| period_end | DateTime | Fin del período |
| plan_data | JSON | Plan completo (lista de tareas con timing) |
| status | CharField(20) | ACTIVE, COMPLETED, SUPERSEDED, ABORTED |
| total_tasks | Integer | Total de tareas en el plan |
| completed_tasks | Integer | Tareas completadas |
| failed_tasks | Integer | Tareas fallidas |
| created_at | DateTime | Fecha creación |
| updated_at | DateTime | Fecha actualización |

**Índices:**
- (olt_id, period_start)
- status

---

## 🔄 Cambios en Tablas Existentes

### **snmp_job_hosts** (MODIFICADO)

**Nuevos campos agregados:**

| Campo | Tipo | Descripción | Nota |
|-------|------|-------------|------|
| **next_run_at** | DateTime (nullable) | Próxima ejecución para ESTA OLT | ⭐ NUEVO - Gestión independiente por OLT |
| **last_run_at** | DateTime (nullable) | Última ejecución para ESTA OLT | ⭐ NUEVO - Tracking por OLT |

**Nuevos índices:**
- next_run_at

**Descripción:**
Ahora `SnmpJobHost` gestiona `next_run_at` de forma **independiente por cada OLT**. 
Esto permite que cada OLT tenga su propio horario de ejecución sin afectar a otras OLTs.

---

## 🏗️ Arquitectura del Sistema de Coordinación

```
SnmpJob (Plantilla/Agrupador)
  ↓
  ├─ Define: QUÉ hacer (OID, tipo, intervalo sugerido)
  ├─ Se asocia a múltiples OLTs
  └─ NO gestiona CUÁNDO ejecutar

SnmpJobHost (Gestión por OLT) ⭐ MODIFICADO
  ↓
  ├─ Relación: SnmpJob ←→ OLT
  ├─ next_run_at: CUÁNDO ejecutar en ESTA OLT
  ├─ last_run_at: CUÁNDO se ejecutó en ESTA OLT
  └─ Permite horarios independientes por OLT

Execution Coordinator (Gestor de Ejecuciones)
  ↓
  ├─ Loop cada 5 segundos
  ├─ Lee SnmpJobHost.next_run_at (por OLT)
  ├─ Ejecuta por prioridad: Discovery (P90) > GET (P40)
  ├─ Gestiona colisiones automáticamente
  ├─ Callbacks: Ejecuta siguiente tarea INMEDIATAMENTE
  └─ Respeta intervalos configurados
```

---

## 📋 Flujo de Ejecución

```
1. Usuario habilita tarea en Admin
   ↓
2. Signal inicializa SnmpJobHost.next_run_at = now + 1 minuto
   ↓
3. Coordinator loop (cada 5s) detecta SnmpJobHost.next_run_at <= now
   ↓
4. Ejecuta por prioridad:
   - Discovery (P90) → ejecuta
   - GET (P40) → encola
   ↓
5. Discovery termina → Callback al coordinator
   ↓
6. Coordinator ejecuta GET INMEDIATAMENTE (desde cola)
   ↓
7. Actualiza SnmpJobHost.next_run_at = now + intervalo
   ↓
8. Ciclo se repite respetando intervalos
```

---

## 🔑 Claves del Diseño

- ✅ **Sin catch-up**: Tareas habilitadas empiezan en 1 minuto (no ejecutan pasadas)
- ✅ **Por OLT independiente**: Cada OLT tiene su propio horario
- ✅ **Ejecución eficiente**: Siguiente tarea ejecuta inmediatamente al terminar anterior
- ✅ **Respeto de intervalos**: Cada tarea cumple su cuota (ej: 5 min = 12 exec/hora)
- ✅ **Sin colisiones**: Solo 1 tarea SNMP pesada por OLT a la vez
- ✅ **Priorización**: Discovery siempre antes que GET

