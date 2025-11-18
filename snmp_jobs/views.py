# snmp_jobs/views.py
import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from hosts.models import OLT
from executions.models import Execution
from brands.models import Brand
from olt_models.models import OLTModel
from oids.models import OID
from .models import (
    SnmpJob,
    SnmpJobHost,
    TaskTemplate,
    TaskFunction,
    OLTWorkflow,
    WorkflowNode,
    WorkflowEdge,
    WorkflowTemplate,
    WorkflowTemplateNode,
    WorkflowTemplateLink,
)
from .services.workflow_template_service import WorkflowTemplateService


# ---------------------------------------------------------------------------
# Vistas legacy
# ---------------------------------------------------------------------------


@staff_member_required
def execution_status(request, execution_id):
    execution = get_object_or_404(Execution, id=execution_id)
    return JsonResponse({
        'id': execution.id,
        'status': execution.status,
        'result_summary': execution.result_summary,
        'raw_output': execution.raw_output,
        'error_message': execution.error_message,
        'finished_at': execution.finished_at.isoformat() if execution.finished_at else None,
        'duration_ms': execution.duration_ms,
    })


@staff_member_required
def program_job(request, job_id):
    job = get_object_or_404(SnmpJob, id=job_id)
    executions = []
    
    for job_host in job.job_hosts.filter(enabled=True):
        execution = Execution.objects.create(
            snmp_job=job,
            job_host=job_host,
            olt=job_host.olt,
            status='PENDING',
            attempt=0,
        )
        executions.append(execution)
    
    return JsonResponse({
        'message': f'Se han programado {len(executions)} ejecuciones',
        'execution_ids': [e.id for e in executions],
    })


# ---------------------------------------------------------------------------
# Interfaz tipo Airflow (workflow builder)
# ---------------------------------------------------------------------------


def _ensure_demo_workflow():
    """
    Crea (si no existe) un workflow de demostración para la OLT SMP-10
    con un nodo de descubrimiento Huawei, para ilustrar la interfaz.
    """
    try:
        olt = OLT.objects.select_related('marca', 'modelo').get(abreviatura='SMP-10')
    except OLT.DoesNotExist:
        return None

    demo_function, _ = TaskFunction.objects.get_or_create(
        code='demo_discovery_huawei',
        defaults={
            'name': 'Discovery Huawei MA5800',
            'description': 'Función demo: ejecuta el descubrimiento principal en OLT Huawei MA5800.',
            'module_path': 'snmp_jobs.tasks',
            'callable_name': 'discovery_main_task',
            'function_type': 'descubrimiento',
            'default_parameters': {
                'queue': 'discovery_main',
                'timeout': 180,
            },
        },
    )

    discovery_job = (
        SnmpJob.objects
        .filter(job_type='descubrimiento', marca=olt.marca, enabled=True)
        .select_related('oid')
        .order_by('nombre')
        .first()
    )
    oid_value = discovery_job.oid.oid if discovery_job and discovery_job.oid_id else None
    oid_name = discovery_job.oid.nombre if discovery_job and discovery_job.oid_id else None

    demo_template, created_template = TaskTemplate.objects.get_or_create(
        slug='demo-discovery-huawei',
        defaults={
            'name': 'Discovery Huawei – MA5800',
            'description': 'Plantilla de demostración para descubrimiento de ONUs Huawei (MA5800).',
            'function': demo_function,
            'default_interval_seconds': 180,
            'default_priority': 1,
            'default_retry_policy': {'max_retries': 2, 'retry_interval': 30},
            'default_run_options': {
                'queue': 'discovery_main',
                'requires_lock': True,
            },
            'default_color': '#f97316',
            'default_icon': '🛰️',
            'metadata': {
                'demo': True,
                'marca': olt.marca.nombre,
                'modelo': olt.modelo.nombre if olt.modelo else None,
                'oid': oid_value,
                'oid_nombre': oid_name,
            },
        },
    )
    if not created_template and demo_template.function_id != demo_function.id:
        demo_template.function = demo_function
        demo_template.save(update_fields=['function', 'updated_at'])

    demo_workflow, _ = OLTWorkflow.objects.get_or_create(
        olt=olt,
        defaults={
            'name': f'Workflow Demo {olt.abreviatura}',
            'description': 'Ejemplo de DAG para descubrimiento Huawei MA5800.',
            'is_active': True,
            'theme': 'dark',
            'layout': {'demo': True},
        },
    )

    demo_node, node_created = WorkflowNode.objects.get_or_create(
        workflow=demo_workflow,
        template=demo_template,
        defaults={
            'name': 'Discovery ONU Huawei',
            'interval_seconds': demo_template.default_interval_seconds,
            'priority': 1,
            'enabled': True,
            'position_x': 160,
            'position_y': 120,
            'color_override': demo_template.default_color,
            'icon_override': demo_template.default_icon,
            'parameters': {
                'oid': oid_value,
                'oid_nombre': oid_name,
                'marca': olt.marca.nombre,
                'modelo': olt.modelo.nombre if olt.modelo else None,
            },
            'metadata': {
                'demo': True,
                'descripcion': 'Nodo ejemplo: Discovery prioridad A (Huawei).',
            },
        },
    )

    return {
        'workflow': demo_workflow,
        'node': demo_node,
        'template': demo_template,
        'function': demo_function,
        'snmp_job': discovery_job,
        'oid_value': oid_value,
        'oid_name': oid_name,
        'olt': olt,
    }


