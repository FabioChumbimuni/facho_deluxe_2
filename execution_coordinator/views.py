from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from hosts.models import OLT
from snmp_jobs.models import SnmpJob, SnmpJobHost
from executions.models import Execution
from .models import QuotaTracker, CoordinatorLog
from .coordinator import ExecutionCoordinator


@login_required
def coordinator_dashboard(request):
    """
    Dashboard de coordinación en tiempo real
    Muestra el estado de todas las OLTs y sus tareas programadas
    """
    context = {
        'title': 'Dashboard de Coordinación',
    }
    return render(request, 'execution_coordinator/dashboard.html', context)


@login_required
def coordinator_dashboard_data(request):
    """
    API endpoint que retorna datos en JSON para el dashboard
    """
    olts_data = []
    
    # Obtener OLTs habilitadas
    active_olts = OLT.objects.filter(habilitar_olt=True).order_by('abreviatura')
    
    current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
    
    for olt in active_olts:
        # Obtener tareas asociadas a esta OLT
        job_hosts = SnmpJobHost.objects.filter(
            olt=olt,
            enabled=True,
            snmp_job__enabled=True
        ).select_related('snmp_job', 'snmp_job__oid').order_by('-snmp_job__job_type', 'snmp_job__nombre')
        
        tasks_info = []
        total_executions_hour = 0
        
        for jh in job_hosts:
            job = jh.snmp_job
            
            # Calcular cuántas veces se ejecuta por hora
            interval_seconds = job.interval_seconds or 3600
            executions_per_hour = max(1, 3600 // interval_seconds)
            total_executions_hour += executions_per_hour
            
            # IMPORTANTE: Tiempo hasta próxima ejecución desde SnmpJobHost (POR OLT)
            if jh.next_run_at:
                time_until = jh.next_run_at - timezone.now()
                seconds_until = int(time_until.total_seconds())
                
                if seconds_until < 0:
                    time_until_str = "Listo para ejecutar"
                    time_class = "ready"
                elif seconds_until < 60:
                    time_until_str = f"{seconds_until}s"
                    time_class = "soon"
                elif seconds_until < 3600:
                    minutes = seconds_until // 60
                    time_until_str = f"{minutes}m"
                    time_class = "normal"
                else:
                    hours = seconds_until // 3600
                    minutes = (seconds_until % 3600) // 60
                    time_until_str = f"{hours}h {minutes}m"
                    time_class = "normal"
            else:
                time_until_str = "No programado"
                time_class = "normal"
            
            # Obtener quota tracker
            quota_tracker = QuotaTracker.objects.filter(
                olt=olt,
                task_type__icontains=job.job_type,
                period_start=current_hour
            ).first()
            
            quota_info = {
                'completed': 0,
                'required': executions_per_hour,
                'percentage': 0
            }
            
            if quota_tracker:
                quota_info['completed'] = quota_tracker.quota_completed
                quota_info['required'] = quota_tracker.quota_required
                quota_info['percentage'] = quota_tracker.completion_percentage()
            
            # Última ejecución
            last_execution = Execution.objects.filter(
                olt=olt,
                snmp_job=job
            ).order_by('-created_at').first()
            
            last_exec_info = {
                'time': '',
                'status': '',
                'duration': 0
            }
            
            if last_execution:
                last_exec_info['time'] = timezone.localtime(last_execution.created_at).strftime('%H:%M:%S')
                last_exec_info['status'] = last_execution.status
                last_exec_info['duration'] = last_execution.duration_ms or 0
            
            tasks_info.append({
                'name': job.nombre,
                'type': job.job_type,
                'type_display': job.get_job_type_display(),
                'interval_raw': job.interval_raw,
                'interval_seconds': interval_seconds,
                'executions_per_hour': executions_per_hour,
                'next_run': timezone.localtime(jh.next_run_at).strftime('%H:%M:%S') if jh.next_run_at else 'N/A',  # ← De SnmpJobHost
                'time_until': time_until_str,
                'time_class': time_class,
                'priority': 90 if job.job_type == 'descubrimiento' else 40,
                'quota': quota_info,
                'last_execution': last_exec_info,
                'oid': job.oid.nombre if job.oid else 'N/A',
            })
        
        # Ejecuciones activas
        active_executions = Execution.objects.filter(
            olt=olt,
            status__in=['RUNNING', 'PENDING']
        ).count()
        
        # Últimos logs del coordinator para esta OLT
        recent_logs = CoordinatorLog.objects.filter(
            olt=olt,
            timestamp__gte=timezone.now() - timedelta(hours=1)
        ).order_by('-timestamp')[:5]
        
        logs_info = []
        for log in recent_logs:
            logs_info.append({
                'time': timezone.localtime(log.timestamp).strftime('%H:%M:%S'),
                'level': log.level,
                'event': log.get_event_type_display(),
                'message': log.message[:100]
            })
        
        # Cuotas de la hora actual
        quota_trackers = QuotaTracker.objects.filter(
            olt=olt,
            period_start=current_hour
        )
        
        quota_summary = {
            'total_required': sum(q.quota_required for q in quota_trackers),
            'total_completed': sum(q.quota_completed for q in quota_trackers),
            'total_failed': sum(q.quota_failed for q in quota_trackers),
        }
        
        if quota_summary['total_required'] > 0:
            quota_summary['percentage'] = (quota_summary['total_completed'] / quota_summary['total_required']) * 100
        else:
            quota_summary['percentage'] = 0
        
        olts_data.append({
            'id': olt.id,
            'name': olt.abreviatura,
            'ip': olt.ip_address,
            'tasks': tasks_info,
            'tasks_count': len(tasks_info),
            'total_executions_hour': total_executions_hour,
            'active_executions': active_executions,
            'recent_logs': logs_info,
            'quota_summary': quota_summary,
        })
    
    # Estadísticas globales
    global_stats = {
        'total_olts': active_olts.count(),
        'total_tasks': sum(olt['tasks_count'] for olt in olts_data),
        'total_executions_hour': sum(olt['total_executions_hour'] for olt in olts_data),
        'current_time': timezone.localtime(timezone.now()).strftime('%H:%M:%S'),
        'current_date': timezone.localtime(timezone.now()).strftime('%d/%m/%Y'),
    }
    
    # Información de estrategia
    strategy_info = {
        'name': 'Coordinación con Prioridades y Cuotas',
        'description': 'Ejecución secuencial por OLT con sistema de cuotas por hora',
        'features': [
            'Una tarea SNMP por OLT a la vez',
            'Discovery (P90) ejecuta antes que GET (P40)',
            'Cuotas de ejecución por hora',
            'Reformulación dinámica ante cambios',
            'Detección de colisiones en < 5 segundos'
        ]
    }
    
    return JsonResponse({
        'olts': olts_data,
        'stats': global_stats,
        'strategy': strategy_info,
        'timestamp': timezone.now().isoformat()
    })
