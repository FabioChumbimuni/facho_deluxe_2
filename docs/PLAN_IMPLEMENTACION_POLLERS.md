# 📋 PLAN DE IMPLEMENTACIÓN: Reemplazo de Coordinador por Pollers Zabbix

## 🎯 OBJETIVOS

1. Reemplazar el coordinador actual por modelo de Pollers Zabbix
2. Mantener protección OLT (1 nodo a la vez por OLT)
3. Tratar nodos encadenados como UN SOLO NODO compuesto
4. Separar pollers internos (get_poller) de pollers del sistema
5. Crear API REST para consultar información de pollers

---

## 📐 ARQUITECTURA

### Componentes Principales

```
┌─────────────────────────────────────────────────────────────┐
│              ZABBIX SCHEDULER (Nuevo)                       │
│              (Reemplaza coordinator_loop_task)              │
│                                                               │
│  - Loop cada 1 segundo                                        │
│  - Identifica nodos listos (nextcheck <= now)                │
│  - Agrupa nodos master + encadenados = 1 nodo compuesto     │
│  - Calcula delay y marca como delayed                       │
│  - Envía a PollerManager                                     │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              POLLER MANAGER                                  │
│                                                               │
│  - Gestiona N pollers paralelos                              │
│  - Verifica protección OLT (1 nodo por OLT)                │
│  - Asigna nodos a pollers libres                             │
│  - Maneja cola de nodos pendientes                           │
│  - Monitorea saturación (busy > 75%)                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              POLLERS (N instancias)                          │
│                                                               │
│  - Ejecutan nodos (master + encadenados como unidad)        │
│  - Actualizan lastcheck, nextcheck                           │
│  - Calculan métricas (busy %, tareas completadas)           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              POLLERS INTERNOS (Separados)                    │
│              (get_poller_task - NO tocar)                    │
│                                                               │
│  - Procesan lotes de ONUs en paralelo                        │
│  - Control de concurrencia por OLT                           │
│  - Subdivisión progresiva                                    │
│  - NO se combinan con pollers del sistema                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔑 CONCEPTOS CLAVE

### 1. Nodo = Item (Zabbix)
- Un nodo individual del workflow
- Tiene `nextcheck`, `lastcheck`, `interval_seconds`

### 2. Workflow = Host (Zabbix)
- Un workflow completo de una OLT
- Contiene múltiples nodos

### 3. Nodo Compuesto (Master + Encadenados)
- **Un nodo master con sus encadenados = 1 NODO COMPUESTO**
- Aunque sean 7 nodos, si están encadenados cuentan como 1
- La demora de ejecución incluye todos los encadenados
- Solo el master tiene `nextcheck`, los encadenados no

### 4. Pollers Internos (Separados)
- `get_poller_task` en `snmp_get/tasks.py`
- Procesan lotes de ONUs en paralelo
- **NO se combinan** con pollers del sistema Zabbix
- Funcionamiento interno independiente

---

## 📝 PASOS DE IMPLEMENTACIÓN

### PASO 1: Crear Modelos de Datos

**Archivo**: `zabbix_pollers/models.py`

```python
from django.db import models
from django.utils import timezone

class Poller(models.Model):
    """Representa un poller individual del sistema"""
    poller_id = models.IntegerField(unique=True)
    status = models.CharField(max_length=10, default='FREE')  # FREE, BUSY
    current_node_id = models.IntegerField(null=True, blank=True)
    busy_time = models.FloatField(default=0.0)
    total_time = models.FloatField(default=0.0)
    tasks_completed = models.IntegerField(default=0)
    tasks_delayed = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class PollerStats(models.Model):
    """Estadísticas globales del sistema de pollers"""
    total_pollers = models.IntegerField(default=0)
    free_pollers = models.IntegerField(default=0)
    busy_pollers = models.IntegerField(default=0)
    busy_percentage = models.FloatField(default=0.0)
    queue_size = models.IntegerField(default=0)
    is_saturated = models.BooleanField(default=False)
    total_tasks_completed = models.IntegerField(default=0)
    total_tasks_delayed = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now=True)
