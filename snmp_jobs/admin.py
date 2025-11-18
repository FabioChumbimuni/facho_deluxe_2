from django.contrib import admin
from django.contrib.admin import helpers as admin_helpers
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.template.response import TemplateResponse
from django.urls import path
from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.contrib.admin.widgets import FilteredSelectMultiple
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)
from .models import (
    SnmpJob,
    SnmpJobHost,
    TaskFunction,
    TaskTemplate,
    OLTWorkflow,
    WorkflowNode,
    WorkflowEdge,
    WorkflowTemplate,
    WorkflowTemplateNode,
    WorkflowTemplateLink,
)
from .forms import SnmpJobForm
from brands.models import Brand
from hosts.models import OLT
from oids.models import OID

@admin.register(SnmpJob)
class SnmpJobAdmin(admin.ModelAdmin):
    """Admin para programar tareas SNMP"""
    
    change_list_template = 'admin/snmp_jobs/snmpjob/olt_task_list.html'
    
    def add_view(self, request, form_url='', extra_context=None):
        """Redirigir la vista de creación a programar_tarea"""
        return self.programar_tarea_view(request)
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Redirigir la vista de edición a programar_tarea"""
        return self.programar_tarea_view(request, object_id)
    
    list_display = ('nombre', 'marca', 'get_olts_count', 'get_oid_display', 'get_schedule_display', 'get_next_run_display', 'get_time_until_next_run', 'job_type', 'get_status_icon')
    list_display_links = ('nombre',)
    list_filter = ('marca', 'job_type', 'enabled')
    search_fields = ('nombre', 'descripcion')
    readonly_fields = ('interval_seconds', 'get_job_hosts_info')
    form = SnmpJobForm
    actions = ['deshabilitar_tareas_seleccionadas', 'habilitar_tareas_seleccionadas', 'mostrar_estadisticas_tareas', 'ejecutar_tareas_seleccionadas', 'deshabilitar_tarea_individual']
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(self._build_olt_task_context(request))
        return super().changelist_view(request, extra_context=extra_context)

    def _build_olt_task_context(self, request):
        """Construye el contexto para la tabla OLT ↔ tareas."""
        olt_filter = request.GET.get('olt') or ''
        type_filter = request.GET.get('task_type') or ''
        search_query = (request.GET.get('search') or '').strip().lower()

        job_hosts = SnmpJobHost.objects.select_related('snmp_job', 'olt')

        if olt_filter:
            job_hosts = job_hosts.filter(olt_id=olt_filter)
        if type_filter:
            job_hosts = job_hosts.filter(snmp_job__job_type=type_filter)

        if search_query:
            job_hosts = job_hosts.filter(
                models.Q(snmp_job__nombre__icontains=search_query) |
                models.Q(olt__abreviatura__icontains=search_query)
            )

        job_hosts = job_hosts.order_by('olt__abreviatura', 'snmp_job__nombre')

        grouped = defaultdict(list)
        for link in job_hosts:
            grouped[link.olt].append(link)

        olt_groups = []
        for olt, links in grouped.items():
            olt_groups.append({
                'olt': olt,
                'tasks': [{
                    'id': link.snmp_job_id,
                    'name': link.snmp_job.nombre,
                    'job_type': link.snmp_job.job_type,
                    'interval': link.snmp_job.interval_seconds,
                    'enabled': link.enabled and link.snmp_job.enabled,
                    'next_run_at': link.next_run_at,
                    'last_run_at': link.last_run_at,
                } for link in links],
            })

        olt_groups.sort(key=lambda item: item['olt'].abreviatura)

        olt_choices = OLT.objects.order_by('abreviatura').values('id', 'abreviatura')

        summary_total = sum(len(item['tasks']) for item in olt_groups)

        return {
            'olt_groups': olt_groups,
            'olt_choices': olt_choices,
            'selected_olt': olt_filter,
            'selected_task_type': type_filter,
            'search_query': search_query,
            'task_type_choices': SnmpJob.JOB_TYPES,
            'summary_total': summary_total,
        }

    def get_olts_count(self, obj):
        """Retorna el número de OLTs asociadas a la tarea"""
        return obj.olts.count()
    get_olts_count.short_description = 'OLTs'
    
    def get_oid_display(self, obj):
        """Retorna el nombre del OID"""
        if obj.oid:
            return f"{obj.oid.nombre}"
        return "-"
    get_oid_display.short_description = 'OID'
    
    def get_schedule_display(self, obj):
        """Muestra la descripción del horario programado"""
        return obj.get_schedule_description()
    get_schedule_display.short_description = 'Horario'
    
    def get_status_icon(self, obj):
        """Muestra un ícono visual del estado de la tarea"""
        if obj.enabled:
            return '🟢 Activa'
        else:
            return '🔴 Inactiva'
    get_status_icon.short_description = 'Estado'
    get_status_icon.admin_order_field = 'enabled'
    
    def get_job_hosts_info(self, obj):
        """
        Muestra información detallada de próximas ejecuciones por OLT
        """
        from django.utils.html import format_html
        from snmp_jobs.models import SnmpJobHost
        import pytz
        
        job_hosts = SnmpJobHost.objects.filter(
            snmp_job=obj,
            enabled=True
        ).select_related('olt').order_by('next_run_at')
        
        if not job_hosts:
            return format_html('<span style="color: orange;">⚠️ Sin OLTs asociadas</span>')
        
        lima_tz = pytz.timezone('America/Lima')
        html_parts = ['<table style="border-collapse: collapse; width: 100%;">']
        html_parts.append('<tr style="background-color: #f0f0f0; font-weight: bold;">')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">OLT</th>')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Próxima Ejecución</th>')
        html_parts.append('<th style="padding: 8px; text-align: left; border: 1px solid #ddd;">Estado</th>')
        html_parts.append('</tr>')
        
        for jh in job_hosts:
            # Color según estado de la OLT
            olt_color = 'green' if jh.olt.habilitar_olt else 'gray'
            olt_icon = '🟢' if jh.olt.habilitar_olt else '⚫'
            
            # Próxima ejecución
            if jh.next_run_at:
                next_run_lima = jh.next_run_at.astimezone(lima_tz)
                next_run_str = next_run_lima.strftime('%d/%m/%Y %H:%M:%S')
                status_color = 'blue'
                status_icon = '⏰'
            else:
                next_run_str = 'Sin programar'
                status_color = 'red'
                status_icon = '⚠️'
            
            html_parts.append('<tr>')
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ddd;"><span style="color: {olt_color};">{olt_icon} {jh.olt.abreviatura}</span></td>')
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ddd;"><span style="color: {status_color};">{next_run_str}</span></td>')
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ddd;"><span style="color: {status_color};">{status_icon}</span></td>')
            html_parts.append('</tr>')
        
        html_parts.append('</table>')
        
        return format_html(''.join(html_parts))
    get_job_hosts_info.short_description = 'Próximas Ejecuciones por OLT'


@admin.register(TaskFunction)
class TaskFunctionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "function_type", "module_path", "callable_name", "is_active")
    list_filter = ("function_type", "is_active")
    search_fields = ("code", "name", "module_path", "callable_name")
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "function", "default_priority", "default_interval_seconds", "is_active")
    list_filter = ("default_priority", "is_active", "function__function_type")
    search_fields = ("name", "slug", "function__name", "function__code")
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(OLTWorkflow)
class OLTWorkflowAdmin(admin.ModelAdmin):
    list_display = ("olt", "name", "is_active", "theme", "node_count")
    list_filter = ("is_active", "theme")
    search_fields = ("olt__abreviatura", "olt__ip_address", "name")
    readonly_fields = ("created_at", "updated_at")

    def node_count(self, obj):
        return obj.nodes.count()
    node_count.short_description = "Nodos"


@admin.register(WorkflowNode)
class WorkflowNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "workflow", "template", "priority", "interval_seconds", "enabled")
    list_filter = ("priority", "enabled", "workflow__theme", "template__function__function_type")
    search_fields = ("name", "workflow__olt__abreviatura", "template__name")
    readonly_fields = ("created_at", "updated_at")
    actions = ["deshabilitar_nodos"]

    @admin.action(description="Deshabilitar nodos seleccionados")
    def deshabilitar_nodos(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(
            request,
            f"{updated} nodo(s) deshabilitado(s).",
            level=messages.SUCCESS,
        )


@admin.register(WorkflowEdge)
class WorkflowEdgeAdmin(admin.ModelAdmin):
    list_display = ("workflow", "upstream_node", "downstream_node", "edge_type")
    list_filter = ("edge_type",)
    search_fields = ("workflow__olt__abreviatura", "upstream_node__name", "downstream_node__name")
    readonly_fields = ("created_at",)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('programar-tarea/', self.admin_site.admin_view(self.programar_tarea_view), 
                 name='snmp_jobs_snmpjob_programar_tarea'),
            path('documentacion/', self.admin_site.admin_view(self.documentacion_view),
                 name='snmp_jobs_snmpjob_documentacion'),
            path('get-olts/', self.admin_site.admin_view(self.get_olts_view),
                 name='snmp_jobs_snmpjob_get_olts'),
            path('get-oids/', self.admin_site.admin_view(self.get_oids_view),
                 name='snmp_jobs_snmpjob_get_oids'),
            path('get-oids-for-marca/', self.admin_site.admin_view(self.get_oids_for_marca_view),
                 name='snmp_jobs_snmpjob_get_oids_for_marca'),
        ]
        return custom_urls + urls
        
    def get_olts_view(self, request):
        """Vista para obtener OLTs filtrados por marca"""
        marca_id = request.GET.get('marca_id')
        try:
            # Incluir todas las OLTs de la marca, tanto habilitadas como deshabilitadas
            olts = OLT.objects.filter(marca_id=marca_id).order_by('abreviatura')
            data = []
            for olt in olts:
                data.append({
                    'id': str(olt.id),
                    'text': f"{olt.abreviatura} - {olt.ip_address}",
                    'enabled': olt.habilitar_olt,  # Agregar estado de habilitación
                    'selected': False
                })
            return JsonResponse({'results': data})
        except Exception as e:
            # Si hay algún error, devolver todas las OLTs
            olts = OLT.objects.all().order_by('abreviatura')
            data = []
            for olt in olts:
                data.append({
                    'id': str(olt.id),
                    'text': f"{olt.abreviatura} - {olt.ip_address}",
                    'enabled': olt.habilitar_olt,
                    'selected': False
                })
            return JsonResponse({'results': data})
        
    def get_oids_view(self, request):
        """Vista para obtener OIDs filtrados por marca"""
        marca_id = request.GET.get('marca_id')
        try:
            oids = OID.objects.filter(marca_id=marca_id).order_by('nombre')
            data = []
            for oid in oids:
                data.append({
                    'id': str(oid.id),
                    'text': f"{oid.nombre} ({oid.oid})",
                    'selected': False
                })
            return JsonResponse({'results': data})
        except Exception as e:
            # Si hay algún error, devolver todos los OIDs
            oids = OID.objects.all().order_by('nombre')
            data = []
            for oid in oids:
                data.append({
                    'id': str(oid.id),
                    'text': f"{oid.nombre} ({oid.oid})",
                    'selected': False
                })
            return JsonResponse({'results': data})
    
    def get_oids_for_marca_view(self, request):
        """Vista para obtener OIDs de una marca específica"""
        marca_id = request.GET.get('marca_id')
        
        if not marca_id:
            return JsonResponse({'oids': []})
        
        oids = OID.objects.filter(marca_id=marca_id).order_by('nombre')
        
        oids_data = []
        for oid in oids:
            oids_data.append({
                'id': oid.id,
                'text': f"{oid.nombre} ({oid.oid})",
                'nombre': oid.nombre,
                'oid': oid.oid,
                'espacio': oid.espacio,
                'espacio_display': oid.get_espacio_display(),
                'marca': oid.marca.nombre
            })
        
        return JsonResponse({'oids': oids_data})
    
    def programar_tarea_view(self, request, object_id=None):
        """Vista para programar o editar tareas SNMP"""
        instance = None
        initial_data = {}
        
        if object_id:
            instance = self.get_object(request, object_id)
            if instance:
                
                # Preparar datos iniciales para el formulario
                initial_data = {
                    'nombre': instance.nombre,
                    'descripcion': instance.descripcion,
                    'marca': instance.marca,
                    'oid': instance.oid.id if instance.oid else None,  # Usar ID en lugar de string
                    'job_type': instance.job_type,
                    'interval_raw': instance.interval_raw,
                    'cron_expr': instance.cron_expr,
                    'enabled': instance.enabled,
                    'olts': instance.olts.all(),
                }
        
        if request.method == 'POST':
            # Si estamos editando, agregar la marca al POST data si no está presente
            if instance and 'marca' not in request.POST:
                # Crear una copia mutable del POST data
                post_data = request.POST.copy()
                post_data['marca'] = str(instance.marca.id)
                form = SnmpJobForm(post_data, instance=instance, initial=initial_data)
            else:
                form = SnmpJobForm(request.POST, instance=instance, initial=initial_data)
            
            if form.is_valid():
                try:
                    if instance:
                        try:
                            with transaction.atomic():
                                # Actualizar campos básicos
                                instance.nombre = form.cleaned_data['nombre']
                                instance.descripcion = form.cleaned_data['descripcion']
                                # En edición, mantener la marca original
                                # instance.marca = form.cleaned_data['marca']  # Comentado para evitar cambios
                                
                                # Usar el método clean_oid del formulario
                                instance.oid = form.cleaned_data['oid']
                                
                                instance.job_type = form.cleaned_data['job_type']
                                instance.interval_raw = form.cleaned_data['interval_raw']
                                instance.enabled = form.cleaned_data['enabled']
                                instance.save()
                                
                                # Obtener OLTs seleccionadas
                                selected_olts = form.cleaned_data.get('olts', [])
                                if not selected_olts:
                                    raise ValidationError('Debe seleccionar al menos una OLT.')
                                
                                # Actualizar OLTs
                                try:
                                    # Eliminar relaciones existentes
                                    SnmpJobHost.objects.filter(snmp_job=instance).delete()
                                    
                                    # IMPORTANTE: Usar .create() en lugar de bulk_create()
                                    # para que se dispare el signal post_save que inicializa next_run_at
                                    for olt in selected_olts:
                                        SnmpJobHost.objects.create(
                                            snmp_job=instance,
                                            olt=olt,
                                            enabled=True
                                        )
                                    
                                    # NOTA: Si algún signal falla, el coordinador auto-repara en ~5 segundos
                                    # Ver: execution_coordinator/dynamic_scheduler.py::get_ready_tasks()
                                    
                                    logger.info(f"✅ {len(selected_olts)} OLTs actualizadas para {instance.nombre}")
                                except Exception as e:
                                    raise ValidationError(f'Error al guardar OLTs: {str(e)}')
                                
                                # Las ejecuciones pendientes se manejan automáticamente en el modelo SnmpJob.save()
                                
                            messages.success(request, f'Tarea SNMP actualizada: {instance.nombre}')
                        except Exception as e:
                            messages.error(request, f'Error al actualizar tarea: {str(e)}')
                    else:
                        # Crear nueva tarea
                        # Usar el método clean_oid del formulario
                        snmp_job = SnmpJob.objects.create(
                            nombre=form.cleaned_data['nombre'],
                            descripcion=form.cleaned_data['descripcion'],
                            marca=form.cleaned_data['marca'],
                            oid=form.cleaned_data['oid'],
                            job_type=form.cleaned_data['job_type'],
                            interval_raw=form.cleaned_data['interval_raw'],
                            enabled=form.cleaned_data['enabled']
                        )
                        
                        # Agregar OLTs usando through model
                        # IMPORTANTE: Usar .create() individual para disparar signals
                        for olt in form.cleaned_data['olts']:
                            SnmpJobHost.objects.create(
                                snmp_job=snmp_job,
                                olt=olt,
                                enabled=True
                            )
                        
                        logger.info(f"✅ Tarea creada con {len(form.cleaned_data['olts'])} OLTs")
                        messages.success(request, f'Tarea SNMP programada: {snmp_job.nombre}')
                    
                    return redirect('admin:snmp_jobs_snmpjob_changelist')
                    
                except Exception as e:
                    messages.error(request, f'Error al programar tarea: {str(e)}')
        else:
            form = SnmpJobForm(instance=instance, initial=initial_data)
        
        # Datos para JavaScript
        brands_data = []
        for brand in Brand.objects.all():
            brands_data.append({
                'id': brand.id,
                'name': brand.nombre
            })
        
        # Preparar datos iniciales
        if instance:
            # En edición, obtener OLTs de la marca actual (todas, habilitadas y deshabilitadas)
            marca_id = instance.marca_id
            all_olts = OLT.objects.filter(marca_id=marca_id)  # Incluir todas las OLTs
            selected_olts = instance.olts.all()
            oids = OID.objects.filter(marca_id=marca_id)
        else:
            # En creación, obtener OLTs de la marca seleccionada (si hay una)
            marca_id = None
            if request.GET.get('marca_id'):
                marca_id = request.GET.get('marca_id')
                all_olts = OLT.objects.filter(marca_id=marca_id)  # Incluir todas las OLTs de la marca
                oids = OID.objects.filter(marca_id=marca_id)
            else:
                # Sin marca seleccionada, mostrar todas las OLTs habilitadas
                all_olts = OLT.objects.filter(habilitar_olt=True)
                oids = OID.objects.all()
            selected_olts = []
            
        # Preparar datos de OLTs
        olts_data = []
        selected_olt_ids = set(selected_olts.values_list('id', flat=True)) if instance else set()
        
        for olt in all_olts.select_related('marca'):
            olts_data.append({
                'id': str(olt.id),  # Convertir a string para comparación JS
                'text': f"{olt.abreviatura} - {olt.ip_address}",
                'brand_id': olt.marca_id,
                'enabled': olt.habilitar_olt,  # Agregar estado de habilitación
                'selected': olt.id in selected_olt_ids
            })
        
        # Preparar datos de OIDs
        oids_data = []
        for oid in oids.select_related('marca'):
            oids_data.append({
                'id': str(oid.id),  # Convertir a string para comparación JS
                'text': f"{oid.nombre} ({oid.oid})",
                'oid': oid.oid,  # Agregar el valor del OID para búsqueda
                'brand_id': oid.marca_id,
                'espacio': oid.espacio,  # Agregar información del espacio
                'espacio_display': oid.get_espacio_display(),  # Agregar display del espacio
                'selected': instance and instance.oid and instance.oid.id == oid.id
            })
        
        title = 'Editar Tarea SNMP' if instance else 'Programar Nueva Tarea SNMP'
        context = {
            'title': title,
            'form': form,
            'brands_data': json.dumps(brands_data, cls=DjangoJSONEncoder),
            'olts_data': json.dumps(olts_data, cls=DjangoJSONEncoder),
            'oids_data': json.dumps(oids_data, cls=DjangoJSONEncoder),
            'opts': {
                'app_label': 'snmp_jobs',
                'app_config': self.model._meta.app_config,
                'verbose_name_plural': self.model._meta.verbose_name_plural,
            },
            'is_edit': bool(instance),
            'original': instance,
        }
        
        return TemplateResponse(request, 'admin/snmp_jobs/programar_tarea.html', context)
    
    def has_add_permission(self, request):
        """Permitir crear tareas SNMP"""
        return True
    
    def has_change_permission(self, request, obj=None):
        # Permitir edición
        return True
    
    def get_next_run_display(self, obj):
        """
        Muestra la próxima ejecución MÁS CERCANA entre todas las OLTs
        (Cada OLT tiene su propio next_run_at en SnmpJobHost)
        """
        if not obj.enabled:
            return "No disponible"
        
        # Buscar el next_run_at más cercano entre todos los job_hosts
        from snmp_jobs.models import SnmpJobHost
        import pytz
        
        next_runs = SnmpJobHost.objects.filter(
            snmp_job=obj,
            enabled=True,
            next_run_at__isnull=False,
            olt__habilitar_olt=True  # Solo OLTs habilitadas
        ).values_list('next_run_at', 'olt__abreviatura').order_by('next_run_at')[:1]
        
        if next_runs:
            next_run, olt_name = next_runs[0]
            lima_tz = pytz.timezone('America/Lima')
            next_run_lima = next_run.astimezone(lima_tz)
            return f"{next_run_lima.strftime('%d/%m/%Y %H:%M:%S')} ({olt_name})"
        
        return "No programado"
    get_next_run_display.short_description = 'Próxima Ejecución'
    
    def get_time_until_next_run(self, obj):
        """
        Muestra el tiempo restante hasta la próxima ejecución MÁS CERCANA
        """
        if not obj.enabled:
            return "⚫ No disponible"
        
        # Buscar el next_run_at más cercano
        from snmp_jobs.models import SnmpJobHost
        from django.utils import timezone
        
        next_run_obj = SnmpJobHost.objects.filter(
            snmp_job=obj,
            enabled=True,
            next_run_at__isnull=False,
            olt__habilitar_olt=True  # Solo OLTs habilitadas
        ).order_by('next_run_at').first()
        
        if not next_run_obj or not next_run_obj.next_run_at:
            return "⚠️ Sin programar"
        
        now = timezone.now()
        if next_run_obj.next_run_at <= now:
            return f"🔴 Listo para ejecutar"
        
        diff = next_run_obj.next_run_at - now
        total_seconds = int(diff.total_seconds())
        
        if total_seconds < 60:
            return f"⏰ En {total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"⏰ En {minutes}m {seconds}s"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"⏰ En {hours}h {minutes}m"
        else:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            return f"⏰ En {days}d {hours}h"
    get_time_until_next_run.short_description = 'Tiempo Restante'

    # Auto-refresh removido por solicitud del usuario
    def deshabilitar_tareas_seleccionadas(self, request, queryset):
        """Acción para deshabilitar tareas SNMP seleccionadas"""
        # Filtrar solo las tareas que están habilitadas
        tareas_a_deshabilitar = queryset.filter(enabled=True)
        count = tareas_a_deshabilitar.count()
        
        if count == 0:
            self.message_user(
                request,
                _('No hay tareas habilitadas para deshabilitar.'),
                messages.WARNING
            )
            return
        
        # Deshabilitar las tareas
        tareas_a_deshabilitar.update(enabled=False)
        
        # Mostrar mensaje de éxito
        if count == 1:
            self.message_user(
                request,
                _('1 tarea ha sido deshabilitada exitosamente.'),
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                _('{} tareas han sido deshabilitadas exitosamente.').format(count),
                messages.SUCCESS
            )
        
        # Mostrar información adicional
        if queryset.count() > count:
            no_cambiadas = queryset.count() - count
            self.message_user(
                request,
                _('{} tareas ya estaban deshabilitadas y no fueron modificadas.').format(no_cambiadas),
                messages.INFO
            )
    
    deshabilitar_tareas_seleccionadas.short_description = _('Deshabilitar tareas seleccionadas')

    def habilitar_tareas_seleccionadas(self, request, queryset):
        """Acción para habilitar tareas SNMP seleccionadas"""
        # Filtrar solo las tareas que están deshabilitadas
        tareas_a_habilitar = queryset.filter(enabled=False)
        count = tareas_a_habilitar.count()
        
        if count == 0:
            self.message_user(
                request,
                _('No hay tareas deshabilitadas para habilitar.'),
                messages.WARNING
            )
            return
        
        # Habilitar las tareas usando el nuevo método SIN catch-up
        for tarea in tareas_a_habilitar:
            tarea.enable_with_catchup_prevention()
        
        # Mostrar mensaje de éxito
        if count == 1:
            self.message_user(
                request,
                _('1 tarea ha sido habilitada exitosamente. Se ejecutará según su intervalo programado.'),
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                _('{} tareas han sido habilitadas exitosamente. Se ejecutarán según sus intervalos programados.').format(count),
                messages.SUCCESS
            )
        
        # Mostrar información adicional
        if queryset.count() > count:
            no_cambiadas = queryset.count() - count
            self.message_user(
                request,
                _('{} tareas ya estaban habilitadas y no fueron modificadas.').format(no_cambiadas),
                messages.INFO
            )
    
    habilitar_tareas_seleccionadas.short_description = _('Habilitar tareas seleccionadas')

    def mostrar_estadisticas_tareas(self, request, queryset):
        """Acción para mostrar estadísticas de las tareas seleccionadas"""
        from django.db.models import Count
        from executions.models import Execution
        from django.utils import timezone
        from datetime import timedelta
        
        # Obtener estadísticas de las últimas 24 horas
        ultimas_24h = timezone.now() - timedelta(hours=24)
        
        total_tareas = queryset.count()
        tareas_habilitadas = queryset.filter(enabled=True).count()
        tareas_deshabilitadas = queryset.filter(enabled=False).count()
        
        # Obtener ejecuciones de las tareas seleccionadas
        ejecuciones = Execution.objects.filter(
            snmp_job__in=queryset,
            created_at__gte=ultimas_24h
        )
        
        total_ejecuciones = ejecuciones.count()
        ejecuciones_exitosas = ejecuciones.filter(status='SUCCESS').count()
        ejecuciones_fallidas = ejecuciones.filter(status='FAILED').count()
        ejecuciones_pendientes = ejecuciones.filter(status='PENDING').count()
        
        # Calcular tasa de éxito
        tasa_exito = 0
        if total_ejecuciones > 0:
            tasa_exito = (ejecuciones_exitosas / total_ejecuciones) * 100
        
        # Mostrar estadísticas
        self.message_user(
            request,
            f'📊 Estadísticas de {total_tareas} tareas seleccionadas:',
            messages.INFO
        )
        
        self.message_user(
            request,
            f'🟢 Tareas habilitadas: {tareas_habilitadas} | 🔴 Tareas deshabilitadas: {tareas_deshabilitadas}',
            messages.INFO
        )
        
        self.message_user(
            request,
            f'📈 Ejecuciones (24h): {total_ejecuciones} | ✅ Exitosas: {ejecuciones_exitosas} | ❌ Fallidas: {ejecuciones_fallidas} | ⏳ Pendientes: {ejecuciones_pendientes}',
            messages.INFO
        )
        
        self.message_user(
            request,
            f'📊 Tasa de éxito: {tasa_exito:.1f}%',
            messages.INFO
        )
    
    mostrar_estadisticas_tareas.short_description = _('Mostrar estadísticas de tareas')

    def ejecutar_tareas_seleccionadas(self, request, queryset):
        """Acción para ejecutar manualmente las tareas SNMP seleccionadas (MÁXIMA PRIORIDAD)
        
        Permite ejecutar tareas inactivas MANUALMENTE, pero SOLO con OLTs habilitadas.
        Las OLTs deshabilitadas NUNCA se ejecutarán.
        """
        from executions.models import Execution
        from .tasks import discovery_manual_task
        from snmp_get.tasks import get_manual_task
        from django.utils import timezone
        import logging
        
        logger = logging.getLogger(__name__)
        
        # CAMBIO: Ya NO filtrar por enabled=True - permitir ejecutar tareas inactivas MANUALMENTE
        # La restricción de OLTs habilitadas se mantiene más abajo
        tareas_seleccionadas = queryset
        
        # Si no se ha confirmado, mostrar ventana modal con resumen simple
        if request.POST.get('post') != 'yes':
            # Separar tareas activas e inactivas para el modal
            tareas_activas = tareas_seleccionadas.filter(enabled=True)
            tareas_inactivas = tareas_seleccionadas.filter(enabled=False)
            
            context = {
                **self.admin_site.each_context(request),
                'title': 'Confirmar Ejecución Manual de Tareas SNMP',
                'queryset': tareas_seleccionadas,
                'total_tareas': tareas_seleccionadas.count(),
                'tareas_activas': tareas_activas,
                'tareas_inactivas': tareas_inactivas,
                'action_checkbox_name': admin_helpers.ACTION_CHECKBOX_NAME,
            }
            
            return render(request, 'admin/snmp_jobs/confirmar_ejecucion_manual.html', context)
        
        # Código original de ejecución
        
        if not tareas_seleccionadas.exists():
            self.message_user(
                request,
                '⚠️ No hay tareas seleccionadas para ejecutar.',
                messages.WARNING
            )
            return
        
        total_ejecuciones_creadas = 0
        total_tareas_procesadas = 0
        tareas_inactivas_ejecutadas = 0
        
        for tarea in tareas_seleccionadas:
            # Contar tareas inactivas que se están ejecutando manualmente
            if not tarea.enabled:
                tareas_inactivas_ejecutadas += 1
            # Obtener job_hosts habilitados para esta tarea
            job_hosts = tarea.job_hosts.filter(enabled=True)
            
            if not job_hosts.exists():
                continue
                
            ejecuciones_tarea = 0
            total_tareas_procesadas += 1
            
            for job_host in job_hosts:
                # Verificar que la OLT esté habilitada
                if job_host.olt.habilitar_olt:
                    # Crear Execution
                    execution = Execution.objects.create(
                        snmp_job=tarea,
                        job_host=job_host,
                        olt=job_host.olt,
                        status='PENDING',
                        attempt=0,  # Ejecución principal siempre es attempt 0
                        requested_by=request.user
                    )
                    
                    # ENCOLAR EN COLA DE MÁXIMA PRIORIDAD (SIN BLOQUEAR ADMIN)
                    # Usar tarea correcta según job_type
                    try:
                        if tarea.job_type == 'get':
                            # Tarea GET: usar get_manual_task
                            get_manual_task.delay(tarea.id, job_host.olt.id, execution.id)
                            logger.info(f"📥 Tarea GET manual encolada: {execution.id} para OLT {job_host.olt.abreviatura}")
                        else:
                            # Tarea Discovery/otros: usar discovery_manual_task
                            discovery_manual_task.delay(tarea.id, job_host.olt.id, execution.id)
                            logger.info(f"🔍 Tarea Discovery manual encolada: {execution.id} para OLT {job_host.olt.abreviatura}")
                        
                        ejecuciones_tarea += 1
                        total_ejecuciones_creadas += 1
                    except Exception as e:
                        # Marcar como fallida si hay error al encolar
                        execution.status = 'FAILED'
                        execution.error_message = f"Error al encolar: {str(e)}"
                        execution.finished_at = timezone.now()
                        execution.save()
                        ejecuciones_tarea += 1
                        total_ejecuciones_creadas += 1
            
            if ejecuciones_tarea > 0:
                # Actualizar last_run_at de la tarea
                tarea.last_run_at = timezone.now()
                tarea.save()
        
        # Mostrar mensaje de éxito
        if total_ejecuciones_creadas > 0:
            self.message_user(
                request,
                f'🚀 Ejecutadas {total_tareas_procesadas} tareas: {total_ejecuciones_creadas} ejecuciones creadas y encoladas con MÁXIMA PRIORIDAD.',
                messages.SUCCESS
            )
            
            # Mensaje especial si se ejecutaron tareas inactivas
            if tareas_inactivas_ejecutadas > 0:
                self.message_user(
                    request,
                    f'⚠️ NOTA: Se ejecutaron {tareas_inactivas_ejecutadas} tarea(s) INACTIVA(S) manualmente. Solo se procesaron OLTs habilitadas.',
                    messages.WARNING
                )
            
            self.message_user(
                request,
                f'📊 Las ejecuciones aparecerán en "Ejecuciones" y se procesarán inmediatamente en la cola discovery_manual.',
                messages.INFO
            )
            
            self.message_user(
                request,
                f'✅ Solo se ejecutaron en OLTs HABILITADAS. OLTs deshabilitadas fueron ignoradas.',
                messages.INFO
            )
        else:
            self.message_user(
                request,
                '⚠️ No se crearon ejecuciones. Verifique que las tareas tengan OLTs habilitadas asociadas.',
                messages.WARNING
            )
    
    ejecutar_tareas_seleccionadas.short_description = _('🚀 Ejecutar tareas seleccionadas')

    def documentacion_view(self, request):
        """Vista para mostrar la documentación de tareas SNMP"""
        context = {
            **self.admin_site.each_context(request),
            'title': '📚 Documentación de Tareas SNMP',
        }
        
        return render(request, 'admin/snmp_jobs/documentacion_tareas.html', context)

    def deshabilitar_tarea_individual(self, request, queryset):
        """Acción para deshabilitar una tarea individual rápidamente"""
        if queryset.count() != 1:
            self.message_user(
                request,
                '⚠️ Esta acción solo funciona con una tarea seleccionada.',
                messages.WARNING
            )
            return
        
        tarea = queryset.first()
        
        if not tarea.enabled:
            self.message_user(
                request,
                f'ℹ️ La tarea "{tarea.nombre}" ya está deshabilitada.',
                messages.INFO
            )
            return
        
        try:
            # Deshabilitar la tarea
            tarea.enabled = False
            tarea.save()
            
            # El modelo se encarga automáticamente de abortar ejecuciones pendientes
            self.message_user(
                request,
                f'✅ Tarea "{tarea.nombre}" deshabilitada correctamente.',
                messages.SUCCESS
            )
            
        except Exception as e:
            self.message_user(
                request,
                f'❌ Error al deshabilitar tarea: {str(e)}',
                messages.ERROR
            )
    
    deshabilitar_tarea_individual.short_description = _('🛑 Deshabilitar tarea (rápido)')

    def has_delete_permission(self, request, obj=None):
        # Permitir eliminación
        return True




@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "olts_count_display", "node_count", "workflow_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at", "olts_count_display")
    
    fieldsets = (
        ("Información Básica", {
            "fields": ("name", "description", "is_active")
        }),
        ("Estado", {
            "fields": ("olts_count_display", "node_count", "workflow_count"),
            "description": "⚠️ IMPORTANTE: Una plantilla solo puede ejecutarse si está vinculada a al menos una OLT. "
                          "Las plantillas sin OLTs asignadas no generan ejecuciones."
        }),
        ("Fechas", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def node_count(self, obj):
        return obj.template_nodes.count()
    node_count.short_description = "Nodos"
    
    def workflow_count(self, obj):
        return obj.workflow_links.count()
    workflow_count.short_description = "Workflows Vinculados"
    
    def olts_count_display(self, obj):
        """Muestra el número de OLTs asignadas con advertencia si está activa sin OLTs"""
        count = obj.olts_count
        if obj.is_active and count == 0:
            return format_html(
                '<span style="color: red; font-weight: bold;">⚠️ {} OLTs (NO EJECUTABLE)</span>',
                count
            )
        elif count == 0:
            return format_html(
                '<span style="color: orange;">{} OLTs (Inactiva)</span>',
                count
            )
        else:
            return format_html(
                '<span style="color: green;">✅ {} OLTs</span>',
                count
            )
    olts_count_display.short_description = "OLTs Asignadas"


@admin.register(WorkflowTemplateNode)
class WorkflowTemplateNodeAdmin(admin.ModelAdmin):
    list_display = ("name", "template", "key", "oid", "get_espacio_display", "priority", "interval_seconds", "enabled")
    list_filter = ("priority", "enabled", "template", "oid__espacio", "oid__marca", "oid__modelo")
    search_fields = ("name", "key", "template__name", "oid__nombre", "oid__oid")
    readonly_fields = ("created_at", "updated_at", "get_espacio_display")
    autocomplete_fields = ["oid"]
    
    def get_espacio_display(self, obj):
        """Muestra el espacio del OID"""
        return obj.oid.get_espacio_display() if obj.oid else "-"
    get_espacio_display.short_description = "Tipo"


@admin.register(WorkflowTemplateLink)
class WorkflowTemplateLinkAdmin(admin.ModelAdmin):
    list_display = ("template", "workflow", "auto_sync", "created_at")
    list_filter = ("auto_sync", "template")
    search_fields = ("template__name", "workflow__olt__abreviatura")
    readonly_fields = ("created_at", "updated_at")


# No registrar estos modelos en el admin
# @admin.register(SnmpJobHost)
# @admin.register(SnmpJobOID)
