from django.db import models
from django.utils import timezone


class QuotaTracker(models.Model):
    """
    Rastrea el cumplimiento de cuotas por OLT y tipo de tarea
    Una cuota representa cuántas veces debe ejecutarse una tarea en un período (ej: 4 veces/hora)
    """
    olt = models.ForeignKey('hosts.OLT', on_delete=models.CASCADE, db_column='olt_id', related_name='quota_trackers')
    task_type = models.CharField(max_length=50, help_text='Tipo de tarea: discovery, get_descripcion, get_plan, etc.')
    
    # Período de la cuota (normalmente 1 hora)
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField()
    
    # Cuotas
    quota_required = models.IntegerField(help_text='Número de ejecuciones requeridas en el período')
    quota_completed = models.IntegerField(default=0, help_text='Ejecuciones completadas exitosamente')
    quota_failed = models.IntegerField(default=0, help_text='Ejecuciones fallidas')
    quota_skipped = models.IntegerField(default=0, help_text='Ejecuciones omitidas por falta de tiempo')
    quota_pending = models.IntegerField(default=0, help_text='Ejecuciones pendientes')
    
    # Métricas de rendimiento
    total_duration_ms = models.BigIntegerField(default=0, help_text='Tiempo total consumido en ms')
    avg_duration_ms = models.IntegerField(null=True, blank=True, help_text='Duración promedio en ms')
    
    # Estado
    STATUS_CHOICES = [
        ('IN_PROGRESS', 'En Progreso'),
        ('COMPLETED', 'Completado'),
        ('PARTIAL', 'Completado Parcial'),
        ('FAILED', 'Fallido'),
        ('QUOTA_NOT_MET', 'Cuota No Cumplida'),
        ('INTERRUPTED', 'Interrumpido'),
        ('ADJUSTED', 'Ajustado'),
        ('AT_RISK', 'En Riesgo'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'quota_tracker'
        unique_together = ('olt', 'task_type', 'period_start')
        ordering = ['-period_start', 'olt', 'task_type']
        indexes = [
            models.Index(fields=['olt', 'period_start']),
            models.Index(fields=['status']),
        ]
        verbose_name = 'Rastreador de Cuotas'
        verbose_name_plural = 'Rastreadores de Cuotas'
    
    def __str__(self):
        olt_name = self.olt.abreviatura if self.olt else 'N/A'
        return f"{olt_name} - {self.task_type} ({self.quota_completed}/{self.quota_required})"
    
    @classmethod
    def get_current(cls, olt_id, task_type):
        """Obtiene el tracker actual para una OLT y tipo de tarea"""
        current_hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        tracker, created = cls.objects.get_or_create(
            olt_id=olt_id,
            task_type=task_type,
            period_start=current_hour,
            defaults={
                'period_end': current_hour + timezone.timedelta(hours=1),
                'quota_required': 0,
            }
        )
        return tracker
    
    def completion_percentage(self):
        """Calcula el porcentaje de cumplimiento"""
        if self.quota_required == 0:
            return 100.0
        return (self.quota_completed / self.quota_required) * 100
    
    def is_at_risk(self):
        """Determina si la cuota está en riesgo de no cumplirse"""
        now = timezone.now()
        time_elapsed = (now - self.period_start).total_seconds()
        time_total = (self.period_end - self.period_start).total_seconds()
        progress_percentage = (time_elapsed / time_total) * 100
        
        completion = self.completion_percentage()
        
        # Si el progreso temporal supera al progreso de completitud en más de 20%
        return progress_percentage > completion + 20


class QuotaViolation(models.Model):
    """
    Registro de violaciones de cuota (cuando no se cumple la cuota esperada)
    """
    olt = models.ForeignKey('hosts.OLT', on_delete=models.CASCADE, db_column='olt_id', related_name='quota_violations')
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField()
    
    # Reporte completo en JSON
    report = models.JSONField(help_text='Reporte detallado de la violación')
    
    # Severidad
    SEVERITY_CHOICES = [
        ('LOW', 'Baja'),       # < 20% perdido
        ('MEDIUM', 'Media'),   # 20-50% perdido
        ('HIGH', 'Alta'),      # 50-80% perdido
        ('CRITICAL', 'Crítica'), # > 80% perdido
    ]
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='MEDIUM')
    
    # Notificación
    notified = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'quota_violations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['olt', 'created_at']),
            models.Index(fields=['severity']),
            models.Index(fields=['notified']),
        ]
        verbose_name = 'Violación de Cuota'
        verbose_name_plural = 'Violaciones de Cuota'
    
    def __str__(self):
        olt_name = self.olt.abreviatura if self.olt else 'N/A'
        return f"{olt_name} - {self.severity} - {self.period_start.strftime('%Y-%m-%d %H:%M')}"


