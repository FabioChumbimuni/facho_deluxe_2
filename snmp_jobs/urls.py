# snmp_jobs/urls.py
from django.urls import path

from . import views

app_name = 'snmp_jobs'

urlpatterns = [
    path('execution/status/<int:execution_id>/', views.execution_status, name='execution_status'),
    path('job/<int:job_id>/program/', views.program_job, name='program_job'),

    # URL de workflows/ eliminada - ahora se usa React + Vite como frontend
    # path('workflows/', views.workflow_builder, name='workflow_builder'),

    path('api/task-templates/', views.task_templates_api, name='task_templates_api'),
    path('api/workflows/', views.workflows_api, name='workflows_api'),
    path('api/workflows/<int:workflow_id>/', views.workflow_detail_api, name='workflow_detail_api'),
    path('api/workflows/<int:workflow_id>/nodes/', views.workflow_nodes_api, name='workflow_nodes_api'),
    path('api/workflows/<int:workflow_id>/nodes/<int:node_id>/', views.workflow_node_detail_api, name='workflow_node_detail_api'),
    path('api/workflows/<int:workflow_id>/nodes/from-job/', views.workflow_node_from_job_api, name='workflow_node_from_job_api'),
    path('api/workflows/<int:workflow_id>/edges/', views.workflow_edges_api, name='workflow_edges_api'),
    path('api/workflows/<int:workflow_id>/edges/<int:edge_id>/', views.workflow_edge_detail_api, name='workflow_edge_detail_api'),
    path('api/olts/<int:olt_id>/legacy-jobs/', views.legacy_jobs_api, name='legacy_jobs_api'),
    path('api/olts/<int:olt_id>/legacy-jobs/<int:job_host_id>/', views.legacy_job_detail_api, name='legacy_job_detail_api'),
    path('api/olts/<int:olt_id>/legacy-jobs/<int:job_host_id>/create-node/', views.create_node_from_legacy_api, name='create_node_from_legacy_api'),
    path('api/legacy-jobs/', views.legacy_jobs_global_api, name='legacy_jobs_global_api'),
    path('legacy/', views.legacy_control, name='legacy_control'),
    
    # API para Workflow Templates (Plantillas tipo Zabbix)
    path('api/workflow-templates/', views.workflow_templates_api, name='workflow_templates_api'),
    path('api/workflow-templates/<int:template_id>/', views.workflow_template_detail_api, name='workflow_template_detail_api'),
    path('api/workflow-templates/<int:template_id>/nodes/', views.workflow_template_nodes_api, name='workflow_template_nodes_api'),
    path('api/workflow-templates/<int:template_id>/nodes/<int:node_id>/', views.workflow_template_node_detail_api, name='workflow_template_node_detail_api'),
    path('api/workflow-templates/<int:template_id>/apply-to-olts/', views.apply_template_to_olts_api, name='apply_template_to_olts_api'),
    path('api/workflow-templates/<int:template_id>/sync/', views.sync_template_changes_api, name='sync_template_changes_api'),
    path('api/workflow-templates/<int:template_id>/workflows/<int:workflow_id>/unlink/', views.unlink_template_from_workflow_api, name='unlink_template_from_workflow_api'),
    
    # API para brands, models y OIDs
    path('api/brands/', views.brands_api, name='brands_api'),
    path('api/models/', views.models_api, name='models_api'),
    path('api/oids/', views.oids_api, name='oids_api'),
    path('api/oids/<int:oid_id>/', views.oid_detail_api, name='oid_detail_api'),
]
