# 📊 Análisis del Sistema de Ejecución - Facho Deluxe v2

## 🎯 Resumen Ejecutivo

Este documento analiza la lógica actual de ejecución de tareas y propone mejoras para un ejecutor tipo Zabbix que no sobrecargue el servidor y permita múltiples ejecuciones simultáneas.

---

## 🔍 ¿Qué se está utilizando para ejecutar las tareas?

### 1. **Coordinator Loop (Corazón del Sistema)**

**Ubicación**: `execution_coordinator/tasks.py` → `coordinator_loop_task()`

**Funcionamiento**:
- Se ejecuta cada 5 segundos mediante Celery Beat
- Procesa todas las OLTs activas (`habilitar_olt=True`)
- Para cada OLT:
  1. Auto-corrige desfases de tiempo
  2. Lee estado actual del sistema
  3. Detecta cambios (comparación de hashes)
  4. **Procesa tareas listas** mediante `DynamicScheduler`

**Código clave**:
```python
@shared_task(queue='coordinator', bind=True)
def coordinator_loop_task(self):
    active_olts = OLT.objects.filter(habilitar_olt=True)
    for olt in active_olts:
        scheduler = DynamicScheduler(olt.id)
        tasks_processed = scheduler.process_ready_tasks(olt)
```

---

### 2. **Dynamic Scheduler (Planificador Dinámico)**

**Ubicación**: `execution_coordinator/dynamic_scheduler.py`

**Funcionamiento**:
- Identifica tareas listas: `WorkflowNode.next_run_at <= now`
- Verifica si OLT está ocupada (una tarea por OLT a la vez)
- Verifica capacidad de Celery (límites globales)
- Ejecuta o encola según disponibilidad

**Lógica de ejecución**:
```python
def process_ready_tasks(self, olt):
    ready_tasks = self.get_ready_tasks()  # Obtiene nodos listos
    
    if not ready_tasks:
        return 0
    
    is_busy = self.is_olt_busy()  # Verifica si OLT está ocupada
    
    if is_busy:
        # Encolar todas las tareas listas
        for task in ready_tasks:
            self.enqueue_task(task)
        return 0
    else:
        # Ejecutar la de mayor prioridad
        first_task = ready_tasks[0]
        executed = self._execute_task_now(first_task, olt)
        # Encolar el resto
        for task in ready_tasks[1:]:
            self.enqueue_task(task)
        return 1 if executed else 0
```

---

### 3. **Sistema de Colas Redis**

**Funcionamiento**:
- Cada OLT tiene su propia cola: `queue:olt:{olt_id}:pending`
- Las tareas se encolan cuando la OLT está ocupada
- Se ordenan por prioridad (mayor primero)
- Cuando una tarea termina, se ejecuta inmediatamente la siguiente

**Estructura de datos en cola**:
```json
{
    "workflow_node_id": 123,
    "node_name": "DESCRIPCION",
    "job_type": "get",
    "priority": 50,
    "enqueued_at": "2025-11-22T09:20:00Z"
}
```

---

### 4. **Callbacks de Finalización**

**Ubicación**: `execution_coordinator/callbacks.py` → `on_task_completed()`

**Funcionamiento**:
- Se ejecuta cuando una tarea SNMP termina (SUCCESS o FAILED)
- Actualiza `WorkflowNode.last_success_at` si fue exitosa
- **Ejecuta nodos en cadena** si el master terminó exitosamente
- Ejecuta inmediatamente la siguiente tarea en cola

**Lógica de nodos en cadena**:
```python
if workflow_node and status == 'SUCCESS' and not workflow_node.is_chain_node:
    # Es un nodo master, buscar nodos en su cadena
    chain_nodes = workflow_node.get_chain_nodes()
    
    if chain_nodes.exists():
        # Ejecutar el primer nodo de la cadena
        first_chain_node = chain_nodes.first()
        can_execute, reason = first_chain_node.can_execute_now()
        
        if can_execute:
            scheduler._execute_task_now(task_info, olt)
```

---

### 5. **Verificación de Capacidad Celery**

**Ubicación**: `execution_coordinator/dynamic_scheduler.py` → `_check_celery_capacity()`