def _workflow_to_dict(workflow: OLTWorkflow):
    nodes = workflow.nodes.select_related('template', 'template__function', 'template_node', 'template_node__template').all()
    edges = workflow.edges.all()

    def _dt(value):
        return value.isoformat() if value else None

    # Obtener plantillas vinculadas
    template_links = workflow.template_links.select_related('template').all()
    linked_templates = [
        {
            'id': link.template_id,
            'name': link.template.name,
            'auto_sync': link.auto_sync,
        }
        for link in template_links
    ]

    return {
        'id': workflow.id,
        'olt_id': workflow.olt_id,
        'olt_name': workflow.olt.abreviatura if workflow.olt else None,
        'name': workflow.name,
        'description': workflow.description,
        'theme': workflow.theme,
        'is_active': workflow.is_active,
        'layout': workflow.layout or {},
        'linked_templates': linked_templates,
        'nodes': [
            {
                'id': node.id,
                'key': node.key or '',
                'name': node.name,
                'template_id': node.template_id,
                'template_name': node.template.name,
                'template_node_id': node.template_node_id,
                'template_node_key': node.template_node.key if node.template_node else None,
                'function_type': node.template.function.function_type,
                'interval_seconds': node.interval_seconds,
                'priority': node.priority,
                'enabled': node.enabled,
                'override_interval': getattr(node, 'override_interval', False),
                'override_priority': getattr(node, 'override_priority', False),
                'override_enabled': getattr(node, 'override_enabled', False),
                'override_parameters': getattr(node, 'override_parameters', False),
                'position': {
                    'x': float(node.position_x),
                    'y': float(node.position_y),
                },
                'color': node.color_override or node.template.default_color,
                'icon': node.icon_override or node.template.default_icon,
                'parameters': node.parameters,
                'retry_policy': node.retry_policy,
                'metadata': node.metadata,
                'next_run_at': _dt(getattr(node, 'next_run_at', None)),
                'last_run_at': _dt(getattr(node, 'last_run_at', None)),
                'last_success_at': _dt(getattr(node, 'last_success_at', None)),
                'last_failure_at': _dt(getattr(node, 'last_failure_at', None)),
                'consecutive_failures': getattr(node, 'consecutive_failures', 0),
            }
            for node in nodes
        ],
        'edges': [
            {
                'id': edge.id,
                'upstream_id': edge.upstream_node_id,
                'downstream_id': edge.downstream_node_id,
                'edge_type': edge.edge_type,
                'condition': edge.condition,
                'metadata': edge.metadata,
            }
            for edge in edges
        ],
    }


@staff_member_required
@require_http_methods(["GET"])
def task_templates_api(request):
    templates = TaskTemplate.objects.filter(is_active=True).select_related('function').order_by('name')
    data = [
        {
            'id': tpl.id,
            'name': tpl.name,
            'slug': tpl.slug,
            'function_id': tpl.function_id,
            'function_name': tpl.function.name,
            'function_type': tpl.function.function_type,
            'default_interval_seconds': tpl.default_interval_seconds,
            'default_priority': tpl.default_priority,
            'default_retry_policy': tpl.default_retry_policy,
            'default_run_options': tpl.default_run_options,
            'default_color': tpl.default_color,
            'default_icon': tpl.default_icon,
        }
        for tpl in templates
    ]
    return JsonResponse({'templates': data})


# Vista workflow_builder ELIMINADA - ahora se usa React + Vite como frontend separado
# @staff_member_required
# def workflow_builder(request):
#     demo_info = _ensure_demo_workflow()
#     templates = TaskTemplate.objects.filter(is_active=True).select_related('function').order_by('name')
#     functions = TaskFunction.objects.filter(is_active=True).order_by('name')
#     olts = OLT.objects.order_by('abreviatura')
#     workflows = OLTWorkflow.objects.select_related('olt').order_by('olt__abreviatura')
#     return render(
#         request,
#         'snmp_jobs/workflow_builder.html',
#         {
#             'templates': templates,
#             'functions': functions,
#             'olts': olts,
#             'workflows': workflows,
#             'demo_info': demo_info,
#         }
#     )


