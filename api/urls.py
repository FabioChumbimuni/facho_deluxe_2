"""
URLs para la API REST de Facho Deluxe v2
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView
)

from .views import (
    UserViewSet, BrandViewSet, OLTModelViewSet, OLTViewSet,
    SNMPJobViewSet, ExecutionViewSet, OnuInventoryViewSet,
    OnuIndexMapViewSet, OnuStateLookupViewSet, OIDViewSet, IndexFormulaViewSet,
    ODFViewSet, ODFHilosViewSet, ZabbixPortDataViewSet,
    AreaViewSet, PersonalViewSet, ZabbixConfigViewSet,
    WorkflowTemplateViewSet, WorkflowTemplateNodeViewSet,
    OLTWorkflowViewSet, WorkflowNodeViewSet, ConfiguracionSistemaViewSet,
    ConfiguracionSNMPViewSet,
    dashboard_stats, health_check, onu_info_view_list, onu_stats_by_olt,
    future_executions_list
)

# Crear el router
router = DefaultRouter()

# Registrar los viewsets
router.register(r'users', UserViewSet, basename='user')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'olt-models', OLTModelViewSet, basename='olt-model')
router.register(r'olts', OLTViewSet, basename='olt')
router.register(r'snmp-jobs', SNMPJobViewSet, basename='snmp-job')
router.register(r'executions', ExecutionViewSet, basename='execution')
router.register(r'onus', OnuInventoryViewSet, basename='onu')
router.register(r'onu-index-map', OnuIndexMapViewSet, basename='onu-index-map')
router.register(r'onu-states', OnuStateLookupViewSet, basename='onu-state')
router.register(r'oids', OIDViewSet, basename='oid')
router.register(r'formulas', IndexFormulaViewSet, basename='formula')
router.register(r'odfs', ODFViewSet, basename='odf')
router.register(r'odf-hilos', ODFHilosViewSet, basename='odf-hilo')
router.register(r'zabbix-ports', ZabbixPortDataViewSet, basename='zabbix-port')
router.register(r'areas', AreaViewSet, basename='area')
router.register(r'personal', PersonalViewSet, basename='personal')
router.register(r'zabbix-config', ZabbixConfigViewSet, basename='zabbix-config')
router.register(r'workflow-templates', WorkflowTemplateViewSet, basename='workflow-template')
router.register(r'workflow-template-nodes', WorkflowTemplateNodeViewSet, basename='workflow-template-node')
router.register(r'olt-workflows', OLTWorkflowViewSet, basename='olt-workflow')
router.register(r'workflow-nodes', WorkflowNodeViewSet, basename='workflow-node')
router.register(r'configuracion-sistema', ConfiguracionSistemaViewSet, basename='configuracion-sistema')
router.register(r'configuracion-snmp', ConfiguracionSNMPViewSet, basename='configuracion-snmp')

# URLs de la API
urlpatterns = [
    # Autenticación
    path('auth/login/', obtain_auth_token, name='api-token-auth'),
    
    # Estadísticas y salud
    path('dashboard/stats/', dashboard_stats, name='dashboard-stats'),
    path('health/', health_check, name='health-check'),
    
    # ONT - Vista de PostgreSQL
    path('ont/info/', onu_info_view_list, name='ont-info-list'),
    path('ont/stats/', onu_stats_by_olt, name='ont-stats'),
    
    # Futuras ejecuciones de workflows
    path('workflows/future-executions/', future_executions_list, name='future-executions-list'),
    
    # Pollers Zabbix (reemplaza coordinador) - ANTES del router para evitar conflictos
    path('pollers/', include('zabbix_pollers.urls')),
    
    # Documentación de la API
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Incluir las rutas del router (al final para evitar conflictos)
    path('', include(router.urls)),
]

