# 🟦 MODELO DE POLLERS ZABBIX - Diseño Completo

## 📚 REFERENCIAS ZABBIX

### Repositorio Oficial
- **GitHub**: https://github.com/zabbix/zabbix
- **Archivos clave**:
  - `src/zabbix_server/poller/poller.c` - Implementación del poller
  - `src/zabbix_server/poller/poller_manager.c` - Gestión de pollers
  - `src/zabbix_server/poller/queue.c` - Cola de tareas
  - `src/zabbix_server/scheduler/scheduler.c` - Scheduler principal

### Conceptos Clave de Zabbix
- **StartPollers**: Número de procesos poller paralelos
- **Busy Time**: Porcentaje de tiempo que un poller está ocupado
- **Queue**: Cola FIFO de items (nodos) listos para ejecutar
- **Delay**: Tiempo que un item está retrasado respecto a su intervalo
- **Nextcheck**: Timestamp de próxima ejecución programada
- **Lastcheck**: Timestamp de última ejecución realizada

---

## 🏗️ ARQUITECTURA DEL SISTEMA DE POLLERS

```
┌─────────────────────────────────────────────────────────────┐
│                    SCHEDULER PRINCIPAL                       │
│                  (Loop cada 1 segundo)                       │
│                                                               │
│  1. Identifica nodos listos (nextcheck <= now)              │
│  2. Calcula delay (now - nextcheck)                           │
│  3. Envía a cola si hay pollers libres                      │
│  4. Marca como "delayed" si delay > interval                │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    COLA DE TAREAS (FIFO)                    │
│                                                               │
│  - Nodos listos ordenados por prioridad                     │
│  - Nodos retrasados tienen mayor prioridad                  │
│  - No se duplican nodos en cola                             │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  POLLER MANAGER                              │
│                  (StartPollers = N)                          │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Poller 1 │  │ Poller 2 │  │ Poller 3 │  │ Poller N │   │
│  │          │  │          │  │          │  │          │   │
│  │ Busy: 45%│  │ Busy: 78%│  │ Busy: 12%│  │ Busy: 90%│   │
│  │ Status:  │  │ Status:  │  │ Status:  │  │ Status:  │   │
│  │ FREE     │  │ BUSY     │  │ FREE     │  │ BUSY     │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                               │
│  Métricas:                                                    │
│  - Total Busy: 56%                                            │
│  - Cola: 23 nodos                                             │
│  - Estado: SATURADO (>75% busy)                              │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    EJECUCIÓN DE NODO                         │
│                                                               │
│  1. ✅ Verificar si OLT tiene nodo ejecutándose             │
│     SI OLT ocupada → Encolar                                │
│     SI OLT libre → Continuar                                │
│  2. Poller toma nodo de cola                                 │
│  3. Marca poller como BUSY                                  │
│  4. Ejecuta función del nodo                                │
│  5. Registra execution_time                                 │
│  6. Actualiza lastcheck = now                               │
│  7. Calcula nextcheck = now + interval                      │
│  8. Marca poller como FREE                                   │
│  9. ✅ Procesar siguiente nodo de esa OLT en cola          │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 COMPONENTES DETALLADOS

### 1. SCHEDULER DE ZABBIX (Adaptado)

#### Pseudocódigo
```
FUNCIÓN scheduler_loop():
    MIENTRAS scheduler_activo:
        ahora = obtener_tiempo_actual()
        nodos_listos = []
        
        PARA CADA nodo EN nodos_activos:
            SI nodo.enabled Y nodo.nextcheck <= ahora:
                delay = ahora - nodo.nextcheck
                
                SI delay > nodo.interval:
                    nodo.delayed = True
                    nodo.delay_time = delay
                
                AGREGAR nodo A nodos_listos
        
        ORDENAR nodos_listos POR:
            1. delayed (True primero)
            2. delay_time (mayor primero)
            3. prioridad (mayor primero)
        
        PARA CADA nodo EN nodos_listos:
            SI hay_poller_libre():
                asignar_nodo_a_poller(nodo)
            SINO:
                agregar_a_cola(nodo)
        
        ESPERAR 1 segundo
```

#### Código Python
```python
import time
from datetime import datetime, timedelta
from queue import Queue
from threading import Thread, Lock
from typing import List, Optional