```

### PASO 2: Crear Scheduler Zabbix

**Archivo**: `zabbix_pollers/scheduler.py`

```python
class ZabbixScheduler:
    """
    Scheduler estilo Zabbix que reemplaza al coordinador
    """
    def __init__(self, poller_manager):
        self.poller_manager = poller_manager
        self.running = False
    
    def scheduler_loop(self):
        """Loop principal cada 1 segundo"""
        while self.running:
            now = timezone.now()
            ready_nodes = self._get_ready_nodes(now)
            
            # Agrupar nodos master + encadenados como nodos compuestos
            composite_nodes = self._group_chain_nodes(ready_nodes)
            
            # Ordenar por prioridad
            composite_nodes.sort(key=lambda n: (
                not n.delayed,
                -n.delay_time,
                -n.priority
            ))
            
            # Asignar a pollers o encolar
            for composite_node in composite_nodes:
                if self.poller_manager.has_free_poller():
                    self.poller_manager.assign_node(composite_node)
                else:
                    self.poller_manager.queue.put(composite_node)
            
            time.sleep(1)
    
    def _get_ready_nodes(self, now):
        """Identificar nodos listos (nextcheck <= now)"""
        # Solo nodos master (los encadenados no tienen nextcheck)
        from snmp_jobs.models import WorkflowNode
        return WorkflowNode.objects.filter(
            enabled=True,
            is_chain_node=False,  # Solo masters
            next_run_at__lte=now,
            next_run_at__isnull=False
        ).select_related('workflow__olt')
    
    def _group_chain_nodes(self, nodes):
        """
        Agrupa nodos master + encadenados como nodos compuestos
        Un nodo master con 6 encadenados = 1 nodo compuesto
        """
        composite_nodes = []
        processed_master_ids = set()
        
        for node in nodes:
            if node.id in processed_master_ids:
                continue
            
            # Obtener nodos encadenados
            chain_nodes = node.chain_nodes.filter(enabled=True).order_by('priority', 'id')
            
            # Crear nodo compuesto
            composite = CompositeNode(
                master=node,
                chain_nodes=list(chain_nodes),
                workflow=node.workflow,
                olt=node.workflow.olt
            )
            
            composite_nodes.append(composite)
            processed_master_ids.add(node.id)
            
            # Marcar encadenados como procesados
            for chain_node in chain_nodes:
                processed_master_ids.add(chain_node.id)
        
        return composite_nodes
```

### PASO 3: Crear CompositeNode

**Archivo**: `zabbix_pollers/composite_node.py`

```python
class CompositeNode:
    """
    Representa un nodo compuesto: master + encadenados
    Cuenta como UN SOLO NODO aunque tenga múltiples encadenados
    """
    def __init__(self, master, chain_nodes, workflow, olt):
        self.master = master
        self.chain_nodes = chain_nodes
        self.workflow = workflow
        self.olt = olt
        
        # Propiedades del master (usadas para scheduling)
        self.id = master.id
        self.name = master.name
        self.nextcheck = master.next_run_at
        self.lastcheck = master.last_run_at
        self.interval_seconds = master.interval_seconds
        self.priority = master.priority
        self.enabled = master.enabled
        
        # Estado
        self.delayed = False
        self.delay_time = 0.0
        self.execution_time = 0.0
    
    def execute(self):
        """
        Ejecuta el nodo compuesto: master primero, luego encadenados secuencialmente
        La demora total incluye todos los encadenados
        """
        start_time = timezone.now()
        
        # 1. Ejecutar master
        master_result = self.master.execute()
        
        # 2. Ejecutar encadenados secuencialmente
        for chain_node in self.chain_nodes:
            chain_result = chain_node.execute()
        
        end_time = timezone.now()
        self.execution_time = (end_time - start_time).total_seconds()
        
        # Actualizar nextcheck del master
        self.master.last_run_at = end_time
        self.master.next_run_at = end_time + timedelta(seconds=self.interval_seconds)
        self.master.save(update_fields=['last_run_at', 'next_run_at'])
        
        return master_result
