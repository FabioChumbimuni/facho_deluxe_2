from django.db import models
from django.core.exceptions import ValidationError


class ZabbixConfiguration(models.Model):
    """
    Configuración global de Zabbix para sincronización de puertos ODF.
    Solo debe existir UNA configuración activa.
    """
    # Configuración de conexión
    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Nombre de Configuración',
        help_text='Nombre identificador de esta configuración'
    )
    
    zabbix_url = models.URLField(
        max_length=255,
        verbose_name='URL Zabbix API',
        help_text='URL completa de la API de Zabbix (ej: http://zabbix.example.com/api_jsonrpc.php)'
    )
    
    zabbix_token = models.CharField(
        max_length=255,
        verbose_name='Token de Autenticación',
        help_text='Token de autenticación de Zabbix (se guardará de forma segura)'
    )
    
    # Configuración de item master
    item_key = models.CharField(
        max_length=100,
        default='port.descover.walk',
        verbose_name='Clave del Item Master',
        help_text='Clave del item master en Zabbix que contiene el SNMP walk completo'
    )
    
    # Estado de la configuración
    activa = models.BooleanField(
        default=True,
        verbose_name='Configuración Activa',
        help_text='Solo puede haber una configuración activa a la vez'
    )
    
    # Configuración adicional
    timeout = models.IntegerField(
        default=30,
        verbose_name='Timeout (segundos)',
        help_text='Tiempo máximo de espera para peticiones a Zabbix'
    )
    
    verificar_ssl = models.BooleanField(
        default=True,
        verbose_name='Verificar SSL',
        help_text='Verificar certificados SSL en las peticiones'
    )
    
    # Metadatos
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name='Descripción',
        help_text='Descripción adicional de esta configuración'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')
    
    class Meta:
        db_table = 'zabbix_configuration'
        verbose_name = 'Configuración de Zabbix'
        verbose_name_plural = 'Configuraciones de Zabbix'
        ordering = ['-activa', '-updated_at']
        indexes = [
            models.Index(fields=['activa']),
            models.Index(fields=['nombre']),
        ]
    
    def __str__(self):
        estado = "✅ ACTIVA" if self.activa else "⏸️ Inactiva"
        return f"{self.nombre} ({estado})"
    
    def clean(self):
        """Validación: Solo una configuración puede estar activa"""
        if self.activa:
            # Verificar si ya existe otra configuración activa
            existing_active = ZabbixConfiguration.objects.filter(activa=True).exclude(pk=self.pk)
            if existing_active.exists():
                raise ValidationError(
                    'Ya existe una configuración activa. '
                    'Desactiva la configuración actual antes de activar otra.'
                )
    
    def save(self, *args, **kwargs):
        # Validar antes de guardar
        self.full_clean()
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_config(cls):
        """Obtiene la configuración activa"""
        return cls.objects.filter(activa=True).first()
    
    def get_service(self):
        """
        Crea una instancia de ZabbixService con esta configuración
        """
        from odf_management.services.zabbix_service import ZabbixService
        return ZabbixService(
            zabbix_url=self.zabbix_url,
            token=self.zabbix_token
        )
