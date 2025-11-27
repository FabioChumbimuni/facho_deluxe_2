"""
API REST para consultar información de pollers
"""
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import logging

from .tasks import get_poller_manager, get_scheduler
from .throttling import MonitoringRateThrottle

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([MonitoringRateThrottle])
def get_pollers(request):
    """
    GET /api/v1/pollers/
    
    Devuelve estado de todos los pollers
    """
    try:
        poller_manager = get_poller_manager()
        
        # Obtener estadísticas de cada poller
        # ✅ MEJORADO: Usar quick_mode=False para obtener estado real y preciso
        # Esto asegura que las estadísticas individuales coincidan con las globales
        pollers_data = []
        for poller in poller_manager.pollers:
            pollers_data.append(poller.get_stats(quick_mode=False))
        
        # Log de depuración: mostrar todos los poller_ids que se están devolviendo
        poller_ids = [p.get('poller_id') for p in pollers_data if p and p.get('poller_id') is not None]
        poller_ids_sorted = sorted(poller_ids)
        logger.debug(f"get_pollers: Devolviendo {len(pollers_data)} pollers con IDs: {poller_ids_sorted}")
        
        # Estadísticas globales
        global_stats = poller_manager.get_stats()
        
        # Asegurar que siempre devolvemos datos válidos
        response_data = {
            'pollers': pollers_data if pollers_data else [],
            'global_stats': global_stats if global_stats else {}
        }
        
        logger.debug(f"get_pollers: {len(pollers_data)} pollers, stats: {global_stats}")
        return Response(response_data)
    except Exception as e:
        logger.error(f"Error en get_pollers: {e}", exc_info=True)
        return Response(
            {
                'error': str(e),
                'pollers': [],
                'global_stats': {}
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([MonitoringRateThrottle])
def get_queue(request):
    """
    GET /api/v1/pollers/queue/
    
    Devuelve estado de la cola Y nodos listos para ejecutar
    """
    try:
        from django.utils import timezone
        from snmp_jobs.models import WorkflowNode, OLTWorkflow
        from executions.models import Execution
        from zabbix_pollers.scheduler import ZabbixScheduler
        
        poller_manager = get_poller_manager()
        queue = poller_manager.queue
        
        # ✅ SOLO mostrar nodos que están REALMENTE en cola o tienen ejecuciones activas
        # No mostrar nodos "listos" que aún no se han asignado
        try:
            # 1. Obtener nodos que están realmente en la cola
            next_nodes_from_queue = queue.peek(20)  # Primeros 20 nodos de la cola
        except Exception as e:
            logger.warning(f"Error al obtener nodos de cola: {e}")
            next_nodes_from_queue = []
        
        # 2. Obtener nodos con ejecuciones activas (PENDING o RUNNING)
        active_executions = []
        try:
            now = timezone.now()
            
            # Obtener ejecuciones activas con sus nodos
            active_execs = Execution.objects.filter(
                status__in=['PENDING', 'RUNNING'],
                workflow_node__isnull=False
            ).select_related('workflow_node', 'workflow_node__workflow', 'workflow_node__workflow__olt').only(
                'id', 'status', 'created_at', 'workflow_node_id',
                'workflow_node__name', 'workflow_node__id',
                'workflow_node__workflow__olt__abreviatura', 'workflow_node__workflow__olt__id'
            )[:50]  # Limitar a 50 para rendimiento
            
            for exec_obj in active_execs:
                if exec_obj.workflow_node:
                    active_executions.append({
                        'id': exec_obj.workflow_node.id,
                        'name': exec_obj.workflow_node.name,
                        'olt': exec_obj.workflow_node.workflow.olt.abreviatura if exec_obj.workflow_node.workflow and exec_obj.workflow_node.workflow.olt else 'N/A',
                        'next_run_at': None,  # No tiene next_run_at porque ya está ejecutándose
                        'status': exec_obj.status.lower(),  # 'pending' o 'running'
                        'delayed': False,
                        'priority': getattr(exec_obj.workflow_node, 'priority', 0),
                        'execution_id': exec_obj.id,
                        'execution_created_at': exec_obj.created_at.isoformat() if exec_obj.created_at else None
                    })
        except Exception as e:
            logger.warning(f"Error al obtener ejecuciones activas: {e}", exc_info=True)
            active_executions = []
        
        # 3. Convertir nodos de la cola a formato para el frontend
        queued_nodes_info = []
        for composite_node in next_nodes_from_queue:
            queued_nodes_info.append({
                'id': composite_node.id,
                'name': composite_node.name,
                'olt': composite_node.olt.abreviatura if composite_node.olt else 'N/A',
                'next_run_at': composite_node.nextcheck.isoformat() if composite_node.nextcheck else None,
                'status': 'queued',  # Está en cola
                'delayed': composite_node.delayed,
                'priority': composite_node.priority
            })
        
        # 4. Combinar: nodos en cola + ejecuciones activas
        # Eliminar duplicados (si un nodo está en cola Y tiene ejecución activa, mostrar solo la ejecución activa)
        all_pending_nodes = []
        queued_node_ids = {node['id'] for node in queued_nodes_info}
        active_node_ids = {node['id'] for node in active_executions}
        
        # Primero agregar ejecuciones activas (tienen prioridad)
        for exec_node in active_executions:
            all_pending_nodes.append(exec_node)
        
        # Luego agregar nodos en cola que NO tienen ejecución activa
        for queued_node in queued_nodes_info:
            if queued_node['id'] not in active_node_ids:
                all_pending_nodes.append(queued_node)
        
        # Asegurar que siempre devolvemos datos válidos
        queue_info = {
            'size': queue.qsize() if queue else 0,
            'is_overload': queue.is_overload() if queue else False,
            'overload_threshold': queue.overload_threshold if queue else 800,
            'max_size': queue.max_size if queue else 1000,
            'next_nodes': all_pending_nodes,  # ✅ Solo nodos en cola + ejecuciones activas
            'queued_nodes_count': len(queued_nodes_info),  # Nodos realmente en cola
            'active_executions_count': len(active_executions),  # Ejecuciones activas (PENDING/RUNNING)
            'total_pending_count': len(all_pending_nodes)  # Total: cola + activas
        }
        
        logger.debug(f"get_queue: size={queue_info['size']}, queued={len(queued_nodes_info)}, active={len(active_executions)}, total={len(all_pending_nodes)}")
        return Response(queue_info)
    except Exception as e:
        logger.error(f"Error en get_queue: {e}", exc_info=True)
        return Response(
            {
                'error': str(e),
                'size': 0,
                'is_overload': False,
                'overload_threshold': 800,
                'max_size': 1000,
                'next_nodes': [],
                'queued_nodes_count': 0,
                'active_executions_count': 0,
                'total_pending_count': 0
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@throttle_classes([MonitoringRateThrottle])
def get_stats(request):
    """
    GET /api/v1/pollers/stats/
    
    Devuelve estadísticas globales del scheduler
    """
    try:
        poller_manager = get_poller_manager()
        stats = poller_manager.get_stats()
        
        # Agregar información adicional
        stats['scheduler_running'] = True  # TODO: obtener del scheduler
        stats['start_pollers'] = poller_manager.start_pollers
        
        # Asegurar que todos los campos requeridos estén presentes
        default_stats = {
            'total_pollers': 0,
            'free_pollers': 0,
            'busy_pollers': 0,
            'busy_percentage': 0.0,
            'queue_size': 0,
            'is_saturated': False,
            'is_overload': False,
            'total_tasks_completed': 0,
            'total_tasks_delayed': 0,
            'scheduler_running': True,
            'start_pollers': 10
        }
        
        # Combinar stats con defaults para asegurar que todos los campos estén presentes
        response_stats = {**default_stats, **stats}
        
        logger.debug(f"get_stats: {response_stats}")
        return Response(response_stats)
    except Exception as e:
        logger.error(f"Error en get_stats: {e}", exc_info=True)
        return Response(
            {
                'error': str(e),
                'total_pollers': 0,
                'free_pollers': 0,
                'busy_pollers': 0,
                'busy_percentage': 0.0,
                'queue_size': 0,
                'is_saturated': False,
                'is_overload': False,
                'total_tasks_completed': 0,
                'total_tasks_delayed': 0,
                'scheduler_running': False,
                'start_pollers': 10
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_node_manually(request, node_id):
    """
    POST /api/v1/pollers/nodes/{node_id}/run/
    
    Ejecutar nodo manualmente
    """
    try:
        from snmp_jobs.models import WorkflowNode
        from .composite_node import CompositeNode
        
        # Obtener nodo
        try:
            node = WorkflowNode.objects.select_related('workflow__olt').get(id=node_id)
        except WorkflowNode.DoesNotExist:
            return Response(
                {'error': f'Nodo {node_id} no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verificar que sea master (no encadenado)
        if node.is_chain_node:
            return Response(
                {'error': 'No se puede ejecutar manualmente un nodo encadenado. Ejecute el nodo master.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Obtener nodos encadenados
        chain_nodes = node.chain_nodes.filter(enabled=True).order_by('priority', 'id')
        
        # Crear nodo compuesto
        composite_node = CompositeNode(
            master=node,
            chain_nodes=list(chain_nodes),
            workflow=node.workflow,
            olt=node.workflow.olt
        )
        
        # Asignar a poller
        poller_manager = get_poller_manager()
        poller_manager.assign_node(composite_node)
        
        return Response({
            'status': 'assigned',
            'node_id': node_id,
            'node_name': node.name,
            'olt': node.workflow.olt.abreviatura,
            'chain_nodes_count': len(chain_nodes),
            'message': f'Nodo compuesto asignado (master + {len(chain_nodes)} encadenados)'
        })
    except Exception as e:
        logger.error(f"Error en run_node_manually: {e}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

