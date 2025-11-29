from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import ConfiguracionSistema, ConfiguracionSNMP


@admin.register(ConfiguracionSistema)
class ConfiguracionSistemaAdmin(admin.ModelAdmin):
    """Admin para configuraciones del sistema"""
    
    list_display = (
        'nombre', 'get_categoria_display', 'get_tipo_display', 
        'get_valor_preview', 'get_modo_prueba_badge', 'activo', 'solo_lectura', 'fecha_modificacion'
    )
    list_filter = ('categoria', 'tipo', 'activo', 'modo_prueba', 'solo_lectura', 'fecha_creacion')
    search_fields = ('nombre', 'descripcion', 'valor')
    readonly_fields = ('fecha_creacion', 'fecha_modificacion', 'modificado_por')
    
    fieldsets = (
        ('🧪 MODO PRUEBA (IMPORTANTE)', {
            'fields': ('modo_prueba',),
            'description': '⚠️ Si está activo, TODAS las ejecuciones SNMP se simulan sin realizar consultas reales. Los tiempos son aleatorios (milisegundos a 3 minutos).',
            'classes': ('wide',)
        }),
        ('Información Básica', {
            'fields': ('nombre', 'descripcion', 'categoria')
        }),
        ('Valor', {
            'fields': ('tipo', 'valor')
        }),
        ('Estado', {
            'fields': ('activo', 'solo_lectura')
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_modificacion', 'modificado_por'),
            'classes': ('collapse',)
        }),
    )

    def get_valor_preview(self, obj):
        """Muestra una vista previa del valor"""
        valor = obj.valor
        if len(valor) > 50:
            valor = valor[:47] + "..."
        
        # Colorear según el tipo
        color_map = {
            'string': '#28a745',
            'integer': '#007bff',
            'float': '#17a2b8',
            'boolean': '#ffc107',
            'json': '#6f42c1',
            'url': '#fd7e14',
            'email': '#e83e8c',
        }
        color = color_map.get(obj.tipo, '#6c757d')
        
        return format_html(
            '<span style="color: {}; font-family: monospace;">{}</span>',
            color, valor
        )
    get_valor_preview.short_description = 'Valor'
    get_valor_preview.admin_order_field = 'valor'
    
    def get_modo_prueba_badge(self, obj):
        """Muestra el estado del modo prueba con badge destacado"""
        if obj.modo_prueba:
            return format_html(
                '<span style="background: #dc3545; color: white; padding: 4px 12px; '
                'border-radius: 12px; font-size: 11px; font-weight: bold;">'
                '🧪 MODO PRUEBA ACTIVO'
                '</span>'
            )
        return format_html(
            '<span style="background: #28a745; color: white; padding: 4px 12px; '
            'border-radius: 12px; font-size: 11px; font-weight: bold;">'
            '✅ PRODUCCIÓN'
            '</span>'
        )
    get_modo_prueba_badge.short_description = 'Modo'
    get_modo_prueba_badge.admin_order_field = 'modo_prueba'

    def save_model(self, request, obj, form, change):
        """Guardar el usuario que modificó"""
        if change:
            obj.modificado_por = request.user
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        """Hacer campos de solo lectura si está marcado como tal"""
        readonly = list(self.readonly_fields)
        if obj and obj.solo_lectura:
            readonly.extend(['nombre', 'tipo', 'categoria'])
        return readonly

    def has_delete_permission(self, request, obj=None):
        """Prevenir eliminación de configuraciones críticas"""
        if obj and obj.solo_lectura:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(ConfiguracionSNMP)
