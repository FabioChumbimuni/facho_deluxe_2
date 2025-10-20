from django.contrib import admin
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

logger = logging.getLogger(__name__)
from .models import (
    SnmpJob,
    SnmpJobHost,
)
from .forms import SnmpJobForm
from brands.models import Brand
from hosts.models import OLT
from oids.models import OID

@admin.register(SnmpJob)
class SnmpJobAdmin(admin.ModelAdmin):
    """Admin para programar tareas SNMP"""
    
    change_list_template = 'admin/snmp_jobs/change_list.html'
    
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
    readonly_fields = ('interval_seconds', 'next_run_at', 'last_run_at')
    form = SnmpJobForm
    actions = ['deshabilitar_tareas_seleccionadas', 'habilitar_tareas_seleccionadas', 'mostrar_estadisticas_tareas', 'ejecutar_tareas_seleccionadas', 'deshabilitar_tarea_individual']
    
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
                                    
                                    # Crear nuevas relaciones
                                    bulk_olts = [
                                        SnmpJobHost(
                                            snmp_job=instance,
                                            olt=olt,
                                            enabled=True
                                        ) for olt in selected_olts
                                    ]
                                    SnmpJobHost.objects.bulk_create(bulk_olts)
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
                        for olt in form.cleaned_data['olts']:
                            SnmpJobHost.objects.create(
                                snmp_job=snmp_job,
                                olt=olt
                            )
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
    
    def get_next_run_display(self, obj):
        """Muestra la próxima ejecución en formato legible"""
        return obj.get_next_run_display()
    get_next_run_display.short_description = 'Próxima Ejecución'
    get_next_run_display.admin_order_field = 'next_run_at'
    
    def get_time_until_next_run(self, obj):
        """Muestra el tiempo restante hasta la próxima ejecución"""
        time_until = obj.get_time_until_next_run()
        
        # Si el job está deshabilitado, mostrar sin ícono
        if not obj.enabled:
            return f"⚫ {time_until}"
        elif obj.is_ready_to_run():
            return f"🔴 {time_until}"
        else:
            return f"⏰ {time_until}"
    get_time_until_next_run.short_description = 'Tiempo Restante'
    get_time_until_next_run.admin_order_field = 'next_run_at'

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
        """Acción para ejecutar manualmente las tareas SNMP seleccionadas (MÁXIMA PRIORIDAD)"""
        from executions.models import Execution
        from .tasks import discovery_manual_task
        from snmp_get.tasks import get_manual_task
        from django.utils import timezone
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Filtrar solo tareas habilitadas
        tareas_habilitadas = queryset.filter(enabled=True)
        
        # Si no se ha confirmado, mostrar ventana modal con resumen simple
        if request.POST.get('post') != 'yes':
            context = {
                **self.admin_site.each_context(request),
                'title': 'Confirmar Ejecución Manual de Tareas SNMP',
                'queryset': tareas_habilitadas,
                'total_tareas': tareas_habilitadas.count(),
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            }
            
            return render(request, 'admin/snmp_jobs/confirmar_ejecucion_manual.html', context)
        
        # Código original de ejecución
        
        if not tareas_habilitadas.exists():
            self.message_user(
                request,
                '⚠️ No hay tareas habilitadas seleccionadas para ejecutar.',
                messages.WARNING
            )
            return
        
        total_ejecuciones_creadas = 0
        total_tareas_procesadas = 0
        
        for tarea in tareas_habilitadas:
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
            self.message_user(
                request,
                f'📊 Las ejecuciones aparecerán en "Ejecuciones" y se procesarán inmediatamente en la cola discovery_manual.',
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




# No registrar estos modelos en el admin
# @admin.register(SnmpJobHost)
# @admin.register(SnmpJobOID)