def _job_host_to_dict(job_host: SnmpJobHost):
    job = job_host.snmp_job
    template = TaskTemplate.objects.filter(metadata__snmp_job_id=job.id).first()
    return {
        'id': job_host.id,
        'job_id': job.id,
        'name': job.nombre,
        'description': job.descripcion,
        'job_type': job.job_type,
        'interval_seconds': job.interval_seconds,
        'queue_name': job_host.queue_name,
        'host_enabled': job_host.enabled,
        'job_enabled': job.enabled,
        'enabled': job_host.enabled and job.enabled,
        'template_id': template.id if template else None,
        'template_name': template.name if template else None,
        'next_run_at': job_host.next_run_at.isoformat() if job_host.next_run_at else None,
        'last_run_at': job_host.last_run_at.isoformat() if job_host.last_run_at else None,
        'last_success_at': job_host.last_success_at.isoformat() if job_host.last_success_at else None,
        'last_failure_at': job_host.last_failure_at.isoformat() if job_host.last_failure_at else None,
        'consecutive_failures': job_host.consecutive_failures,
    }


@staff_member_required
@require_http_methods(["GET"])
def legacy_jobs_api(request, olt_id):
    olt = get_object_or_404(OLT, id=olt_id)
    job_hosts = (
        SnmpJobHost.objects
        .select_related('snmp_job')
        .filter(olt=olt)
        .order_by('snmp_job__nombre')
    )
    data = [_job_host_to_dict(jh) for jh in job_hosts]
    return JsonResponse({'olt': {'id': olt.id, 'name': olt.abreviatura}, 'jobs': data})


@staff_member_required
@require_http_methods(["PATCH"])
def legacy_job_detail_api(request, olt_id, job_host_id):
    olt = get_object_or_404(OLT, id=olt_id)
    job_host = get_object_or_404(
        SnmpJobHost.objects.select_related('snmp_job'),
        id=job_host_id,
        olt=olt,
    )

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    updated_fields = []

    if 'enabled' in payload:
        enabled_value = bool(payload['enabled'])
        if job_host.enabled != enabled_value:
            job_host.enabled = enabled_value
            updated_fields.append('enabled')
            if enabled_value and not job_host.next_run_at:
                job_host.initialize_next_run(is_new=False)
                updated_fields.append('next_run_at')
            if not enabled_value:
                job_host.next_run_at = None
                updated_fields.append('next_run_at')

    if 'queue_name' in payload:
        queue_name = payload.get('queue_name') or None
        if job_host.queue_name != queue_name:
            job_host.queue_name = queue_name
            updated_fields.append('queue_name')

    if not updated_fields:
        job_data = _job_host_to_dict(job_host)
        return JsonResponse({'job': job_data})

    job_host.save(update_fields=list(set(updated_fields)))

    job = job_host.snmp_job
    if 'enabled' in payload:
        enabled_value = bool(payload['enabled'])
        if enabled_value:
            if not job.enabled:
                job.enable_with_catchup_prevention()
        else:
            still_enabled = job.job_hosts.exclude(pk=job_host.pk).filter(enabled=True).exists()
            if job.enabled and not still_enabled:
                job.enabled = False
                job.next_run_at = None
                job.save(update_fields=['enabled', 'next_run_at', 'updated_at'])

    job_data = _job_host_to_dict(job_host)
    return JsonResponse({'job': job_data})


@staff_member_required
@require_http_methods(["POST"])
def workflow_node_from_job_api(request, workflow_id):
    workflow = get_object_or_404(
        OLTWorkflow.objects.select_related('olt'),
        id=workflow_id,
    )

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    job_host_id = payload.get('job_host_id')
    if not job_host_id:
        return HttpResponseBadRequest('job_host_id es requerido')

    job_host = get_object_or_404(
        SnmpJobHost.objects.select_related('snmp_job', 'olt'),
        id=job_host_id,
    )

    if job_host.olt_id != workflow.olt_id:
        return HttpResponseBadRequest('El SnmpJob pertenece a otra OLT.')

    template = TaskTemplate.objects.filter(metadata__snmp_job_id=job_host.snmp_job_id).first()
    if not template:
        return HttpResponseBadRequest('No existe una plantilla vinculada a este SnmpJob.')

    defaults = {
        'name': payload.get('name') or template.name,
        'interval_seconds': template.default_interval_seconds or (job_host.snmp_job.interval_seconds or 300),
        'priority': template.default_priority or 3,
        'enabled': True,
        'position_x': payload.get('position', {}).get('x', 160),
        'position_y': payload.get('position', {}).get('y', 120 + workflow.nodes.count() * 60),
        'color_override': template.default_color,
        'icon_override': template.default_icon,
    }

    node, created = WorkflowNode.objects.get_or_create(
        workflow=workflow,
        template=template,
        defaults=defaults,
    )

    if not created:
        node.enabled = True
        node.interval_seconds = template.default_interval_seconds or node.interval_seconds
        node.priority = template.default_priority or node.priority
        node.color_override = node.color_override or template.default_color
        node.icon_override = node.icon_override or template.default_icon
        node.save(update_fields=['enabled', 'interval_seconds', 'priority', 'color_override', 'icon_override', 'updated_at'])

    workflow_dict = _workflow_to_dict(workflow)
    node_dict = next((n for n in workflow_dict['nodes'] if n['id'] == node.id), None)

    return JsonResponse({'node': node_dict, 'created': created})


