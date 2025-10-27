from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta
from .models import QuotaTracker, QuotaViolation, CoordinatorLog


@admin.register(QuotaTracker)
class QuotaTrackerAdmin(admin.ModelAdmin):
    list_display = ('olt_display', 'task_type', 'period_display', 'quota_display', 'completion_bar', 'status_badge', 'updated_at')
    list_filter = ('status', 'task_type', 'olt', 'period_start')
    search_fields = ('olt__abreviatura', 'task_type')
    readonly_fields = ('created_at', 'updated_at', 'completion_percentage_display', 'risk_indicator')
    date_hierarchy = 'period_start'
    
    fieldsets = (
        ('OLT y Tarea', {
            'fields': ('olt', 'task_type')
        }),
        ('Período', {
            'fields': ('period_start', 'period_end')
        }),
        ('Cuotas', {
            'fields': ('quota_required', 'quota_completed', 'quota_failed', 'quota_skipped', 'quota_pending')
        }),
        ('Métricas', {
            'fields': ('total_duration_ms', 'avg_duration_ms', 'completion_percentage_display', 'risk_indicator')
        }),
        ('Estado', {
            'fields': ('status',)
        }),
        ('Fechas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def olt_display(self, obj):
        return obj.olt.abreviatura if obj.olt else 'N/A'
    olt_display.short_description = 'OLT'
    
    def period_display(self, obj):
        start = timezone.localtime(obj.period_start).strftime('%d/%m %H:%M')
        end = timezone.localtime(obj.period_end).strftime('%H:%M')
        return f"{start} - {end}"
    period_display.short_description = 'Período'
    
    def quota_display(self, obj):
        return f"{obj.quota_completed}/{obj.quota_required}"
    quota_display.short_description = 'Cumplimiento'
    
    def completion_bar(self, obj):
        percentage = obj.completion_percentage()
        
        # Color según porcentaje
        if percentage >= 80:
            color = '#28a745'  # Verde
        elif percentage >= 50:
            color = '#ffc107'  # Amarillo
        else:
            color = '#dc3545'  # Rojo
        
        return format_html(
            '<div style="width:100px; background-color:#e9ecef; border-radius:3px;">'
            '<div style="width:{}%; background-color:{}; height:20px; border-radius:3px; text-align:center; color:white; font-size:11px; line-height:20px;">'
            '{}%'
            '</div>'
            '</div>',
            min(percentage, 100),
            color,
            int(percentage)
        )
    completion_bar.short_description = 'Progreso'
    
    def status_badge(self, obj):
        colors = {
            'IN_PROGRESS': '#17a2b8',
            'COMPLETED': '#28a745',
            'PARTIAL': '#ffc107',
            'FAILED': '#dc3545',
            'QUOTA_NOT_MET': '#dc3545',
            'INTERRUPTED': '#6c757d',
            'ADJUSTED': '#17a2b8',
            'AT_RISK': '#fd7e14',
        }
        color = colors.get(obj.status, '#6c757d')
        
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 8px; border-radius:3px; font-size:11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Estado'
    
    def completion_percentage_display(self, obj):
        return f"{obj.completion_percentage():.1f}%"
    completion_percentage_display.short_description = 'Porcentaje de Completitud'
    
    def risk_indicator(self, obj):
        if obj.is_at_risk():
            return format_html(
                '<span style="color:#dc3545; font-weight:bold;">⚠️ EN RIESGO</span>'
            )
        return format_html(
            '<span style="color:#28a745;">✅ Normal</span>'
        )
    risk_indicator.short_description = 'Indicador de Riesgo'


@admin.register(QuotaViolation)
class QuotaViolationAdmin(admin.ModelAdmin):
    list_display = ('olt_display', 'period_display', 'severity_badge', 'completion_display', 'notified_badge', 'created_at')
    list_filter = ('severity', 'notified', 'olt', 'created_at')
    search_fields = ('olt__abreviatura',)
    readonly_fields = ('created_at', 'report_display')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Información General', {
            'fields': ('olt', 'period_start', 'period_end', 'severity')
        }),
        ('Reporte', {
            'fields': ('report_display',)
        }),
        ('Notificación', {
            'fields': ('notified', 'notified_at')
        }),
        ('Fecha', {
            'fields': ('created_at',)
        }),
    )
    
    def olt_display(self, obj):
        return obj.olt.abreviatura if obj.olt else 'N/A'
    olt_display.short_description = 'OLT'
    
    def period_display(self, obj):
        start = timezone.localtime(obj.period_start).strftime('%d/%m %H:%M')
        return start
    period_display.short_description = 'Período'
    
    def severity_badge(self, obj):
        colors = {
            'LOW': '#28a745',
            'MEDIUM': '#ffc107',
            'HIGH': '#fd7e14',
            'CRITICAL': '#dc3545',
        }
        color = colors.get(obj.severity, '#6c757d')
        
        return format_html(
            '<span style="background-color:{}; color:white; padding:3px 8px; border-radius:3px; font-size:11px; font-weight:bold;">{}</span>',
            color,
            obj.get_severity_display().upper()
        )
    severity_badge.short_description = 'Severidad'
    
    def completion_display(self, obj):
        report = obj.report
        if isinstance(report, dict):
            completion = report.get('completion_percentage', 0)
            return f"{completion:.1f}%"
        return 'N/A'
    completion_display.short_description = 'Cumplimiento'
    
    def notified_badge(self, obj):
        if obj.notified:
            return format_html(
                '<span style="color:#28a745;">✅ Sí</span>'
            )
        return format_html(
            '<span style="color:#dc3545;">❌ No</span>'
        )
    notified_badge.short_description = 'Notificado'
    
    def report_display(self, obj):
        import json
        report_json = json.dumps(obj.report, indent=2, ensure_ascii=False)
        return format_html(
            '<pre style="background-color:#f8f9fa; padding:10px; border-radius:5px; font-size:12px;">{}</pre>',
            report_json
        )
    report_display.short_description = 'Reporte Completo'


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
