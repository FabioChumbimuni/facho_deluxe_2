from django.urls import path
from . import views

app_name = 'configuracion_avanzada'

urlpatterns = [
    # Dashboard principal
    path('', views.configuracion_dashboard, name='dashboard'),
    
    # Configuraciones por categoría
    path('categoria/<str:categoria>/', views.configuracion_categoria, name='categoria'),
    
    # API para configuraciones
    path('api/configuracion/', views.ConfiguracionAPIView.as_view(), name='api_configuracion'),
    path('api/configuracion/<str:nombre>/', views.ConfiguracionAPIView.as_view(), name='api_configuracion_detail'),
    
    # Dashboards específicos
    path('snmp/', views.configuracion_snmp_dashboard, name='snmp_dashboard'),
]
