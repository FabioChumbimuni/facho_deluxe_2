from django.db import models
from brands.models import Brand


class OLTModel(models.Model):
    """
    Modelos específicos de OLT con sus características técnicas.
    Permite organizar y categorizar los diferentes modelos por marca.
    """
    
    # === CAMPOS OBLIGATORIOS ===
    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Nombre del modelo',
        help_text='Nombre del modelo de OLT (ej: MA5800, C320, AN5516-06)'
    )
    marca = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        db_column='marca_id',
        verbose_name='Marca',
        help_text='Marca del fabricante'
    )
    descripcion = models.TextField(
        verbose_name='Descripción',
        help_text='Descripción técnica del modelo'
    )
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Si está activo, aparecerá en las listas de selección'
    )
    
    # === CAMPOS OPCIONALES TÉCNICOS ===
    tipo_olt = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Tipo de OLT',
        help_text='Tipo de OLT (ej: GPON, EPON, XG-PON, XGS-PON)'
    )
    capacidad_puertos = models.IntegerField(
        blank=True,
        null=True,
        verbose_name='Capacidad de puertos',
        help_text='Número máximo de puertos GPON/EPON soportados'
    )
    capacidad_onus = models.IntegerField(
        blank=True,
        null=True,
        verbose_name='Capacidad de ONUs',
        help_text='Número máximo de ONUs soportadas por puerto'
    )
    slots_disponibles = models.IntegerField(
        blank=True,
        null=True,
        verbose_name='Slots disponibles',
        help_text='Número de slots para tarjetas de línea'
    )
    
    # === CAMPOS OPCIONALES DE CONFIGURACIÓN ===
    version_firmware_minima = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Versión firmware mínima',
        help_text='Versión mínima de firmware requerida para SNMP'
    )
    comunidad_snmp_default = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Comunidad SNMP por defecto',
        help_text='Comunidad SNMP más común para este modelo'
    )
    puerto_snmp_default = models.IntegerField(
        blank=True,
        null=True,
        default=161,
        verbose_name='Puerto SNMP por defecto',
        help_text='Puerto SNMP estándar (normalmente 161)'
    )
    
    # === CAMPOS OPCIONALES DE DOCUMENTACIÓN ===
    url_documentacion = models.URLField(
        blank=True,
        null=True,
        verbose_name='URL de documentación',
        help_text='Enlace a la documentación técnica del modelo'
    )
    url_manual_usuario = models.URLField(
        blank=True,
        null=True,
        verbose_name='URL manual de usuario',
        help_text='Enlace al manual de usuario'
    )
    notas_tecnicas = models.TextField(
        blank=True,
        null=True,
        verbose_name='Notas técnicas',
        help_text='Notas adicionales sobre configuración o características especiales'
    )
    
    # === CAMPOS OPCIONALES DE SOPORTE ===
    soporte_tecnico_contacto = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Contacto soporte técnico',
        help_text='Información de contacto para soporte técnico específico del modelo'
    )
    fecha_lanzamiento = models.DateField(
        blank=True,
        null=True,
        verbose_name='Fecha de lanzamiento',
        help_text='Fecha aproximada de lanzamiento del modelo'
    )
    fecha_fin_soporte = models.DateField(
        blank=True,
        null=True,
        verbose_name='Fin de soporte',
        help_text='Fecha estimada de fin de soporte del fabricante'
    )
    
    # === METADATA ===
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        db_table = 'olt_models'
        verbose_name = 'Modelo de OLT'
        verbose_name_plural = 'Modelos de OLT'
        ordering = ['marca__nombre', 'nombre']
        indexes = [
            models.Index(fields=['marca', 'activo']),
            models.Index(fields=['activo']),
            models.Index(fields=['nombre']),
        ]

    def __str__(self):
        # Si es el modelo genérico, mostrar solo "🌐 Genérico" (no repetir)
        if self.marca.nombre == '🌐 Genérico' and self.nombre == 'Genérico':
            return '🌐 Genérico'
        # Para otros casos, mostrar marca y modelo
        return f"{self.marca.nombre} - {self.nombre}"
    
    def get_capacidad_display(self):
        """Muestra la capacidad de forma legible"""
        if self.capacidad_puertos and self.capacidad_onus:
            return f"{self.capacidad_puertos} puertos × {self.capacidad_onus} ONUs"
        elif self.capacidad_puertos:
            return f"{self.capacidad_puertos} puertos"
        return "No especificado"
    
    def get_estado_soporte(self):
        """Determina el estado del soporte basado en fechas"""
        if not self.fecha_fin_soporte:
            return "Soporte activo"
        
        from django.utils import timezone
        today = timezone.now().date()
        
        if self.fecha_fin_soporte < today:
            return "Soporte finalizado"
        elif (self.fecha_fin_soporte - today).days <= 365:
            return "Soporte próximo a finalizar"
        else:
            return "Soporte activo"
    
    def get_estado_soporte_color(self):
        """Color para el estado de soporte"""
        estado = self.get_estado_soporte()
        if estado == "Soporte finalizado":
            return "#dc3545"  # Rojo
        elif estado == "Soporte próximo a finalizar":
            return "#ffc107"  # Amarillo
        else:
            return "#28a745"  # Verde