@staff_member_required
def legacy_control(request):
    selected_olt = request.GET.get('olt')
    job_hosts_qs = (
        SnmpJobHost.objects
        .select_related('snmp_job', 'olt')
        .order_by('olt__abreviatura', 'snmp_job__nombre')
    )
    if selected_olt:
        job_hosts_qs = job_hosts_qs.filter(olt_id=selected_olt)

    grouped = {}
    for host in job_hosts_qs:
        grouped.setdefault(host.olt, []).append(_job_host_to_dict(host))

    olt_groups = [
        {
            'olt': olt,
            'jobs': jobs,
        }
        for olt, jobs in grouped.items()
    ]
    olt_groups.sort(key=lambda item: item['olt'].abreviatura)

    available_olts = (
        OLT.objects
        .filter(job_host_links__isnull=False)
        .distinct()
        .order_by('abreviatura')
    )

    return render(
        request,
        'snmp_jobs/legacy_control.html',
        {
            'olt_groups': olt_groups,
            'available_olts': available_olts,
            'selected_olt': selected_olt,
        },
    )


@staff_member_required
@require_http_methods(["GET"])
def legacy_jobs_global_api(request):
    job_hosts = (
        SnmpJobHost.objects
        .select_related('snmp_job', 'olt')
        .order_by('olt__abreviatura', 'snmp_job__nombre')
    )
    data = {}
    for jh in job_hosts:
        olt_id = jh.olt_id
        if olt_id not in data:
            data[olt_id] = {
                'olt_id': olt_id,
                'olt_name': jh.olt.abreviatura,
                'jobs': [],
            }
        data[olt_id]['jobs'].append(_job_host_to_dict(jh))

    return JsonResponse({'olts': list(data.values())})


@staff_member_required
@require_http_methods(["GET", "POST"])
def workflows_api(request):
    if request.method == "GET":
        workflows = OLTWorkflow.objects.select_related('olt').order_by('olt__abreviatura')
        data = [_workflow_to_dict(wf) for wf in workflows]
        return JsonResponse({'workflows': data})

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    olt_id = payload.get('olt_id')
    if not olt_id:
        return HttpResponseBadRequest('olt_id es requerido')

    olt = get_object_or_404(OLT, id=olt_id)
    workflow, created = OLTWorkflow.objects.get_or_create(
        olt=olt,
        defaults={
            'name': payload.get('name', f'Workflow SNMP - {olt.abreviatura}'),
            'description': payload.get('description', ''),
            'theme': payload.get('theme', 'auto'),
            'is_active': payload.get('is_active', True),
        },
    )
    if not created:
        workflow.name = payload.get('name', workflow.name)
        workflow.description = payload.get('description', workflow.description)
        workflow.theme = payload.get('theme', workflow.theme)
        workflow.is_active = payload.get('is_active', workflow.is_active)
        workflow.save(update_fields=['name', 'description', 'theme', 'is_active', 'updated_at'])

    return JsonResponse({'workflow': _workflow_to_dict(workflow)}, status=201 if created else 200)


@staff_member_required
@require_http_methods(["GET", "PUT", "DELETE"])
def workflow_detail_api(request, workflow_id):
    workflow = get_object_or_404(OLTWorkflow, id=workflow_id)

    if request.method == "GET":
        return JsonResponse({'workflow': _workflow_to_dict(workflow)})
    
    if request.method == "DELETE":
        olt_name = workflow.olt.abreviatura if workflow.olt else 'OLT'
        workflow.delete()
        return JsonResponse({'deleted': True, 'message': f'Workflow de {olt_name} eliminado correctamente.'})

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    for field in ['name', 'description', 'theme', 'is_active', 'layout']:
        if field in payload:
            setattr(workflow, field, payload[field])
    workflow.save()
    return JsonResponse({'workflow': _workflow_to_dict(workflow)})