**Límites actuales**:
```python
CAPACITY_LIMITS = {
    'descubrimiento': 25,  # Máximo 25 Discovery PENDING
    'get': 25              # Máximo 25 GET PENDING
}
```

**Funcionamiento**:
- Antes de ejecutar, verifica cuántas tareas PENDING hay del mismo tipo
- Si alcanza el límite, NO ejecuta (mantiene en cola interna)
- Previene saturación de Celery

---

### 6. **Modo de Prueba (Simulación)**

**Ubicación**: `configuracion_avanzada/models.py` → `ConfiguracionSistema.is_modo_prueba()`

**Funcionamiento**:
- Se verifica en `snmp_jobs/tasks.py` y `snmp_get/tasks.py`
- Si `modo_prueba=True`, NO ejecuta consultas SNMP reales
- Simula duración aleatoria (0.001 a 180 segundos)
- Usa porcentajes configurables de éxito/fallo/interrupción
- Marca ejecución como `simulated: True` en `result_summary`

**Porcentajes por defecto**:
- 80% éxito
- 15% fallo
- 5% interrumpido

**Código clave**:
```python
if is_modo_prueba or is_test_job:
    # Simular tiempo de ejecución
    simulation_duration = random.uniform(0.001, 180)
    time.sleep(simulation_duration)
    
    # Determinar resultado según porcentajes
    rand = random.random()
    if rand < porcentaje_exito:
        execution.status = 'SUCCESS'
    elif rand < (porcentaje_exito + porcentaje_fallo):
        execution.status = 'FAILED'
    else:
        execution.status = 'INTERRUPTED'
```

---

## ⚠️ Problemas Identificados

### 1. **Una Tarea por OLT a la Vez**

**Problema**:
- Solo se ejecuta una tarea SNMP pesada por OLT simultáneamente
- Si una OLT tiene múltiples tareas listas, se encolan todas
- Esto limita el paralelismo y puede crear cuellos de botella

**Evidencia**:
```python
def is_olt_busy(self):
    # Verifica lock de ejecución
    lock_data = redis_client.get(self.lock_key)
    if lock_data is not None:
        return True  # OLT ocupada
```

**Impacto**:
- OLTs con muchas tareas tardan más en completar todas
- No se aprovecha el paralelismo dentro de la misma OLT

---

### 2. **Límites Globales de Capacidad**

**Problema**:
- Los límites (25 discovery, 25 GET) son **globales**, no por OLT
- Si hay 10 OLTs, cada una puede tener máximo 2-3 tareas PENDING
- No considera la capacidad real del servidor (CPU/memoria)

**Evidencia**:
```python
CAPACITY_LIMITS = {
    'descubrimiento': 25,  # Global, no por OLT
    'get': 25
}

pending_count = Execution.objects.filter(
    status='PENDING',
    snmp_job__job_type=job_type
).count()  # Cuenta TODAS las OLTs
```

**Impacto**:
- No escala bien con muchas OLTs
- Puede saturarse con pocas OLTs muy activas

---

### 3. **Nodos en Cadena Esperan Indefinidamente**

**Problema**:
- Los nodos en cadena verifican `master_node.last_success_at`
- Si el master no marca `last_success_at`, los nodos en cadena nunca se ejecutan
- Los logs muestran: `"Master 'NODO MAESTRO' no ha ejecutado exitosamente"`

**Evidencia**:
```python
def can_execute_now(self):
    if self.is_chain_node:
        if not self.master_node.last_success_at:
            return False, f"Master '{self.master_node.name}' no ha ejecutado exitosamente"
```

**Causa probable**:
- El callback `on_task_completed()` actualiza `last_success_at`
- Pero si la ejecución falla o se interrumpe, NO se actualiza
- Los nodos en cadena quedan bloqueados

---

### 4. **No Hay Control de Carga del Servidor**

**Problema**:
- No verifica CPU/memoria antes de ejecutar
- Puede sobrecargar el servidor si hay muchas tareas simultáneas
- No hay límites dinámicos basados en recursos

**Impacto**:
- Riesgo de saturación del servidor
- No se adapta a la carga real del sistema

---

## 🚀 Propuestas de Mejora (Tipo Zabbix)

### **Método Recomendado: Sistema de Pollers con Control de Carga**