class ConfiguracionSNMPAdmin(admin.ModelAdmin):
    """Admin para configuraciones SNMP por tipo de operación"""
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Configuraciones SNMP por Tipo de Operación'
        return super().changelist_view(request, extra_context)
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = 'Editar Configuración SNMP'
        return super().change_view(request, object_id, form_url, extra_context)
    
    list_display = (
        'nombre', 'get_tipo_operacion_badge', 'version', 'timeout', 'reintentos',
        'get_poller_config', 'activo', 'fecha_modificacion'
    )
    list_filter = ('tipo_operacion', 'version', 'activo', 'fecha_creacion')
    search_fields = ('nombre', 'comunidad')
    readonly_fields = ('fecha_creacion', 'fecha_modificacion')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('nombre', 'tipo_operacion', 'activo'),
            'description': 'Configuración general de SNMP por tipo de operación'
        }),
        ('Configuración SNMP Base', {
            'fields': ('version', 'comunidad', 'timeout', 'reintentos'),
            'description': 'Aplica a: Todas las operaciones SNMP'
        }),
        ('Configuración de Pollers GET', {
            'fields': (
                'max_pollers_por_olt',
                'tamano_lote_inicial',
                'tamano_subdivision',
                'max_reintentos_individuales',
                'delay_entre_reintentos',
                'max_consultas_snmp_simultaneas'
            ),
            'description': 'Aplica solo a: Operaciones GET con sistema de pollers',
            'classes': ('collapse',)  # Colapsado por defecto
        }),
        ('Metadatos', {
            'fields': ('fecha_creacion', 'fecha_modificacion'),
            'classes': ('collapse',)
        }),
    )

    def get_tipo_operacion_badge(self, obj):
        """Muestra el tipo de operación con badge de color"""
        color_map = {
            'descubrimiento': '#28a745',  # Verde
            'get': '#007bff',             # Azul
            'bulk': '#ffc107',            # Amarillo
            'table': '#17a2b8',           # Cyan
            'general': '#6c757d',         # Gris
        }
        color = color_map.get(obj.tipo_operacion, '#6c757d')
        
        return format_html(
            '<span style="background: {}; color: white; padding: 4px 12px; '
            'border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.get_tipo_operacion_display()
        )
    get_tipo_operacion_badge.short_description = 'Tipo de Operación'
    get_tipo_operacion_badge.admin_order_field = 'tipo_operacion'

    def get_poller_config(self, obj):
        """Muestra resumen de configuración de pollers GET"""
        if obj.tipo_operacion == 'get':
            return format_html(
                '<span style="font-family: monospace; font-size: 11px;">'
                'Pollers: {} | Lote: {} | Sub: {} | Semáforo: {}'
                '</span>',
                obj.max_pollers_por_olt,
                obj.tamano_lote_inicial,
                obj.tamano_subdivision,
                obj.max_consultas_snmp_simultaneas
            )
        return format_html('<span style="color: #999;">N/A</span>')
    get_poller_config.short_description = 'Config. Pollers'


# Personalizar el título del admin
admin.site.site_header = "Facho Deluxe v2 - Administración"
admin.site.site_title = "Facho Deluxe v2"
admin.site.index_title = "Panel de Administración"

# Agregar enlace al dashboard de configuración avanzada
from django.urls import reverse
from django.utils.html import format_html

def configuracion_dashboard_link():
    """Agregar enlace al dashboard de configuración avanzada en el admin"""
    url = reverse('configuracion_avanzada:dashboard')
    return format_html(
        '<div style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #007cba;">'
        '<h3 style="margin: 0 0 10px 0; color: #007cba;">🔧 Configuración Avanzada</h3>'
        '<p style="margin: 0 0 15px 0; color: #666;">Gestiona configuraciones del sistema, SNMP y Celery de forma centralizada.</p>'
        '<a href="{}" class="button default" style="text-decoration: none; padding: 8px 16px; background: #007cba; color: white; border-radius: 4px; display: inline-block;">'
        '📊 Ir al Dashboard de Configuración'
        '</a>'
        '</div>',
        url
    )

# Registrar el enlace en el admin
# admin.site.index_template = 'admin/custom_index.html'  # Comentado temporalmente