class ZabbixScheduler:
    def __init__(self, poller_manager):
        self.poller_manager = poller_manager
        self.queue = Queue()
        self.running = False
        self.lock = Lock()
        
    def scheduler_loop(self):
        """Loop principal del scheduler (cada 1 segundo)"""
        while self.running:
            now = datetime.now()
            ready_nodes = []
            
            # Identificar nodos listos
            with self.lock:
                for node in self.get_active_nodes():
                    if node.enabled and node.nextcheck <= now:
                        delay = (now - node.nextcheck).total_seconds()
                        
                        # Marcar como delayed si supera el intervalo
                        if delay > node.interval_seconds:
                            node.delayed = True
                            node.delay_time = delay
                        else:
                            node.delayed = False
                            node.delay_time = 0
                        
                        ready_nodes.append(node)
            
            # Ordenar por prioridad
            ready_nodes.sort(key=lambda n: (
                not n.delayed,  # Delayed primero
                -n.delay_time,  # Mayor delay primero
                -n.priority     # Mayor prioridad primero
            ))
            
            # Asignar a pollers o encolar
            for node in ready_nodes:
                if self.poller_manager.has_free_poller():
                    self.poller_manager.assign_node(node)
                else:
                    self.queue.put(node)
            
            time.sleep(1)
    
    def get_active_nodes(self) -> List['Node']:
        """Obtener nodos activos desde BD"""
        # Implementar según tu modelo
        pass
```

---

### 2. POLLER MANAGER

#### Pseudocódigo
```
CLASE PollerManager:
    ATRIBUTOS:
        pollers: Lista[Poller]
        start_pollers: int
        total_tasks: int
        completed_tasks: int
        delayed_tasks: int
    
    FUNCIÓN __init__(start_pollers):
        PARA i EN rango(start_pollers):
            poller = crear_poller(i)
            pollers.append(poller)
    
    FUNCIÓN has_free_poller():
        PARA CADA poller EN pollers:
            SI poller.status == FREE:
                RETORNAR True
        RETORNAR False
    
    FUNCIÓN assign_node(nodo):
        # ✅ PROTECCIÓN OLT: Verificar si OLT ya tiene nodo ejecutándose
        SI is_olt_busy(nodo.workflow.olt_id):
            agregar_a_cola(nodo)  # OLT ocupada, encolar
            RETORNAR
        
        # OLT libre, continuar normalmente
        poller_libre = obtener_poller_libre()
        SI poller_libre:
            poller_libre.execute_node(nodo)
        SINO:
            agregar_a_cola(nodo)
    
    FUNCIÓN is_olt_busy(olt_id):
        # Verificar en ejecuciones activas
        RETORNAR existe_ejecucion(olt_id, status=['RUNNING', 'PENDING'])
    
    FUNCIÓN get_busy_percentage():
        total_busy_time = 0
        PARA CADA poller EN pollers:
            total_busy_time += poller.busy_time
        RETORNAR (total_busy_time / total_time) * 100
    
    FUNCIÓN is_saturated():
        SI get_busy_percentage() > 75:
            RETORNAR True
        SI queue.size() > start_pollers * 2:
            RETORNAR True
        RETORNAR False
```

#### Código Python
```python
from threading import Thread, Lock
from datetime import datetime, timedelta
from typing import List, Optional

class Poller:
    def __init__(self, poller_id: int):
        self.poller_id = poller_id
        self.status = 'FREE'  # FREE, BUSY
        self.current_node = None
        self.busy_time = 0.0
        self.total_time = 0.0
        self.tasks_completed = 0
        self.tasks_delayed = 0
        self.lock = Lock()
        self.start_time = datetime.now()
    
    def execute_node(self, node: 'Node'):
        """
        Ejecutar un nodo
        
        ✅ NO CAMBIA: El comportamiento es exactamente igual que antes
        Solo se agrega la verificación de OLT ocupada en PollerManager.assign_node()
        """
        with self.lock:
            self.status = 'BUSY'
            self.current_node = node
            task_start = datetime.now()
        
        try:
            # Ejecutar función del nodo
            result = node.execute()
            
            # Calcular tiempos
            task_end = datetime.now()
            execution_time = (task_end - task_start).total_seconds()
            
            # Actualizar métricas
            with self.lock:
                self.busy_time += execution_time
                self.total_time = (task_end - self.start_time).total_seconds()
                self.tasks_completed += 1
                
                # Actualizar nodo
                node.lastcheck = task_end
                node.nextcheck = task_end + timedelta(seconds=node.interval_seconds)
                node.execution_time = execution_time
                node.delayed = False
                node.delay_time = 0
                
                self.status = 'FREE'
                self.current_node = None
                
        except Exception as e:
            with self.lock:
                self.status = 'FREE'
                self.current_node = None
                node.error_count += 1
            raise
    
    def get_busy_percentage(self) -> float:
        """Calcular porcentaje de tiempo ocupado"""
        with self.lock:
            if self.total_time == 0:
                return 0.0
            return (self.busy_time / self.total_time) * 100

