from django.contrib import admin
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.core.exceptions import ValidationError
from .models import OLT


@admin.register(OLT)
class OLTAdmin(admin.ModelAdmin):
    # ✅ Template personalizado para mostrar botón de restaurar
    change_form_template = 'admin/hosts/olt/change_form.html'
    
    class Media:
        css = {
            'all': ('hosts/css/olt_admin_styles.css',)
        }
    
    list_display = ('abreviatura', 'marca', 'get_modelo_display', 'ip_address', 'get_status_icon', 'get_deleted_status')
    list_filter = ('marca', 'modelo', 'habilitar_olt', 'is_deleted')
    search_fields = ('abreviatura', 'ip_address', 'descripcion', 'modelo__nombre')
    list_per_page = 20
    actions = ['deshabilitar_olts_seleccionadas', 'habilitar_olts_seleccionadas', 'restore_olts_seleccionadas']
    
    # ✅ Usar all_objects para mostrar todas las OLTs en admin
    def get_queryset(self, request):
        qs = OLT.all_objects.select_related('marca', 'modelo')
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs
    
    # Configuración para formulario de selección limitado
    autocomplete_fields = ['marca', 'modelo']

    # ✅ Campos readonly para mostrar información de soft delete
    readonly_fields = ['get_soft_delete_info', 'created_at', 'updated_at']

    def get_fieldsets(self, request, obj=None):
        """Campos dinámicos según si la OLT está eliminada o no"""
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
        
        # Si la OLT está eliminada, agregar información de eliminación
        if obj and obj.is_deleted:
            fieldsets = fieldsets + (
                ('🗑️ Información de Eliminación', {
                    'fields': (
                        'get_soft_delete_info',
                    ),
                    'classes': ('alert', 'alert-error'),
                    'description': 'Esta OLT está eliminada. Use el botón "Restaurar OLT" para restaurarla.'
                }),
            )
        
        # Agregar timestamps al final
        fieldsets = fieldsets + (
            ('Metadata', {
                'fields': (
                    'created_at',
                    'updated_at',
                ),
                'classes': ('collapse',),
            }),
        )
        
        return fieldsets

    def get_modelo_display(self, obj):
        """Muestra el modelo de forma legible"""
        if obj.modelo:
            return f"🔧 {obj.modelo.nombre}"
        return "🌐 Sin modelo"
    get_modelo_display.short_description = 'Modelo'
    
    def get_status_icon(self, obj):
        """Muestra un ícono visual del estado de la OLT"""
        if obj.is_deleted:
            return '🗑️ Eliminada'
        elif obj.habilitar_olt:
            return '🟢 Habilitada'
        else:
            return '🔴 Deshabilitada'
    get_status_icon.short_description = 'Estado'
    get_status_icon.admin_order_field = 'habilitar_olt'
    
    def get_deleted_status(self, obj):
        """Muestra información sobre el soft delete"""
        if obj.is_deleted:
            deleted_by = f" por {obj.deleted_by.username}" if obj.deleted_by else ""
            deleted_at = obj.deleted_at.strftime("%Y-%m-%d %H:%M") if obj.deleted_at else "N/A"
            return f"🗑️ Eliminada{deleted_by} el {deleted_at}"
        return "✅ Activa"
    get_deleted_status.short_description = 'Estado de Eliminación'

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
    
    def restore_olts_seleccionadas(self, request, queryset):
        """Acción para restaurar OLTs eliminadas"""
        # Filtrar solo las OLTs que están eliminadas
        olts_a_restaurar = queryset.filter(is_deleted=True)
        count = olts_a_restaurar.count()
        
        if count == 0:
            self.message_user(
                request,
                _('No hay OLTs eliminadas para restaurar.'),
                messages.WARNING
            )
            return
        
        # Restaurar las OLTs
        restored_count = 0
        renamed_count = 0
        errors = []
        rename_messages = []
        
        for olt in olts_a_restaurar:
            try:
                # Restaurar con renombrado automático si hay conflicto
                restore_info = olt.restore(user=request.user, rename_on_conflict=True)
                restored_count += 1
                
                # Registrar si fue renombrada
                if restore_info.get('renamed', False):
                    renamed_count += 1
                    rename_messages.append(
                        f"{restore_info['original_abreviatura']} → {restore_info['new_abreviatura']}"
                    )
            except Exception as e:
                errors.append(f"{olt.abreviatura}: {str(e)}")
        
        # Mostrar mensaje de éxito
        if restored_count > 0:
            if restored_count == 1:
                if renamed_count == 1:
                    message = _('1 OLT ha sido restaurada exitosamente (renombrada automáticamente).')
                else:
                    message = _('1 OLT ha sido restaurada exitosamente.')
            else:
                message = _('{} OLTs han sido restauradas exitosamente.').format(restored_count)
                if renamed_count > 0:
                    message += _(' {} fueron renombradas automáticamente.').format(renamed_count)
            
            self.message_user(request, message, messages.SUCCESS)
            
            # Mostrar detalles de renombrados
            if rename_messages:
                for rename_msg in rename_messages:
                    self.message_user(
                        request,
                        _('🔄 Renombrado: {}').format(rename_msg),
                        messages.INFO
                    )
        
        # Mostrar errores si hubo
        if errors:
            for error in errors:
                self.message_user(request, error, messages.ERROR)
    
    restore_olts_seleccionadas.short_description = _('Restaurar OLTs eliminadas')
    
    def get_soft_delete_info(self, obj):
        """Muestra información detallada del soft delete con soporte para tema claro/oscuro"""
        if not obj.is_deleted:
            return format_html(
                '<span class="olt-active-indicator" style="color: #28a745 !important; font-weight: bold;">✅ OLT Activa</span>'
            )
        
        info_parts = []
        
        if obj.deleted_at:
            info_parts.append(
                f'<strong style="color: inherit !important;">📅 Fecha de eliminación:</strong> {obj.deleted_at.strftime("%Y-%m-%d %H:%M:%S")}'
            )
        
        if obj.deleted_by:
            full_name = obj.deleted_by.get_full_name() or ""
            info_parts.append(
                f'<strong style="color: inherit !important;">👤 Eliminada por:</strong> {obj.deleted_by.username} ({full_name})'
            )
        
        if obj.deletion_reason:
            info_parts.append(f'<strong style="color: inherit !important;">📝 Razón:</strong> {obj.deletion_reason}')
        
        if not info_parts:
            return format_html(
                '<span class="olt-deleted-minimal" style="color: #e35f5f !important;">🗑️ OLT Eliminada (sin información adicional)</span>'
            )
        
        # HTML con clases CSS y estilos inline explícitos para ambos temas
        html = '''
        <div class="olt-deleted-info" style="
            background-color: #fff3cd !important;
            padding: 10px !important;
            border-left: 4px solid #ffc107 !important;
            margin: 10px 0 !important;
            border-radius: 4px !important;
            color: #856404 !important;
        ">
            <strong class="olt-deleted-title" style="
                color: #856404 !important;
                display: block !important;
                margin-bottom: 10px !important;
                font-size: 1.1em !important;
            ">🗑️ OLT Eliminada</strong>
            <div class="olt-deleted-details" style="
                color: #856404 !important;
                line-height: 1.6 !important;
            ">
        '''
        html += '<br>'.join(info_parts)
        html += '''
            </div>
        </div>
        '''
        
        return format_html(html)
    get_soft_delete_info.short_description = 'Información de Eliminación'
    
    def get_readonly_fields(self, request, obj=None):
        """Campos readonly dinámicos"""
        readonly = list(self.readonly_fields)
        
        # Si la OLT está eliminada, hacer todos los campos readonly excepto get_soft_delete_info
        if obj and obj.is_deleted:
            # Obtener todos los campos del modelo
            model_fields = [f.name for f in obj._meta.get_fields() if hasattr(f, 'name')]
            # Agregar campos personalizados que NO deben ser readonly
            excluded = ['get_soft_delete_info']
            readonly.extend([f for f in model_fields if f not in excluded and f not in readonly])
        
        return readonly
    
    def get_urls(self):
        """Agregar URLs personalizadas para restaurar"""
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/restore/',
                self.admin_site.admin_view(self.restore_olt_view),
                name='hosts_olt_restore',
            ),
        ]
        return custom_urls + urls
    
    def restore_olt_view(self, request, object_id):
        """Vista para restaurar una OLT individual desde el formulario"""
        try:
            olt = OLT.all_objects.get(pk=object_id, is_deleted=True)
        except OLT.DoesNotExist:
            self.message_user(
                request,
                _('OLT no encontrada o no está eliminada.'),
                messages.ERROR
            )
            return redirect('admin:hosts_olt_changelist')
        
        try:
            restore_info = olt.restore(user=request.user, rename_on_conflict=True)
            
            if restore_info.get('renamed', False):
                message = _(
                    '✅ OLT "{original}" restaurada exitosamente. '
                    'Abreviatura cambiada a "{new}" porque ya existe una OLT activa con ese nombre.'
                ).format(
                    original=restore_info['original_abreviatura'],
                    new=restore_info['new_abreviatura']
                )
                self.message_user(request, message, messages.SUCCESS)
            else:
                self.message_user(
                    request,
                    _('✅ OLT "{abreviatura}" restaurada exitosamente.').format(abreviatura=olt.abreviatura),
                    messages.SUCCESS
                )
            
            # Redirigir a la página de edición de la OLT restaurada
            return redirect('admin:hosts_olt_change', object_id)
            
        except ValidationError as e:
            self.message_user(request, str(e), messages.ERROR)
            return redirect('admin:hosts_olt_change', object_id)
        except Exception as e:
            self.message_user(
                request,
                _('❌ Error al restaurar OLT: {}').format(str(e)),
                messages.ERROR
            )
            return redirect('admin:hosts_olt_change', object_id)
    
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """Agregar botón de restaurar en el formulario"""
        extra_context = extra_context or {}
        
        if object_id:
            try:
                olt = OLT.all_objects.get(pk=object_id)
                if olt.is_deleted:
                    # Agregar URL para restaurar
                    restore_url = reverse('admin:hosts_olt_restore', args=[object_id])
                    extra_context['restore_url'] = restore_url
                    extra_context['is_deleted'] = True
            except OLT.DoesNotExist:
                pass
        
        return super().changeform_view(request, object_id, form_url, extra_context)