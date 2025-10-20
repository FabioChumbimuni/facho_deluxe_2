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
    dashboard_stats, health_check
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

# URLs de la API
urlpatterns = [
    # Autenticación
    path('auth/login/', obtain_auth_token, name='api-token-auth'),
    
    # Estadísticas y salud
    path('dashboard/stats/', dashboard_stats, name='dashboard-stats'),
    path('health/', health_check, name='health-check'),
    
    # Documentación de la API
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Incluir las rutas del router
    path('', include(router.urls)),
]

