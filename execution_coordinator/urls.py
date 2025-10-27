from django.urls import path
from . import views

app_name = 'execution_coordinator'

urlpatterns = [
    path('dashboard/', views.coordinator_dashboard, name='dashboard'),
    path('dashboard/data/', views.coordinator_dashboard_data, name='dashboard_data'),
]

