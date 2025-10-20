"""
Views y ViewSets para la API REST de Facho Deluxe v2
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

# Importar modelos
from hosts.models import OLT
from brands.models import Brand
from olt_models.models import OLTModel
from snmp_jobs.models import SnmpJob
from executions.models import Execution
from discovery.models import OnuIndexMap, OnuStateLookup, OnuInventory
from oids.models import OID
from snmp_formulas.models import IndexFormula
from odf_management.models import ODF, ODFHilos, ZabbixPortData
from personal.models import Personal, Area
from zabbix_config.models import ZabbixConfiguration

# Importar serializers
from .serializers import (
    UserSerializer, BrandSerializer, OLTModelSerializer,
    OLTSerializer, OLTListSerializer, SNMPJobSerializer,
    ExecutionSerializer, OnuIndexMapSerializer, OnuStateLookupSerializer,
    OnuInventorySerializer, OnuInventoryListSerializer,
    OIDSerializer, IndexFormulaSerializer, ODFSerializer, ODFHilosSerializer,
    ZabbixPortDataSerializer, AreaSerializer, PersonalSerializer,
    ZabbixConfigSerializer, DashboardStatsSerializer
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
    """ViewSet para OLTs"""
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
    queryset = Execution.objects.select_related('snmp_job', 'olt').all()
    serializer_class = ExecutionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['snmp_job', 'olt', 'status']
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
    queryset = OnuInventory.objects.select_related(
        'olt', 
        'onu_index', 
        'onu_index__status'
    ).all()
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
    queryset = OnuIndexMap.objects.select_related('olt', 'odf_hilo').all()
    serializer_class = OnuIndexMapSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['olt', 'slot', 'port']
    search_fields = ['raw_index_key', 'normalized_id']


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
    queryset = OID.objects.all()
    serializer_class = OIDSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['nombre', 'oid']
    filterset_fields = ['marca', 'espacio']  # Campos reales del modelo


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
    queryset = ODF.objects.select_related('olt').all()
    serializer_class = ODFSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['numero_odf', 'nombre_troncal', 'descripcion']
    filterset_fields = ['olt']


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
    queryset = ZabbixPortData.objects.select_related('olt').all()
    serializer_class = ZabbixPortDataSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['olt', 'disponible', 'operativo_noc', 'estado_administrativo']
    search_fields = ['descripcion_zabbix', 'interface_name']


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

