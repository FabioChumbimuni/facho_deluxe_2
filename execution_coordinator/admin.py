from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta
from .models import CoordinatorLog, CoordinatorEvent


@admin.register(CoordinatorLog)
class CoordinatorLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp_display', 'level_badge', 'olt_display', 'event_type_badge', 'message_short')
    list_filter = ('level', 'event_type', 'olt', 'timestamp')
    search_fields = ('message', 'olt__abreviatura')
    readonly_fields = ('timestamp', 'details_display')
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Información', {
            'fields': ('olt', 'event_type', 'level', 'message')
        }),
        ('Detalles', {
            'fields': ('details_display',),
            'classes': ('collapse',)
        }),
        ('Fecha', {
            'fields': ('timestamp',)
        }),
    )
    
    def timestamp_display(self, obj):
        return timezone.localtime(obj.timestamp).strftime('%d/%m/%Y %H:%M:%S')
    timestamp_display.short_description = 'Fecha/Hora'
    
    def level_badge(self, obj):
        colors = {
            'DEBUG': '#6c757d',
            'INFO': '#17a2b8',
            'WARNING': '#ffc107',
            'ERROR': '#dc3545',
            'CRITICAL': '#dc3545',
        }
        color = colors.get(obj.level, '#6c757d')
        
        return format_html(
            '<span style="background-color:{}; color:white; padding:2px 6px; border-radius:3px; font-size:10px; font-weight:bold;">{}</span>',
            color,
            obj.level
        )
    level_badge.short_description = 'Nivel'
    
    def olt_display(self, obj):
        if obj.olt:
            return obj.olt.abreviatura
        return format_html('<span style="color:#6c757d;">GLOBAL</span>')
    olt_display.short_description = 'OLT'
    
    def event_type_badge(self, obj):
        return format_html(
            '<span style="background-color:#e9ecef; color:#495057; padding:2px 6px; border-radius:3px; font-size:10px;">{}</span>',
            obj.get_event_type_display()
        )
    event_type_badge.short_description = 'Tipo de Evento'
    
    def message_short(self, obj):
        max_length = 80
        if len(obj.message) > max_length:
            return obj.message[:max_length] + '...'
        return obj.message
    message_short.short_description = 'Mensaje'
    
    def details_display(self, obj):
        if obj.details:
            import json
            details_json = json.dumps(obj.details, indent=2, ensure_ascii=False)
            return format_html(
                '<pre style="background-color:#f8f9fa; padding:10px; border-radius:5px; font-size:12px;">{}</pre>',
                details_json
            )
        return 'Sin detalles'
    details_display.short_description = 'Detalles'
    
    def has_add_permission(self, request):
        # No permitir agregar logs manualmente
        return False
    
    def has_change_permission(self, request, obj=None):
        # Solo lectura
        return False


# ExecutionPlanAdmin eliminado - modelo no usado en el sistema


@admin.register(CoordinatorEvent)
class CoordinatorEventAdmin(admin.ModelAdmin):
    list_display = (
        'created_at_display',
        'source_badge',
        'event_type_badge',
        'decision_badge',
        'olt_display',
        'job_display',
        'execution_id',
    )
    list_filter = (
        'source',
        'event_type',
        'decision',
        'olt',
        'snmp_job',
        'created_at',
    )
    search_fields = (
        'reason',
        'details',
        'olt__abreviatura',
        'snmp_job__nombre',
        'execution__id',
    )
    readonly_fields = (
        'created_at',
        'execution',
        'snmp_job',
        'job_host',
        'olt',
        'event_type',
        'decision',
        'source',
        'reason',
        'details_pretty',
    )
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Contexto', {
            'fields': ('created_at', 'source', 'event_type', 'decision')
        }),
        ('Objetos relacionados', {
            'fields': ('execution', 'snmp_job', 'job_host', 'olt')
        }),
        ('Detalle', {
            'fields': ('reason', 'details_pretty')
        }),
    )

    def created_at_display(self, obj):
        return timezone.localtime(obj.created_at).strftime('%d/%m/%Y %H:%M:%S')
    created_at_display.short_description = 'Fecha/Hora'

    def source_badge(self, obj):
        colors = {
            'SCHEDULER': '#17a2b8',
            'QUEUE': '#6f42c1',
            'DELIVERY_CHECKER': '#fd7e14',
            'AUTO_REPAIR': '#28a745',
            'ADMIN': '#20c997',
            'SYSTEM': '#343a40',
        }
        color = colors.get(obj.source, '#6c757d')
        return format_html(
            '<span style="background-color:{}; color:white; padding:2px 6px; border-radius:3px; font-size:10px;">{}</span>',
            color,
            obj.get_source_display()
        )
    source_badge.short_description = 'Origen'

    def event_type_badge(self, obj):
        return format_html(
            '<span style="background-color:#e9ecef; color:#495057; padding:2px 6px; border-radius:3px; font-size:10px;">{}</span>',
            obj.get_event_type_display()
        )
    event_type_badge.short_description = 'Evento'

    def decision_badge(self, obj):
        if not obj.decision:
            return format_html('<span style="color:#6c757d;">Sin decisión</span>')
        colors = {
            'ENQUEUE': '#007bff',
            'REQUEUE': '#6610f2',
            'SKIP': '#dc3545',
            'WAIT': '#ffc107',
            'RETRY': '#20c997',
            'ADJUST': '#17a2b8',
            'ABORT': '#343a40',
            'COMPLETE': '#28a745',
        }
        color = colors.get(obj.decision, '#6c757d')
        return format_html(
            '<span style="background-color:{}; color:white; padding:2px 6px; border-radius:3px; font-size:10px;">{}</span>',
            color,
            obj.get_decision_display()
        )
    decision_badge.short_description = 'Decisión'

    def olt_display(self, obj):
        if obj.olt:
            return obj.olt.abreviatura
        return format_html('<span style="color:#6c757d;">GLOBAL</span>')
    olt_display.short_description = 'OLT'

    def job_display(self, obj):
        if obj.snmp_job:
            return obj.snmp_job.nombre
        return format_html('<span style="color:#6c757d;">Sin job</span>')
    job_display.short_description = 'Job'

    def details_pretty(self, obj):
        if obj.details:
            import json
            details_json = json.dumps(obj.details, indent=2, ensure_ascii=False)
            return format_html(
                '<pre style="background-color:#f8f9fa; padding:10px; border-radius:5px; font-size:12px;">{}</pre>',
                details_json
            )
        return 'Sin detalles'
    details_pretty.short_description = 'Detalles'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

