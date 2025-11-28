"""
URLs para API REST de Pollers
"""
from django.urls import path
from . import views

app_name = 'zabbix_pollers'

urlpatterns = [
    path('', views.get_pollers, name='pollers-list'),
    path('queue/', views.get_queue, name='pollers-queue'),
    path('stats/', views.get_stats, name='pollers-stats'),
    path('nodes/<int:node_id>/run/', views.run_node_manually, name='pollers-node-run'),
]

