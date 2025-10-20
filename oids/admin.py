from django.contrib import admin
from django.utils.html import mark_safe
from .models import OID


@admin.register(OID)
class OIDAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'oid', 'get_marca_badge', 'get_modelo_badge', 'get_espacio_y_campo', 'get_config_badges')
    list_filter = ('marca', 'modelo', 'espacio', 'keep_previous_value', 'format_mac')
    search_fields = ('nombre', 'oid', 'modelo__nombre')
    list_per_page = 20
    actions = ['duplicate_oid']

    readonly_fields = ('get_target_field_info',)
    autocomplete_fields = ['marca', 'modelo']
    
    fieldsets = (
        ('Información Básica', {
            'fields': (
                'nombre',
                'oid',
                'marca',
                'modelo',
                'espacio',
                'get_target_field_info',
            ),
            'description': '💡 IMPORTANTE: Marca y Modelo son OBLIGATORIOS. Usar "🌐 Genérico" cuando aplica universalmente.'
        }),
        ('Configuración GET (OnuInventory)', {
            'fields': (
                'keep_previous_value',
                'format_mac',
            ),
            'description': 'Configuración para tareas de tipo GET que actualizan onu_inventory',
            'classes': ('collapse',),
        }),
    )
    
    def get_target_field_info(self, obj):
        """Muestra el campo destino que se asignará automáticamente"""
        from .models import OID
        target = OID.ESPACIO_TO_FIELD.get(obj.espacio)
        if target:
            return mark_safe(f'<span style="background:#17a2b8;color:white;padding:4px 10px;border-radius:3px;font-family:monospace;font-size:12px;">→ {target}</span>')
        return mark_safe('<span style="color:#6c757d;font-style:italic;">No aplica (Discovery)</span>')
    
    get_target_field_info.short_description = 'Campo destino en onu_inventory'
    
    def get_marca_badge(self, obj):
        """Muestra la marca con badge de color"""
        if obj.marca.nombre == '🌐 Genérico':
            return mark_safe(
                f'<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                f'🌐 Genérico</span>'
            )
        return mark_safe(
            f'<span style="background:#007bff;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
            f'🏷️ {obj.marca.nombre}</span>'
        )
    
    get_marca_badge.short_description = 'Marca'
    
    def get_modelo_badge(self, obj):
        """Muestra el modelo con badge de color"""
        modelo_display = str(obj.modelo)
        
        if modelo_display == '🌐 Genérico':
            return mark_safe(
                f'<span style="background:#28a745;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                f'🌐 Genérico</span>'
            )
        return mark_safe(
            f'<span style="background:#6c757d;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
            f'🔧 {modelo_display}</span>'
        )
    
    get_modelo_badge.short_description = 'Modelo'
    
    def get_espacio_y_campo(self, obj):
        """Muestra espacio y campo destino combinados"""
        espacio_display = obj.get_espacio_display()
        if obj.target_field:
            return f"{espacio_display} → {obj.target_field}"
        return espacio_display
    
    get_espacio_y_campo.short_description = 'Espacio / Campo'
    
    def get_config_badges(self, obj):
        """Muestra badges de configuración"""
        badges = []
        if obj.keep_previous_value:
            badges.append('<span style="background:#28a745;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">✓ Mantiene previo</span>')
        if obj.format_mac:
            badges.append('<span style="background:#007bff;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">✓ Formatea MAC</span>')
        
        # Mostrar el campo destino en la lista también
        if obj.target_field:
            badges.append(f'<span style="background:#6c757d;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">→ {obj.target_field}</span>')
        
        return mark_safe(' '.join(badges) if badges else '-')
    
    get_config_badges.short_description = 'Configuración'
    
    def duplicate_oid(self, request, queryset):
        """
        Acción para duplicar OIDs seleccionados.
        Crea copias con el prefijo "[COPIA]" en el nombre.
        """
        duplicated_count = 0
        
        for oid in queryset:
            # Crear una copia del OID
            oid_copy = OID(
                nombre=f"[COPIA] {oid.nombre}",
                oid=oid.oid,
                marca=oid.marca,
                modelo=oid.modelo,
                espacio=oid.espacio,
                keep_previous_value=oid.keep_previous_value,
                format_mac=oid.format_mac
            )
            
            try:
                oid_copy.save()
                duplicated_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Error al duplicar "{oid.nombre}": {str(e)}',
                    level='ERROR'
                )
        
        if duplicated_count > 0:
            self.message_user(
                request,
                f'✅ {duplicated_count} OID(s) duplicado(s) exitosamente. '
                f'Se crearon con el prefijo "[COPIA]" en el nombre.',
                level='SUCCESS'
            )
    
    duplicate_oid.short_description = '📋 Duplicar OIDs seleccionados'