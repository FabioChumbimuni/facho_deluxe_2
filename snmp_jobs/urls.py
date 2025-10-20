# snmp_jobs/urls.py
from django.urls import path
from django.contrib import admin
from . import views

app_name = 'snmp_jobs'

urlpatterns = [
    path('execution/status/<int:execution_id>/', views.execution_status, name='execution_status'),
    path('job/<int:job_id>/program/', views.program_job, name='program_job'),
]
