from django.db import models
from brands.models import Brand


class OID(models.Model):
    ESPACIO_CHOICES = [
        ('descubrimiento', 'Descubrimiento'),  # Excepción: va a onu_index_map + onu_status
        ('descripcion', 'Descripción'),         # → snmp_description
        ('mac', 'MAC Address'),                 # → mac_address
        ('plan_onu', 'Plan ONU'),              # → plan_onu
        ('distancia_onu', 'Distancia ONU'),    # → distancia_onu
        ('modelo_onu', 'Modelo ONU'),          # → modelo_onu
        ('serial', 'Serial Number'),           # → serial_number
        ('subscriber', 'Subscriber ID'),       # → subscriber_id
        ('zabbix_state', 'Zabbix - Estado Admin'),      # → Estado administrativo del puerto
        ('zabbix_interface', 'Zabbix - Nombre Interface'),  # → Nombre de interfaz (ej: GPON 0/1/1)
        ('zabbix_description', 'Zabbix - Descripción'),     # → Descripción del puerto
    ]
    
    # Mapeo automático espacio → campo
    ESPACIO_TO_FIELD = {
        'descubrimiento': None,  # Excepción
        'descripcion': 'snmp_description',
        'mac': 'mac_address',
        'plan_onu': 'plan_onu',
        'distancia_onu': 'distancia_onu',
        'modelo_onu': 'modelo_onu',
        'serial': 'serial_number',
        'subscriber': 'subscriber_id',
        'zabbix_state': 'admin_state',         # Estado administrativo (1=up, 2=down)
        'zabbix_interface': 'interface_name',  # Nombre de interfaz
        'zabbix_description': 'port_description',  # Descripción del puerto
    }
    
    nombre = models.CharField(max_length=255)
    oid = models.CharField(max_length=255)
    marca = models.ForeignKey(
        Brand, 
        models.CASCADE, 
        db_column='marca_id',
        verbose_name='Marca',
        help_text='Marca del equipo. Usar "🌐 Genérico" para aplicar a todas las marcas'
    )
    modelo = models.ForeignKey(
        'olt_models.OLTModel',
        on_delete=models.CASCADE,
        db_column='modelo_id',
        verbose_name='Modelo',
        help_text='Modelo del equipo. Usar "🌐 Genérico" para aplicar a todos los modelos'
    )
    espacio = models.CharField(
        max_length=20, 
        choices=ESPACIO_CHOICES, 
        default='descubrimiento',
        help_text='Tipo de información que proporciona este OID'
    )
    target_field = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        editable=False,  # Se completa automáticamente basado en espacio
        verbose_name='Campo destino (automático)',
        help_text='Se asigna automáticamente según el espacio seleccionado'
    )
    keep_previous_value = models.BooleanField(
        default=False,
        verbose_name='Mantener valor previo',
        help_text='Si está marcado, conserva el valor anterior cuando GET devuelve vacío (lógica facho_deluxe)'
    )
    format_mac = models.BooleanField(
        default=False,
        verbose_name='Formatear MAC',
        help_text='Elimina ":" y espacios de direcciones MAC (AC:DC:SD → ACDCSD)'
    )

    class Meta:
        db_table = 'oids'
        managed = True
        ordering = ['id']  # ✅ Ordenamiento por defecto para evitar warning de paginación

    def clean(self):
        """Validaciones personalizadas"""
        from django.core.exceptions import ValidationError
        
        # Validar que marca esté presente
        if not self.marca_id and not self.marca:
            raise ValidationError({'marca': 'Marca es obligatoria. Use "🌐 Genérico" si aplica universalmente.'})
        
        # Validar que modelo esté presente
        if not self.modelo_id and not self.modelo:
            raise ValidationError({'modelo': 'Modelo es obligatorio. Use "🌐 Genérico" si aplica universalmente.'})
    
    def save(self, *args, **kwargs):
        """Auto-completar target_field basado en espacio y validar"""
        self.target_field = self.ESPACIO_TO_FIELD.get(self.espacio)
        self.full_clean()  # Ejecutar validaciones
        super().save(*args, **kwargs)

    def __str__(self):
        modelo_str = f" [{self.modelo.nombre}]" if self.modelo else ""
        return f"{self.nombre} ({self.oid}) - {self.get_espacio_display()}{modelo_str}"
    
    @classmethod
    def get_zabbix_oids_for_olt(cls, olt):
        """
        Obtiene los 3 OIDs de Zabbix para una OLT específica.
        
        Lógica de búsqueda (cascada) para cada tipo:
        1. Marca + Modelo específico (ej: Huawei + MA5800)
        2. Marca + Modelo genérico (ej: Huawei + 🌐 Genérico)
        3. Genérico completo (🌐 Genérico + 🌐 Genérico)
        
        Args:
            olt: Instancia de OLT con marca y modelo (ambos obligatorios)
            
        Returns:
            Dict con los 3 OIDs: {
                'state': OID instance o None,
                'interface': OID instance o None,
                'description': OID instance o None
            }
        """
        from brands.models import Brand
        from olt_models.models import OLTModel
        
        result = {
            'state': None,
            'interface': None,
            'description': None
        }
        
        # Mapeo de tipos de Zabbix
        zabbix_types = {
            'state': 'zabbix_state',
            'interface': 'zabbix_interface',
            'description': 'zabbix_description'
        }
        
        for key, espacio_type in zabbix_types.items():
            # 1. Buscar por marca + modelo específico
            oid = cls.objects.filter(
                espacio=espacio_type,
                marca=olt.marca,
                modelo=olt.modelo
            ).first()
            
            if oid:
                result[key] = oid
                continue
            
            # 2. Buscar marca específica + modelo genérico
            try:
                generic_model = OLTModel.objects.get(nombre='Genérico', marca__nombre='🌐 Genérico')
                oid = cls.objects.filter(
                    espacio=espacio_type,
                    marca=olt.marca,
                    modelo=generic_model
                ).first()
                
                if oid:
                    result[key] = oid
                    continue
            except OLTModel.DoesNotExist:
                pass
            
            # 3. Buscar genérico completo (marca genérica + modelo genérico)
            try:
                generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                generic_model = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
                oid = cls.objects.filter(
                    espacio=espacio_type,
                    marca=generic_brand,
                    modelo=generic_model
                ).first()
                
                if oid:
                    result[key] = oid
            except (Brand.DoesNotExist, OLTModel.DoesNotExist):
                pass
        
        return result
    
    @classmethod
    def get_zabbix_oid_for_olt(cls, olt):
        """
        DEPRECATED: Usar get_zabbix_oids_for_olt() en su lugar.
        Mantiene compatibilidad retornando solo el OID de estado.
        """
        oids = cls.get_zabbix_oids_for_olt(olt)
        return oids['state']