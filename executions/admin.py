from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from .models import Execution


@admin.register(Execution)
class ExecutionAdmin(admin.ModelAdmin):
    """Admin para historiales de ejecución SNMP"""
    list_display = (
        'id', 'snmp_job', 'olt', 'status',
        'get_attempts_display', 'get_elapsed_time', 'started_at', 'finished_at', 'duration_ms'
    )
    list_filter = ('status', 'attempt', 'started_at', 'finished_at')
    search_fields = ('snmp_job__nombre', 'olt__abreviatura', 'celery_task_id')
    readonly_fields = ('created_at', 'result_summary', 'raw_output', 'error_message')
    actions = ['delete_masivo']
    
    def get_attempts_display(self, obj):
        """Muestra el número de intentos con indicadores visuales"""
        if obj.status == 'PENDING':
            if obj.attempt == 0:
                return "🟡 Esperando"
            else:
                return f"🔄 Esperando (reintento {obj.attempt})"
        elif obj.status == 'RUNNING':
            if obj.attempt == 0:
                return "⚡ Ejecutando"
            else:
                return f"⚡ Ejecutando (reintento {obj.attempt})"
        elif obj.status == 'SUCCESS':
            if obj.attempt == 0:
                return f"✅ Exitoso"
            else:
                return f"✅ Exitoso (reintento {obj.attempt})"
        elif obj.status == 'FAILED':
            if obj.attempt == 0:
                return f"❌ Fallido"
            else:
                return f"❌ Fallido (reintento {obj.attempt})"
        elif obj.status == 'INTERRUPTED':
            if obj.attempt == 0:
                return f"⏹️ Interrumpido"
            else:
                return f"⏹️ Interrumpido (reintento {obj.attempt})"
        else:
            if obj.attempt == 0:
                return "Principal"
            else:
                return f"Reintento {obj.attempt}"
    
    get_attempts_display.short_description = 'Intentos'
    get_attempts_display.admin_order_field = 'attempt'
    
    def get_elapsed_time(self, obj):
        """Muestra el tiempo transcurrido desde la creación"""
        from django.utils import timezone
        
        now = timezone.now()
        if obj.status in ['PENDING', 'RUNNING']:
            # Para ejecuciones activas, mostrar tiempo desde created_at
            elapsed = now - obj.created_at
        elif obj.finished_at:
            # Para ejecuciones terminadas, mostrar duración total
            elapsed = obj.finished_at - obj.created_at
        else:
            return "N/A"
        
        total_seconds = int(elapsed.total_seconds())
        
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    get_elapsed_time.short_description = 'Tiempo'
    get_elapsed_time.admin_order_field = 'created_at'
    
    def delete_masivo(self, request, queryset):
        """
        Elimina las ejecuciones seleccionadas usando sistema de cola optimizado
        """
        selected_ids = list(queryset.values_list('id', flat=True))
        total_selected = len(selected_ids)
        
        if total_selected == 0:
            self.message_user(
                request,
                _('No hay ejecuciones seleccionadas para eliminar.'),
                messages.WARNING
            )
            return
        
        try:
            # Importar la tarea de Celery
            from snmp_jobs.tasks import delete_history_records
            
            # Ejecutar tarea en background usando la cola background_deletes
            task = delete_history_records.delay(selected_ids)
            
            # Mostrar información inmediata
            self.message_user(
                request,
                _('✅ Borrado masivo iniciado: {} ejecuciones en cola background_deletes').format(total_selected),
                messages.SUCCESS
            )
            
            self.message_user(
                request,
                _('📦 Task ID: {} - Borrado optimizado iniciado').format(task.id),
                messages.INFO
            )
            
            # Nota: No esperamos el resultado aquí para evitar timeouts en el admin
            # El resultado se puede verificar en los logs de Celery
            
        except Exception as e:
            self.message_user(
                request,
                _('❌ Error al iniciar borrado masivo: {}').format(str(e)),
                messages.ERROR
            )
    
    delete_masivo.short_description = _('Borrar masivo')
    

    
    def has_add_permission(self, request):
        # No permitir creación manual
        return False
    
    def has_change_permission(self, request, obj=None):
        # Solo lectura
        return False