```

### PASO 4: Crear PollerManager con Protección OLT

**Archivo**: `zabbix_pollers/poller_manager.py`

```python
class PollerManager:
    def __init__(self, start_pollers: int = 10):
        self.start_pollers = start_pollers
        self.pollers: List[Poller] = []
        self.queue = NodeQueue()
        self.lock = Lock()
        
        # Crear pollers
        for i in range(start_pollers):
            poller = Poller(poller_id=i)
            self.pollers.append(poller)
    
    def is_olt_busy(self, olt_id: int) -> bool:
        """
        ✅ PROTECCIÓN OLT: Verificar si OLT ya tiene un nodo ejecutándose
        Solo 1 nodo a la vez por OLT
        """
        from executions.models import Execution
        return Execution.objects.filter(
            olt_id=olt_id,
            status__in=['RUNNING', 'PENDING']
        ).exists()
    
    def assign_node(self, composite_node: 'CompositeNode'):
        """
        Asignar nodo compuesto a poller libre, respetando límite de 1 por OLT
        """
        olt_id = composite_node.olt.id
        
        # ✅ PROTECCIÓN OLT
        if self.is_olt_busy(olt_id):
            self.queue.put(composite_node)
            return
        
        # OLT libre, asignar a poller libre
        poller = self.get_free_poller()
        if poller:
            thread = Thread(target=self._execute_and_process_queue, args=(poller, composite_node, olt_id))
            thread.start()
        else:
            self.queue.put(composite_node)
    
    def _execute_and_process_queue(self, poller: Poller, composite_node: 'CompositeNode', olt_id: int):
        """Ejecutar nodo compuesto y procesar siguiente de esa OLT"""
        try:
            poller.execute_composite_node(composite_node)
        finally:
            # Procesar siguiente nodo de esta OLT en cola
            self._process_queue_for_olt(olt_id)
```

### PASO 5: Crear API REST

**Archivo**: `zabbix_pollers/views.py`

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pollers(request):
    """GET /api/v1/pollers/ - Estado de todos los pollers"""
    poller_manager = get_poller_manager()  # Singleton
    stats = poller_manager.get_stats()
    return Response(stats)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_queue(request):
    """GET /api/v1/pollers/queue/ - Estado de la cola"""
    poller_manager = get_poller_manager()
    queue_info = {
        'size': poller_manager.queue.qsize(),
        'is_overload': poller_manager.queue.is_overload(),
        'next_nodes': poller_manager.queue.peek(10)  # Primeros 10
    }
    return Response(queue_info)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_stats(request):
    """GET /api/v1/pollers/stats/ - Estadísticas globales"""
    poller_manager = get_poller_manager()
    return Response(poller_manager.get_stats())

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_node_manually(request, node_id):
    """POST /api/v1/pollers/nodes/{node_id}/run/ - Ejecutar nodo manualmente"""
    # Implementar
    pass
```

### PASO 6: Reemplazar Coordinator Loop

**Archivo**: `zabbix_pollers/tasks.py`

```python
from celery import shared_task

@shared_task(queue='zabbix_scheduler', bind=True)
def zabbix_scheduler_loop_task(self):
    """
    Reemplaza coordinator_loop_task
    Loop principal del scheduler Zabbix cada 1 segundo
    """
    from .scheduler import ZabbixScheduler
    from .poller_manager import PollerManager
    
    poller_manager = PollerManager(start_pollers=10)
    scheduler = ZabbixScheduler(poller_manager)
    scheduler.running = True
    
    try:
        scheduler.scheduler_loop()
    except Exception as e:
        logger.error(f"Error en scheduler loop: {e}")
        raise
```