class PollerManager:
    def __init__(self, start_pollers: int = 5):
        self.start_pollers = start_pollers
        self.pollers: List[Poller] = []
        self.queue = Queue()
        self.lock = Lock()
        
        # Crear pollers
        for i in range(start_pollers):
            poller = Poller(i)
            self.pollers.append(poller)
    
    def has_free_poller(self) -> bool:
        """Verificar si hay poller libre"""
        with self.lock:
            return any(p.status == 'FREE' for p in self.pollers)
    
    def get_free_poller(self) -> Optional[Poller]:
        """Obtener un poller libre"""
        with self.lock:
            for poller in self.pollers:
                if poller.status == 'FREE':
                    return poller
            return None
    
    def is_olt_busy(self, olt_id: int) -> bool:
        """
        ✅ PROTECCIÓN OLT: Verificar si OLT ya tiene un nodo ejecutándose
        Solo 1 nodo a la vez por OLT para evitar saturación
        """
        from executions.models import Execution
        running = Execution.objects.filter(
            olt_id=olt_id,
            status__in=['RUNNING', 'PENDING']
        ).exists()
        return running
    
    def assign_node(self, node: 'Node'):
        """
        Asignar nodo a poller libre, respetando límite de 1 nodo por OLT
        """
        # ✅ PROTECCIÓN OLT: Verificar si OLT ya tiene un nodo ejecutándose
        olt_id = node.workflow.olt_id
        if self.is_olt_busy(olt_id):
            # OLT ocupada, encolar nodo (NO se ejecuta simultáneamente)
            self.queue.put(node)
            return
        
        # OLT libre, intentar asignar a poller libre
        poller = self.get_free_poller()
        if poller:
            # Ejecutar nodo y cuando termine, verificar cola de esa OLT
            thread = Thread(target=self._execute_and_process_queue, args=(poller, node, olt_id))
            thread.start()
        else:
            # No hay poller libre, encolar
            self.queue.put(node)
    
    def _execute_and_process_queue(self, poller: Poller, node: 'Node', olt_id: int):
        """
        Ejecutar nodo y después procesar siguiente nodo de esa OLT en cola
        """
        try:
            poller.execute_node(node)
        finally:
            # Cuando termina, verificar si hay más nodos de esta OLT en cola
            self._process_queue_for_olt(olt_id)
    
    def _process_queue_for_olt(self, olt_id: int):
        """
        Procesar siguiente nodo de una OLT específica desde la cola
        """
        # Buscar siguiente nodo de esta OLT en cola
        next_node = None
        temp_queue = Queue()
        
        # Revisar cola y encontrar nodo de esta OLT
        while not self.queue.empty():
            try:
                node = self.queue.get_nowait()
                if node.workflow.olt_id == olt_id and next_node is None:
                    next_node = node
                else:
                    temp_queue.put(node)
            except:
                break
        
        # Devolver nodos que no son de esta OLT a la cola
        while not temp_queue.empty():
            try:
                self.queue.put(temp_queue.get_nowait())
            except:
                break
        
        # Si hay siguiente nodo de esta OLT y OLT está libre, ejecutarlo
        if next_node and not self.is_olt_busy(olt_id):
            poller = self.get_free_poller()
            if poller:
                thread = Thread(target=self._execute_and_process_queue, args=(poller, next_node, olt_id))
                thread.start()
            else:
                # No hay poller libre, devolver a cola
                self.queue.put(next_node)
    
    def get_busy_percentage(self) -> float:
        """Calcular porcentaje promedio de busy"""
        with self.lock:
            if not self.pollers:
                return 0.0
            total_busy = sum(p.get_busy_percentage() for p in self.pollers)
            return total_busy / len(self.pollers)
    
    def is_saturated(self) -> bool:
        """Detectar saturación"""
        busy_pct = self.get_busy_percentage()
        queue_size = self.queue.qsize()
        
        if busy_pct > 75:
            return True
        if queue_size > self.start_pollers * 2:
            return True
        return False
    
    def get_stats(self) -> dict:
        """Obtener estadísticas"""
        with self.lock:
            return {
                'total_pollers': len(self.pollers),
                'free_pollers': sum(1 for p in self.pollers if p.status == 'FREE'),
                'busy_pollers': sum(1 for p in self.pollers if p.status == 'BUSY'),
                'busy_percentage': self.get_busy_percentage(),
                'queue_size': self.queue.qsize(),
                'is_saturated': self.is_saturated(),
                'total_tasks_completed': sum(p.tasks_completed for p in self.pollers),
                'total_tasks_delayed': sum(p.tasks_delayed for p in self.pollers),
            }
