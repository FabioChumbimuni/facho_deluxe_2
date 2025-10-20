from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from .models import OLT


@admin.register(OLT)
class OLTAdmin(admin.ModelAdmin):
    list_display = ('abreviatura', 'marca', 'get_modelo_display', 'ip_address', 'get_status_icon')
    list_filter = ('marca', 'modelo', 'habilitar_olt')
    search_fields = ('abreviatura', 'ip_address', 'descripcion', 'modelo__nombre')
    list_per_page = 20
    actions = ['deshabilitar_olts_seleccionadas', 'habilitar_olts_seleccionadas']
    
    # Configuración para formulario de selección limitado
    autocomplete_fields = ['marca', 'modelo']

    fieldsets = (
        (None, {
            'fields': (
                'abreviatura',
                'marca',
                'modelo',
                'ip_address',
                'descripcion',
                'comunidad',
            )
        }),
        ('Configuración', {
            'fields': (
                'habilitar_olt',
            )
        }),
    )

    def get_modelo_display(self, obj):
        """Muestra el modelo de forma legible"""
        if obj.modelo:
            return f"🔧 {obj.modelo.nombre}"
        return "🌐 Sin modelo"
    get_modelo_display.short_description = 'Modelo'
    
    def get_status_icon(self, obj):
        """Muestra un ícono visual del estado de la OLT"""
        if obj.habilitar_olt:
            return '🟢 Habilitada'
        else:
            return '🔴 Deshabilitada'
    get_status_icon.short_description = 'Estado'
    get_status_icon.admin_order_field = 'habilitar_olt'

    def deshabilitar_olts_seleccionadas(self, request, queryset):
        """Acción para deshabilitar OLTs seleccionadas"""
        # Filtrar solo las OLTs que están habilitadas
        olts_a_deshabilitar = queryset.filter(habilitar_olt=True)
        count = olts_a_deshabilitar.count()
        
        if count == 0:
            self.message_user(
                request,
                _('No hay OLTs habilitadas para deshabilitar.'),
                messages.WARNING
            )
            return
        
        # Deshabilitar las OLTs
        olts_a_deshabilitar.update(habilitar_olt=False)
        
        # Abortar ejecuciones PENDING para las OLTs deshabilitadas
        from snmp_jobs.models import SnmpJob
        total_aborted = 0
        for olt in olts_a_deshabilitar:
            aborted = SnmpJob.abort_pending_executions_for_olt(olt.id, "OLT deshabilitada")
            total_aborted += aborted
        
        # Mostrar mensaje de éxito
        if count == 1:
            message = _('1 OLT ha sido deshabilitada exitosamente.')
            if total_aborted > 0:
                message += f' {total_aborted} ejecuciones pendientes fueron abortadas.'
            self.message_user(request, message, messages.SUCCESS)
        else:
            message = _('{} OLTs han sido deshabilitadas exitosamente.').format(count)
            if total_aborted > 0:
                message += f' {total_aborted} ejecuciones pendientes fueron abortadas.'
            self.message_user(request, message, messages.SUCCESS)
        
        # Mostrar información adicional
        if queryset.count() > count:
            no_cambiadas = queryset.count() - count
            self.message_user(
                request,
                _('{} OLTs ya estaban deshabilitadas y no fueron modificadas.').format(no_cambiadas),
                messages.INFO
            )
    
    deshabilitar_olts_seleccionadas.short_description = _('Deshabilitar OLTs seleccionadas')

    def habilitar_olts_seleccionadas(self, request, queryset):
        """Acción para habilitar OLTs seleccionadas"""
        # Filtrar solo las OLTs que están deshabilitadas
        olts_a_habilitar = queryset.filter(habilitar_olt=False)
        count = olts_a_habilitar.count()
        
        if count == 0:
            self.message_user(
                request,
                _('No hay OLTs deshabilitadas para habilitar.'),
                messages.WARNING
            )
            return
        
        # Habilitar las OLTs
        olts_a_habilitar.update(habilitar_olt=True)
        
        # Mostrar mensaje de éxito
        if count == 1:
            self.message_user(
                request,
                _('1 OLT ha sido habilitada exitosamente.'),
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                _('{} OLTs han sido habilitadas exitosamente.').format(count),
                messages.SUCCESS
            )
        
        # Mostrar información adicional
        if queryset.count() > count:
            no_cambiadas = queryset.count() - count
            self.message_user(
                request,
                _('{} OLTs ya estaban habilitadas y no fueron modificadas.').format(no_cambiadas),
                messages.INFO
            )
    
    habilitar_olts_seleccionadas.short_description = _('Habilitar OLTs seleccionadas')