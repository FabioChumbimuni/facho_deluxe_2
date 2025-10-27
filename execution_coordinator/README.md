# Sistema de Coordinación Inteligente de Ejecuciones SNMP

## 📋 Descripción General

El **Execution Coordinator** es un sistema inteligente que gestiona la ejecución secuencial y ordenada de tareas SNMP (Discovery y GET) sobre las OLTs, evitando colisiones, gestionando cuotas y reformulando planes dinámicamente.

## 🎯 Objetivos

1. **Evitar Colisiones**: Una sola operación SNMP pesada por OLT a la vez
2. **Gestionar Cuotas**: Asegurar que las tareas se ejecuten N veces por hora
3. **Reacción Dinámica**: Detectar cambios (tareas deshabilitadas, OLTs offline) y reformular planes
4. **Priorización**: Discovery tiene prioridad sobre GET
5. **Observabilidad**: Logs detallados de todas las decisiones del coordinator

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│              EXECUTION COORDINATOR                       │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Coordinator Loop (cada 5 segundos)              │  │
│  │  - Lee estado completo de cada OLT activa       │  │
│  │  - Detecta cambios (hash comparison)            │  │
│  │  - Reformula planes si hay cambios              │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Quota Manager                                   │  │
│  │  - Rastrea ejecuciones por hora                 │  │
│  │  - Detecta violaciones de cuota                 │  │
│  │  - Genera alertas                               │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Logger Dual                                     │  │
│  │  - Escribe en BD (consultas)                    │  │
│  │  - Escribe en archivo (troubleshooting)         │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 📦 Componentes

### 1. Modelos (`models.py`)

#### **QuotaTracker**
Rastrea el cumplimiento de cuotas por OLT y tipo de tarea.

Campos principales:
- `olt`: OLT asociada
- `task_type`: Tipo de tarea (discovery, get_descripcion, etc.)
- `period_start/period_end`: Período de la cuota (normalmente 1 hora)
- `quota_required`: Número de ejecuciones requeridas
- `quota_completed`: Ejecuciones completadas exitosamente
- `quota_failed`: Ejecuciones fallidas
- `quota_skipped`: Ejecuciones omitidas por falta de tiempo
- `status`: Estado actual (IN_PROGRESS, COMPLETED, QUOTA_NOT_MET, etc.)

#### **QuotaViolation**
Registra violaciones de cuota cuando no se cumple lo esperado.

Campos principales:
- `olt`: OLT afectada
- `period_start/period_end`: Período afectado
- `report`: Reporte completo en JSON
- `severity`: LOW, MEDIUM, HIGH, CRITICAL
- `notified`: Si se envió notificación

#### **CoordinatorLog**
Log detallado de todas las acciones del coordinator.

Campos principales:
- `olt`: OLT asociada (opcional, puede ser GLOBAL)
- `event_type`: Tipo de evento (TASK_ADDED, PLAN_ADJUSTED, etc.)
- `level`: DEBUG, INFO, WARNING, ERROR, CRITICAL
- `message`: Mensaje descriptivo
- `details`: Datos adicionales en JSON
- `timestamp`: Fecha/hora del evento

(ExecutionPlan eliminado - no se usaba)

Campos principales:
- `olt`: OLT asociada
- `period_start/period_end`: Período del plan
- `plan_data`: Plan completo en JSON (lista de tareas con timing)
- `status`: ACTIVE, COMPLETED, SUPERSEDED, ABORTED
- `total_tasks/completed_tasks/failed_tasks`: Métricas

### 2. Logger (`logger.py`)

**CoordinatorLogger**: Sistema de logging dual.