```

---

### 3. COLA DE TAREAS (QUEUE)

#### Características
- **FIFO**: First In, First Out
- **Priorización**: Nodos delayed primero
- **Sin duplicados**: Un nodo no puede estar dos veces en cola
- **Overload**: Si cola > umbral → marcar como overload

#### Implementación
```python
from queue import Queue, PriorityQueue
from typing import Set

class NodeQueue:
    def __init__(self, max_size: int = 1000):
        self.queue = PriorityQueue(maxsize=max_size)
        self.node_ids_in_queue: Set[int] = set()
        self.lock = Lock()
        self.overload_threshold = max_size * 0.8
    
    def put(self, node: 'Node'):
        """Agregar nodo a cola con prioridad"""
        with self.lock:
            if node.id in self.node_ids_in_queue:
                return  # Ya está en cola
            
            # Prioridad: (delayed, -delay_time, -priority)
            priority = (
                not node.delayed,  # Delayed primero (False < True)
                -node.delay_time,  # Mayor delay primero
                -node.priority     # Mayor prioridad primero
            )
            
            self.queue.put((priority, node))
            self.node_ids_in_queue.add(node.id)
    
    def get(self) -> Optional['Node']:
        """Obtener siguiente nodo de cola"""
        try:
            priority, node = self.queue.get_nowait()
            with self.lock:
                self.node_ids_in_queue.discard(node.id)
            return node
        except:
            return None
    
    def is_overload(self) -> bool:
        """Verificar si cola está sobrecargada"""
        return self.queue.qsize() > self.overload_threshold
```

---

### 4. API REST

#### Endpoints
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict

app = FastAPI()

class PollerStats(BaseModel):
    poller_id: int
    status: str
    busy_percentage: float
    tasks_completed: int
    current_node_id: Optional[int]

class QueueStats(BaseModel):
    size: int
    is_overload: bool
    next_nodes: List[Dict]

class GlobalStats(BaseModel):
    total_pollers: int
    free_pollers: int
    busy_pollers: int
    busy_percentage: float
    queue_size: int
    is_saturated: bool
    total_tasks_completed: int
    total_tasks_delayed: int

@app.get("/pollers", response_model=List[PollerStats])
def get_pollers():
    """Obtener estado de todos los pollers"""
    stats = []
    for poller in poller_manager.pollers:
        stats.append(PollerStats(
            poller_id=poller.poller_id,
            status=poller.status,
            busy_percentage=poller.get_busy_percentage(),
            tasks_completed=poller.tasks_completed,
            current_node_id=poller.current_node.id if poller.current_node else None
        ))
    return stats

@app.get("/queue", response_model=QueueStats)
def get_queue():
    """Obtener estado de la cola"""
    queue_size = scheduler.queue.qsize()
    next_nodes = []
    # Obtener primeros 10 nodos sin removerlos
    # (implementar según tu cola)
    return QueueStats(
        size=queue_size,
        is_overload=scheduler.queue.is_overload(),
        next_nodes=next_nodes
    )

@app.get("/stats", response_model=GlobalStats)
def get_stats():
    """Obtener estadísticas globales"""
    stats = poller_manager.get_stats()
    return GlobalStats(**stats)

@app.post("/node/{node_id}/run")
def run_node_manually(node_id: int):
    """Ejecutar nodo manualmente"""
    node = get_node_by_id(node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    
    if poller_manager.has_free_poller():
        poller_manager.assign_node(node)
        return {"status": "assigned", "node_id": node_id}
    else:
        scheduler.queue.put(node)
        return {"status": "queued", "node_id": node_id}
```

