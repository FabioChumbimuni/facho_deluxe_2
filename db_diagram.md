# Diagrama de Base de Datos - Facho Deluxe v2

## Actualizado: 2025-11-08

## 📊 Nuevas Tablas del Sistema de Coordinación

### execution_coordinator App

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

#### **coordinator_events**
Registro estructurado de decisiones y acciones coordinadas.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | BigInt | PK |
| execution_id | ForeignKey | Referencia a executions.Execution (nullable) |
| snmp_job_id | ForeignKey | Referencia a snmp_jobs.SnmpJob (nullable) |
| job_host_id | ForeignKey | Referencia a snmp_jobs.SnmpJobHost (nullable) |
| olt_id | ForeignKey | Referencia a hosts.OLT (nullable) |
| event_type | CharField(40) | ENQUEUED, REQUEUED, AUTO_REPAIR, etc. |
| decision | CharField(20) | ENQUEUE, REQUEUE, WAIT, SKIP, etc. |
| source | CharField(30) | SCHEDULER, DELIVERY_CHECKER, AUTO_REPAIR, ADMIN, etc. |
| reason | Text | Motivo resumido (nullable) |
| details | JSON | Contexto adicional (nullable) |
| created_at | DateTime | Fecha/hora del evento |

**Índices:**
- created_at
- event_type
- decision
- source
- (olt_id, created_at)

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
- ✅ **Respeto de intervalos**: Cada tarea reprograma su siguiente ejecución según su intervalo
- ✅ **Sin colisiones**: Solo 1 tarea SNMP pesada por OLT a la vez
- ✅ **Priorización**: Discovery siempre antes que GET

