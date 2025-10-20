from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


class Area(models.Model):
    """
    Áreas de trabajo del personal - completamente personalizable
    """
    nombre = models.CharField(
        max_length=100,
        unique=True,
        help_text="Nombre único del área (ej: Proyectos, NOC, Técnico de Campo)"
    )
    descripcion = models.TextField(
        blank=True,
        null=True,
        help_text="Descripción detallada del área"
    )
    activa = models.BooleanField(
        default=True,
        help_text="Si el área está activa"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "personal_area"
        verbose_name = "Área de Trabajo"
        verbose_name_plural = "Áreas de Trabajo"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class NivelPrivilegio(models.Model):
    """
    Niveles de privilegios para el personal
    """
    NIVEL_CHOICES = [
        (1, 'Básico - Solo lectura'),
        (2, 'Operador - Lectura y escritura limitada'),
        (3, 'Supervisor - Gestión completa de su área'),
        (4, 'Administrador - Gestión completa del sistema'),
        (5, 'Super Admin - Acceso total'),
    ]
    
    nivel = models.IntegerField(
        unique=True,
        choices=NIVEL_CHOICES,
        help_text="Nivel numérico de privilegio (1-5)"
    )
    nombre = models.CharField(
        max_length=50,
        help_text="Nombre del nivel de privilegio"
    )
    descripcion = models.TextField(
        help_text="Descripción detallada de los permisos"
    )
    permisos_odf = models.JSONField(
        default=dict,
        help_text="Permisos específicos para gestión de ODFs"
    )
    permisos_hilos = models.JSONField(
        default=dict,
        help_text="Permisos específicos para gestión de hilos"
    )
    activo = models.BooleanField(
        default=True,
        help_text="Si el nivel está activo"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "personal_nivel_privilegio"
        verbose_name = "Nivel de Privilegio"
        verbose_name_plural = "Niveles de Privilegio"
        ordering = ["nivel"]

    def __str__(self):
        return f"Nivel {self.nivel} - {self.nombre}"


class Personal(models.Model):
    """
    Personal del sistema con áreas y privilegios específicos
    """
    ESTADO_CHOICES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('suspendido', 'Suspendido'),
    ]
    
    # Información personal
    nombres = models.CharField(
        max_length=100,
        help_text="Nombres completos"
    )
    apellidos = models.CharField(
        max_length=100,
        help_text="Apellidos completos"
    )
    documento_identidad = models.CharField(
        max_length=20,
        unique=True,
        help_text="Número de documento de identidad"
    )
    email = models.EmailField(
        unique=True,
        help_text="Correo electrónico corporativo"
    )
    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Número de teléfono"
    )
    
    # Información laboral
    codigo_empleado = models.CharField(
        max_length=20,
        unique=True,
        help_text="Código único del empleado"
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.PROTECT,
        help_text="Área de trabajo del personal"
    )
    nivel_privilegio = models.ForeignKey(
        NivelPrivilegio,
        on_delete=models.PROTECT,
        help_text="Nivel de privilegios en el sistema"
    )
    cargo = models.CharField(
        max_length=100,
        help_text="Cargo o posición"
    )
    fecha_ingreso = models.DateField(
        help_text="Fecha de ingreso a la empresa"
    )
    
    # Estado y configuración
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='activo',
        help_text="Estado actual del personal"
    )
    usuario_django = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Usuario Django asociado (opcional)"
    )
    
    # Campos de seguimiento
    observaciones = models.TextField(
        blank=True,
        null=True,
        help_text="Observaciones adicionales"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personal_creado",
        help_text="Personal que creó este registro"
    )

    class Meta:
        db_table = "personal"
        verbose_name = "Personal"
        verbose_name_plural = "Personal"
        ordering = ["apellidos", "nombres"]
        indexes = [
            models.Index(fields=["area"]),
            models.Index(fields=["nivel_privilegio"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["codigo_empleado"]),
            models.Index(fields=["documento_identidad"]),
        ]

    def __str__(self):
        return f"{self.nombres} {self.apellidos} ({self.area.nombre})"

    @property
    def nombre_completo(self):
        """Retorna el nombre completo"""
        return f"{self.nombres} {self.apellidos}"

    @property
    def identificador_completo(self):
        """Retorna identificador completo con área y cargo"""
        return f"{self.nombre_completo} - {self.cargo} ({self.area.nombre})"

    @property
    def puede_gestionar_odfs(self):
        """Verifica si puede gestionar ODFs"""
        return self.nivel_privilegio.permisos_odf.get('gestionar', False)

    @property
    def puede_gestionar_hilos(self):
        """Verifica si puede gestionar hilos"""
        return self.nivel_privilegio.permisos_hilos.get('gestionar', False)

    @property
    def es_supervisor(self):
        """Verifica si tiene nivel de supervisor o superior"""
        return self.nivel_privilegio.nivel >= 3

    def clean(self):
        """Validaciones personalizadas"""
        # Validar que el email sea único
        if self.email:
            existing = Personal.objects.filter(
                email__iexact=self.email
            ).exclude(pk=self.pk)
            
            if existing.exists():
                raise ValidationError({
                    'email': f'Ya existe personal con el email {self.email}'
                })

    def save(self, *args, **kwargs):
        """Guardar con validaciones"""
        self.clean()
        super().save(*args, **kwargs)


class HistorialAcceso(models.Model):
    """
    Historial de accesos y modificaciones del personal
    """
    ACCION_CHOICES = [
        ('login', 'Inicio de sesión'),
        ('logout', 'Cierre de sesión'),
        ('create_odf', 'Creación de ODF'),
        ('update_odf', 'Modificación de ODF'),
        ('create_hilo', 'Creación de hilo'),
        ('update_hilo', 'Modificación de hilo'),
        ('enable_hilo', 'Habilitación de hilo'),
        ('disable_hilo', 'Deshabilitación de hilo'),
    ]
    
    personal = models.ForeignKey(
        Personal,
        on_delete=models.CASCADE,
        help_text="Personal que realizó la acción"
    )
    accion = models.CharField(
        max_length=20,
        choices=ACCION_CHOICES,
        help_text="Tipo de acción realizada"
    )
    descripcion = models.TextField(
        help_text="Descripción detallada de la acción"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Dirección IP desde donde se realizó la acción"
    )
    user_agent = models.TextField(
        blank=True,
        null=True,
        help_text="User agent del navegador"
    )
    objeto_afectado_tipo = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Tipo de objeto afectado (ODF, Hilo, etc.)"
    )
    objeto_afectado_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID del objeto afectado"
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "personal_historial_acceso"
        verbose_name = "Historial de Acceso"
        verbose_name_plural = "Historial de Accesos"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["personal"]),
            models.Index(fields=["accion"]),
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self):
        return f"{self.personal.nombre_completo} - {self.get_accion_display()} ({self.timestamp})"