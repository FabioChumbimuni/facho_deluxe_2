# Lógica del Estado del Poller

## 📊 Flujo de Ejecución

### 1. Ejecución de Nodo MASTER

```
1. Scheduler encuentra nodo master listo
   ↓
2. PollerManager.assign_node(composite_node)
   - composite_node contiene: master + chain_nodes
   ↓
3. Poller.execute_composite_node(composite_node)
   - Poller se marca como BUSY
   - Guarda: current_composite_node = composite_node
   ↓
4. composite_node.execute() ejecuta SOLO el master:
   - _execute_node(self.master) crea Execution del MASTER
   - Retorna la Execution del master
   ↓
5. Poller guarda:
   - current_execution_id = Execution.id (del MASTER)
   - Status = BUSY (se mantiene mientras Execution esté PENDING/RUNNING)
   ↓
6. Execution se envía a Celery (PENDING → RUNNING)
   ↓
7. Cuando master termina → callback on_task_completed()
   ↓
8. Callback marca poller como FREE
   - current_execution_id = None
   - current_composite_node = None
   - status = FREE
```

### 2. Ejecución de Nodo de CADENA

```
1. Callback detecta que master terminó (SUCCESS/FAILED)
   ↓
2. Callback busca nodos de cadena del master
   ↓
3. Callback crea NUEVO CompositeNode para primer nodo de cadena
   - CompositeNode(master_node=chain_node, chain_nodes=[], ...)
   ↓
4. Callback asigna a OTRO poller (o encola):
   - poller_manager.assign_node(composite_node)
   - O poller_manager.queue.put(composite_node)
   ↓
5. NUEVO poller ejecuta el nodo de cadena:
   - Poller.execute_composite_node(composite_node)
   - Guarda current_execution_id = Execution.id (del nodo de cadena)
   ↓
6. Cuando nodo de cadena termina → callback ejecuta siguiente nodo de cadena
   ↓
7. Proceso se repite hasta que no haya más nodos de cadena
```

## ⚠️ Problema Identificado

### ¿Por qué se pierde el estado?

1. **Solo se trackea el MASTER:**
   - `current_execution_id` solo guarda la Execution del MASTER
   - Los nodos de cadena se ejecutan en OTROS pollers
   - No hay relación entre el poller original y los nodos de cadena

2. **El poller se marca como FREE cuando el master termina:**
   - El callback marca el poller como FREE inmediatamente
   - Pero los nodos de cadena aún pueden estar ejecutándose
   - El poller original ya no tiene tracking de las cadenas

3. **Los nodos de cadena se ejecutan en otros pollers:**
   - Cada nodo de cadena puede ejecutarse en un poller diferente
   - No hay tracking centralizado de qué poller ejecutó qué nodo de cadena
   - Solo se ve el estado del poller que ejecuta el nodo actual

### ¿Solo aparece cuando ejecuta un nodo master?

**Sí, pero con matices:**

- ✅ **Nodo MASTER:** El poller muestra estado BUSY mientras el master está PENDING/RUNNING
- ⚠️ **Nodo de CADENA:** El poller muestra estado BUSY, pero:
  - Es un poller DIFERENTE al que ejecutó el master
  - No hay relación visible entre master y cadena en el dashboard
  - El poller original ya está FREE cuando la cadena se ejecuta

## 🔍 Cómo Funciona get_stats()

```python
def get_stats(self) -> dict:
    # 1. Obtiene estado básico del poller
    base_status = self.status  # FREE o BUSY
    execution_id = self.current_execution_id
    
    # 2. Si hay execution_id, verifica en BD
    if execution_id:
        execution = Execution.objects.get(id=execution_id)
        if execution.status in ['PENDING', 'RUNNING']:
            actual_status = 'BUSY'  # Poller está ocupado
        else:
            actual_status = 'FREE'  # Execution terminó
    
    # 3. Retorna estado verificado
    return {
        'status': actual_status,
        'current_node_id': ...,
        'current_node_name': ...,
    }
```

**Limitaciones:**
- Solo verifica la Execution del `current_execution_id`
- Si el poller ejecutó un master y ya terminó, no muestra las cadenas
- Si el poller ejecuta una cadena, solo muestra esa cadena, no el master

## 📈 Estado Actual vs Zabbix

**"Zabbix" se refiere al sistema de pollers Zabbix (no al servidor Zabbix):**

1. **Sistema de Pollers Zabbix:**
   - 10 pollers que ejecutan nodos compuestos
   - Cada poller puede ejecutar un nodo a la vez
   - Los pollers se reutilizan para diferentes nodos

2. **Estado del Poller:**
   - **FREE:** Poller disponible, sin ejecuciones activas
   - **BUSY:** Poller ejecutando un nodo (master o cadena)
   - El estado se verifica en tiempo real consultando la BD

3. **Tracking:**
   - Solo se trackea la Execution actual del poller
   - No hay tracking histórico de qué poller ejecutó qué
   - No hay relación visible entre master y cadenas

## ✅ Soluciones Posibles

### Opción 1: Mejorar el tracking en Execution
- Agregar campo `poller_id` a Execution
- Guardar qué poller ejecutó cada Execution
- Permitir rastrear master y cadenas

### Opción 2: Mantener relación master-cadena
- Guardar en Execution el `master_execution_id` para cadenas
- Mostrar en dashboard la relación master → cadena
- Agrupar por OLT y mostrar orden de ejecución

### Opción 3: Mejorar get_stats()
- Buscar todas las Executions activas relacionadas
- Si es master, buscar sus cadenas activas
- Si es cadena, buscar su master y otras cadenas

## 📝 Resumen

**Pregunta:** ¿Por qué se pierde el estado del poller?

**Respuesta:**
1. El poller solo guarda `current_execution_id` del nodo que está ejecutando
2. Cuando el master termina, el poller se marca como FREE
3. Los nodos de cadena se ejecutan en otros pollers
4. No hay tracking de la relación master → cadena
5. Solo se ve el estado del nodo actual, no el contexto completo

**Pregunta:** ¿Solo aparece cuando ejecuta un nodo master?

**Respuesta:**
- El poller muestra estado BUSY cuando ejecuta:
  - ✅ Nodo MASTER (mientras está PENDING/RUNNING)
  - ✅ Nodo de CADENA (mientras está PENDING/RUNNING)
- Pero:
  - El master y las cadenas se ejecutan en pollers diferentes
  - No hay relación visible entre ellos
  - El poller original se marca como FREE cuando el master termina