Características:
- Escribe en **base de datos** (CoordinatorLog) para consultas en Django Admin
- Escribe en **archivo rotativo** (logs/coordinator/*.log) para troubleshooting
- Archivos de 10 MB con rotación de 5 backups
- Métodos de conveniencia para eventos específicos

Ejemplo de uso:
```python
from execution_coordinator.logger import coordinator_logger

coordinator_logger.log_task_added("GET Descripción", olt=olt)
coordinator_logger.log_quota_violation(olt, "discovery", "CRITICAL")
coordinator_logger.log_emergency_replan(olt, "Múltiples fallos detectados")
```

### 3. Coordinador (`coordinator.py`)

**ExecutionCoordinator**: Lógica principal de coordinación.

Métodos principales:
- `get_system_state()`: Lee estado completo (OLT, tareas, ejecuciones, locks, colas)
- `calculate_state_hash()`: Hash SHA256 para detectar cambios
- `detect_changes()`: Compara estado actual vs anterior
- `handle_changes()`: Ejecuta acciones según cambios detectados

Tipos de cambios detectados:
- `task_added`: Tarea habilitada o creada
- `task_removed`: Tarea deshabilitada
- `task_interval_changed`: Intervalo modificado
- `olt_enabled`: OLT habilitada
- `olt_disabled`: OLT deshabilitada

### 4. Tareas Celery (`tasks.py`)

#### **coordinator_loop_task**
Loop principal que se ejecuta **cada 5 segundos**.

Flujo:
1. Obtiene todas las OLTs activas
2. Para cada OLT:
   - Lee estado actual
   - Compara con estado anterior (hash)
   - Si hay cambios → detecta cambios específicos
   - Ejecuta acciones necesarias
   - Guarda estado actual

#### **check_quota_violations_task**
Se ejecuta **cada hora** al final del período.

Flujo:
1. Busca QuotaTrackers del período anterior
2. Identifica aquellos que no cumplieron cuota (< 80%)
3. Crea QuotaViolation con severidad según % de cumplimiento
4. Log de la violación

#### **cleanup_old_coordinator_logs_task**
Se ejecuta **diariamente** para limpiar logs antiguos (> 7 días).

### 5. Admin (`admin.py`)

Interfaz administrativa completa con visualizaciones HTML/CSS.

Features:
- **QuotaTrackerAdmin**: Barras de progreso, badges de estado, indicadores de riesgo
- **QuotaViolationAdmin**: Badges de severidad, reportes JSON formateados
- **CoordinatorLogAdmin**: Filtros por nivel/tipo, búsqueda, detalles JSON

## 🚀 Uso

### Instalación

1. La app ya está registrada en `settings.py`:
```python
INSTALLED_APPS = [
    ...
    'execution_coordinator',
    ...
]
```

2. Ejecutar migraciones:
```bash
python manage.py makemigrations execution_coordinator
python manage.py migrate
```

3. Las tareas Celery ya están configuradas en `CELERY_BEAT_SCHEDULE`:
- `coordinator-loop`: Cada 5 segundos
- `check-quota-violations`: Cada hora
- `cleanup-coordinator-logs`: Diariamente

### Visualización en Django Admin

1. Acceder a Django Admin: `http://localhost:8000/admin/`

2. Secciones disponibles:
   - **Rastreadores de Cuotas**: Ver cumplimiento en tiempo real
   - **Violaciones de Cuota**: Alertas de cuotas no cumplidas
   - **Logs del Coordinador**: Historial completo de eventos
   - **Planes de Ejecución**: Planes generados por el coordinator

### Logs en Archivo

Los logs se guardan en: `logs/coordinator/main.log`

Formato:
```
2025-10-21 08:30:15 [INFO] coordinator.coordinator_loop: 🔄 Cambios detectados en OLT-CENTRAL-01
2025-10-21 08:30:15 [WARNING] coordinator.coordinator_loop: ❌ Tarea 'GET Descripción' removida del plan
2025-10-21 08:30:20 [CRITICAL] coordinator.coordinator_loop: 🚨 Violación de cuota [HIGH]: discovery
```

## 📊 Escenarios de Uso

### Escenario 1: Usuario deshabilita una tarea

1. Usuario deshabilita "GET Descripción" en Django Admin
2. Coordinator loop detecta cambio (en 5 segundos)
3. Acciones automáticas:
   - Aborta ejecuciones PENDING de esa tarea
   - Remueve de cola de espera
   - Ajusta QuotaTracker
   - Log del evento
4. Plan reformulado sin esa tarea

### Escenario 2: Cuota no se cumple

1. Al final de la hora, `check_quota_violations_task` se ejecuta
2. Detecta que Discovery solo completó 2/4 ejecuciones
3. Acciones automáticas:
   - Crea QuotaViolation con severity=HIGH
   - Log crítico del evento
   - Reporte disponible en Django Admin

### Escenario 3: OLT se deshabilita

1. Usuario deshabilita OLT en Django Admin
2. Coordinator loop detecta cambio
3. Acciones automáticas:
   - Aborta TODAS las ejecuciones de esa OLT
   - Limpia locks de Redis
   - Limpia cola de espera
   - Marca cuotas como INTERRUPTED

## 🔧 Configuración

### Frecuencia del Loop

Modificar en `settings.py`:
```python
CELERY_BEAT_SCHEDULE = {
    'coordinator-loop': {
        'task': 'execution_coordinator.tasks.coordinator_loop_task',
        'schedule': 5.0,  # Cambiar aquí (en segundos)
    },
}
```

### Retención de Logs

Modificar en `settings.py`:
```python
CELERY_BEAT_SCHEDULE = {
    'cleanup-coordinator-logs': {
        'task': 'execution_coordinator.tasks.cleanup_old_coordinator_logs_task',
        'schedule': 86400.0,
        'kwargs': {'days_old': 7},  # Cambiar aquí
    },
}
```

## 📈 Métricas y Monitoreo

### Métricas Disponibles

- **Cuotas por hora**: Ver en QuotaTracker
- **Violaciones**: Ver en QuotaViolation
- **Eventos del coordinator**: Ver en CoordinatorLog

### Queries Útiles

Ver cuotas de la hora actual:
```python
from execution_coordinator.models import QuotaTracker
from django.utils import timezone

current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
QuotaTracker.objects.filter(period_start=current_hour)
```

Ver violaciones recientes:
```python
from execution_coordinator.models import QuotaViolation
from datetime import timedelta

last_24h = timezone.now() - timedelta(hours=24)
QuotaViolation.objects.filter(created_at__gte=last_24h)
```

## 🐛 Troubleshooting

### El coordinator no está corriendo

1. Verificar que Celery Beat esté corriendo:
```bash
ps aux | grep celery
```

2. Verificar logs:
```bash
tail -f logs/coordinator/main.log
```

### Las cuotas no se actualizan

1. Verificar que el coordinator loop esté ejecutándose
2. Revisar CoordinatorLog en Django Admin
3. Verificar que las OLTs estén habilitadas

### Logs no aparecen en archivo

1. Verificar permisos del directorio `logs/coordinator/`
2. Verificar que el path esté correcto en `logger.py`

## 📝 Notas de Desarrollo

- El coordinator es **stateless**: toda la información se guarda en Redis y BD
- Los hashes de estado permiten detección rápida de cambios sin comparaciones costosas
- El sistema es **reactivo**: responde a cambios en segundos
- Logs duales permiten **consultas SQL** (BD) y **troubleshooting** (archivos)

## 🔮 Futuras Mejoras

- [ ] Predicción de tiempos de ejecución usando ML
- [ ] Re-empaquetado inteligente cuando hay tiempo sobrante
- [ ] Notificaciones push de violaciones de cuota
- [ ] Dashboard en tiempo real
- [ ] Métricas de rendimiento por OLT
- [ ] Sistema de alertas configurables
- [ ] API REST para consultar estado del coordinator

## 📄 Licencia

Parte del proyecto Facho Deluxe v2.