### PASO 7: Actualizar Celery Beat Schedule

**Archivo**: `core/celery.py` o `core/settings.py`

```python
CELERY_BEAT_SCHEDULE = {
    # Reemplazar coordinator-loop por zabbix-scheduler
    'zabbix-scheduler': {
        'task': 'zabbix_pollers.tasks.zabbix_scheduler_loop_task',
        'schedule': 1.0,  # Cada 1 segundo
        'options': {
            'queue': 'zabbix_scheduler',
            'expires': 0.5,
        }
    },
    # Mantener otras tareas...
}
```

---

## 🔄 MIGRACIÓN PASO A PASO

### Fase 1: Preparación
1. ✅ Crear modelos de datos (Poller, PollerStats)
2. ✅ Crear estructura de directorios `zabbix_pollers/`
3. ✅ Crear CompositeNode para manejar nodos encadenados

### Fase 2: Implementación Core
4. ✅ Implementar ZabbixScheduler
5. ✅ Implementar PollerManager con protección OLT
6. ✅ Implementar Poller individual
7. ✅ Implementar NodeQueue

### Fase 3: API y Monitoreo
8. ✅ Crear endpoints API REST
9. ✅ Agregar rutas en `api/urls.py`
10. ✅ Crear serializers para respuestas

### Fase 4: Migración
11. ✅ Crear tarea Celery `zabbix_scheduler_loop_task`
12. ✅ Actualizar Celery Beat schedule
13. ✅ Desactivar `coordinator_loop_task` (comentar)
14. ✅ Probar en desarrollo

### Fase 5: Despliegue
15. ✅ Migraciones de BD (si es necesario)
16. ✅ Actualizar Supervisor (si es necesario)
17. ✅ Desplegar y monitorear

---

## ⚠️ CONSIDERACIONES IMPORTANTES

### 1. Nodos Encadenados como Unidad
- **Master + encadenados = 1 nodo compuesto**
- Solo el master tiene `nextcheck`
- La ejecución incluye todos los encadenados secuencialmente
- El tiempo total de ejecución incluye todos los encadenados

### 2. Separación de Pollers Internos
- **NO tocar** `get_poller_task` en `snmp_get/tasks.py`
- Son pollers internos para procesar lotes de ONUs
- Funcionan independientemente
- NO se combinan con pollers del sistema Zabbix

### 3. Protección OLT
- **1 nodo compuesto a la vez por OLT**
- Verificar antes de asignar: `is_olt_busy(olt_id)`
- Si OLT ocupada → encolar
- Cuando termina → procesar siguiente de esa OLT

### 4. Compatibilidad
- Mantener modelos existentes (WorkflowNode, Execution, etc.)
- No cambiar estructura de BD
- Solo agregar nuevos modelos si es necesario

---

## 📊 ENDPOINTS API REQUERIDOS

1. `GET /api/v1/pollers/` - Estado de todos los pollers
2. `GET /api/v1/pollers/queue/` - Estado de la cola
3. `GET /api/v1/pollers/stats/` - Estadísticas globales
4. `POST /api/v1/pollers/nodes/{node_id}/run/` - Ejecutar nodo manualmente

---

## ✅ CHECKLIST DE IMPLEMENTACIÓN

- [ ] Crear estructura `zabbix_pollers/`
- [ ] Crear modelos (Poller, PollerStats)
- [ ] Implementar CompositeNode
- [ ] Implementar ZabbixScheduler
- [ ] Implementar PollerManager
- [ ] Implementar Poller individual
- [ ] Implementar NodeQueue
- [ ] Crear API REST endpoints
- [ ] Crear tarea Celery zabbix_scheduler_loop_task
- [ ] Actualizar Celery Beat schedule
- [ ] Desactivar coordinator_loop_task
- [ ] Probar en desarrollo
- [ ] Migraciones de BD
- [ ] Desplegar

