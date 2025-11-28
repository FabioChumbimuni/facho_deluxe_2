"""
Views y ViewSets para la API REST de Facho Deluxe v2
"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.db import connection
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from datetime import datetime, timedelta
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

logger = logging.getLogger(__name__)


# ============================================================================
# CLASES DE PAGINACIÓN PERSONALIZADAS
# ============================================================================

class CustomPageNumberPagination(PageNumberPagination):
    """
    Paginación personalizada que permite al cliente controlar el page_size.
    Uso: ?page=1&page_size=25
    """
    page_size = 50  # Por defecto
    page_size_query_param = 'page_size'  # Permitir al cliente controlar page_size
    max_page_size = 1000  # Límite máximo


# Importar modelos
from hosts.models import OLT
from brands.models import Brand
from olt_models.models import OLTModel
from snmp_jobs.models import SnmpJob, WorkflowTemplate, WorkflowTemplateNode, OLTWorkflow, WorkflowNode
from snmp_jobs.services.workflow_template_service import WorkflowTemplateService
from executions.models import Execution
from discovery.models import OnuIndexMap, OnuStateLookup, OnuInventory, OnuStatus
from oids.models import OID
from snmp_formulas.models import IndexFormula
from odf_management.models import ODF, ODFHilos, ZabbixPortData
from personal.models import Personal, Area
from zabbix_config.models import ZabbixConfiguration
from configuracion_avanzada.models import ConfiguracionSistema, ConfiguracionSNMP

# Importar serializers
from .serializers import (
    UserSerializer, BrandSerializer, OLTModelSerializer,
    OLTSerializer, OLTListSerializer, SNMPJobSerializer,
    ExecutionSerializer, OnuIndexMapSerializer, OnuStateLookupSerializer,
    OnuInventorySerializer, OnuInventoryListSerializer,
    OIDSerializer, IndexFormulaSerializer, ODFSerializer, ODFHilosSerializer,
    ZabbixPortDataSerializer, AreaSerializer, PersonalSerializer,
    ZabbixConfigSerializer, DashboardStatsSerializer,
    WorkflowTemplateSerializer, WorkflowTemplateNodeSerializer,
    OLTWorkflowSerializer, WorkflowNodeSerializer,
    ConfiguracionSistemaSerializer, ConfiguracionSNMPSerializer
)


# ============================================================================
# VIEWSETS DE AUTENTICACIÓN
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar usuarios del sistema"),
    retrieve=extend_schema(description="Obtener detalles de un usuario"),
    create=extend_schema(description="Crear nuevo usuario"),
    update=extend_schema(description="Actualizar usuario completo"),
    partial_update=extend_schema(description="Actualizar usuario parcialmente"),
    destroy=extend_schema(description="Eliminar usuario"),
)
class UserViewSet(viewsets.ModelViewSet):
    """ViewSet para usuarios"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'date_joined']
    ordering = ['-date_joined']
    
    @extend_schema(
        description="Obtener información del usuario autenticado",
        responses={200: UserSerializer}
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Obtener información del usuario actual"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


# ============================================================================
# VIEWSETS DE HOSTS Y BRANDS
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar marcas de equipos"),
    retrieve=extend_schema(description="Obtener detalles de una marca"),
    create=extend_schema(description="Crear nueva marca"),
    update=extend_schema(description="Actualizar marca completa"),
    partial_update=extend_schema(description="Actualizar marca parcialmente"),
    destroy=extend_schema(description="Eliminar marca"),
)
class BrandViewSet(viewsets.ModelViewSet):
    """ViewSet para marcas de equipos"""
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre']
    ordering = ['nombre']


@extend_schema_view(
    list=extend_schema(description="Listar modelos de OLT"),
    retrieve=extend_schema(description="Obtener detalles de un modelo"),
    create=extend_schema(description="Crear nuevo modelo"),
    update=extend_schema(description="Actualizar modelo completo"),
    partial_update=extend_schema(description="Actualizar modelo parcialmente"),
    destroy=extend_schema(description="Eliminar modelo"),
)
class OLTModelViewSet(viewsets.ModelViewSet):
    """ViewSet para modelos de OLT"""
    queryset = OLTModel.objects.all()
    serializer_class = OLTModelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['marca']
    search_fields = ['nombre', 'descripcion']


