from django.db import models
from django.utils import timezone


class OnuIndexMap(models.Model):
    """
    Mapea y descompone el índice crudo (ej. 4194312192.2) en componentes reutilizables.
    Unique por (olt_id, raw_index_key).
    """
    olt = models.ForeignKey("hosts.OLT", on_delete=models.CASCADE, db_column="olt_id")
    raw_index_key = models.CharField(max_length=255)
    slot = models.IntegerField(null=True, blank=True)
    port = models.IntegerField(null=True, blank=True)
    logical = models.IntegerField(null=True, blank=True)
    normalized_id = models.CharField(max_length=255)
    marca_formula = models.TextField(null=True, blank=True)
    odf_hilo = models.ForeignKey(
        "odf_management.ODFHilos", 
        on_delete=models.SET_NULL, 
        db_column="odf_hilo_id",
        null=True, 
        blank=True,
        help_text="Enlaza el SNMPINDEX lógico con el puerto/hilo físico"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onu_index_map"
        unique_together = [('olt', 'raw_index_key')]
        ordering = ["-created_at"]
        verbose_name = "Mapeo de Índice ONU"
        verbose_name_plural = "Mapeos de Índices ONU"
        indexes = [
            models.Index(fields=["olt", "raw_index_key"]),
            models.Index(fields=["normalized_id"]),
        ]

    def __str__(self):
        return f"{self.olt.abreviatura} - {self.raw_index_key}"
    
    def save(self, *args, **kwargs):
        """
        Calcula automáticamente slot, port y logical usando fórmulas configurables de BD
        """
        # Solo calcular si no están ya calculados
        if self.slot is None or self.port is None or self.logical is None:
            # Buscar fórmula configurada para esta marca/modelo
            from snmp_formulas.models import IndexFormula
            
            # Intentar primero con marca + modelo específico
            formula = None
            if self.olt.modelo:
                formula = IndexFormula.objects.filter(
                    marca=self.olt.marca,
                    modelo=self.olt.modelo,
                    activo=True
                ).first()
            
            # Si no hay fórmula específica, buscar fórmula genérica para la marca
            if not formula:
                formula = IndexFormula.objects.filter(
                    marca=self.olt.marca,
                    modelo__isnull=True,  # Fórmula genérica (sin modelo específico)
                    activo=True
                ).first()
            
            # Si no hay fórmula para la marca, buscar fórmula completamente genérica (sin marca)
            if not formula:
                formula = IndexFormula.objects.filter(
                    marca__isnull=True,  # Fórmula completamente genérica (sin marca)
                    modelo__isnull=True,  # Sin modelo específico
                    activo=True
                ).first()
            
            # Si hay fórmula, calcular componentes
            if formula:
                components = formula.calculate_components(self.raw_index_key)
                
                if components['slot'] is not None:
                    self.slot = components['slot']
                    self.port = components['port']
                    self.logical = components['logical']
                    
                    # Actualizar normalized_id usando el formato de la fórmula
                    self.normalized_id = formula.get_normalized_id(
                        self.slot, 
                        self.port, 
                        self.logical
                    )
        
        super().save(*args, **kwargs)


class OnuStateLookup(models.Model):
    """
    Lookup para mapear valores numéricos a etiquetas por marca si es necesario.
    Permite tener el mismo valor numérico para diferentes marcas con diferentes etiquetas.
    """
    value = models.SmallIntegerField()
    label = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    marca = models.ForeignKey("brands.Brand", on_delete=models.CASCADE, db_column="marca_id", null=True, blank=True)

    class Meta:
        db_table = "onu_state_lookup"
        ordering = ["value"]
        verbose_name = "Estado ONU (Lookup)"
        verbose_name_plural = "Estados ONU (Lookup)"
        unique_together = [('value', 'marca')]  # Permite mismo valor para diferentes marcas
        indexes = [
            models.Index(fields=['value', 'marca']),
            models.Index(fields=['marca']),
        ]

    def __str__(self):
        return f"{self.value} - {self.label}"


class OnuStatus(models.Model):
    """
    Tabla ligera que representa el estado actual (sin histórico).
    Se usa para filtrar targets del GET masivo.
    """
    PRESENCE_CHOICES = [
        ('ENABLED', 'ENABLED'),
        ('DISABLED', 'DISABLED'),
    ]

    onu_index = models.OneToOneField(OnuIndexMap, on_delete=models.CASCADE, db_column="onu_index_id", related_name="status")
    olt = models.ForeignKey("hosts.OLT", on_delete=models.CASCADE, db_column="olt_id")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_state_value = models.SmallIntegerField(null=True, blank=True)  # guarda el int observado (1,2)
    last_state_label = models.CharField(max_length=50, null=True, blank=True)  # ACTIVO / SUSPENDIDO
    presence = models.CharField(max_length=20, choices=PRESENCE_CHOICES, default='ENABLED')  # vista consolidada
    consecutive_misses = models.IntegerField(default=0)
    last_change_execution = models.ForeignKey("executions.Execution", on_delete=models.SET_NULL, db_column="last_change_execution_id", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "onu_status"
        ordering = ["-last_seen_at"]
        verbose_name = "Estado Actual ONU"
        verbose_name_plural = "Estados Actuales ONU"
        indexes = [
            models.Index(fields=["olt", "presence"]),
            models.Index(fields=["last_seen_at"]),
            models.Index(fields=["consecutive_misses"]),
        ]

    def __str__(self):
        return f"{self.onu_index.normalized_id} - {self.presence}"


class OnuInventory(models.Model):
    """
    Registro maestro (único por ONU conocida). Aquí se guarda la descripción y metadatos
    sin conservar histórico. Ideal target del GET masivo.
    """
    onu_index = models.OneToOneField(OnuIndexMap, on_delete=models.CASCADE, db_column="onu_index_id", related_name="inventory")
    olt = models.ForeignKey("hosts.OLT", on_delete=models.CASCADE, db_column="olt_id")
    serial_number = models.CharField(max_length=255, blank=True, null=True)
    mac_address = models.CharField(max_length=64, blank=True, null=True)
    subscriber_id = models.CharField(max_length=255, blank=True, null=True)
    snmp_description = models.TextField(blank=True, null=True)  # campo principal que se actualiza/reescribe por GET masivo
    snmp_metadata = models.JSONField(default=dict, blank=True)  # datos adicionales devueltos por GET (sin histórico)
    
    # Campos con lógica de "mantener valor previo" (como facho_deluxe)
    plan_onu = models.CharField(max_length=100, blank=True, null=True, verbose_name="Plan ONU")
    distancia_onu = models.CharField(max_length=50, blank=True, null=True, verbose_name="Distancia ONU")
    modelo_onu = models.CharField(max_length=100, blank=True, null=True, verbose_name="Modelo ONU")
    
    snmp_last_collected_at = models.DateTimeField(null=True, blank=True)
    snmp_last_execution = models.ForeignKey("executions.Execution", on_delete=models.SET_NULL, db_column="snmp_last_execution_id", null=True, blank=True)
    active = models.BooleanField(default=True, help_text="Sincronizado manualmente con presence de OnuStatus por tareas SNMP")  # Se sincroniza con presence por tareas de descubrimiento
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def presence_status(self):
        """Obtiene el presence desde OnuStatus (ENABLED/DISABLED)"""
        if hasattr(self.onu_index, 'status'):
            return self.onu_index.status.presence
        return 'UNKNOWN'

    class Meta:
        db_table = "onu_inventory"
        ordering = ["-created_at"]
        verbose_name = "Inventario ONU"
        verbose_name_plural = "Inventario ONUs"
        indexes = [
            models.Index(fields=["olt", "active"]),
            models.Index(fields=["serial_number"]),
            models.Index(fields=["mac_address"]),
        ]

    def __str__(self):
        return f"{self.onu_index.normalized_id} - {self.serial_number or 'Sin SN'}"