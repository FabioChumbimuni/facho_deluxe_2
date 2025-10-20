# snmp_jobs/views.py
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404
from .models import SnmpJob, SnmpJobHost
from executions.models import Execution

@staff_member_required
def execution_status(request, execution_id):
    """
    Vista para obtener el estado de una ejecución
    """
    execution = get_object_or_404(Execution, id=execution_id)
    return JsonResponse({
        'id': execution.id,
        'status': execution.status,
        'result_summary': execution.result_summary,
        'raw_output': execution.raw_output,
        'error_message': execution.error_message,
        'finished_at': execution.finished_at.isoformat() if execution.finished_at else None,
        'duration_ms': execution.duration_ms
    })

@staff_member_required
def program_job(request, job_id):
    """
    Vista para programar la ejecución inmediata de un job
    """
    job = get_object_or_404(SnmpJob, id=job_id)
    executions = []
    
    # Crear ejecuciones para cada OLT habilitada
    for job_host in job.job_hosts.filter(enabled=True):
        execution = Execution.objects.create(
            snmp_job=job,
            job_host=job_host,
            olt=job_host.olt,
            status='PENDING',
            attempt=0  # Ejecución principal siempre es attempt 0
        )
        executions.append(execution)
        
        # TODO: Aquí se encolará la tarea en Celery cuando implementemos las tareas
        # execute_one.apply_async(args=[execution.id], queue=job_host.queue_name)
    
    return JsonResponse({
        'message': f'Se han programado {len(executions)} ejecuciones',
        'execution_ids': [e.id for e in executions]
    })