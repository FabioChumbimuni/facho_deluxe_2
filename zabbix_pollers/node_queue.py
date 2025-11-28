"""
Cola de nodos estilo Zabbix (FIFO con priorización)
"""
from queue import PriorityQueue, Queue
from threading import Lock
from typing import Optional, Set


class NodeQueue:
    """
    Cola de nodos con priorización estilo Zabbix
    - FIFO dentro de misma prioridad
    - Prioriza nodos delayed
    - Sin duplicados
    """
    
    def __init__(self, max_size: int = 1000):
        self.queue = PriorityQueue(maxsize=max_size)
        self.node_ids_in_queue: Set[int] = set()
        self.lock = Lock()
        self.overload_threshold = max_size * 0.8
        self.max_size = max_size
    
    def put(self, composite_node):
        """
        Agregar nodo compuesto a cola con prioridad
        
        Prioridad:
        1. Delayed (True primero)
        2. Delay time (mayor primero)
        3. Priority (mayor primero)
        """
        with self.lock:
            # Verificar si ya está en cola (por ID del master)
            if composite_node.id in self.node_ids_in_queue:
                return  # Ya está en cola, no duplicar
            
            # Calcular prioridad
            priority = (
                not composite_node.delayed,  # Delayed primero (False < True)
                -composite_node.delay_time,  # Mayor delay primero
                -composite_node.priority     # Mayor prioridad primero
            )
            
            try:
                self.queue.put((priority, composite_node), block=False)
                self.node_ids_in_queue.add(composite_node.id)
            except:
                # Cola llena
                pass
    
    def get(self) -> Optional:
        """Obtener siguiente nodo compuesto de cola"""
        try:
            priority, composite_node = self.queue.get_nowait()
            with self.lock:
                self.node_ids_in_queue.discard(composite_node.id)
            return composite_node
        except:
            return None
    
    def peek(self, n: int = 10):
        """
        Ver primeros N nodos sin removerlos
        Útil para API de consulta
        """
        nodes = []
        temp_queue = PriorityQueue()
        
        # Obtener primeros N
        for _ in range(min(n, self.queue.qsize())):
            try:
                priority, node = self.queue.get_nowait()
                nodes.append({
                    'id': node.id,
                    'name': node.name,
                    'olt': node.olt.abreviatura,
                    'delayed': node.delayed,
                    'delay_time': node.delay_time,
                    'priority': node.priority
                })
                temp_queue.put((priority, node))
            except:
                break
        
        # Devolver a cola
        while not temp_queue.empty():
            try:
                self.queue.put(temp_queue.get_nowait(), block=False)
            except:
                break
        
        return nodes
    
    def qsize(self) -> int:
        """Tamaño de la cola"""
        return self.queue.qsize()
    
    def is_overload(self) -> bool:
        """Verificar si cola está sobrecargada"""
        return self.qsize() > self.overload_threshold
    
    def empty(self) -> bool:
        """Verificar si cola está vacía"""
        return self.queue.empty()

