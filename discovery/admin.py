from django.contrib import admin
from django.utils.html import format_html
from .models import OnuIndexMap, OnuStatus, OnuInventory, OnuStateLookup


@admin.register(OnuStateLookup)
class OnuStateLookupAdmin(admin.ModelAdmin):
    """Admin para lookup de estados ONU"""
    list_display = ('value', 'label', 'marca', 'description')
    list_filter = ('marca',)
    search_fields = ('label', 'description')
    ordering = ('value',)


@admin.register(OnuIndexMap)
class OnuIndexMapAdmin(admin.ModelAdmin):
    """Admin para mapeo de índices ONU"""
    list_display = ('id', 'olt', 'raw_index_key', 'slot', 'port', 'logical', 'normalized_id', 'created_at')
    list_filter = ('olt', 'created_at')
    search_fields = ('raw_index_key', 'normalized_id')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    def has_add_permission(self, request):
        return False  # Solo se crean automáticamente por las tareas


@admin.register(OnuStatus)
class OnuStatusAdmin(admin.ModelAdmin):
    """Admin para estado actual de ONUs"""
    list_display = (
        'id', 'get_onu_info', 'olt', 'last_seen_at', 'get_state_info', 
        'presence', 'consecutive_misses', 'updated_at'
    )
    list_filter = ('olt', 'presence', 'last_state_label', 'last_seen_at')
    search_fields = ('onu_index__raw_index_key', 'onu_index__normalized_id')
    readonly_fields = (
        'onu_index', 'olt', 'last_seen_at', 'last_state_value', 
        'last_state_label', 'consecutive_misses', 'last_change_execution', 'updated_at'
    )
    ordering = ('-last_seen_at',)
    
    def get_onu_info(self, obj):
        return f"{obj.onu_index.normalized_id} ({obj.onu_index.raw_index_key})"
    get_onu_info.short_description = 'ONU'
    
    def get_state_info(self, obj):
        if obj.last_state_value is not None:
            color = 'green' if obj.last_state_value == 1 else 'orange' if obj.last_state_value == 2 else 'red'
            return format_html(
                '<span style="color: {};">{} ({})</span>',
                color,
                obj.last_state_label or 'UNKNOWN',
                obj.last_state_value
            )
        return '-'
    get_state_info.short_description = 'Estado'
    
    def has_add_permission(self, request):
        return False  # Solo se crean automáticamente por las tareas
    
    def has_change_permission(self, request, obj=None):
        return False  # Solo lectura


@admin.register(OnuInventory)
class OnuInventoryAdmin(admin.ModelAdmin):
    """Admin para inventario de ONUs - Vista original sin cambios"""
    list_display = (
        'id', 'get_onu_info', 'olt', 'serial_number', 'mac_address', 
        'get_snmp_description_preview', 'get_presence_display', 'snmp_last_collected_at', 'created_at'
    )
    list_filter = ('olt', 'active', 'snmp_last_collected_at', 'created_at')
    search_fields = (
        'onu_index__raw_index_key', 'onu_index__normalized_id', 
        'serial_number', 'mac_address', 'subscriber_id', 'snmp_description'
    )
    readonly_fields = (
        'onu_index', 'olt', 'snmp_last_collected_at', 'snmp_last_execution', 
        'created_at', 'updated_at'
    )
    fieldsets = (
        ('Información Básica', {
            'fields': ('onu_index', 'olt', 'active')
        }),
        ('Datos de Inventario', {
            'fields': ('serial_number', 'mac_address', 'subscriber_id')
        }),
        ('Datos SNMP', {
            'fields': ('snmp_description', 'snmp_metadata', 'snmp_last_collected_at', 'snmp_last_execution')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    ordering = ('-created_at',)
    
    def get_onu_info(self, obj):
        return f"{obj.onu_index.normalized_id} ({obj.onu_index.raw_index_key})"
    get_onu_info.short_description = 'ONU'
    
    def get_presence_display(self, obj):
        """Muestra Presence (ENABLED/DISABLED) sincronizado con active"""
        if obj.active:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">ENABLED</span>'
            )
        else:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">DISABLED</span>'
            )
    get_presence_display.short_description = 'Presence'
    get_presence_display.admin_order_field = 'active'
    
    def get_snmp_description_preview(self, obj):
        """Muestra preview de la descripción SNMP obtenida por GET"""
        if obj.snmp_description:
            desc = obj.snmp_description
            # Truncar si es muy largo
            if len(desc) > 40:
                desc_preview = desc[:37] + "..."
            else:
                desc_preview = desc
            
            # Colorear según si tiene datos
            return format_html(
                '<span style="color: #28a745; font-family: monospace;">{}</span>',
                desc_preview
            )
        return format_html('<span style="color: #999;">-</span>')
    get_snmp_description_preview.short_description = 'SNMP Description'
    get_snmp_description_preview.admin_order_field = 'snmp_description'
    
    def has_add_permission(self, request):
        return False  # Solo se crean automáticamente por las tareas
