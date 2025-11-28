"""
Utilidades de ejecución - Callbacks, eventos y logging

Este módulo contiene las utilidades necesarias para:
- Callbacks de ejecución (on_task_completed, on_task_failed)
- Creación de eventos de ejecución
- Logging estructurado

Movido desde execution_coordinator para eliminar dependencias del coordinador antiguo.
"""

# Imports lazy para evitar problemas de carga de Django
def _get_callbacks():
    from .callbacks import on_task_completed, on_task_failed, update_workflow_node_on_completion
    return on_task_completed, on_task_failed, update_workflow_node_on_completion

def _get_event_utils():
    from .event_utils import create_execution_event
    return create_execution_event

def _get_logger():
    from .logger import coordinator_logger
    return coordinator_logger

# Re-exportar para compatibilidad
__all__ = [
    'on_task_completed',
    'on_task_failed',
    'update_workflow_node_on_completion',
    'create_execution_event',
    'coordinator_logger',
]