@staff_member_required
@require_http_methods(["GET", "POST"])
def workflow_nodes_api(request, workflow_id):
    workflow = get_object_or_404(OLTWorkflow, id=workflow_id)

    if request.method == "GET":
        return JsonResponse({'nodes': _workflow_to_dict(workflow)['nodes']})

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    template_id = payload.get('template_id')
    template = get_object_or_404(TaskTemplate, id=template_id)

    # Generar key si no se proporciona
    key = payload.get('key')
    if not key:
        # Generar key basada en nombre
        import re
        name_lower = (payload.get('name') or template.name).lower().replace(' ', '.')
        name_clean = re.sub(r'[^a-z0-9.]', '', name_lower)
        interval_min = payload.get('interval_seconds', template.default_interval_seconds) // 60
        if interval_min > 0:
            key = f"{name_clean}.{interval_min}min"
        else:
            key = f"{name_clean}.{payload.get('interval_seconds', template.default_interval_seconds)}s"
        
        # Asegurar unicidad
        base_key = key
        counter = 1
        while WorkflowNode.objects.filter(workflow=workflow, key=key).exists():
            key = f"{base_key}.{counter}"
            counter += 1
    
    node = WorkflowNode.objects.create(
        workflow=workflow,
        template=template,
        key=key,
        name=payload.get('name', template.name),
        interval_seconds=payload.get('interval_seconds', template.default_interval_seconds),
        priority=payload.get('priority', template.default_priority),
        enabled=payload.get('enabled', True),
        position_x=payload.get('position', {}).get('x', 0),
        position_y=payload.get('position', {}).get('y', 0),
        color_override=payload.get('color'),
        icon_override=payload.get('icon'),
        parameters=payload.get('parameters', template.default_run_options or {}),
        retry_policy=payload.get('retry_policy', template.default_retry_policy or {}),
        metadata=payload.get('metadata', {}),
    )
    return JsonResponse({'node': next(n for n in _workflow_to_dict(workflow)['nodes'] if n['id'] == node.id)}, status=201)


@staff_member_required
@require_http_methods(["PUT", "DELETE"])
def workflow_node_detail_api(request, workflow_id, node_id):
    workflow = get_object_or_404(OLTWorkflow, id=workflow_id)
    node = get_object_or_404(WorkflowNode, workflow=workflow, id=node_id)

    if request.method == "DELETE":
        node.delete()
        return JsonResponse({'deleted': True})

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    for field in ['name', 'key', 'interval_seconds', 'priority', 'enabled', 'color_override', 'icon_override', 'parameters', 'retry_policy', 'metadata']:
        if field in payload:
            setattr(node, field, payload[field])
    if 'position' in payload:
        pos = payload['position'] or {}
        node.position_x = pos.get('x', node.position_x)
        node.position_y = pos.get('y', node.position_y)
    if 'template_id' in payload and payload['template_id']:
        node.template = get_object_or_404(TaskTemplate, id=payload['template_id'])
    if 'override_interval' in payload:
        node.override_interval = bool(payload['override_interval'])
    if 'override_priority' in payload:
        node.override_priority = bool(payload['override_priority'])
    if 'override_enabled' in payload:
        node.override_enabled = bool(payload['override_enabled'])
    if 'override_parameters' in payload:
        node.override_parameters = bool(payload['override_parameters'])
    node.save()
    return JsonResponse({'node': next(n for n in _workflow_to_dict(workflow)['nodes'] if n['id'] == node.id)})


@staff_member_required
@require_http_methods(["GET", "POST"])
def workflow_edges_api(request, workflow_id):
    workflow = get_object_or_404(OLTWorkflow, id=workflow_id)

    if request.method == "GET":
        return JsonResponse({'edges': _workflow_to_dict(workflow)['edges']})

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    upstream = get_object_or_404(WorkflowNode, workflow=workflow, id=payload.get('upstream_id'))
    downstream = get_object_or_404(WorkflowNode, workflow=workflow, id=payload.get('downstream_id'))

    edge, created = WorkflowEdge.objects.get_or_create(
        workflow=workflow,
        upstream_node=upstream,
        downstream_node=downstream,
        defaults={
            'edge_type': payload.get('edge_type', 'secuencial'),
            'condition': payload.get('condition', {}),
            'metadata': payload.get('metadata', {}),
        },
    )
    if not created:
        edge.edge_type = payload.get('edge_type', edge.edge_type)
        edge.condition = payload.get('condition', edge.condition)
        edge.metadata = payload.get('metadata', edge.metadata)
        edge.save()

    return JsonResponse({'edge': next(e for e in _workflow_to_dict(workflow)['edges'] if e['id'] == edge.id)}, status=201 if created else 200)


@staff_member_required
@require_http_methods(["PUT", "DELETE"])
def workflow_edge_detail_api(request, workflow_id, edge_id):
    workflow = get_object_or_404(OLTWorkflow, id=workflow_id)
    edge = get_object_or_404(WorkflowEdge, workflow=workflow, id=edge_id)

    if request.method == "DELETE":
        edge.delete()
        return JsonResponse({'deleted': True})

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')

    for field in ['edge_type', 'condition', 'metadata']:
        if field in payload:
            setattr(edge, field, payload[field])
    edge.save()
    return JsonResponse({'edge': next(e for e in _workflow_to_dict(workflow)['edges'] if e['id'] == edge.id)})


