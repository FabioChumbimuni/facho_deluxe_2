from django.contrib import admin
from django.utils.html import mark_safe
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from .models import ZabbixConfiguration


@admin.register(ZabbixConfiguration)
class ZabbixConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        'nombre',
        'get_estado_badge',
        'item_key',
        'get_url_display',
        'updated_at'
    )
    
    list_filter = ('activa', 'verificar_ssl')
    search_fields = ('nombre', 'descripcion', 'zabbix_url', 'item_key')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Información Básica', {
            'fields': (
                'nombre',
                'descripcion',
                'activa',
            )
        }),
        ('Conexión a Zabbix', {
            'fields': (
                'zabbix_url',
                'zabbix_token',
                'timeout',
                'verificar_ssl',
            ),
            'classes': ('wide',),
        }),
        ('Configuración de Datos', {
            'fields': (
                'item_key',
            ),
            'description': (
                '<strong>Item Key:</strong> Clave del item master en Zabbix que contiene el SNMP walk completo.<br>'
                '<strong>Nota:</strong> La fórmula SNMP se obtiene automáticamente de cada OLT según su marca/modelo.'
            ),
        }),
        ('Metadatos', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        })
    )
    
    actions = ['activar_configuracion', 'desactivar_configuracion', 'probar_conexion']
    
    def get_estado_badge(self, obj):
        """Muestra el estado de la configuración con badge"""
        if obj.activa:
            return mark_safe(
                '<span style="background:#28a745;color:white;padding:4px 10px;'
                'border-radius:4px;font-weight:bold;">✅ ACTIVA</span>'
            )
        else:
            return mark_safe(
                '<span style="background:#6c757d;color:white;padding:4px 10px;'
                'border-radius:4px;">⏸️ Inactiva</span>'
            )
    get_estado_badge.short_description = 'Estado'
    
    def get_url_display(self, obj):
        """Muestra la URL de forma compacta"""
        url = obj.zabbix_url
        if len(url) > 40:
            return f"{url[:37]}..."
        return url
    get_url_display.short_description = 'URL Zabbix'
    
    def activar_configuracion(self, request, queryset):
        """Activa una configuración (desactiva las demás)"""
        if queryset.count() != 1:
            self.message_user(
                request,
                _('⚠️ Selecciona exactamente UNA configuración para activar.'),
                messages.WARNING
            )
            return
        
        config = queryset.first()
        
        # Desactivar todas las demás
        ZabbixConfiguration.objects.filter(activa=True).update(activa=False)
        
        # Activar la seleccionada
        config.activa = True
        config.save()
        
        self.message_user(
            request,
            _(f'✅ Configuración "{config.nombre}" activada exitosamente.'),
            messages.SUCCESS
        )
    activar_configuracion.short_description = "✅ Activar configuración seleccionada"
    
    def desactivar_configuracion(self, request, queryset):
        """Desactiva las configuraciones seleccionadas"""
        count = queryset.filter(activa=True).update(activa=False)
        
        if count > 0:
            self.message_user(
                request,
                _(f'⏸️ {count} configuración(es) desactivada(s) exitosamente.'),
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                _('ℹ️ Las configuraciones seleccionadas ya estaban inactivas.'),
                messages.INFO
            )
    desactivar_configuracion.short_description = "⏸️ Desactivar configuraciones"
    
    def probar_conexion(self, request, queryset):
        """Prueba la conexión con Zabbix"""
        if queryset.count() != 1:
            self.message_user(
                request,
                _('⚠️ Selecciona exactamente UNA configuración para probar.'),
                messages.WARNING
            )
            return
        
        config = queryset.first()
        
        try:
            # Obtener servicio de Zabbix
            zabbix_service = config.get_service()
            
            # Intentar obtener versión de Zabbix como prueba
            result = zabbix_service._make_request("apiinfo.version", {})
            
            if result:
                self.message_user(
                    request,
                    _(f'✅ Conexión exitosa con Zabbix. Versión: {result}'),
                    messages.SUCCESS
                )
            else:
                self.message_user(
                    request,
                    _('❌ Error: No se pudo conectar con Zabbix. Verifica la URL y el token.'),
                    messages.ERROR
                )
                
        except Exception as e:
            self.message_user(
                request,
                _(f'❌ Error probando conexión: {str(e)}'),
                messages.ERROR
            )
    probar_conexion.short_description = "🔍 Probar conexión con Zabbix"
    
    def save_model(self, request, obj, form, change):
        """Sobrescribir save para manejar validación de única activa"""
        try:
            super().save_model(request, obj, form, change)
            if obj.activa:
                self.message_user(
                    request,
                    _(f'✅ Configuración "{obj.nombre}" guardada y activada correctamente.'),
                    messages.SUCCESS
                )
        except Exception as e:
            self.message_user(
                request,
                _(f'❌ Error guardando configuración: {str(e)}'),
                messages.ERROR
            )
            raise
