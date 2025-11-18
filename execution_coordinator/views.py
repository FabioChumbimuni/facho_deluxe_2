
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from hosts.models import OLT
from snmp_jobs.models import SnmpJobHost
from executions.models import Execution
from .models import CoordinatorEvent


@login_required
def coordinator_dashboard(request):
    """Vista principal del dashboard del coordinator."""
    context = {
        'title': 'Dashboard de Coordinación',
    }
    return render(request, 'execution_coordinator/dashboard.html', context)


@login_required
def coordinator_dashboard_data(request):
    """Endpoint JSON con estado casi en tiempo real del coordinator."""
    now = timezone.now()

    # OLTs habilitadas
    active_olts = OLT.objects.filter(habilitar_olt=True).order_by('abreviatura')

    # Conteo global de ejecuciones pendientes/ejecutándose por OLT
    status_counts_map = defaultdict(dict)
    pending_running_by_olt = Execution.objects.filter(
        status__in=[Execution.STATUS_PENDING, Execution.STATUS_RUNNING]
    ).values('olt_id', 'status').annotate(count=Count('id'))

    global_pending = 0
    global_running = 0
    for row in pending_running_by_olt:
        status_counts_map[row['olt_id']][row['status']] = row['count']
        if row['status'] == Execution.STATUS_PENDING:
            global_pending += row['count']
        elif row['status'] == Execution.STATUS_RUNNING:
            global_running += row['count']

    # Resumen de cola por tipo de job
    job_type_labels = {
        'descubrimiento': 'Descubrimiento',
        'get': 'GET',
    }
    queue_breakdown_map = defaultdict(lambda: {
        'type': '',
        'type_display': '',
        'pending': 0,
        'running': 0,
    })
    pending_running_by_type = Execution.objects.filter(
        status__in=[Execution.STATUS_PENDING, Execution.STATUS_RUNNING]
    ).values('snmp_job__job_type', 'status').annotate(count=Count('id'))

    for row in pending_running_by_type:
        type_key = row['snmp_job__job_type'] or 'sin_tipo'
        entry = queue_breakdown_map[type_key]
        entry['type'] = type_key
        entry['type_display'] = job_type_labels.get(type_key, type_key.capitalize())
        if row['status'] == Execution.STATUS_PENDING:
            entry['pending'] = row['count']
        else:
            entry['running'] = row['count']

    queue_breakdown = sorted(
        queue_breakdown_map.values(),
        key=lambda item: item['pending'] + item['running'],
        reverse=True
    )

    # Eventos recientes del coordinator
    latest_events_qs = CoordinatorEvent.objects.select_related('olt', 'snmp_job').order_by('-created_at')[:30]
    events_data = []
    events_by_olt = defaultdict(list)

    for event in latest_events_qs:
        local_ts = timezone.localtime(event.created_at)
        details_summary = ''
        if isinstance(event.details, dict):
            parts = []
            for key, value in event.details.items():
                if value is None:
                    continue
                if isinstance(value, (dict, list)):
                    value = '…'
                parts.append(f"{key}: {value}")
                if len(parts) == 2:
                    break
            details_summary = ', '.join(parts)

        payload = {
            'id': event.id,
            'time': local_ts.strftime('%H:%M:%S'),
            'timestamp_iso': event.created_at.isoformat(),
            'event_type': event.get_event_type_display(),
            'event_code': event.event_type,
            'decision': event.get_decision_display() if event.decision else '',
            'decision_code': event.decision or '',
            'source': event.get_source_display(),
            'source_code': event.source,
            'olt': event.olt.abreviatura if event.olt else 'GLOBAL',
            'olt_id': event.olt_id,
            'job': event.snmp_job.nombre if event.snmp_job else 'Sin job',
            'job_type': event.snmp_job.job_type if event.snmp_job else '',
            'execution_id': event.execution_id,
            'reason': event.reason or '',
            'details_summary': details_summary,
            'details': event.details or {},
        }
        events_data.append(payload)

        if event.olt_id and len(events_by_olt[event.olt_id]) < 3:
            events_by_olt[event.olt_id].append(payload)

    interrupted_last_hour = Execution.objects.filter(
        status=Execution.STATUS_INTERRUPTED,
        created_at__gte=now - timedelta(hours=1)
    ).count()

    olts_data = []
    total_collisions = 0
    total_ready_tasks = 0

    for olt in active_olts:
        job_hosts = SnmpJobHost.objects.filter(
            olt=olt,
            enabled=True,
            snmp_job__enabled=True
        ).select_related('snmp_job', 'snmp_job__oid').order_by('-snmp_job__job_type', 'snmp_job__nombre')

        tasks_info = []
        total_executions_hour = 0
        collision_times = []
        ready_tasks_local = 0

        for job_host in job_hosts:
            job = job_host.snmp_job
            interval_seconds = job.interval_seconds or 3600
            executions_per_hour = max(1, 3600 // interval_seconds)
            total_executions_hour += executions_per_hour

            seconds_until = None
            time_until_str = 'No programado'
            time_class = 'normal'
            is_ready = False
            next_run_display = 'N/A'
            next_run_iso = None

            if job_host.next_run_at:
                next_run_iso = job_host.next_run_at.isoformat()
                next_run_display = timezone.localtime(job_host.next_run_at).strftime('%H:%M:%S')
                diff_seconds = int((job_host.next_run_at - now).total_seconds())
                seconds_until = diff_seconds

                if diff_seconds <= 0:
                    time_until_str = 'Listo para ejecutar'
                    time_class = 'ready'
                    is_ready = True
                elif diff_seconds < 60:
                    time_until_str = f"{diff_seconds}s"
                    time_class = 'soon'
                elif diff_seconds < 3600:
                    minutes = diff_seconds // 60
                    time_until_str = f"{minutes}m"
                else:
                    hours = diff_seconds // 3600
                    minutes = (diff_seconds % 3600) // 60
                    time_until_str = f"{hours}h {minutes}m"

                collision_times.append(job_host.next_run_at)

            if is_ready:
                ready_tasks_local += 1

            last_execution = Execution.objects.filter(
                olt=olt,
                snmp_job=job
            ).order_by('-created_at').first()

            last_exec_info = {
                'time': '',
                'status': '',
                'duration': 0,
            }
            if last_execution:
                last_exec_info['time'] = timezone.localtime(last_execution.created_at).strftime('%H:%M:%S')
                last_exec_info['status'] = last_execution.status
                last_exec_info['duration'] = last_execution.duration_ms or 0

            tasks_info.append({
                'name': job.nombre,
                'type': job.job_type,
                'type_display': job.get_job_type_display(),
                'interval_raw': job.interval_raw or f"{interval_seconds // 60}m",
                'interval_seconds': interval_seconds,
                'executions_per_hour': executions_per_hour,
                'next_run': next_run_display,
                'next_run_iso': next_run_iso,
                'time_until': time_until_str,
                'time_class': time_class,
                'time_until_seconds': seconds_until,
                'is_ready': is_ready,
                'priority': 90 if job.job_type == 'descubrimiento' else 40,
                'quota': {
                    'completed': 0,
                    'required': executions_per_hour,
                    'percentage': 0,
                },
                'last_execution': last_exec_info,
                'oid': job.oid.nombre if job.oid else 'N/A',
            })

        collision_pairs = 0
        ordered_times = sorted(collision_times)
        for idx, base_time in enumerate(ordered_times):
            for compare_time in ordered_times[idx + 1:]:
                if abs((compare_time - base_time).total_seconds()) < 60:
                    collision_pairs += 1
                else:
                    break

        total_collisions += collision_pairs
        total_ready_tasks += ready_tasks_local

        status_counts = status_counts_map.get(olt.id, {})

        olts_data.append({
            'id': olt.id,
            'name': olt.abreviatura,
            'ip': olt.ip_address,
            'tasks': tasks_info,
            'tasks_count': len(tasks_info),
            'total_executions_hour': total_executions_hour,
            'status_counts': {
                'PENDING': status_counts.get(Execution.STATUS_PENDING, 0),
                'RUNNING': status_counts.get(Execution.STATUS_RUNNING, 0),
            },
            'ready_tasks': ready_tasks_local,
            'collisions': collision_pairs,
            'recent_events': events_by_olt.get(olt.id, []),
        })

    global_stats = {
        'total_olts': active_olts.count(),
        'total_tasks': sum(olt['tasks_count'] for olt in olts_data),
        'total_executions_hour': sum(olt['total_executions_hour'] for olt in olts_data),
        'current_time': timezone.localtime(now).strftime('%H:%M:%S'),
        'current_date': timezone.localtime(now).strftime('%d/%m/%Y'),
        'pending_executions': global_pending,
        'running_executions': global_running,
        'events_count': len(events_data),
        'interrupted_last_hour': interrupted_last_hour,
        'queue_breakdown': queue_breakdown,
    }

    strategy_info = {
        'name': 'Coordinación con Prioridades en Vivo',
        'description': 'Ejecución secuencial por OLT con telemetría continua',
        'features': [
            'Una tarea SNMP por OLT a la vez',
            'Discovery (P90) ejecuta antes que GET (P40)',
            'Auto-reparación continua de JobHosts',
            'Detección temprana de colisiones (< 60s)'
        ],
        'metrics': {
            'collisions_detected': total_collisions,
            'tasks_sequenced': sum(len(olt['tasks']) for olt in olts_data),
            'ready_to_run': total_ready_tasks,
        }
    }

    return JsonResponse({
        'olts': olts_data,
        'events': events_data,
        'stats': global_stats,
        'strategy': strategy_info,
        'timestamp': now.isoformat()
    })