---

## 🔄 FLUJO COMPLETO

```
1. SCHEDULER (cada 1 segundo):
   ├─ Identifica nodos con nextcheck <= now
   ├─ Calcula delay
   ├─ Marca como delayed si delay > interval
   └─ Envía a cola o asigna a poller

2. POLLER MANAGER:
   ├─ Verifica pollers libres
   ├─ Asigna nodos de cola a pollers libres
   └─ Monitorea saturación

3. POLLER:
   ├─ Toma nodo de cola
   ├─ Ejecuta función del nodo
   ├─ Actualiza lastcheck, nextcheck
   └─ Libera poller

4. COLA:
   ├─ Almacena nodos pendientes
   ├─ Prioriza nodos delayed
   └─ Detecta overload
```

---

## ⚠️ PROTECCIÓN CONTRA SATURACIÓN DE OLT

### Problema Identificado

**Zabbix NO limita automáticamente consultas concurrentes por host/OLT**:
- Múltiples pollers pueden ejecutar items/nodos de la misma OLT simultáneamente
- Depende de configuración manual de intervalos para evitar saturación
- Casos reportados: OLTs pueden saturarse con múltiples consultas SNMP simultáneas

### ✅ Solución Simple: Solo Agregar Verificación

**NO es necesario cambiar todo el sistema**. Solo se agrega una verificación en `PollerManager.assign_node()`:

```python
def assign_node(self, node: 'Node'):
    # ✅ AGREGAR: Verificar si OLT ya tiene un nodo ejecutándose
    olt_id = node.workflow.olt_id
    if self.is_olt_busy(olt_id):
        # OLT ocupada, encolar (NO ejecutar simultáneamente)
        self.queue.put(node)
        return
    
    # Resto del código NO CAMBIA
    poller = self.get_free_poller()
    if poller:
        thread = Thread(target=poller.execute_node, args=(node,))
        thread.start()
    else:
        self.queue.put(node)
```

**Eso es todo**. El resto del sistema funciona exactamente igual:
- ✅ Scheduler funciona igual
- ✅ Pollers funcionan igual
- ✅ Cola funciona igual
- ✅ Cálculo de nextcheck igual
- ✅ Solo se agrega: "verificar OLT ocupada antes de asignar"

### Comparativa

| Aspecto | Zabbix Original | Pollers Zabbix + Protección OLT |
|---------|----------------|--------------------------------|
| **Consultas simultáneas por OLT** | Ilimitadas | Máximo 1 |
| **Protección automática** | ❌ No | ✅ Sí |
| **Complejidad** | Baja | Baja (solo 1 verificación) |
| **Riesgo de saturación** | Alto | Bajo |
| **Cambios al sistema** | - | Mínimos (solo 1 función) |

---

## 📊 MÉTRICAS Y MONITOREO

### Métricas por Poller
- `busy_percentage`: % tiempo ocupado
- `tasks_completed`: Tareas completadas
- `tasks_delayed`: Tareas retrasadas
- `current_node_id`: Nodo en ejecución

### Métricas Globales
- `total_pollers`: Total de pollers
- `free_pollers`: Pollers libres
- `busy_pollers`: Pollers ocupados
- `busy_percentage`: Promedio de busy
- `queue_size`: Tamaño de cola
- `is_saturated`: Estado de saturación
- `total_tasks_completed`: Total completadas
- `total_tasks_delayed`: Total retrasadas

### Detección de Saturación
- **Busy > 75%**: Sistema saturado
- **Cola > (StartPollers * 2)**: Sistema colapsado
- **Overload**: Cola > 80% capacidad máxima

---

## 🎯 DIFERENCIAS CON SISTEMA ACTUAL

| Aspecto | Sistema Actual | Modelo Pollers Zabbix |
|---------|---------------|----------------------|
| **Arquitectura** | Coordinador central | Pollers paralelos |
| **Asignación** | Por OLT (1 a la vez) | Por poller (N simultáneos) |
| **Cola** | Redis (persistente) | Memoria (FIFO) |
| **Saturación** | Monitoreo complejo | Simple (busy > 75%) |
| **Escalabilidad** | Horizontal (más OLTs) | Vertical (más pollers) |
| **Complejidad** | Alta | Media |

