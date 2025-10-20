from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class ConfiguracionSistema(models.Model):
    """
    Configuración avanzada del sistema para ajustes globales
    """
    nombre = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Nombre identificador de la configuración"
    )
    descripcion = models.TextField(
        blank=True,
        help_text="Descripción de qué hace esta configuración"
    )
    valor = models.TextField(
        help_text="Valor de la configuración (puede ser texto, número, JSON, etc.)"
    )
    tipo = models.CharField(
        max_length=20,
        choices=[
            ('string', 'Texto'),
            ('integer', 'Número Entero'),
            ('float', 'Número Decimal'),
            ('boolean', 'Verdadero/Falso'),
            ('json', 'JSON'),
            ('url', 'URL'),
            ('email', 'Email'),
        ],
        default='string',
        help_text="Tipo de dato del valor"
    )
    categoria = models.CharField(
        max_length=50,
        choices=[
            ('snmp', 'SNMP'),
            ('celery', 'Celery'),
            ('redis', 'Redis'),
            ('database', 'Base de Datos'),
            ('logging', 'Logging'),
            ('security', 'Seguridad'),
            ('performance', 'Rendimiento'),
            ('general', 'General'),
        ],
        default='general',
        help_text="Categoría de la configuración"
    )
    activo = models.BooleanField(
        default=True,
        help_text="Si está activo, la configuración se aplica"
    )
    solo_lectura = models.BooleanField(
        default=False,
        help_text="Si es solo lectura, no se puede modificar desde el admin"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    modificado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Usuario que modificó por última vez esta configuración"
    )

    class Meta:
        db_table = 'configuracion_sistema'
        verbose_name = 'Configuración del Sistema'
        verbose_name_plural = 'Configuraciones del Sistema'
        ordering = ['categoria', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.categoria})"

    def get_valor_typed(self):
        """
        Retorna el valor convertido al tipo correcto
        """
        if self.tipo == 'integer':
            try:
                return int(self.valor)
            except (ValueError, TypeError):
                return 0
        elif self.tipo == 'float':
            try:
                return float(self.valor)
            except (ValueError, TypeError):
                return 0.0
        elif self.tipo == 'boolean':
            return self.valor.lower() in ('true', '1', 'yes', 'si', 'sí')
        elif self.tipo == 'json':
            import json
            try:
                return json.loads(self.valor)
            except (ValueError, TypeError):
                return {}
        else:
            return self.valor

    def set_valor_typed(self, valor):
        """
        Convierte el valor al tipo correcto y lo guarda como string
        """
        if self.tipo == 'boolean':
            self.valor = 'true' if valor else 'false'
        elif self.tipo == 'json':
            import json
            self.valor = json.dumps(valor, ensure_ascii=False)
        else:
            self.valor = str(valor)


class ConfiguracionSNMP(models.Model):
    """
    Configuraciones específicas para SNMP por tipo de operación
    """
    TIPO_OPERACION_CHOICES = [
        ('descubrimiento', 'Descubrimiento (SNMP Walk)'),
        ('get', 'GET (Consultas Individuales)'),
        ('bulk', 'BULK (Consultas Masivas)'),
        ('table', 'TABLE (Tablas)'),
        ('general', 'General (Todas las operaciones)'),
    ]
    
    nombre = models.CharField(
        max_length=100,
        unique=True,
        help_text="Nombre de la configuración SNMP"
    )
    tipo_operacion = models.CharField(
        max_length=20,
        choices=TIPO_OPERACION_CHOICES,
        default='general',
        help_text="Tipo de operación SNMP a la que se aplica"
    )
    timeout = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(300)],
        help_text="Timeout en segundos (1-300)"
    )
    reintentos = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(10)],
        help_text="Número de reintentos SNMP (0-10)"
    )
    comunidad = models.CharField(
        max_length=50,
        default='public',
        help_text="Comunidad SNMP por defecto"
    )
    version = models.CharField(
        max_length=10,
        choices=[
            ('1', 'SNMPv1'),
            ('2c', 'SNMPv2c'),
            ('3', 'SNMPv3'),
        ],
        default='2c',
        help_text="Versión de SNMP"
    )
    
    # Configuración específica para pollers GET
    max_pollers_por_olt = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Máximo de pollers concurrentes por OLT (solo para GET)"
    )
    tamano_lote_inicial = models.PositiveIntegerField(
        default=200,
        validators=[MinValueValidator(10), MaxValueValidator(1000)],
        help_text="Tamaño del lote inicial de ONUs (solo para GET)"
    )
    tamano_subdivision = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(5), MaxValueValidator(500)],
        help_text="Tamaño al subdividir lotes con errores (solo para GET)"
    )
    max_reintentos_individuales = models.PositiveSmallIntegerField(
        default=2,
        validators=[MaxValueValidator(10)],
        help_text="Reintentos para ONUs individuales (solo para GET)"
    )
    delay_entre_reintentos = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Segundos entre reintentos (solo para GET)"
    )
    max_consultas_snmp_simultaneas = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Máximo de consultas SNMP simultáneas por poller (Semaphore)"
    )
    
    activo = models.BooleanField(
        default=True,
        help_text="Si está activo, se aplica a las operaciones del tipo especificado"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuracion_snmp'
        verbose_name = 'Configuración SNMP'
        verbose_name_plural = 'Configuraciones SNMP'
        ordering = ['tipo_operacion', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_operacion_display()}) - v{self.version}, timeout: {self.timeout}s"
    
    @staticmethod
    def get_config_for_tipo(tipo_operacion='general'):
        """
        Obtiene la configuración activa para un tipo de operación específico.
        Si no hay configuración para ese tipo, usa 'general'.
        """
        try:
            # Intentar obtener configuración específica para el tipo
            config = ConfiguracionSNMP.objects.filter(
                tipo_operacion=tipo_operacion,
                activo=True
            ).first()
            
            # Si no existe, usar configuración general
            if not config:
                config = ConfiguracionSNMP.objects.filter(
                    tipo_operacion='general',
                    activo=True
                ).first()
            
            return config
        except Exception:
            return None


class ConfiguracionCelery(models.Model):
    """
    Configuraciones específicas para Celery
    """
    nombre = models.CharField(
        max_length=100,
        unique=True,
        help_text="Nombre de la configuración Celery"
    )
    cola = models.CharField(
        max_length=50,
        help_text="Nombre de la cola de Celery"
    )
    concurrencia = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Número de workers concurrentes (1-50)"
    )
    timeout_tarea = models.PositiveIntegerField(
        default=300,
        validators=[MinValueValidator(30), MaxValueValidator(3600)],
        help_text="Timeout de tareas en segundos (30-3600)"
    )
    reintentos_tarea = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(10)],
        help_text="Número de reintentos automáticos (0-10)"
    )
    activo = models.BooleanField(
        default=True,
        help_text="Si está activo, se aplica a la cola"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuracion_celery'
        verbose_name = 'Configuración Celery'
        verbose_name_plural = 'Configuraciones Celery'
        ordering = ['cola', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.cola}, {self.concurrencia} workers)"