@extend_schema_view(
    list=extend_schema(description="Listar OLTs del sistema"),
    retrieve=extend_schema(description="Obtener detalles de una OLT"),
    create=extend_schema(description="Crear nueva OLT"),
    update=extend_schema(description="Actualizar OLT completa"),
    partial_update=extend_schema(description="Actualizar OLT parcialmente"),
    destroy=extend_schema(description="Eliminar OLT"),
)
class OLTViewSet(viewsets.ModelViewSet):
    """ViewSet para OLTs (excluye eliminadas por defecto)"""
    # ✅ Usar manager personalizado que excluye eliminadas automáticamente
    queryset = OLT.objects.select_related('marca', 'modelo').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['marca', 'habilitar_olt']
    search_fields = ['abreviatura', 'ip_address', 'descripcion']
    ordering_fields = ['abreviatura', 'ip_address']
    ordering = ['abreviatura']
    
    def get_serializer_class(self):
        """Usar serializer diferente para listado"""
        if self.action == 'list':
            return OLTListSerializer
        return OLTSerializer
    
    @extend_schema(
        description="Obtener estadísticas de una OLT",
        responses={200: {
            'type': 'object',
            'properties': {
                'total_jobs': {'type': 'integer'},
                'jobs_activos': {'type': 'integer'},
                'total_ejecuciones': {'type': 'integer'},
                'ejecuciones_exitosas': {'type': 'integer'},
                'ejecuciones_fallidas': {'type': 'integer'},
                'total_onus': {'type': 'integer'},
            }
        }}
    )
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Obtener estadísticas de una OLT"""
        olt = self.get_object()
        
        total_jobs = olt.snmp_jobs.count()
        jobs_activos = olt.snmp_jobs.filter(enabled=True).count()
        
        total_ejecuciones = Execution.objects.filter(olt=olt).count()
        ejecuciones_exitosas = Execution.objects.filter(
            olt=olt, status='SUCCESS'
        ).count()
        ejecuciones_fallidas = Execution.objects.filter(
            olt=olt, status='FAILED'
        ).count()
        
        total_onus = OnuInventory.objects.filter(olt=olt, active=True).count()
        
        return Response({
            'total_jobs': total_jobs,
            'jobs_activos': jobs_activos,
            'total_ejecuciones': total_ejecuciones,
            'ejecuciones_exitosas': ejecuciones_exitosas,
            'ejecuciones_fallidas': ejecuciones_fallidas,
            'total_onus': total_onus,
        })
    
    @extend_schema(
        description="Habilitar/deshabilitar una OLT",
        request={'application/json': {'type': 'object', 'properties': {'habilitar': {'type': 'boolean'}}}},
        responses={200: OLTSerializer}
    )
    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Habilitar o deshabilitar una OLT"""
        olt = self.get_object()
        habilitar = request.data.get('habilitar')
        
        if habilitar is not None:
            olt.habilitar_olt = habilitar
            olt.save()
            serializer = self.get_serializer(olt)
            return Response(serializer.data)
        
        return Response(
            {'error': 'Se requiere el parámetro "habilitar"'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @extend_schema(
        description="Eliminar OLT de forma suave (soft delete)",
        request={'application/json': {
            'type': 'object',
            'properties': {
                'reason': {'type': 'string', 'description': 'Razón de la eliminación'}
            }
        }},
        responses={200: {'description': 'OLT eliminada exitosamente'}}
    )
    def destroy(self, request, *args, **kwargs):
        """Soft delete: marca la OLT como eliminada en lugar de borrarla físicamente"""
        olt = self.get_object()
        reason = request.data.get('reason', 'Eliminación desde API')
        
        # Usar soft_delete en lugar de borrado físico
        olt.soft_delete(user=request.user, reason=reason)
        
        # Abortar ejecuciones PENDING para esta OLT
        from snmp_jobs.models import SnmpJob
        aborted_count = SnmpJob.abort_pending_executions_for_olt(
            olt.id,
            f"OLT {olt.abreviatura} eliminada (soft delete)"
        )
        
        return Response({
            'message': f'OLT "{olt.abreviatura}" eliminada exitosamente',
            'abreviatura': olt.abreviatura,
            'executions_aborted': aborted_count
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Restaurar una OLT eliminada (undo soft delete)",
        responses={200: OLTSerializer}
    )
    @action(detail=True, methods=['post'], url_path='restore')
    def restore(self, request, pk=None):
        """Restaurar una OLT eliminada (renombra automáticamente si hay conflicto)"""
        # Obtener desde all_objects para incluir eliminadas
        try:
            olt = OLT.all_objects.get(pk=pk, is_deleted=True)
        except OLT.DoesNotExist:
            return Response(
                {'error': 'OLT no encontrada o no está eliminada'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # Restaurar con renombrado automático si hay conflicto
            restore_info = olt.restore(user=request.user, rename_on_conflict=True)
            serializer = self.get_serializer(olt)
            
            # Incluir información sobre el renombrado en la respuesta
            response_data = serializer.data
            response_data['restore_info'] = restore_info
            
            return Response(response_data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


# ============================================================================
# VIEWSETS DE SNMP JOBS Y EJECUCIONES
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar trabajos SNMP"),
    retrieve=extend_schema(description="Obtener detalles de un trabajo SNMP"),
    create=extend_schema(description="Crear nuevo trabajo SNMP"),
    update=extend_schema(description="Actualizar trabajo SNMP completo"),
    partial_update=extend_schema(description="Actualizar trabajo SNMP parcialmente"),
    destroy=extend_schema(description="Eliminar trabajo SNMP"),
)
class SNMPJobViewSet(viewsets.ModelViewSet):
    """ViewSet para trabajos SNMP"""
    queryset = SnmpJob.objects.select_related('marca', 'oid').prefetch_related('olts').all()
    serializer_class = SNMPJobSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['marca', 'job_type', 'enabled']
    search_fields = ['nombre', 'descripcion']
    ordering_fields = ['nombre', 'next_run_at', 'last_run_at']
    ordering = ['-id']
    
    @extend_schema(
        description="Ejecutar manualmente un trabajo SNMP",
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}}
    )
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Ejecutar manualmente un trabajo SNMP"""
        job = self.get_object()
        # Aquí deberías llamar a la tarea de Celery para ejecutar el job
        return Response({
            'message': f'Trabajo "{job.nombre}" ejecutado manualmente',
            'job_id': job.id
        })


@extend_schema_view(
    list=extend_schema(description="Listar ejecuciones de trabajos"),
    retrieve=extend_schema(description="Obtener detalles de una ejecución"),
)
class ExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para ejecuciones (solo lectura)"""
    serializer_class = ExecutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['snmp_job', 'olt', 'status', 'workflow_node']  # ✅ Agregado workflow_node para filtrar por nodo
    search_fields = ['snmp_job__nombre', 'olt__abreviatura', 'olt__ip_address', 'error_message', 'workflow_node__name', 'workflow_node__workflow__name']
    ordering_fields = ['started_at', 'finished_at', 'created_at']
    ordering = ['-created_at']
    
    @extend_schema(
        description="Obtener ejecuciones recientes",
        parameters=[
            OpenApiParameter(name='limit', type=OpenApiTypes.INT, description='Número de ejecuciones a retornar'),
        ],
        responses={200: ExecutionSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Obtener ejecuciones recientes"""
        limit = int(request.query_params.get('limit', 10))
        executions = self.get_queryset().order_by('-created_at')[:limit]
        serializer = self.get_serializer(executions, many=True)
        return Response(serializer.data)
    
    def get_queryset(self):
        """Excluir ejecuciones de OLTs eliminadas y agregar logs de diagnóstico"""
        queryset = Execution.objects.select_related(
            'snmp_job', 
            'olt',
            'workflow_node',
            'workflow_node__workflow',
            'workflow_node__template_node',
            'workflow_node__template_node__template'
        ).filter(olt__is_deleted=False)  # ✅ Excluir ejecuciones de OLTs eliminadas
        
        # Log cuando se filtra por workflow_node
        workflow_node_id = self.request.query_params.get('workflow_node')
        if workflow_node_id:
            try:
                node_id = int(workflow_node_id)
                filtered_count = queryset.filter(workflow_node_id=node_id).count()
                logger.info(
                    f"📊 ExecutionViewSet: Filtrado por workflow_node={node_id}, "
                    f"total ejecuciones encontradas: {filtered_count}"
                )
            except (ValueError, TypeError):
                pass
        
        return queryset


# ============================================================================
# VIEWSETS DE DISCOVERY
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar ONUs (Inventario completo)"),
    retrieve=extend_schema(description="Obtener detalles de una ONU"),
    create=extend_schema(description="Crear nueva ONU (crea en 3 tablas automáticamente)"),
    update=extend_schema(description="Actualizar ONU completa"),
    partial_update=extend_schema(description="Actualizar ONU parcialmente"),
    destroy=extend_schema(description="Eliminar ONU"),
)
class OnuInventoryViewSet(viewsets.ModelViewSet):
    """ViewSet para inventario de ONUs (OnuInventory)"""
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'olt': ['exact'],
        'active': ['exact'],
        'plan_onu': ['exact', 'icontains'],
        'modelo_onu': ['exact', 'icontains'],
        'onu_index__slot': ['exact'],  # Filtrar por slot desde OnuIndexMap
        'onu_index__port': ['exact'],  # Filtrar por port desde OnuIndexMap
        'onu_index__logical': ['exact'],  # Filtrar por logical desde OnuIndexMap
    }
    search_fields = ['serial_number', 'mac_address', 'subscriber_id', 'snmp_description']
    ordering_fields = ['created_at', 'updated_at', 'snmp_last_collected_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Excluir ONUs de OLTs eliminadas"""
        return OnuInventory.objects.select_related(
            'olt', 
            'onu_index', 
            'onu_index__status'
        ).filter(olt__is_deleted=False)
    
    def get_serializer_class(self):
        """Usar serializer diferente para listado"""
        if self.action == 'list':
            return OnuInventoryListSerializer
        return OnuInventorySerializer
    
    @extend_schema(
        description="Obtener ONUs activas (active=True)",
        responses={200: OnuInventoryListSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def activas(self, request):
        """Obtener solo ONUs activas"""
        onus = self.get_queryset().filter(active=True)
        page = self.paginate_queryset(onus)
        if page is not None:
            serializer = OnuInventoryListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = OnuInventoryListSerializer(onus, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        description="Desactivar ONU (soft delete) - Cambia presence a DISABLED y active a False",
        responses={200: {'description': 'ONU desactivada exitosamente'}}
    )
    @action(detail=True, methods=['post'], url_path='desactivar')
    def desactivar(self, request, pk=None):
        """
        ELIMINACIÓN SUAVE: Desactiva la ONU cambiando:
        - active = False en OnuInventory
        - presence = DISABLED en OnuStatus
        
        La ONU se ignorará hasta que el recolector la identifique otra vez.
        """
        from discovery.models import OnuStatus
        
        onu = self.get_object()
        
        # Cambiar active a False en OnuInventory
        onu.active = False
        onu.save()
        
        # Cambiar presence y estado a DISABLED/SUSPENDIDO en OnuStatus
        if hasattr(onu.onu_index, 'status'):
            onu_status = onu.onu_index.status
            onu_status.presence = 'DISABLED'
            onu_status.last_state_label = 'SUSPENDIDO'
            onu_status.last_state_value = 2  # 2=SUSPENDIDO
            onu_status.save()
        
        return Response({
            'message': 'ONU desactivada exitosamente',
            'id': onu.id,
            'presence': onu.onu_index.status.presence if hasattr(onu.onu_index, 'status') else None,
            'estado': onu.onu_index.status.last_state_label if hasattr(onu.onu_index, 'status') else None
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Activar presence de ONU (ENABLED) manteniendo estado administrativo",
        responses={200: {'description': 'Presence activado exitosamente'}}
    )
    @action(detail=True, methods=['post'], url_path='activar-presence')
    def activar_presence(self, request, pk=None):
        """
        Activa el PRESENCE a ENABLED y sincroniza active=True.
        
        - active = True (en OnuInventory)
        - presence = ENABLED (en OnuStatus)
        - estado (last_state_label) = NO CAMBIA
        """
        from discovery.models import OnuStatus
        
        onu = self.get_object()
        
        # Cambiar active a True en OnuInventory
        onu.active = True
        onu.save()
        
        # Cambiar presence a ENABLED en OnuStatus
        if hasattr(onu.onu_index, 'status'):
            onu_status = onu.onu_index.status
            onu_status.presence = 'ENABLED'
            onu_status.save()
        
        return Response({
            'message': 'Presence activado exitosamente',
            'id': onu.id,
            'presence': onu.onu_index.status.presence if hasattr(onu.onu_index, 'status') else None,
            'estado': onu.onu_index.status.last_state_label if hasattr(onu.onu_index, 'status') else None
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Desactivar presence de ONU (DISABLED) manteniendo estado administrativo",
        responses={200: {'description': 'Presence desactivado exitosamente'}}
    )
    @action(detail=True, methods=['post'], url_path='desactivar-presence')
    def desactivar_presence(self, request, pk=None):
        """
        Desactiva el PRESENCE a DISABLED y sincroniza active=False.
        
        - active = False (en OnuInventory)
        - presence = DISABLED (en OnuStatus)
        - estado (last_state_label) = NO CAMBIA
        """
        from discovery.models import OnuStatus
        
        onu = self.get_object()
        
        # Cambiar active a False en OnuInventory
        onu.active = False
        onu.save()
        
        # Cambiar presence a DISABLED en OnuStatus
        if hasattr(onu.onu_index, 'status'):
            onu_status = onu.onu_index.status
            onu_status.presence = 'DISABLED'
            onu_status.save()
        
        return Response({
            'message': 'Presence desactivado exitosamente',
            'id': onu.id,
            'presence': onu.onu_index.status.presence if hasattr(onu.onu_index, 'status') else None,
            'estado': onu.onu_index.status.last_state_label if hasattr(onu.onu_index, 'status') else None
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Cambiar estado a ACTIVO (activa el servicio administrativamente)",
        responses={200: {'description': 'Estado cambiado a ACTIVO exitosamente'}}
    )
    @action(detail=True, methods=['post'], url_path='activar-estado')
    def activar_estado(self, request, pk=None):
        """
        Cambia el estado administrativo a ACTIVO.
        
        - last_state_label = ACTIVO
        - last_state_value = 1
        - active y presence = NO CAMBIAN (son independientes)
        """
        from discovery.models import OnuStatus
        
        onu = self.get_object()
        
        # Solo cambiar estado a ACTIVO en OnuStatus
        if hasattr(onu.onu_index, 'status'):
            onu_status = onu.onu_index.status
            onu_status.last_state_label = 'ACTIVO'
            onu_status.last_state_value = 1
            onu_status.save()
        
        return Response({
            'message': 'Estado cambiado a ACTIVO exitosamente',
            'id': onu.id,
            'estado': onu.onu_index.status.last_state_label if hasattr(onu.onu_index, 'status') else None,
            'presence': onu.onu_index.status.presence if hasattr(onu.onu_index, 'status') else None
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Cambiar estado a SUSPENDIDO (suspende el servicio administrativamente)",
        responses={200: {'description': 'Estado cambiado a SUSPENDIDO exitosamente'}}
    )
    @action(detail=True, methods=['post'], url_path='suspender-estado')
    def suspender_estado(self, request, pk=None):
        """
        Cambia el estado administrativo a SUSPENDIDO.
        
        - last_state_label = SUSPENDIDO
        - last_state_value = 2
        - active y presence = NO CAMBIAN (son independientes)
        """
        from discovery.models import OnuStatus
        
        onu = self.get_object()
        
        # Solo cambiar estado a SUSPENDIDO en OnuStatus
        if hasattr(onu.onu_index, 'status'):
            onu_status = onu.onu_index.status
            onu_status.last_state_label = 'SUSPENDIDO'
            onu_status.last_state_value = 2
            onu_status.save()
        
        return Response({
            'message': 'Estado cambiado a SUSPENDIDO exitosamente',
            'id': onu.id,
            'estado': onu.onu_index.status.last_state_label if hasattr(onu.onu_index, 'status') else None,
            'presence': onu.onu_index.status.presence if hasattr(onu.onu_index, 'status') else None
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Eliminar ONU completamente (hard delete) - Borra de las 3 tablas",
        responses={204: {'description': 'ONU eliminada completamente'}}
    )
    @action(detail=True, methods=['delete'], url_path='eliminar-permanente')
    def eliminar_permanente(self, request, pk=None):
        """
        ELIMINACIÓN COMPLETA: Borra la ONU de las 3 tablas:
        - OnuInventory
        - OnuStatus
        - OnuIndexMap
        
        ⚠️ ADVERTENCIA: Esta acción es IRREVERSIBLE.
        """
        from discovery.models import OnuStatus, OnuIndexMap
        
        onu = self.get_object()
        onu_index_id = onu.onu_index.id
        
        # Guardar info para el response
        info = {
            'id': onu.id,
            'onu_index_id': onu_index_id,
            'slot': onu.onu_index.slot,
            'port': onu.onu_index.port,
            'logical': onu.onu_index.logical,
            'raw_index_key': onu.onu_index.raw_index_key
        }
        
        # 1. Eliminar OnuInventory
        onu.delete()
        
        # 2. Eliminar OnuStatus (si existe)
        OnuStatus.objects.filter(onu_index_id=onu_index_id).delete()
        
        # 3. Eliminar OnuIndexMap
        OnuIndexMap.objects.filter(id=onu_index_id).delete()
        
        return Response({
            'message': 'ONU eliminada permanentemente de las 3 tablas',
            'deleted': info
        }, status=status.HTTP_200_OK)
    
    @extend_schema(
        description="Obtener ONUs por OLT",
        parameters=[
            OpenApiParameter(name='olt_id', type=OpenApiTypes.INT, description='ID de la OLT'),
        ],
        responses={200: OnuInventoryListSerializer(many=True)}
    )
    @action(detail=False, methods=['get'])
    def por_olt(self, request):
        """Obtener ONUs de una OLT específica"""
        olt_id = request.query_params.get('olt_id')
        if not olt_id:
            return Response(
                {'error': 'Se requiere el parámetro olt_id'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        onus = self.get_queryset().filter(olt_id=olt_id)
        page = self.paginate_queryset(onus)
        if page is not None:
            serializer = OnuInventoryListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = OnuInventoryListSerializer(onus, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(description="Listar mapeo de índices ONUs"),
    retrieve=extend_schema(description="Obtener detalles de un mapeo"),
)
class OnuIndexMapViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para mapeo de índices ONUs (OnuIndexMap) - Solo lectura"""
    serializer_class = OnuIndexMapSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['olt', 'slot', 'port']
    search_fields = ['raw_index_key', 'normalized_id']
    
    def get_queryset(self):
        """Excluir índices de OLTs eliminadas"""
        return OnuIndexMap.objects.select_related('olt', 'odf_hilo').filter(olt__is_deleted=False)


@extend_schema_view(
    list=extend_schema(description="Listar estados de ONUs"),
    retrieve=extend_schema(description="Obtener detalles de un estado"),
)
class OnuStateLookupViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para estados de ONUs (solo lectura)"""
    queryset = OnuStateLookup.objects.all()
    serializer_class = OnuStateLookupSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['marca', 'value']  # value es el ID del estado (1, 2, etc.)


# ============================================================================
# VIEWSETS DE OIDS Y FORMULAS
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar OIDs SNMP"),
    retrieve=extend_schema(description="Obtener detalles de un OID"),
    create=extend_schema(description="Crear nuevo OID"),
    update=extend_schema(description="Actualizar OID completo"),
    partial_update=extend_schema(description="Actualizar OID parcialmente"),
    destroy=extend_schema(description="Eliminar OID"),
)
class OIDViewSet(viewsets.ModelViewSet):
    """ViewSet para OIDs SNMP"""
    queryset = OID.objects.all().order_by('id')  # ✅ Ordenamiento explícito para evitar warning de paginación
    serializer_class = OIDSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['nombre', 'oid']
    filterset_fields = ['marca', 'espacio']  # Campos reales del modelo
    ordering_fields = ['id', 'nombre', 'oid', 'espacio', 'marca']
    ordering = ['id']  # ✅ Ordenamiento por defecto para evitar warning de paginación


@extend_schema_view(
    list=extend_schema(description="Listar fórmulas de índices"),
    retrieve=extend_schema(description="Obtener detalles de una fórmula"),
    create=extend_schema(description="Crear nueva fórmula"),
    update=extend_schema(description="Actualizar fórmula completa"),
    partial_update=extend_schema(description="Actualizar fórmula parcialmente"),
    destroy=extend_schema(description="Eliminar fórmula"),
)
class IndexFormulaViewSet(viewsets.ModelViewSet):
    """ViewSet para fórmulas de índices"""
    queryset = IndexFormula.objects.select_related('marca', 'modelo').all()
    serializer_class = IndexFormulaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['marca', 'modelo', 'activo']
    ordering_fields = ['created_at', 'nombre']
    ordering = ['-created_at']  # Más recientes primero


# ============================================================================
# VIEWSETS DE ODF
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar ODFs"),
    retrieve=extend_schema(description="Obtener detalles de un ODF"),
    create=extend_schema(description="Crear nuevo ODF"),
    update=extend_schema(description="Actualizar ODF completo"),
    partial_update=extend_schema(description="Actualizar ODF parcialmente"),
    destroy=extend_schema(description="Eliminar ODF"),
)
class ODFViewSet(viewsets.ModelViewSet):
    """ViewSet para ODFs"""
    serializer_class = ODFSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['numero_odf', 'nombre_troncal', 'descripcion']
    filterset_fields = ['olt']
    
    def get_queryset(self):
        """Excluir ODFs de OLTs eliminadas"""
        return ODF.objects.select_related('olt').filter(olt__is_deleted=False)


@extend_schema_view(
    list=extend_schema(description="Listar hilos de ODF"),
    retrieve=extend_schema(description="Obtener detalles de un hilo"),
    update=extend_schema(description="Actualizar hilo completo"),
    partial_update=extend_schema(description="Actualizar hilo parcialmente"),
)
class ODFHilosViewSet(viewsets.ModelViewSet):
    """ViewSet para hilos de ODF"""
    queryset = ODFHilos.objects.select_related('odf').all()
    serializer_class = ODFHilosSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['odf', 'estado', 'operativo_noc']  # Campos reales del modelo
    search_fields = ['descripcion_manual']  # Campo real del modelo


@extend_schema_view(
    list=extend_schema(description="Listar datos de puertos de Zabbix"),
    retrieve=extend_schema(description="Obtener detalles de un puerto"),
)
class ZabbixPortDataViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para datos de puertos de Zabbix (solo lectura)"""
    serializer_class = ZabbixPortDataSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['olt', 'disponible', 'operativo_noc', 'estado_administrativo']
    search_fields = ['descripcion_zabbix', 'interface_name']
    
    def get_queryset(self):
        """Excluir puertos de OLTs eliminadas"""
        return ZabbixPortData.objects.select_related('olt').filter(olt__is_deleted=False)


# ============================================================================
# VIEWSETS DE PERSONAL
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar áreas"),
    retrieve=extend_schema(description="Obtener detalles de un área"),
)
class AreaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para áreas"""
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    permission_classes = [IsAuthenticated]


@extend_schema_view(
    list=extend_schema(description="Listar personal"),
    retrieve=extend_schema(description="Obtener detalles de personal"),
)
class PersonalViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para personal"""
    queryset = Personal.objects.select_related('area').all()
    serializer_class = PersonalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['area', 'estado']  # 'estado' en lugar de 'activo'
    search_fields = ['nombres', 'apellidos', 'cargo', 'documento_identidad']


# ============================================================================
# VIEWSETS DE CONFIGURACIÓN
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar configuraciones de Zabbix"),
    retrieve=extend_schema(description="Obtener detalles de configuración"),
    create=extend_schema(description="Crear configuración"),
    update=extend_schema(description="Actualizar configuración completa"),
    partial_update=extend_schema(description="Actualizar configuración parcialmente"),
)
class ZabbixConfigViewSet(viewsets.ModelViewSet):
    """ViewSet para configuración de Zabbix"""
    queryset = ZabbixConfiguration.objects.all()
    serializer_class = ZabbixConfigSerializer
    permission_classes = [IsAdminUser]


# ============================================================================
# VISTAS PARA ESTADÍSTICAS Y DASHBOARD
# ============================================================================

@extend_schema(
    description="Obtener estadísticas generales del sistema",
    responses={200: DashboardStatsSerializer}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """Vista para obtener estadísticas del dashboard"""
    hoy = timezone.now().date()
    
    # Estadísticas de OLTs
    total_olts = OLT.objects.count()
    olts_activas = OLT.objects.filter(habilitar_olt=True).count()
    
    # Estadísticas de Jobs
    total_jobs = SnmpJob.objects.count()
    jobs_activos = SnmpJob.objects.filter(enabled=True).count()
    
    # Estadísticas de Ejecuciones
    total_ejecuciones_hoy = Execution.objects.filter(
        created_at__date=hoy
    ).count()
    ejecuciones_exitosas_hoy = Execution.objects.filter(
        created_at__date=hoy,
        status='SUCCESS'
    ).count()
    ejecuciones_fallidas_hoy = Execution.objects.filter(
        created_at__date=hoy,
        status='FAILED'
    ).count()
    
    # Estadísticas de ONUs
    total_onus = OnuInventory.objects.filter(active=True).count()
    
    # Estadísticas de ODF
    total_odfs = ODF.objects.count()
    hilos_ocupados = ODFHilos.objects.filter(estado='ocupado').count()
    hilos_disponibles = ODFHilos.objects.filter(estado='disponible').count()
    
    data = {
        'total_olts': total_olts,
        'olts_activas': olts_activas,
        'total_jobs': total_jobs,
        'jobs_activos': jobs_activos,
        'total_ejecuciones_hoy': total_ejecuciones_hoy,
        'ejecuciones_exitosas_hoy': ejecuciones_exitosas_hoy,
        'ejecuciones_fallidas_hoy': ejecuciones_fallidas_hoy,
        'total_onus': total_onus,
        'total_odfs': total_odfs,
        'hilos_ocupados': hilos_ocupados,
        'hilos_disponibles': hilos_disponibles,
    }
    
    serializer = DashboardStatsSerializer(data)
    return Response(serializer.data)


@extend_schema(
    description="Verificar el estado de salud de la API",
    responses={200: {'type': 'object', 'properties': {
        'status': {'type': 'string'},
        'timestamp': {'type': 'string'},
        'version': {'type': 'string'},
    }}}
)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Vista para verificar el estado de salud de la API"""
    return Response({
        'status': 'ok',
        'timestamp': timezone.now().isoformat(),
        'version': '2.0.0',
    })


# ============================================================================
# VIEWS PARA ONT (Vista de PostgreSQL)
# ============================================================================

@extend_schema(
    description="Obtener información de ONUs desde la vista onu_info_view de PostgreSQL",
    parameters=[
        OpenApiParameter(name='page', type=OpenApiTypes.INT, description='Número de página', required=False),
        OpenApiParameter(name='page_size', type=OpenApiTypes.INT, description='Tamaño de página', required=False),
        OpenApiParameter(name='search', type=OpenApiTypes.STR, description='Búsqueda en campos de texto', required=False),
        OpenApiParameter(name='olt_id', type=OpenApiTypes.INT, description='Filtrar por OLT', required=False),
    ],
    responses={200: OpenApiTypes.OBJECT}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def onu_info_view_list(request):
    """
    Vista para consultar la vista de PostgreSQL onu_info_view.
    No modela la tabla, solo consulta la vista directamente.
    Detecta las columnas dinámicamente para construir filtros correctamente.
    """
    try:
        # Obtener parámetros de paginación
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        search = request.query_params.get('search', '').strip()
        olt_id = request.query_params.get('olt_id')
        estado_filter = request.query_params.get('estado', '').strip().lower()  # 'activo' o 'suspendido'
        modelo_filter = request.query_params.get('modelo', '').strip()
        distancia_filter = request.query_params.get('distancia', '').strip()
        plan_filter = request.query_params.get('plan', '').strip()
        
        # Validar parámetros
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 1000:
            page_size = 50
        
        # Primero obtener las columnas de la vista para construir filtros dinámicamente
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM onu_info_view LIMIT 0")
            available_columns = [col[0] for col in cursor.description]
        
        # Construir la consulta SQL base
        base_query = "SELECT * FROM onu_info_view"
        conditions = []
        params = []
        
        # Agregar filtros solo si las columnas existen
        if olt_id:
            # Buscar columnas relacionadas con OLT (olt_id, olt, host, olt_name, etc.)
            # El usuario mencionó que puede ser "host" en lugar de "olt_id"
            olt_column = None
            possible_olt_columns = ['olt_id', 'olt', 'host', 'olt_name', 'olt_abreviatura']
            
            for col_name in possible_olt_columns:
                if col_name in available_columns:
                    olt_column = col_name
                    break
            
            # Si no encontramos ninguna, buscar columnas que contengan "olt" o "host"
            if not olt_column:
                for col in available_columns:
                    if 'olt' in col.lower() or 'host' in col.lower():
                        olt_column = col
                        break
            
            if olt_column:
                # Determinar el tipo de dato de la columna consultando information_schema
                column_type = None
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT data_type 
                            FROM information_schema.columns 
                            WHERE table_name = 'onu_info_view' 
                            AND column_name = %s
                        """, [olt_column])
                        result = cursor.fetchone()
                        if result:
                            column_type = result[0]
                except Exception as e:
                    logger.warning(f"Error obteniendo tipo de columna {olt_column}: {str(e)}")
                
                # Aplicar filtro según el tipo de dato
                if column_type in ['integer', 'bigint', 'smallint']:
                    # Columna numérica: filtrar por ID directamente
                    conditions.append(f"{olt_column} = %s")
                    params.append(int(olt_id))
                elif column_type in ['character varying', 'text', 'varchar']:
                    # Columna de texto: obtener OLT y buscar por abreviatura o IP
                    try:
                        olt_obj = OLT.objects.get(id=int(olt_id))
                        # Buscar por abreviatura o IP
                        conditions.append(f"({olt_column} = %s OR {olt_column} = %s)")
                        params.extend([olt_obj.abreviatura, olt_obj.ip_address])
                    except OLT.DoesNotExist:
                        logger.warning(f"OLT con id {olt_id} no encontrada")
                else:
                    # Tipo desconocido, intentar como texto por defecto
                    try:
                        olt_obj = OLT.objects.get(id=int(olt_id))
                        conditions.append(f"({olt_column} = %s OR {olt_column} = %s)")
                        params.extend([olt_obj.abreviatura, olt_obj.ip_address])
                    except OLT.DoesNotExist:
                        logger.warning(f"OLT con id {olt_id} no encontrada")
            else:
                # Log para debug
                logger.warning(f"No se encontró columna OLT. Columnas disponibles: {available_columns}")
        
        if search:
            # Búsqueda en columnas de texto y numéricas disponibles
            # Incluir Onudesc y otros campos comunes
            search_columns = [
                col for col in available_columns 
                if col not in ['id'] and any(keyword in col.lower() for keyword in 
                    ['normalized', 'mac', 'serial', 'description', 'desc', 'name', 'abreviatura', 'ip', 
                     'onudesc', 'onu_desc', 'snmp_description', 'modelo', 'plan', 'index', 'snmpindex'])
            ]
            
            if search_columns:
                search_conditions = []
                search_param = f"%{search}%"
                
                for col in search_columns:
                    # Verificar el tipo de dato de la columna
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute("""
                                SELECT data_type 
                                FROM information_schema.columns 
                                WHERE table_name = 'onu_info_view' 
                                AND column_name = %s
                            """, [col])
                            result = cursor.fetchone()
                            
                            if result:
                                col_type = result[0]
                                # Si es numérica, buscar como número y como texto
                                if col_type in ['integer', 'bigint', 'smallint', 'numeric']:
                                    # Buscar como número exacto y como texto
                                    search_conditions.append(f"({col} = %s OR CAST({col} AS TEXT) ILIKE %s)")
                                    # Intentar convertir el search a número si es posible
                                    try:
                                        search_num = int(search)
                                        params.append(search_num)
                                    except:
                                        params.append(None)  # Si no es número, usar None para que no coincida
                                    params.append(search_param)
                                else:
                                    # Si es texto, buscar normalmente
                                    search_conditions.append(f"CAST({col} AS TEXT) ILIKE %s")
                                    params.append(search_param)
                    except:
                        # Si falla la verificación, intentar como texto por defecto
                        search_conditions.append(f"CAST({col} AS TEXT) ILIKE %s")
                        params.append(search_param)
                
                if search_conditions:
                    conditions.append(f"({' OR '.join(search_conditions)})")
        
        # Agregar filtros adicionales (modelo, distancia, plan)
        if modelo_filter:
            # Buscar columna de modelo
            modelo_columns = [col for col in available_columns if any(keyword in col.lower() for keyword in ['modelo', 'model'])]
            if modelo_columns:
                modelo_col = modelo_columns[0]
                conditions.append(f"{modelo_col} = %s")
                params.append(modelo_filter)
        
        if distancia_filter:
            # Buscar columna de distancia
            distancia_columns = [col for col in available_columns if any(keyword in col.lower() for keyword in ['distancia', 'distance'])]
            if distancia_columns:
                distancia_col = distancia_columns[0]
                conditions.append(f"{distancia_col} = %s")
                params.append(distancia_filter)
        
        if plan_filter:
            # Buscar columna de plan
            plan_columns = [col for col in available_columns if any(keyword in col.lower() for keyword in ['plan'])]
            if plan_columns:
                plan_col = plan_columns[0]
                conditions.append(f"{plan_col} = %s")
                params.append(plan_filter)
        
        # Agregar filtro de estado si está presente
        if estado_filter:
            # Buscar columna de estado
            estado_columns = [col for col in available_columns if any(keyword in col.lower() for keyword in ['estado', 'status', 'state', 'presence', 'act_susp', 'last_state', 'last_state_value'])]
            if estado_columns:
                estado_col = estado_columns[0]
                
                # Determinar el tipo de dato de la columna de estado
                estado_col_type = None
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT data_type 
                            FROM information_schema.columns 
                            WHERE table_name = 'onu_info_view' 
                            AND column_name = %s
                        """, [estado_col])
                        result = cursor.fetchone()
                        if result:
                            estado_col_type = result[0]
                except:
                    pass
                
                # Aplicar filtro según el tipo
                if estado_filter == 'activo':
                    if estado_col_type in ['integer', 'bigint', 'smallint']:
                        conditions.append(f"{estado_col} = 1")
                    else:
                        conditions.append(f"({estado_col} = '1' OR {estado_col} = 'ACTIVO' OR {estado_col} ILIKE '%activo%' OR {estado_col} = 'ENABLED')")
                elif estado_filter == 'suspendido':
                    if estado_col_type in ['integer', 'bigint', 'smallint']:
                        conditions.append(f"{estado_col} = 2")
                    else:
                        conditions.append(f"({estado_col} = '2' OR {estado_col} = 'SUSPENDIDO' OR {estado_col} ILIKE '%suspendido%' OR {estado_col} = 'DISABLED')")
        
        # Construir WHERE si hay condiciones
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        # Obtener el total de registros
        count_query = f"SELECT COUNT(*) FROM ({base_query}) AS subquery"
        with connection.cursor() as cursor:
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
        
        # Obtener estadísticas adicionales (total, suspendidos, etc.)
        stats = {}
        try:
            # Contar total sin filtros
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM onu_info_view")
                stats['total'] = cursor.fetchone()[0]
            
            # Buscar columna de estado (puede ser estado, status, last_state_label, last_state_value, act_susp, etc.)
            # El usuario indicó que "Act Susp" es igual a "-" y los valores numéricos son: 1=Activo, 2=Suspendido
            estado_columns = [col for col in available_columns if any(keyword in col.lower() for keyword in ['estado', 'status', 'state', 'presence', 'act_susp', 'last_state', 'last_state_value'])]
            if estado_columns:
                estado_col = estado_columns[0]
                
                # Determinar el tipo de dato de la columna de estado
                estado_col_type = None
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT data_type 
                            FROM information_schema.columns 
                            WHERE table_name = 'onu_info_view' 
                            AND column_name = %s
                        """, [estado_col])
                        result = cursor.fetchone()
                        if result:
                            estado_col_type = result[0]
                except Exception as e:
                    logger.warning(f"Error obteniendo tipo de columna de estado: {str(e)}")
                
                # Contar suspendidos - El usuario indicó que 2 = Suspendido
                try:
                    with connection.cursor() as cursor:
                        if estado_col_type in ['integer', 'bigint', 'smallint']:
                            # Columna numérica: buscar directamente por 2
                            cursor.execute(f"SELECT COUNT(*) FROM onu_info_view WHERE {estado_col} = 2")
                        else:
                            # Columna de texto: buscar por diferentes valores posibles
                            cursor.execute(f"""
                                SELECT COUNT(*) FROM onu_info_view 
                                WHERE {estado_col} = '2'
                                   OR {estado_col} = 'SUSPENDIDO' 
                                   OR {estado_col} ILIKE '%suspendido%'
                                   OR {estado_col} = 'DISABLED'
                            """)
                        stats['suspendidos'] = cursor.fetchone()[0]
                except Exception as e:
                    logger.warning(f"Error contando suspendidos: {str(e)}")
                
                # Contar activos - El usuario indicó que 1 = Activo
                try:
                    with connection.cursor() as cursor:
                        if estado_col_type in ['integer', 'bigint', 'smallint']:
                            # Columna numérica: buscar directamente por 1
                            cursor.execute(f"SELECT COUNT(*) FROM onu_info_view WHERE {estado_col} = 1")
                        else:
                            # Columna de texto: buscar por diferentes valores posibles
                            cursor.execute(f"""
                                SELECT COUNT(*) FROM onu_info_view 
                                WHERE {estado_col} = '1'
                                   OR {estado_col} = 'ACTIVO' 
                                   OR {estado_col} ILIKE '%activo%'
                                   OR {estado_col} = 'ENABLED'
                            """)
                        stats['activos'] = cursor.fetchone()[0]
                except Exception as e:
                    logger.warning(f"Error contando activos: {str(e)}")
            
            # Buscar otras columnas útiles para estadísticas
            # Contar por presencia si existe
            presence_columns = [col for col in available_columns if 'presence' in col.lower()]
            if presence_columns and 'suspendidos' not in stats:
                try:
                    presence_col = presence_columns[0]
                    with connection.cursor() as cursor:
                        cursor.execute(f"SELECT COUNT(*) FROM onu_info_view WHERE {presence_col} = 'DISABLED'")
                        stats['suspendidos'] = cursor.fetchone()[0]
                    with connection.cursor() as cursor:
                        cursor.execute(f"SELECT COUNT(*) FROM onu_info_view WHERE {presence_col} = 'ENABLED'")
                        stats['activos'] = cursor.fetchone()[0]
                except:
                    pass
                    
        except Exception as stats_error:
            logger.warning(f"Error obteniendo estadísticas: {str(stats_error)}")
        
        # Incluir información de debug (columnas disponibles) en modo desarrollo
        debug_info = {}
        if request.query_params.get('debug') == 'true':
            debug_info['available_columns'] = available_columns
        
        # Calcular offset y limit para paginación
        offset = (page - 1) * page_size
        
        # Determinar columna de ordenamiento (preferir id, sino la primera columna)
        order_by = 'id' if 'id' in available_columns else available_columns[0] if available_columns else '1'
        query = f"{base_query} ORDER BY {order_by} LIMIT %s OFFSET %s"
        params.extend([page_size, offset])
        
        # Ejecutar la consulta principal
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
        
        # Convertir resultados a diccionarios
        results = [dict(zip(columns, row)) for row in rows]
        
        # Calcular información de paginación
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
        has_next = page < total_pages
        has_previous = page > 1
        
        # Preparar respuesta
        response_data = {
            'count': total_count,
            'next': f"?page={page + 1}&page_size={page_size}" if has_next else None,
            'previous': f"?page={page - 1}&page_size={page_size}" if has_previous else None,
            'current_page': page,
            'total_pages': total_pages,
            'page_size': page_size,
            'columns': available_columns,  # Incluir columnas disponibles
            'stats': stats,  # Incluir estadísticas
            'results': results
        }
        
        # Agregar debug info si está habilitado
        if debug_info:
            response_data['debug'] = debug_info
        
        # Agregar filtros a next/previous si existen
        if olt_id:
            filter_params = f"&olt_id={olt_id}"
            if response_data['next']:
                response_data['next'] += filter_params
            if response_data['previous']:
                response_data['previous'] += filter_params
        
        if search:
            filter_params = f"&search={search}"
            if response_data['next']:
                response_data['next'] += filter_params
            if response_data['previous']:
                response_data['previous'] += filter_params
        
        return Response(response_data)
    
    except Exception as e:
        logger.error(f"Error consultando onu_info_view: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al consultar la vista: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    description="Obtener estadísticas de ONUs agrupadas por OLT desde modelos de Django",
    responses={200: OpenApiTypes.OBJECT}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def onu_stats_by_olt(request):
    """
    Vista para obtener estadísticas de ONUs agrupadas por OLT.
    Usa los modelos de Django directamente (OnuInventory y OnuStatus).
    Retorna total, activos y suspendidos por cada OLT.
    """
    try:
        # Obtener todas las OLTs
        olts = OLT.objects.all().order_by('abreviatura')
        
        stats_by_olt = []
        
        # Para cada OLT, obtener estadísticas desde los modelos de Django
        for olt in olts:
            try:
                # Para la TABLA: Contar ENABLED y DISABLED (basado en presence)
                enabled = OnuStatus.objects.filter(
                    olt=olt,
                    presence='ENABLED'
                ).count()
                
                disabled = OnuStatus.objects.filter(
                    olt=olt,
                    presence='DISABLED'
                ).count()
                
                # El TOTAL para la tabla debe ser ENABLED + DISABLED
                total_table = enabled + disabled
                
                # Si no hay datos en OnuStatus, intentar desde OnuInventory como fallback
                if total_table == 0:
                    enabled = OnuInventory.objects.filter(olt=olt, active=True).count()
                    disabled = OnuInventory.objects.filter(olt=olt, active=False).count()
                    total_table = enabled + disabled
                
                # Para el GRÁFICO: Contar ACTIVOS y SUSPENDIDOS (basado en last_state_value)
                # IMPORTANTE: Solo contar los que tienen presence='ENABLED'
                # porque el gráfico muestra el estado operativo de las ONUs habilitadas
                activos = OnuStatus.objects.filter(
                    olt=olt,
                    last_state_value=1,
                    presence='ENABLED'  # Solo contar las habilitadas
                ).count()
                
                suspendidos = OnuStatus.objects.filter(
                    olt=olt,
                    last_state_value=2,
                    presence='ENABLED'  # Solo contar las habilitadas
                ).count()
                
                # El TOTAL para el gráfico debe ser ACTIVOS + SUSPENDIDOS (solo de las habilitadas)
                total_graph = activos + suspendidos
                
                # Si no hay last_state_value, usar enabled como aproximación para activos
                # y 0 para suspendidos (porque si no hay last_state_value, no podemos saber)
                if total_graph == 0:
                    # Si no hay datos de last_state_value, usar enabled como aproximación
                    activos = enabled
                    suspendidos = 0
                    total_graph = activos + suspendidos
                
                stats_by_olt.append({
                    'olt': {
                        'id': olt.id,
                        'abreviatura': olt.abreviatura,
                        'ip_address': olt.ip_address,
                        'name': olt.abreviatura or olt.ip_address
                    },
                    'total': total_table,  # Total para la tabla (ENABLED + DISABLED)
                    'total_graph': total_graph,  # Total para el gráfico (ACTIVOS + SUSPENDIDOS)
                    'activos': activos,
                    'suspendidos': suspendidos,
                    'enabled': enabled,
                    'disabled': disabled
                })
                
            except Exception as e:
                logger.warning(f"Error obteniendo estadísticas para OLT {olt.abreviatura}: {str(e)}", exc_info=True)
                # Agregar OLT con valores en 0 si hay error
                stats_by_olt.append({
                    'olt': {
                        'id': olt.id,
                        'abreviatura': olt.abreviatura,
                        'ip_address': olt.ip_address,
                        'name': olt.abreviatura or olt.ip_address
                    },
                    'total': 0,
                    'activos': 0,
                    'suspendidos': 0
                })
        
        return Response({
            'stats': stats_by_olt
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error al obtener estadísticas por OLT: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al obtener estadísticas: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# VIEWSETS DE WORKFLOWS
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar plantillas de workflow"),
    retrieve=extend_schema(description="Obtener detalles de una plantilla"),
    create=extend_schema(description="Crear nueva plantilla"),
    update=extend_schema(description="Actualizar plantilla completa"),
    partial_update=extend_schema(description="Actualizar plantilla parcialmente"),
    destroy=extend_schema(description="Eliminar plantilla"),
)
class WorkflowTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet para plantillas de workflow"""
    queryset = WorkflowTemplate.objects.prefetch_related('template_nodes').all()
    serializer_class = WorkflowTemplateSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def create(self, request, *args, **kwargs):
        """Crear plantilla con manejo de excepciones"""
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except ValidationError as e:
            # Errores de validación del serializer (DRF)
            error_detail = e.detail if hasattr(e, 'detail') else str(e)
            if isinstance(error_detail, dict):
                # Formatear errores de validación
                formatted_errors = []
                for field, errors in error_detail.items():
                    if isinstance(errors, list):
                        # Extraer el mensaje de ErrorDetail si es necesario
                        error_messages = []
                        for error in errors:
                            if hasattr(error, 'code') and hasattr(error, 'string'):
                                error_messages.append(str(error))
                            else:
                                error_messages.append(str(error))
                        formatted_errors.extend([f"{field}: {msg}" for msg in error_messages])
                    else:
                        formatted_errors.append(f"{field}: {errors}")
                error_message = "; ".join(formatted_errors)
            else:
                error_message = str(error_detail)
            logger.warning(f"Error de validación creando plantilla: {error_message}")
            return Response(
                {'error': error_message, 'detail': error_detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        except ValueError as e:
            logger.warning(f"ValueError creando plantilla: {e}")
            return Response(
                {'error': str(e), 'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creando plantilla: {e}", exc_info=True)
            return Response(
                {'error': str(e), 'detail': 'Error interno del servidor al crear la plantilla'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @extend_schema(
        description="Obtener nodos de una plantilla",
        responses={200: WorkflowTemplateNodeSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def nodes(self, request, pk=None):
        """Obtener nodos de una plantilla"""
        template = self.get_object()
        nodes = template.template_nodes.all()
        serializer = WorkflowTemplateNodeSerializer(nodes, many=True)
        return Response({'nodes': serializer.data})
    
    @extend_schema(
        description="Aplicar plantilla a múltiples OLTs",
        request={'application/json': {'type': 'object', 'properties': {'olt_ids': {'type': 'array', 'items': {'type': 'integer'}}}}},
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}}
    )
    @action(detail=True, methods=['post'], url_path='apply-to-olts')
    def apply_to_olts(self, request, pk=None):
        """Aplicar plantilla a múltiples OLTs"""
        template = self.get_object()
        olt_ids = request.data.get('olt_ids', [])
        
        if not olt_ids:
            return Response(
                {'error': 'Debes proporcionar al menos una OLT'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            stats = WorkflowTemplateService.apply_template_to_olts(template.id, olt_ids)
            
            # Construir mensaje detallado
            message_parts = [
                f'Plantilla "{template.name}" aplicada a {stats["olts_processed"]} OLT(s)',
                f'Nodos creados: {stats["nodes_created"]}',
                f'Nodos vinculados: {stats["nodes_linked"]}',
            ]
            
            if stats.get('nodes_incompatible', 0) > 0:
                message_parts.append(
                    f'⚠️ Nodos incompatibles (no aplicados): {stats["nodes_incompatible"]}'
                )
            
            if stats.get('errors'):
                message_parts.append(f'Errores: {len(stats["errors"])}')
            
            return Response({
                'message': '. '.join(message_parts),
                'stats': stats
            })
        except Exception as e:
            logger.error(f"Error aplicando plantilla {template.id} a OLTs: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(
        description="Obtener OLTs asignadas a una plantilla",
        responses={200: {'type': 'object', 'properties': {'olts': {'type': 'array'}}}}
    )
    @action(detail=True, methods=['get'], url_path='assigned-olts')
    def assigned_olts(self, request, pk=None):
        """Obtener OLTs asignadas a una plantilla (excluyendo eliminadas)"""
        template = self.get_object()
        links = template.workflow_links.select_related('workflow__olt').filter(
            workflow__olt__is_deleted=False  # ✅ Excluir OLTs eliminadas
        ).all()
        
        olts_data = []
        for link in links:
            olt = link.workflow.olt
            if olt.is_deleted:  # Doble verificación por seguridad
                continue
            olts_data.append({
                'id': olt.id,
                'abreviatura': olt.abreviatura,
                'ip_address': olt.ip_address,
                'marca': olt.marca.nombre if olt.marca else None,
                'modelo': olt.modelo.nombre if olt.modelo else None,
                'workflow_id': link.workflow.id,
                'auto_sync': link.auto_sync,
                'created_at': link.created_at,
            })
        
        return Response({'olts': olts_data})
    
    @extend_schema(
        description="Agregar OLTs a una plantilla",
        request={'application/json': {'type': 'object', 'properties': {'olt_ids': {'type': 'array', 'items': {'type': 'integer'}}, 'auto_sync': {'type': 'boolean'}}}},
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}}
    )
    @action(detail=True, methods=['post'], url_path='add-olts')
    def add_olts(self, request, pk=None):
        """Agregar OLTs a una plantilla"""
        template = self.get_object()
        olt_ids = request.data.get('olt_ids', [])
        auto_sync = request.data.get('auto_sync', True)
        
        if not olt_ids:
            return Response(
                {'error': 'Debes proporcionar al menos una OLT'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            stats = WorkflowTemplateService.apply_template_to_olts(template.id, olt_ids, auto_sync=auto_sync)
            
            return Response({
                'message': f'Plantilla "{template.name}" aplicada a {stats["olts_processed"]} OLT(s)',
                'stats': stats
            })
        except Exception as e:
            logger.error(f"Error agregando OLTs a plantilla {template.id}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(
        description="Quitar OLTs de una plantilla",
        request={'application/json': {'type': 'object', 'properties': {'workflow_ids': {'type': 'array', 'items': {'type': 'integer'}}, 'delete_nodes': {'type': 'boolean'}}}},
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}}
    )
    @action(detail=True, methods=['post'], url_path='remove-olts')
    def remove_olts(self, request, pk=None):
        """Quitar OLTs de una plantilla"""
        template = self.get_object()
        workflow_ids = request.data.get('workflow_ids', [])
        delete_nodes = request.data.get('delete_nodes', False)
        
        if not workflow_ids:
            return Response(
                {'error': 'Debes proporcionar al menos un workflow'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            total_stats = {
                'nodes_unlinked': 0,
                'nodes_deleted': 0,
                'workflows_unlinked': 0,
            }
            
            for workflow_id in workflow_ids:
                stats = WorkflowTemplateService.unlink_template_from_workflow(
                    template.id, workflow_id, delete_nodes=delete_nodes
                )
                total_stats['nodes_unlinked'] += stats['nodes_unlinked']
                total_stats['nodes_deleted'] += stats['nodes_deleted']
                total_stats['workflows_unlinked'] += 1
            
            return Response({
                'message': f'Plantilla "{template.name}" desvinculada de {total_stats["workflows_unlinked"]} workflow(s)',
                'stats': total_stats
            })
        except Exception as e:
            logger.error(f"Error quitando OLTs de plantilla {template.id}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @extend_schema(
        description="Sincronizar manualmente cambios de plantilla a workflows vinculados",
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}, 'stats': {'type': 'object'}}}}
    )
    @action(detail=True, methods=['post'], url_path='sync-changes')
    def sync_changes(self, request, pk=None):
        """Sincronizar manualmente cambios de plantilla a workflows vinculados"""
        template = self.get_object()
        
        try:
            stats = WorkflowTemplateService.sync_template_changes(template.id)
            
            message_parts = [
                f'Plantilla "{template.name}" sincronizada correctamente',
                f'Workflows sincronizados: {stats.get("workflows_synced", 0)}',
                f'Nodos actualizados: {stats.get("nodes_synced", 0)}',
            ]
            
            if stats.get('nodes_not_found', 0) > 0:
                message_parts.append(f'⚠️ Nodos no encontrados: {stats["nodes_not_found"]}')
            
            return Response({
                'message': '. '.join(message_parts),
                'stats': stats
            })
        except Exception as e:
            logger.error(f"Error sincronizando cambios de plantilla {template.id}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def update(self, request, *args, **kwargs):
        """Actualizar plantilla y sincronizar cambios automáticamente"""
        response = super().update(request, *args, **kwargs)
        
        # Sincronizar cambios automáticamente si la actualización fue exitosa
        if response.status_code == 200:
            template_id = kwargs.get('pk')
            try:
                WorkflowTemplateService.sync_template_changes(template_id)
                logger.info(f"Plantilla {template_id} actualizada y sincronizada automáticamente")
            except Exception as e:
                logger.error(f"Error sincronizando cambios de plantilla {template_id}: {e}", exc_info=True)
        
        return response


@extend_schema_view(
    list=extend_schema(description="Listar nodos de plantilla"),
    retrieve=extend_schema(description="Obtener detalles de un nodo"),
    create=extend_schema(description="Crear nuevo nodo"),
    update=extend_schema(description="Actualizar nodo completo"),
    partial_update=extend_schema(description="Actualizar nodo parcialmente"),
    destroy=extend_schema(description="Eliminar nodo"),
)
class WorkflowTemplateNodeViewSet(viewsets.ModelViewSet):
    """ViewSet para nodos de plantilla de workflow"""
    queryset = WorkflowTemplateNode.objects.select_related('template', 'oid').all()
    serializer_class = WorkflowTemplateNodeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['template', 'enabled']


@extend_schema_view(
    list=extend_schema(description="Listar workflows de OLT"),
    retrieve=extend_schema(description="Obtener detalles de un workflow"),
    create=extend_schema(description="Crear nuevo workflow"),
    update=extend_schema(description="Actualizar workflow completo"),
    partial_update=extend_schema(description="Actualizar workflow parcialmente"),
    destroy=extend_schema(description="Eliminar workflow"),
)
class OLTWorkflowViewSet(viewsets.ModelViewSet):
    """ViewSet para workflows de OLT"""
    serializer_class = OLTWorkflowSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['olt', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Excluir workflows de OLTs eliminadas"""
        return OLTWorkflow.objects.select_related('olt').prefetch_related('nodes').filter(olt__is_deleted=False)
    
    @extend_schema(
        description="Obtener nodos de un workflow con estadísticas de ejecuciones",
        responses={200: WorkflowNodeSerializer(many=True)}
    )
    @action(detail=True, methods=['get'])
    def nodes(self, request, pk=None):
        """Obtener nodos de un workflow con estadísticas de ejecuciones (cuota actual)"""
        from django.utils import timezone
        from datetime import timedelta
        from executions.models import Execution
        import pytz
        
        workflow = self.get_object()
        nodes = workflow.nodes.select_related('master_node', 'template_node', 'template_node__template').all()
        
        # Obtener estadísticas de ejecuciones para cada nodo
        now = timezone.now()
        # ✅ CORREGIDO: Filtrar ejecuciones desde el inicio de la hora actual
        # Por ejemplo, si son las 16:53, mostrar desde las 16:00 hasta ahora
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        peru_tz = pytz.timezone('America/Lima')
        
        nodes_data = []
        for node in nodes:
            node_dict = WorkflowNodeSerializer(node).data
            
            # Calcular ejecuciones de la última hora del nodo (todos los estados)
            from executions.models import Execution
            
            executions_last_hour = Execution.objects.filter(
                workflow_node=node,
                created_at__gte=hour_start
            ).count()
            
            # Log de depuración
            logger.debug(f"Nodo {node.name} (ID: {node.id}): {executions_last_hour} ejecuciones en última hora")
            
            node_dict['execution_stats'] = {
                'executions_last_hour': executions_last_hour
            }
            
            nodes_data.append(node_dict)
        
        return Response({'nodes': nodes_data})


@extend_schema_view(
    list=extend_schema(description="Listar nodos de workflow"),
    retrieve=extend_schema(description="Obtener detalles de un nodo"),
    create=extend_schema(description="Crear nuevo nodo"),
    update=extend_schema(description="Actualizar nodo completo"),
    partial_update=extend_schema(description="Actualizar nodo parcialmente"),
    destroy=extend_schema(description="Eliminar nodo"),
)
class WorkflowNodeViewSet(viewsets.ModelViewSet):
    """ViewSet para nodos de workflow"""
    queryset = WorkflowNode.objects.select_related('workflow', 'template', 'template_node').all()
    serializer_class = WorkflowNodeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['workflow', 'enabled']
    
    def destroy(self, request, *args, **kwargs):
        """Eliminar nodo - previene eliminación de nodos vinculados a plantillas"""
        instance = self.get_object()
        
        # Prevenir eliminación de nodos vinculados a plantillas
        if instance.template_node:
            from rest_framework.response import Response
            from rest_framework import status
            return Response(
                {
                    'error': f'No se puede eliminar este nodo porque está vinculado a la plantilla "{instance.template_node.template.name}". '
                            f'Para eliminar el nodo, debes eliminarlo desde la plantilla correspondiente.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return super().destroy(request, *args, **kwargs)


# ============================================================================
# VIEWSETS DE CONFIGURACIÓN
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar configuraciones del sistema"),
    retrieve=extend_schema(description="Obtener detalles de una configuración"),
    create=extend_schema(description="Crear nueva configuración"),
    update=extend_schema(description="Actualizar configuración completa"),
    partial_update=extend_schema(description="Actualizar configuración parcialmente"),
    destroy=extend_schema(description="Eliminar configuración"),
)
class ConfiguracionSistemaViewSet(viewsets.ModelViewSet):
    """ViewSet para configuraciones del sistema"""
    queryset = ConfiguracionSistema.objects.all()
    serializer_class = ConfiguracionSistemaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['nombre', 'descripcion']
    filterset_fields = ['categoria', 'activo', 'modo_prueba']
    ordering_fields = ['nombre', 'categoria', 'fecha_modificacion']
    ordering = ['-fecha_modificacion']
    
    @extend_schema(
        description="Obtener el estado del modo prueba",
        responses={200: {'type': 'object', 'properties': {'modo_prueba': {'type': 'boolean'}}}}
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def modo_prueba(self, request):
        """Obtener el estado del modo prueba"""
        try:
            # Verificar que el método estático existe y funciona
            if not hasattr(ConfiguracionSistema, 'is_modo_prueba'):
                logger.error("ConfiguracionSistema.is_modo_prueba no existe")
                return Response({
                    'error': 'Método is_modo_prueba no disponible',
                    'modo_prueba': False
                }, status=500)
            
            is_active = ConfiguracionSistema.is_modo_prueba()
            return Response({'modo_prueba': bool(is_active)})
        except Exception as e:
            logger.error(f"Error en modo_prueba: {e}", exc_info=True)
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Traceback completo: {error_trace}")
            return Response({
                'error': f'Error obteniendo estado del modo prueba: {str(e)}',
                'modo_prueba': False
            }, status=500)
    
    @extend_schema(
        description="Activar o desactivar el modo prueba",
        request={'type': 'object', 'properties': {'modo_prueba': {'type': 'boolean'}}},
        responses={200: ConfiguracionSistemaSerializer}
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def toggle_modo_prueba(self, request):
        """
        Activar o desactivar el modo prueba.
        
        Al cambiar el modo prueba:
        - Se abortan todas las ejecuciones PENDING y RUNNING
        - Se recalculan los next_run_at de todos los nodos habilitados
          desde el momento de cambio + intervalo (nada se ejecuta inmediatamente)
        """
        modo_prueba = request.data.get('modo_prueba', False)
        
        # Obtener o crear configuración para modo prueba
        config, created = ConfiguracionSistema.objects.get_or_create(
            nombre='modo_prueba_global',
            defaults={
                'descripcion': 'Configuración global del modo prueba. Si está activo, todas las ejecuciones SNMP se simulan.',
                'tipo': 'boolean',
                'categoria': 'general',
                'activo': True,
                'modo_prueba': modo_prueba
            }
        )
        
        if not created:
            # Guardar el valor anterior para la señal
            old_modo_prueba = config.modo_prueba
            config.modo_prueba = modo_prueba
            config.activo = True
            # El save() disparará la señal post_save que abortará ejecuciones y recalculará tiempos
            config.save()
            
            logger.info(
                f"🔄 Modo prueba {'ACTIVADO' if modo_prueba else 'DESACTIVADO'} desde API. "
                f"Se abortarán ejecuciones y se recalcularán tiempos."
            )
        else:
            # Si es nueva, no hay cambio que detectar, pero igual logueamos
            logger.info(
                f"🔄 Modo prueba {'ACTIVADO' if modo_prueba else 'DESACTIVADO'} desde API (configuración nueva)."
            )
        
        serializer = self.get_serializer(config)
        return Response(serializer.data)
    
    @extend_schema(
        description="Obtener los porcentajes de simulación del modo prueba",
        responses={200: {'type': 'object', 'properties': {
            'porcentaje_exito': {'type': 'number'},
            'porcentaje_fallo': {'type': 'number'},
            'porcentaje_interrumpido': {'type': 'number'}
        }}}
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def porcentajes_simulacion(self, request):
        """Obtener los porcentajes de simulación"""
        try:
            porcentajes = ConfiguracionSistema.get_porcentajes_simulacion()
            return Response(porcentajes)
        except Exception as e:
            logger.error(f"Error en porcentajes_simulacion: {e}", exc_info=True)
            return Response({
                'error': f'Error obteniendo porcentajes: {str(e)}',
                'porcentaje_exito': 80.0,
                'porcentaje_fallo': 15.0,
                'porcentaje_interrumpido': 5.0
            }, status=500)
    
    @extend_schema(
        description="Configurar los porcentajes de simulación del modo prueba",
        request={'type': 'object', 'properties': {
            'porcentaje_exito': {'type': 'number'},
            'porcentaje_fallo': {'type': 'number'},
            'porcentaje_interrumpido': {'type': 'number'}
        }},
        responses={200: {'type': 'object', 'properties': {
            'porcentaje_exito': {'type': 'number'},
            'porcentaje_fallo': {'type': 'number'},
            'porcentaje_interrumpido': {'type': 'number'}
        }}}
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def set_porcentajes_simulacion(self, request):
        """Configurar los porcentajes de simulación"""
        try:
            porcentaje_exito = request.data.get('porcentaje_exito', 80.0)
            porcentaje_fallo = request.data.get('porcentaje_fallo', 15.0)
            porcentaje_interrumpido = request.data.get('porcentaje_interrumpido', 5.0)
            
            config = ConfiguracionSistema.set_porcentajes_simulacion(
                porcentaje_exito, porcentaje_fallo, porcentaje_interrumpido
            )
            porcentajes = ConfiguracionSistema.get_porcentajes_simulacion()
            return Response(porcentajes)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        except Exception as e:
            logger.error(f"Error en set_porcentajes_simulacion: {e}", exc_info=True)
            return Response({
                'error': f'Error actualizando porcentajes: {str(e)}'
            }, status=500)


# ============================================================================
# VIEWSET DE CONFIGURACIÓN SNMP
# ============================================================================

@extend_schema_view(
    list=extend_schema(description="Listar configuraciones SNMP"),
    retrieve=extend_schema(description="Obtener detalles de una configuración SNMP"),
    create=extend_schema(description="Crear una nueva configuración SNMP"),
    update=extend_schema(description="Actualizar una configuración SNMP"),
    partial_update=extend_schema(description="Actualizar parcialmente una configuración SNMP"),
    destroy=extend_schema(description="Eliminar una configuración SNMP"),
)
class ConfiguracionSNMPViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar configuraciones SNMP
    """
    queryset = ConfiguracionSNMP.objects.all()
    serializer_class = ConfiguracionSNMPSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tipo_operacion', 'activo', 'version']
    search_fields = ['nombre', 'tipo_operacion']
    ordering_fields = ['nombre', 'tipo_operacion', 'fecha_creacion', 'fecha_modificacion']
    ordering = ['tipo_operacion', 'nombre']
    pagination_class = CustomPageNumberPagination


# ============================================================================
# ENDPOINT: Futuras Ejecuciones de Workflows
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@extend_schema(
    description="Obtener lista de todas las futuras ejecuciones programadas de workflows",
    parameters=[
        OpenApiParameter(name='limit', type=OpenApiTypes.INT, description='Número máximo de ejecuciones a retornar (default: 50)'),
        OpenApiParameter(name='olt', type=OpenApiTypes.INT, description='Filtrar por OLT ID (opcional)'),
    ],
    responses={200: OpenApiResponse(description='Lista de ejecuciones programadas')}
)
def future_executions_list(request):
    """
    Lista todas las futuras ejecuciones programadas de todos los workflows activos
    """
    from snmp_jobs.models import WorkflowNode, OLTWorkflow
    from hosts.models import OLT
    from django.utils import timezone
    from datetime import timedelta
    import pytz
    
    peru_tz = pytz.timezone('America/Lima')
    now = timezone.now()
    now_peru = timezone.localtime(now, peru_tz)
    
    limit = int(request.query_params.get('limit', 50))
    olt_id = request.query_params.get('olt')
    
    # Obtener todos los workflows activos (excluyendo OLTs eliminadas)
    workflows = OLTWorkflow.objects.filter(
        is_active=True,
        olt__is_deleted=False  # ✅ Excluir workflows de OLTs eliminadas
    ).select_related('olt').order_by('olt__abreviatura')
    
    if olt_id:
        workflows = workflows.filter(olt_id=olt_id)
    
    all_executions = []
    
    for workflow in workflows:
        olt = workflow.olt
        if not olt or not olt.habilitar_olt:
            continue
        
        # Obtener todos los nodos del workflow (solo master/normales, no chain)
        nodes = WorkflowNode.objects.filter(
            workflow=workflow,
            enabled=True,
            is_chain_node=False,
            next_run_at__isnull=False
        ).select_related('template_node', 'template_node__template').order_by('next_run_at')
        
        for node in nodes:
            next_run_peru = timezone.localtime(node.next_run_at, peru_tz)
            time_until = (node.next_run_at - now).total_seconds()
            
            # Calcular tiempo relativo
            if time_until < 0:
                relative_time = f'Hace {int(abs(time_until) // 60)} min'
                status = 'PASADO'
            elif time_until < 60:
                relative_time = f'En {int(time_until)} seg'
                status = 'INMINENTE'
            elif time_until < 300:
                relative_time = f'En {int(time_until // 60)} min'
                status = 'PRÓXIMO'
            elif time_until < 3600:
                relative_time = f'En {int(time_until // 60)} min'
                status = 'PROGRAMADO'
            else:
                hours = int(time_until // 3600)
                mins = int((time_until % 3600) // 60)
                relative_time = f'En {hours}h {mins}m'
                status = 'FUTURO'
            
            interval_min = node.interval_seconds // 60 if node.interval_seconds else 0
            template_name = node.template_node.template.name if node.template_node and node.template_node.template else 'N/A'
            
            all_executions.append({
                'olt': {
                    'id': olt.id,
                    'abreviatura': olt.abreviatura,
                    'ip_address': olt.ip_address
                },
                'workflow': {
                    'id': workflow.id,
                    'name': workflow.name or f'Workflow {workflow.id}'
                },
                'node': {
                    'id': node.id,
                    'name': node.name,
                    'key': node.key
                },
                'template': template_name,
                'interval_minutes': interval_min,
                'interval_seconds': node.interval_seconds or 0,
                'next_run_at': node.next_run_at.isoformat(),
                'next_run_at_peru': next_run_peru.strftime('%Y-%m-%d %H:%M:%S'),
                'next_run_time': next_run_peru.strftime('%H:%M:%S'),
                'next_run_date': next_run_peru.strftime('%Y-%m-%d'),
                'relative_time': relative_time,
                'status': status,
                'time_until_seconds': int(time_until),
                'is_past': time_until < 0,
                'is_imminent': 0 <= time_until < 60
            })
    
    # Ordenar por próxima ejecución
    all_executions.sort(key=lambda x: x['time_until_seconds'])
    all_executions = all_executions[:limit]
    
    return Response({
        'current_time': now.isoformat(),
        'current_time_peru': now_peru.strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(all_executions),
        'limit': limit,
        'executions': all_executions
    }, status=status.HTTP_200_OK)