@staff_member_required
@require_http_methods(["POST"])
def create_node_from_legacy_api(request, olt_id, job_host_id):
    """API para crear un WorkflowNode desde un SnmpJobHost legacy"""
    olt = get_object_or_404(OLT, id=olt_id)
    job_host = get_object_or_404(
        SnmpJobHost.objects.select_related('snmp_job', 'olt'),
        id=job_host_id,
        olt=olt,
    )
    
    # Obtener o crear workflow para esta OLT
    workflow, _ = OLTWorkflow.objects.get_or_create(
        olt=olt,
        defaults={
            'name': f'Workflow SNMP - {olt.abreviatura}',
            'is_active': True,
        }
    )
    
    # Buscar TaskTemplate asociado al SnmpJob
    template = TaskTemplate.objects.filter(metadata__snmp_job_id=job_host.snmp_job_id).first()
    if not template:
        return HttpResponseBadRequest('No existe una plantilla vinculada a este SnmpJob.')
    
    # Generar key basada en nombre del job
    import re
    name_lower = job_host.snmp_job.nombre.lower().replace(' ', '.')
    name_clean = re.sub(r'[^a-z0-9.]', '', name_lower)
    interval_min = job_host.snmp_job.interval_seconds // 60 if job_host.snmp_job.interval_seconds else 10
    key = f"{name_clean}.{interval_min}min"
    
    # Asegurar unicidad
    base_key = key
    counter = 1
    while WorkflowNode.objects.filter(workflow=workflow, key=key).exists():
        key = f"{base_key}.{counter}"
        counter += 1
    
    node, created = WorkflowNode.objects.get_or_create(
        workflow=workflow,
        key=key,
        defaults={
            'template': template,
            'name': job_host.snmp_job.nombre,
            'interval_seconds': job_host.snmp_job.interval_seconds or template.default_interval_seconds,
            'priority': template.default_priority,
            'enabled': True,
            'position_x': 160 + workflow.nodes.count() * 200,
            'position_y': 120,
        }
    )
    
    return JsonResponse({
        'node': next(n for n in _workflow_to_dict(workflow)['nodes'] if n['id'] == node.id),
        'created': created
    })


# ---------------------------------------------------------------------------
# API para Workflow Templates (Plantillas tipo Zabbix)
# ---------------------------------------------------------------------------


def _template_to_dict(template: WorkflowTemplate):
    """Convierte WorkflowTemplate a diccionario"""
    return {
        'id': template.id,
        'name': template.name,
        'description': template.description,
        'is_active': template.is_active,
        'created_at': template.created_at.isoformat() if template.created_at else None,
        'updated_at': template.updated_at.isoformat() if template.updated_at else None,
        'node_count': template.template_nodes.count(),
        'workflow_count': template.workflow_links.count(),
    }


def _template_node_to_dict(template_node: WorkflowTemplateNode):
    """Convierte un WorkflowTemplateNode a diccionario"""
    oid = template_node.oid
    return {
        'id': template_node.id,
        'template_id': template_node.template_id,
        'key': template_node.key,
        'name': template_node.name,
        'oid_id': oid.id if oid else None,
        'oid_nombre': oid.nombre if oid else None,
        'oid_oid': oid.oid if oid else None,
        'oid_espacio': oid.espacio if oid else None,
        'oid_espacio_display': oid.get_espacio_display() if oid else None,
        'oid_marca_id': oid.marca_id if oid else None,
        'oid_marca_nombre': oid.marca.nombre if oid and oid.marca else None,
        'oid_modelo_id': oid.modelo_id if oid else None,
        'oid_modelo_nombre': oid.modelo.nombre if oid and oid.modelo else None,
        'interval_seconds': template_node.interval_seconds,
        'priority': template_node.priority,
        'enabled': template_node.enabled,
        'parameters': template_node.parameters,
        'retry_policy': template_node.retry_policy,
        'position': {
            'x': float(template_node.position_x),
            'y': float(template_node.position_y),
        },
        'color': template_node.color_override or '',
        'icon': template_node.icon_override or '',
        'metadata': template_node.metadata,
    }


