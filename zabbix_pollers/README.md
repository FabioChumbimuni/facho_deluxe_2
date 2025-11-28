# Sistema de Pollers Zabbix

Este módulo reemplaza al coordinador (`execution_coordinator`) con un sistema de ejecución estilo Zabbix.

## 🎯 Características Principales

1. **Scheduler Zabbix**: Loop cada 1 segundo que identifica nodos listos
2. **Poller Manager**: Gestiona múltiples pollers paralelos (configurable, default: 10)
3. **Protección OLT**: Solo 1 nodo a la vez por OLT (evita saturación)
4. **Nodos Compuestos**: Master + encadenados = 1 nodo compuesto (aunque sean 7, cuentan como 1)
5. **API REST**: Endpoints para consultar estado de pollers, cola y estadísticas
6. **🧪 Modo Prueba**: Respeta completamente el modo prueba global para testeo sin consultas SNMP reales

## 📋 Conceptos Clave

### Nodo = Item (Zabbix)
- Un nodo individual del workflow
- Tiene `nextcheck`, `lastcheck`, `interval_seconds`

### Workflow = Host (Zabbix)
- Un workflow completo de una OLT
- Contiene múltiples nodos

### Nodo Compuesto (Master + Encadenados)
- **Un nodo master con sus encadenados = 1 NODO COMPUESTO**
- Aunque sean 7 nodos, si están encadenados cuentan como 1
- La demora de ejecución incluye todos los encadenados
- Solo el master tiene `nextcheck`, los encadenados no

### Pollers Internos (Separados)
- `get_poller_task` en `snmp_get/tasks.py`
- Procesan lotes de ONUs en paralelo
- **NO se combinan** con pollers del sistema Zabbix
- Funcionamiento interno independiente

## 🔄 Flujo de Ejecución

```
1. SCHEDULER (cada 1 segundo):
   ├─ Identifica nodos listos (nextcheck <= now)
   ├─ Agrupa master + encadenados = nodo compuesto
   ├─ Calcula delay y marca como delayed
   └─ Envía a PollerManager

2. POLLER MANAGER:
   ├─ Verifica protección OLT (1 nodo por OLT)
   ├─ Asigna nodos a pollers libres
   ├─ Encola si OLT ocupada o no hay poller libre
   └─ Procesa cola cuando hay pollers libres

3. POLLER:
   ├─ Ejecuta nodo compuesto (master + encadenados secuencialmente)
   ├─ Verifica modo prueba (las tareas discovery_main_task/get_main_task lo verifican)
   ├─ Actualiza lastcheck, nextcheck
   └─ Libera poller y procesa siguiente de esa OLT
```

## 🧪 Modo Prueba

El sistema de pollers Zabbix **respeta completamente el modo prueba** para testeo:

### ✅ Funcionamiento

1. **Verificación Automática**: Las tareas `discovery_main_task` y `get_main_task` verifican automáticamente el modo prueba usando `ConfiguracionSistema.is_modo_prueba()`

2. **Flujo Completo**:
   ```
   Scheduler → PollerManager → Poller → composite_node.execute()
   → discovery_main_task/get_main_task → Verifica modo_prueba
   → Si modo_prueba=True: Simula ejecución sin consultas SNMP
   → Si modo_prueba=False: Ejecuta consultas SNMP reales
   ```

3. **Sin Cambios Necesarios**: El modo prueba funciona automáticamente sin necesidad de modificar el sistema de pollers

### 📋 Cómo Activar/Desactivar

1. **Desde Django Admin**:
   - Ir a `Configuración Avanzada` → `Configuraciones del Sistema`
   - Buscar o crear configuración con `modo_prueba=True`
   - Activar la configuración

2. **Desde API REST**:
   ```bash
   # Activar
   POST /api/v1/configuracion/modo-prueba/
   {"modo_prueba": true}
   
   # Desactivar
   POST /api/v1/configuracion/modo-prueba/
   {"modo_prueba": false}
   ```

3. **Verificar Estado**:
   ```bash
   GET /api/v1/configuracion/modo-prueba/
   ```

### ⚠️ Importante

- **El modo prueba afecta TODAS las ejecuciones**, incluyendo las creadas por el sistema de pollers Zabbix
- Las ejecuciones simuladas tienen `result_summary.simulated = True`
- Los tiempos de ejecución son aleatorios (milisegundos a 3 minutos)
- **No usar en producción**: El modo prueba está diseñado solo para desarrollo y pruebas

## 🚀 Instalación

1. **Agregar a INSTALLED_APPS** (ya hecho):
   ```python
   # core/settings.py
   INSTALLED_APPS = [
       # ...
       "zabbix_pollers",
   ]
   ```

