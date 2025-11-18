from django.db import models


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


# ExecutionPlan eliminado - no se usaba en el sistema
# El coordinator trabaja dinámicamente sin generar planes estáticos


class CoordinatorEvent(models.Model):
    """Registro estructurado de decisiones del coordinator."""

    EVENT_TYPES = [
        ('ENQUEUED', 'Tarea Encolada'),
        ('REQUEUED', 'Tarea Reencolada'),
        ('SKIPPED', 'Tarea Omitida'),
        ('DELAYED', 'Tarea Aplazada'),
        ('EXECUTION_STARTED', 'Inicio de Ejecución'),
        ('EXECUTION_COMPLETED', 'Ejecución Completada'),
        ('EXECUTION_FAILED', 'Ejecución Fallida'),
        ('EXECUTION_INTERRUPTED', 'Ejecución Interrumpida'),
        ('AUTO_REPAIR', 'Auto Reparación'),
        ('SATURATION_WAIT', 'Espera por Saturación'),
        ('DELIVERY_LOST', 'Entrega Perdida'),
        ('STATE_UPDATED', 'Estado Actualizado'),
        ('PLAN_UPDATED', 'Plan Actualizado'),
    ]

    DECISIONS = [
        ('ENQUEUE', 'Encolar'),
        ('REQUEUE', 'Reencolar'),
        ('SKIP', 'Omitir'),
        ('WAIT', 'Esperar'),
        ('RETRY', 'Programar Reintento'),
        ('ADJUST', 'Ajustar Plan'),
        ('ABORT', 'Abortar'),
        ('COMPLETE', 'Completar'),
    ]

    SOURCES = [
        ('SCHEDULER', 'Scheduler'),
        ('QUEUE', 'Cola Diferida'),
        ('DELIVERY_CHECKER', 'Delivery Checker'),
        ('AUTO_REPAIR', 'Auto Reparación'),
        ('ADMIN', 'Acción Manual'),
        ('SYSTEM', 'Sistema'),
    ]

    execution = models.ForeignKey(
        'executions.Execution',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='coordinator_events',
        db_column='execution_id',
    )
    snmp_job = models.ForeignKey(
        'snmp_jobs.SnmpJob',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='coordinator_events',
        db_column='snmp_job_id',
    )
    job_host = models.ForeignKey(
        'snmp_jobs.SnmpJobHost',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='coordinator_events',
        db_column='job_host_id',
    )
    olt = models.ForeignKey(
        'hosts.OLT',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='coordinator_events',
        db_column='olt_id',
    )

    event_type = models.CharField(max_length=40, choices=EVENT_TYPES)
    decision = models.CharField(max_length=20, choices=DECISIONS, blank=True)
    source = models.CharField(max_length=30, choices=SOURCES, default='SCHEDULER')
    reason = models.TextField(null=True, blank=True)
    details = models.JSONField(null=True, blank=True, help_text='Contexto adicional en formato JSON')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'coordinator_events'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['event_type']),
            models.Index(fields=['decision']),
            models.Index(fields=['source']),
            models.Index(fields=['olt', 'created_at']),
        ]
        verbose_name = 'Evento del Coordinador'
        verbose_name_plural = 'Eventos del Coordinador'

    def __str__(self):
        target = []
        if self.olt:
            target.append(self.olt.abreviatura)
        if self.snmp_job:
            target.append(self.snmp_job.nombre)
        target_str = ' / '.join(target) if target else 'GLOBAL'
        return f"{self.get_event_type_display()} - {target_str} ({self.created_at.strftime('%Y-%m-%d %H:%M:%S')})"