class CoordinatorLog(models.Model):
    """
    Log específico del coordinator para tracking detallado de decisiones
    """
    olt = models.ForeignKey('hosts.OLT', on_delete=models.CASCADE, db_column='olt_id', related_name='coordinator_logs', null=True, blank=True)
    
    # Tipo de evento
    EVENT_TYPES = [
        ('STATE_CHANGE', 'Cambio de Estado'),
        ('TASK_ADDED', 'Tarea Agregada'),
        ('TASK_REMOVED', 'Tarea Removida'),
        ('TASK_MODIFIED', 'Tarea Modificada'),
        ('PLAN_CREATED', 'Plan Creado'),
        ('PLAN_ADJUSTED', 'Plan Ajustado'),
        ('EXECUTION_STARTED', 'Ejecución Iniciada'),
        ('EXECUTION_COMPLETED', 'Ejecución Completada'),
        ('EXECUTION_FAILED', 'Ejecución Fallida'),
        ('EXECUTION_ABORTED', 'Ejecución Abortada'),
        ('QUOTA_WARNING', 'Advertencia de Cuota'),
        ('QUOTA_VIOLATION', 'Violación de Cuota'),
        ('OLT_DISABLED', 'OLT Deshabilitada'),
        ('OLT_ENABLED', 'OLT Habilitada'),
        ('SLOW_MODE_ACTIVATED', 'Modo Lento Activado'),
        ('EMERGENCY_REPLAN', 'Re-planificación de Emergencia'),
        ('TRIAGE_MODE', 'Modo Triage Activado'),
    ]
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES, db_index=True)
    
    # Nivel de importancia
    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='INFO')
    
    # Mensaje
    message = models.TextField()
    
    # Datos adicionales en JSON
    details = models.JSONField(null=True, blank=True, help_text='Detalles adicionales del evento')
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'coordinator_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['olt', 'timestamp']),
            models.Index(fields=['event_type', 'timestamp']),
            models.Index(fields=['level', 'timestamp']),
        ]
        verbose_name = 'Log del Coordinador'
        verbose_name_plural = 'Logs del Coordinador'
    
    def __str__(self):
        olt_name = self.olt.abreviatura if self.olt else 'GLOBAL'
        return f"[{self.level}] {olt_name} - {self.event_type} - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    
    @classmethod
    def log(cls, event_type, message, olt=None, level='INFO', details=None):
        """
        Método helper para crear logs rápidamente
        """
        return cls.objects.create(
            olt=olt,
            event_type=event_type,
            level=level,
            message=message,
            details=details or {}
        )


class ExecutionPlan(models.Model):
    """
    Plan de ejecución generado por el coordinator
    Representa el orden y timing de tareas para una OLT en un período
    """
    olt = models.ForeignKey('hosts.OLT', on_delete=models.CASCADE, db_column='olt_id', related_name='execution_plans')
    
    # Período del plan
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField()
    
    # Plan serializado (lista de tareas con timing)
    plan_data = models.JSONField(help_text='Plan completo en formato JSON')
    
    # Estado del plan
    STATUS_CHOICES = [
        ('ACTIVE', 'Activo'),
        ('COMPLETED', 'Completado'),
        ('SUPERSEDED', 'Reemplazado'),
        ('ABORTED', 'Abortado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    
    # Métricas
    total_tasks = models.IntegerField(default=0)
    completed_tasks = models.IntegerField(default=0)
    failed_tasks = models.IntegerField(default=0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'execution_plans'
        ordering = ['-period_start', 'olt']
        indexes = [
            models.Index(fields=['olt', 'period_start']),
            models.Index(fields=['status']),
        ]
        verbose_name = 'Plan de Ejecución'
        verbose_name_plural = 'Planes de Ejecución'
    
    def __str__(self):
        olt_name = self.olt.abreviatura if self.olt else 'N/A'
        return f"{olt_name} - Plan {self.period_start.strftime('%Y-%m-%d %H:%M')}"
    
    def completion_percentage(self):
        """Calcula el porcentaje de completitud"""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100