Zabbix usa un sistema de "pollers" que:
- Tiene múltiples workers ejecutando tareas en paralelo
- Controla la carga del servidor antes de ejecutar
- Distribuye tareas de manera eficiente
- Permite múltiples tareas simultáneas por host (con límites)

---

### **Opción 1: Pollers con Límites por OLT (Recomendada)**

**Ventajas**:
- ✅ Permite múltiples tareas simultáneas por OLT (hasta un límite)
- ✅ Escala mejor con muchas OLTs
- ✅ Más control granular
- ✅ Implementación relativamente simple

**Implementación**:

1. **Modificar `is_olt_busy()` para permitir múltiples tareas**:
```python
def is_olt_busy(self, max_concurrent=3):
    """
    Verifica si la OLT está ocupada.
    Permite hasta max_concurrent tareas simultáneas por OLT.
    """
    from executions.models import Execution
    
    # Contar ejecuciones RUNNING o PENDING de esta OLT
    running_count = Execution.objects.filter(
        olt_id=self.olt_id,
        status__in=['RUNNING', 'PENDING']
    ).count()
    
    return running_count >= max_concurrent
```

2. **Agregar límites configurables por OLT**:
```python
# En modelo OLT o ConfiguracionSistema
max_concurrent_tasks_per_olt = 3  # Configurable
```

3. **Modificar `process_ready_tasks()` para ejecutar múltiples**:
```python
def process_ready_tasks(self, olt):
    ready_tasks = self.get_ready_tasks()
    
    if not ready_tasks:
        return 0
    
    # Calcular cuántas tareas podemos ejecutar
    max_concurrent = olt.max_concurrent_tasks or 3
    current_running = self.get_running_tasks_count(olt)
    available_slots = max_concurrent - current_running
    
    if available_slots <= 0:
        # Encolar todas
        for task in ready_tasks:
            self.enqueue_task(task)
        return 0
    
    # Ejecutar hasta available_slots tareas
    executed = 0
    for task in ready_tasks[:available_slots]:
        if self._execute_task_now(task, olt):
            executed += 1
    
    # Encolar el resto
    for task in ready_tasks[available_slots:]:
        self.enqueue_task(task)
    
    return executed
```

---

### **Opción 2: Pollers con Control de Carga del Servidor**

**Ventajas**:
- ✅ Adapta límites según carga real del servidor
- ✅ Previene saturación automáticamente
- ✅ Más robusto

**Implementación**:

1. **Agregar verificación de carga del servidor**:
```python
import psutil

def check_server_load():
    """
    Verifica la carga del servidor.
    Returns: (cpu_percent, memory_percent, can_execute)
    """
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_percent = psutil.virtual_memory().percent
    
    # Límites configurables
    MAX_CPU = 80  # No ejecutar si CPU > 80%
    MAX_MEMORY = 85  # No ejecutar si memoria > 85%
    
    can_execute = cpu_percent < MAX_CPU and memory_percent < MAX_MEMORY
    
    return cpu_percent, memory_percent, can_execute
```

2. **Integrar en `_check_celery_capacity()`**:
```python
def _check_celery_capacity(self, job_type):
    # Verificar carga del servidor
    cpu, memory, can_execute = check_server_load()
    
    if not can_execute:
        logger.warning(
            f"⚠️ Servidor sobrecargado: CPU={cpu:.1f}%, Memoria={memory:.1f}%"
        )
        return False
    
    # Verificar límites de Celery (existente)
    # ...
```

---

### **Opción 3: Híbrida (Recomendada para Producción)**

**Combina**:
- Límites por OLT (Opción 1)
- Control de carga del servidor (Opción 2)
- Límites globales mejorados

**Implementación**:

```python
def _check_execution_capacity(self, job_type, olt_id):
    """
    Verifica capacidad de ejecución considerando:
    1. Carga del servidor
    2. Límites por OLT
    3. Límites globales
    """
    # 1. Verificar carga del servidor
    cpu, memory, can_execute = check_server_load()
    if not can_execute:
        return False, "Servidor sobrecargado"
    
    # 2. Verificar límites por OLT
    olt_running = Execution.objects.filter(
        olt_id=olt_id,
        status__in=['RUNNING', 'PENDING']
    ).count()
    max_per_olt = 3  # Configurable
    if olt_running >= max_per_olt:
        return False, f"OLT tiene {olt_running} tareas ejecutándose"
    
    # 3. Verificar límites globales
    global_pending = Execution.objects.filter(
        status='PENDING',
        snmp_job__job_type=job_type
    ).count()
    global_limit = 50  # Aumentado de 25
    if global_pending >= global_limit:
        return False, f"Límite global alcanzado: {global_pending}"
    
    return True, "OK"
```

---

## 🔧 Corrección del Problema de Nodos en Cadena

### **Problema**: Nodos en cadena esperan indefinidamente

**Solución**: Mejorar actualización de `last_success_at`

1. **Asegurar actualización en todos los casos**:
```python
# En callbacks.py
def update_workflow_node_on_completion(execution_id, status):
    execution = Execution.objects.get(id=execution_id)
    
    if execution.workflow_node:
        now = timezone.now()
        
        # SIEMPRE actualizar last_run_at
        execution.workflow_node.last_run_at = now
        
        # Actualizar last_success_at solo si fue exitosa
        if status == 'SUCCESS':
            execution.workflow_node.last_success_at = now
        elif status == 'FAILED':
            execution.workflow_node.last_failure_at = now
        
        execution.workflow_node.save(
            update_fields=['last_success_at', 'last_failure_at', 'last_run_at']
        )
```

2. **Verificar que se llame en todos los casos**:
- ✅ En `on_task_completed()` (ya existe)
- ❌ Falta en `on_task_failed()` (agregar)
- ❌ Falta en modo simulación (agregar)

---

## 📋 Plan de Implementación Recomendado

### **Fase 1: Correcciones Críticas** (Prioridad ALTA)
1. ✅ Corregir actualización de `last_success_at` en nodos en cadena
2. ✅ Agregar verificación en modo simulación
3. ✅ Mejorar logs para debugging

### **Fase 2: Mejoras de Capacidad** (Prioridad MEDIA)
1. ✅ Implementar límites por OLT (Opción 1)
2. ✅ Aumentar límites globales (25 → 50)
3. ✅ Agregar configuración en admin

### **Fase 3: Control de Carga** (Prioridad BAJA)
1. ✅ Implementar verificación de carga del servidor
2. ✅ Agregar métricas de monitoreo
3. ✅ Ajustar límites dinámicamente

---

## 🎯 Método Final Recomendado

**Para implementar la mejora, recomiendo usar la Opción 3 (Híbrida)**:

1. **Permite múltiples tareas simultáneas por OLT** (hasta 3 por defecto)
2. **Controla la carga del servidor** antes de ejecutar
3. **Mantiene límites globales** para prevenir saturación
4. **Es configurable** desde Django Admin
5. **Escala bien** con muchas OLTs

**Archivos a modificar**:
- `execution_coordinator/dynamic_scheduler.py` → `is_olt_busy()`, `process_ready_tasks()`, `_check_celery_capacity()`
- `execution_coordinator/callbacks.py` → Mejorar actualización de `last_success_at`
- `hosts/models.py` → Agregar campo `max_concurrent_tasks` (opcional)
- `configuracion_avanzada/models.py` → Agregar configuración de límites

---

## 📊 Comparación: Actual vs Propuesto

| Aspecto | Actual | Propuesto (Híbrida) |
|---------|--------|---------------------|
| Tareas simultáneas por OLT | 1 | 3 (configurable) |
| Control de carga servidor | ❌ No | ✅ Sí |
| Límites globales | 25/25 | 50/50 (configurable) |
| Escalabilidad | Limitada | Mejorada |
| Configuración | Hardcoded | Django Admin |

---

## ✅ Conclusión

El sistema actual funciona correctamente pero tiene limitaciones de escalabilidad. La implementación de la **Opción 3 (Híbrida)** permitirá:

- ✅ Múltiples ejecuciones simultáneas sin sobrecargar el servidor
- ✅ Mejor aprovechamiento de recursos
- ✅ Escalabilidad tipo Zabbix
- ✅ Control granular y configurable

**¿Procedo con la implementación de la Opción 3?**

