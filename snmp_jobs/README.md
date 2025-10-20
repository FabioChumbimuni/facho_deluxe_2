# Sistema de Tareas SNMP

## Arquitectura del Sistema

Este sistema permite la recolección automatizada de datos SNMP de OLTs utilizando Django + Celery. 

### Componentes Principales

1. **Django Admin**: Interface para crear y gestionar tareas SNMP
2. **Celery Beat**: Programador de tareas periódicas
3. **Celery Worker**: Ejecutor de consultas SNMP
4. **Redis**: Broker de mensajes y sistema de locks

## Flujo de Datos

### 1. Creación de Tareas (SnmpJob)

- Usuario crea tarea desde el admin especificando:
  - Marca de OLT
  - OLTs objetivo
  - OIDs a consultar
  - Intervalo de ejecución
  - Tipo de consulta (descubrimiento, get, walk, etc)
  - Máximo de reintentos
  - Delay entre reintentos

### 2. Dispatcher (Celery Beat)

- Revisa cada 30s los `SnmpJob` listos para ejecutar
- Crea `Execution` por cada host
- Encola tareas `execute_one` en Celery
- Actualiza `next_run_at` del job

### 3. Ejecución (Celery Worker)

1. **Pre-ejecución**:
   - Adquiere lock Redis por host
   - Marca ejecución como RUNNING
   - Incrementa contador de intentos

2. **Ejecución SNMP**:
   - Obtiene parámetros del host
   - Ejecuta consulta SNMP según tipo
   - Valida resultados

3. **Post-ejecución exitosa**:
   - Guarda resultados en `Execution`
   - Actualiza `OnuData` en transacción atómica
   - Resetea contador de fallos del host
   - Libera lock Redis

4. **Manejo de Errores**:
   - Guarda error en `Execution`
   - Incrementa contador de fallos del host
   - Si hay reintentos disponibles: reencola
   - Si se agotan reintentos: deshabilita host
   - Libera lock Redis

## Estados y Transiciones

### Estados de Execution
- PENDING: Creado, esperando ejecución
- RUNNING: En proceso
- SUCCESS: Completado exitosamente
- FAILED: Error (temporal o permanente)

### Control de Reintentos
- Máximo 3 intentos por default
- Delay de 120s entre reintentos
- Después de 3 fallos: host deshabilitado

## Tablas Principales

1. **snmp_jobs**: Plantillas de tareas
2. **snmp_job_hosts**: Relación job-host y estado
3. **snmp_job_oids**: OIDs por consultar
4. **snmp_executions**: Registro de ejecuciones
5. **execution_attempts**: Historial de intentos
6. **onu_data**: Datos recolectados

## Configuración Recomendada

### Redis
```python
REDIS_URL = "redis://localhost:6379/0"
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
```

### Celery
```python
CELERY_TASK_ROUTES = {
    'snmp_jobs.tasks.execute_one': {'queue': 'snmp_default'},
    'snmp_jobs.tasks.execute_one_retry': {'queue': 'snmp_retry'},
}

CELERY_TASK_DEFAULT_QUEUE = 'snmp_default'
CELERY_TASK_QUEUES = {
    'snmp_default': {},
    'snmp_retry': {},
    'snmp_highprio': {},
}
```

### Locks Redis
```python
LOCK_TIMEOUT = 60  # segundos
LOCK_PREFIX = "lock:snmp:host:"
```

## Seguridad

- Credenciales SNMP cifradas en BD
- Acceso al admin restringido
- Logs sanitizados
- Timeouts configurados

## Monitoreo

Métricas importantes:
- Tasa de éxito/fallo por host
- Tiempo de ejecución
- Cola de tareas pendientes
- Tiempo entre reintentos
- Hosts deshabilitados