2. **Configurar Celery Beat** (ya hecho):
   ```python
   # core/settings.py
   CELERY_BEAT_SCHEDULE = {
       'zabbix-scheduler': {
           'task': 'zabbix_pollers.tasks.zabbix_scheduler_loop_task',
           'schedule': 1.0,  # Cada 1 segundo
           'options': {
               'queue': 'zabbix_scheduler',
               'expires': 0.5,
           }
       },
   }
   ```

3. **Configurar Cola en Celery** (ya hecho):
   ```python
   # core/celery.py
   app.conf.task_routes = {
       'zabbix_pollers.tasks.zabbix_scheduler_loop_task': {'queue': 'zabbix_scheduler'},
   }
   ```

4. **Agregar Worker en Supervisor**:
   ```ini
   [program:celery_zabbix_scheduler]
   command=/opt/facho_deluxe_2/venv/bin/celery -A core worker
       --queue=zabbix_scheduler
       --concurrency=1
       --loglevel=INFO
       -n zabbix_scheduler@%%h
   directory=/opt/facho_deluxe_2
   user=noc
   autostart=true
   autorestart=true
   stopwaitsecs=60
   stopasgroup=true
   killasgroup=true
   ```

## 📡 API REST

### GET /api/v1/pollers/
Estado de todos los pollers

**Respuesta:**
```json
{
  "pollers": [
    {
      "poller_id": 0,
      "status": "BUSY",
      "busy_percentage": 45.2,
      "tasks_completed": 123,
      "tasks_delayed": 5,
      "current_node_id": 123,
      "current_node_name": "Descover.master"
    }
  ],
  "global_stats": {
    "total_pollers": 10,
    "free_pollers": 7,
    "busy_pollers": 3,
    "busy_percentage": 32.5,
    "queue_size": 5,
    "is_saturated": false,
    "is_overload": false,
    "total_tasks_completed": 1234,
    "total_tasks_delayed": 45
  }
}
```

### GET /api/v1/pollers/queue/
Estado de la cola

**Respuesta:**
```json
{
  "size": 5,
  "is_overload": false,
  "overload_threshold": 800,
  "max_size": 1000,
  "next_nodes": [
    {
      "id": 123,
      "name": "Descover.master",
      "olt": "SMP-10",
      "delayed": true,
      "delay_time": 120.5,
      "priority": 50
    }
  ]
}
```

### GET /api/v1/pollers/stats/
Estadísticas globales

**Respuesta:**
```json
{
  "total_pollers": 10,
  "free_pollers": 7,
  "busy_pollers": 3,
  "busy_percentage": 32.5,
  "queue_size": 5,
  "is_saturated": false,
  "is_overload": false,
  "total_tasks_completed": 1234,
  "total_tasks_delayed": 45,
  "scheduler_running": true,
  "start_pollers": 10
}
```

### POST /api/v1/pollers/nodes/{node_id}/run/
Ejecutar nodo manualmente

**Respuesta:**
```json
{
  "status": "assigned",
  "node_id": 123,
  "node_name": "Descover.master",
  "olt": "SMP-10",
  "chain_nodes_count": 2,
  "message": "Nodo compuesto asignado (master + 2 encadenados)"
}
```

## ⚙️ Configuración

### Número de Pollers

Por defecto: 10 pollers paralelos

Para cambiar, modificar en `zabbix_pollers/tasks.py`:
```python
_poller_manager = PollerManager(start_pollers=15)  # Cambiar aquí
```

### Protección OLT

**Automática**: Solo 1 nodo a la vez por OLT

No requiere configuración adicional.

### Separación de Pollers Internos

Los pollers internos (`get_poller_task`) funcionan independientemente y **NO se combinan** con los pollers del sistema Zabbix.

## 🔍 Monitoreo

### Logs

El scheduler genera logs en:
- `INFO`: Inicio/detención, asignaciones, procesamiento de cola
- `DEBUG`: Detalles de cada loop
- `WARNING`: Saturación detectada
- `ERROR`: Errores en ejecución

### Métricas

- **Busy Percentage**: Porcentaje de tiempo ocupado de los pollers
- **Queue Size**: Tamaño de la cola de nodos pendientes
- **Saturation**: Detecta si `busy > 75%` o `queue > (start_pollers * 2)`

## 🔄 Migración desde Coordinador

1. ✅ Desactivar `coordinator-loop` en `CELERY_BEAT_SCHEDULE` (ya hecho)
2. ✅ Activar `zabbix-scheduler` en `CELERY_BEAT_SCHEDULE` (ya hecho)
3. ⏳ Agregar worker `celery_zabbix_scheduler` en Supervisor
4. ⏳ Reiniciar servicios
5. ⏳ Monitorear logs y métricas

## 📝 Notas Importantes

- **Nodos encadenados**: Se ejecutan secuencialmente después del master
- **Tiempo de ejecución**: Incluye master + todos los encadenados
- **Protección OLT**: Automática, no requiere configuración
- **Pollers internos**: Separados, no se combinan con pollers del sistema

