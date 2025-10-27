"""
Sistema de Desfase Automático (Stagger)

Detecta colisiones de tareas y aplica desfase inteligente
para evitar que múltiples tareas se ejecuten simultáneamente
"""

import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from .logger import coordinator_logger

logger = logging.getLogger(__name__)


class CollisionDetector:
    """
    Detecta colisiones entre tareas de una misma OLT
    """
    
    COLLISION_WINDOW = 60  # Segundos - si 2 tareas están a menos de esto, hay colisión
    STAGGER_OFFSET = 300   # Segundos - desfase entre tareas (5 minutos)
    
    def __init__(self, olt_id):
        self.olt_id = olt_id
    
    def detect_collisions(self, tasks):
        """
        Detecta colisiones entre tareas
        
        Args:
            tasks: Lista de diccionarios con info de tareas
        
        Returns:
            List[dict]: Lista de colisiones detectadas
        """
        collisions = []
        
        for i, task1 in enumerate(tasks):
            for j, task2 in enumerate(tasks[i+1:], start=i+1):
                # Obtener next_run_at de ambas tareas
                next_run1 = task1.get('next_run_at')
                next_run2 = task2.get('next_run_at')
                
                if not next_run1 or not next_run2:
                    continue
                
                # Parsear fechas
                from dateutil import parser
                dt1 = parser.isoparse(next_run1)
                dt2 = parser.isoparse(next_run2)
                
                # Calcular diferencia en segundos
                diff = abs((dt1 - dt2).total_seconds())
                
                if diff < self.COLLISION_WINDOW:
                    collisions.append({
                        'task1_id': task1['job_id'],
                        'task1_name': task1['job_name'],
                        'task1_priority': task1['priority'],
                        'task2_id': task2['job_id'],
                        'task2_name': task2['job_name'],
                        'task2_priority': task2['priority'],
                        'time_diff': diff,
                        'collision_time': dt1.isoformat(),
                    })
        
        return collisions
    
    def apply_stagger(self, tasks_state, olt):
        """
        Aplica desfase automático a tareas que colisionan
        
        Args:
            tasks_state: Lista de tareas del estado actual
            olt: Objeto OLT
        
        Returns:
            int: Número de tareas desfasadas
        """
        from snmp_jobs.models import SnmpJob
        
        # Detectar colisiones
        collisions = self.detect_collisions(tasks_state)
        
        if not collisions:
            return 0
        
        logger.info(
            f"🔍 Detectadas {len(collisions)} colisión(es) en {olt.abreviatura}",
            olt=olt,
            event_type='STATE_CHANGE'
        )
        
        # Agrupar tareas por tiempo de ejecución
        from dateutil import parser
        from collections import defaultdict
        
        time_groups = defaultdict(list)
        for task in tasks_state:
            next_run = task.get('next_run_at')
            if next_run:
                dt = parser.isoparse(next_run)
                # Agrupar por minuto
                time_key = dt.replace(second=0, microsecond=0)
                time_groups[time_key].append(task)
        
        tasks_adjusted = 0
        
        # Procesar cada grupo de colisión
        for time_key, group_tasks in time_groups.items():
            if len(group_tasks) <= 1:
                continue  # No hay colisión
            
            # Ordenar por prioridad (mayor primero)
            group_tasks.sort(key=lambda t: t['priority'], reverse=True)
            
            logger.warning(
                f"⚠️ Colisión en {olt.abreviatura}: {len(group_tasks)} tareas en {time_key.strftime('%H:%M')}",
                olt=olt,
                event_type='PLAN_ADJUSTED',
                details={
                    'collision_time': time_key.isoformat(),
                    'tasks_count': len(group_tasks),
                    'tasks': [t['job_name'] for t in group_tasks]
                }
            )
            
            # Aplicar desfase: primera tarea sin cambio, las demás desfasadas
            with transaction.atomic():
                for idx, task in enumerate(group_tasks):
                    if idx == 0:
                        # Primera tarea (mayor prioridad) se mantiene
                        coordinator_logger.info(
                            f"  ✅ {task['job_name']} mantiene horario (prioridad {task['priority']})",
                            olt=olt,
                            event_type='PLAN_CREATED'
                        )
                    else:
                        # Tareas siguientes se desfasan
                        offset_seconds = self.STAGGER_OFFSET * idx
                        
                        job = SnmpJob.objects.get(id=task['job_id'])
                        old_next_run = job.next_run_at
                        new_next_run = time_key + timedelta(seconds=offset_seconds)
                        
                        job.next_run_at = new_next_run
                        job.save(update_fields=['next_run_at'])
                        
                        tasks_adjusted += 1
                        
                        coordinator_logger.warning(
                            f"  🔄 {task['job_name']} desfasada +{offset_seconds//60} min (prioridad {task['priority']})",
                            olt=olt,
                            event_type='PLAN_ADJUSTED',
                            details={
                                'old_next_run': old_next_run.isoformat() if old_next_run else None,
                                'new_next_run': new_next_run.isoformat(),
                                'offset_seconds': offset_seconds,
                                'reason': 'collision_avoidance'
                            }
                        )
        
        if tasks_adjusted > 0:
            coordinator_logger.warning(
                f"📊 Desfase aplicado: {tasks_adjusted} tarea(s) ajustada(s) en {olt.abreviatura}",
                olt=olt,
                event_type='PLAN_ADJUSTED',
                details={
                    'tasks_adjusted': tasks_adjusted,
                    'collisions_resolved': len(collisions)
                }
            )
        
        return tasks_adjusted


def apply_automatic_stagger_for_olt(olt_id):
    """
    Función helper para aplicar desfase automático a una OLT
    
    Args:
        olt_id: ID de la OLT
    
    Returns:
        int: Número de tareas ajustadas
    """
    from hosts.models import OLT
    from .coordinator import ExecutionCoordinator
    
    try:
        olt = OLT.objects.get(id=olt_id)
        
        # Obtener estado actual
        coordinator = ExecutionCoordinator(olt_id)
        state = coordinator.get_system_state()
        
        if not state or not state.get('tasks'):
            return 0
        
        # Aplicar desfase
        detector = CollisionDetector(olt_id)
        adjusted = detector.apply_stagger(state['tasks'], olt)
        
        return adjusted
        
    except OLT.DoesNotExist:
        logger.error(f"OLT {olt_id} no existe")
        return 0
    except Exception as e:
        logger.error(f"Error aplicando desfase a OLT {olt_id}: {e}")
        return 0