@staff_member_required
@require_http_methods(["GET", "POST"])
def workflow_templates_api(request):
    """API para listar y crear plantillas de workflow"""
    if request.method == "GET":
        templates = WorkflowTemplate.objects.filter(is_active=True).order_by('name')
        data = [_template_to_dict(tpl) for tpl in templates]
        return JsonResponse({'templates': data})
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')
    
    name = payload.get('name')
    if not name:
        return HttpResponseBadRequest('name es requerido')
    
    template, created = WorkflowTemplate.objects.get_or_create(
        name=name,
        defaults={
            'description': payload.get('description', ''),
            'is_active': payload.get('is_active', True),
        }
    )
    
    if not created:
        template.description = payload.get('description', template.description)
        template.is_active = payload.get('is_active', template.is_active)
        template.save(update_fields=['description', 'is_active', 'updated_at'])
    
    return JsonResponse({'template': _template_to_dict(template)}, status=201 if created else 200)


@staff_member_required
@require_http_methods(["GET", "PUT", "DELETE"])
def workflow_template_detail_api(request, template_id):
    """API para obtener, actualizar o eliminar una plantilla"""
    template = get_object_or_404(WorkflowTemplate, id=template_id)
    
    if request.method == "GET":
        template_dict = _template_to_dict(template)
        template_dict['nodes'] = [
            _template_node_to_dict(node) for node in template.template_nodes.all()
        ]
        return JsonResponse({'template': template_dict})
    
    if request.method == "DELETE":
        template.delete()
        return JsonResponse({'deleted': True})
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')
    
    for field in ['name', 'description', 'is_active']:
        if field in payload:
            setattr(template, field, payload[field])
    template.save()
    
    return JsonResponse({'template': _template_to_dict(template)})


@staff_member_required
@require_http_methods(["GET", "POST"])
def workflow_template_nodes_api(request, template_id):
    """API para listar y crear nodos de plantilla"""
    template = get_object_or_404(WorkflowTemplate, id=template_id)
    
    if request.method == "GET":
        nodes = template.template_nodes.all()
        data = [_template_node_to_dict(node) for node in nodes]
        return JsonResponse({'nodes': data})
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')
    
    key = payload.get('key')
    if not key:
        return HttpResponseBadRequest('key es requerido')
    
    oid_id = payload.get('oid_id')
    if not oid_id:
        return HttpResponseBadRequest('oid_id es requerido')
    
    oid = get_object_or_404(OID, id=oid_id)
    
    # Determinar prioridad según el espacio del OID
    # descubrimiento = prioridad 1 (alta), otros = prioridad 3 (baja)
    default_priority = 1 if oid.espacio == 'descubrimiento' else 3
    
    template_node, created = WorkflowTemplateNode.objects.get_or_create(
        template=template,
        key=key,
        defaults={
            'oid': oid,
            'name': payload.get('name', oid.nombre),
            'interval_seconds': payload.get('interval_seconds', 300),
            'priority': payload.get('priority', default_priority),
            'enabled': payload.get('enabled', True),
            'position_x': payload.get('position', {}).get('x', 0),
            'position_y': payload.get('position', {}).get('y', 0),
            'color_override': payload.get('color', ''),
            'icon_override': payload.get('icon', ''),
            'parameters': payload.get('parameters', {}),
            'retry_policy': payload.get('retry_policy', {}),
            'metadata': payload.get('metadata', {}),
        }
    )
    
    if not created:
        return HttpResponseBadRequest(f'Ya existe un nodo con la key "{key}" en esta plantilla')
    
    return JsonResponse({'node': _template_node_to_dict(template_node)}, status=201)


@staff_member_required
@require_http_methods(["PUT", "DELETE"])
def workflow_template_node_detail_api(request, template_id, node_id):
    """API para actualizar o eliminar un nodo de plantilla"""
    template = get_object_or_404(WorkflowTemplate, id=template_id)
    template_node = get_object_or_404(WorkflowTemplateNode, template=template, id=node_id)
    
    if request.method == "DELETE":
        template_node.delete()
        # Sincronizar cambios a workflows vinculados
        WorkflowTemplateService.sync_template_changes(template_id)
        return JsonResponse({'deleted': True})
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')
    
    for field in ['key', 'name', 'interval_seconds', 'priority', 'enabled', 'color_override', 'icon_override', 'parameters', 'retry_policy', 'metadata']:
        if field in payload:
            setattr(template_node, field, payload[field])
    if 'position' in payload:
        pos = payload['position'] or {}
        template_node.position_x = pos.get('x', template_node.position_x)
        template_node.position_y = pos.get('y', template_node.position_y)
    if 'oid_id' in payload:
        oid_id = payload['oid_id']
        if oid_id:
            oid = get_object_or_404(OID, id=oid_id)
            template_node.oid = oid
            # Actualizar prioridad según espacio del OID si no se especificó
            if 'priority' not in payload:
                template_node.priority = 1 if oid.espacio == 'descubrimiento' else 3
        else:
            template_node.oid = None
    
    template_node.save()
    
    # Sincronizar cambios a workflows vinculados
    WorkflowTemplateService.sync_template_changes(template_id)
    
    return JsonResponse({'node': _template_node_to_dict(template_node)})


@staff_member_required
@require_http_methods(["POST"])
def apply_template_to_olts_api(request, template_id):
    """API para aplicar una plantilla a múltiples OLTs"""
    template = get_object_or_404(WorkflowTemplate, id=template_id)
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('JSON inválido')
    
    olt_ids = payload.get('olt_ids', [])
    if not olt_ids:
        return HttpResponseBadRequest('olt_ids es requerido (array de IDs)')
    
    auto_sync = payload.get('auto_sync', True)
    create_custom_nodes = payload.get('create_custom_nodes', True)
    
    stats = WorkflowTemplateService.apply_template_to_olts(
        template_id=template_id,
        olt_ids=olt_ids,
        auto_sync=auto_sync,
        create_custom_nodes=create_custom_nodes
    )
    
    return JsonResponse({
        'success': len(stats['errors']) == 0,
        'stats': stats,
    })


@staff_member_required
@require_http_methods(["POST"])
def sync_template_changes_api(request, template_id):
    """API para sincronizar cambios de una plantilla manualmente"""
    template = get_object_or_404(WorkflowTemplate, id=template_id)
    
    stats = WorkflowTemplateService.sync_template_changes(template_id)
    
    return JsonResponse({
        'success': True,
        'stats': stats,
    })


@staff_member_required
@require_http_methods(['GET'])
def brands_api(request):
    """API para obtener lista de marcas"""
    brands = Brand.objects.all().order_by('nombre')
    return JsonResponse({
        'brands': [
            {
                'id': brand.id,
                'nombre': brand.nombre,
            }
            for brand in brands
        ]
    })


@staff_member_required
@require_http_methods(['GET'])
def models_api(request):
    """API para obtener lista de modelos, opcionalmente filtrados por marca"""
    marca_id = request.GET.get('marca_id')
    queryset = OLTModel.objects.all()
    if marca_id:
        queryset = queryset.filter(marca_id=marca_id)
    models = queryset.order_by('nombre')
    return JsonResponse({
        'models': [
            {
                'id': model.id,
                'nombre': model.nombre,
                'marca_id': model.marca_id,
                'marca_nombre': model.marca.nombre if model.marca else None,
            }
            for model in models
        ]
    })


@staff_member_required
@require_http_methods(['GET'])
def oids_api(request):
    """API para obtener lista de OIDs, filtrados por marca, modelo y espacio"""
    marca_id = request.GET.get('marca_id')
    modelo_id = request.GET.get('modelo_id')
    espacio = request.GET.get('espacio')  # 'descubrimiento' o cualquier otro para GET
    
    queryset = OID.objects.all()
    if marca_id:
        queryset = queryset.filter(marca_id=marca_id)
    if modelo_id:
        queryset = queryset.filter(modelo_id=modelo_id)
    if espacio:
        queryset = queryset.filter(espacio=espacio)
    
    oids = queryset.order_by('nombre')
    return JsonResponse({
        'oids': [
            {
                'id': oid.id,
                'nombre': oid.nombre,
                'oid': oid.oid,
                'marca_id': oid.marca_id,
                'marca_nombre': oid.marca.nombre if oid.marca else None,
                'modelo_id': oid.modelo_id,
                'modelo_nombre': oid.modelo.nombre if oid.modelo else None,
                'espacio': oid.espacio,
                'espacio_display': oid.get_espacio_display(),
            }
            for oid in oids
        ]
    })


@staff_member_required
@require_http_methods(['GET'])
def oid_detail_api(request, oid_id):
    """API para obtener un OID específico"""
    oid = get_object_or_404(OID, id=oid_id)
    return JsonResponse({
        'id': oid.id,
        'nombre': oid.nombre,
        'oid': oid.oid,
        'marca_id': oid.marca_id,
        'marca_nombre': oid.marca.nombre if oid.marca else None,
        'modelo_id': oid.modelo_id,
        'modelo_nombre': oid.modelo.nombre if oid.modelo else None,
        'espacio': oid.espacio,
        'espacio_display': oid.get_espacio_display(),
    })


@staff_member_required
@require_http_methods(["DELETE"])
def unlink_template_from_workflow_api(request, template_id, workflow_id):
    """API para desvincular una plantilla de un workflow"""
    template = get_object_or_404(WorkflowTemplate, id=template_id)
    workflow = get_object_or_404(OLTWorkflow, id=workflow_id)
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        delete_nodes = False
    else:
        delete_nodes = payload.get('delete_nodes', False)
    
    stats = WorkflowTemplateService.unlink_template_from_workflow(
        template_id=template_id,
        workflow_id=workflow_id,
        delete_nodes=delete_nodes
    )
    
    return JsonResponse({
        'success': True,
        'stats': stats,
    })