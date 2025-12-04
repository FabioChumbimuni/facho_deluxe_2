from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta


class ZabbixPortData(models.Model):
    """
    Datos básicos extraídos de Zabbix para cada puerto GPON.
    Solo contiene información cruda que se puede obtener automáticamente.
    """
    olt = models.ForeignKey("hosts.OLT", on_delete=models.CASCADE, db_column="olt_id")
    snmp_index = models.CharField(max_length=50, help_text="Índice SNMP de la interfaz")
    slot = models.IntegerField(help_text="Slot calculado desde SNMP index")
    port = models.IntegerField(help_text="Port calculado desde SNMP index")
    descripcion_zabbix = models.TextField(
        blank=True, 
        null=True, 
        help_text="Descripción cruda desde Zabbix"
    )
    interface_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Nombre de interfaz (ej: GPON 0/4/15)"
    )
    disponible = models.BooleanField(
        default=True,
        help_text="Si el puerto está disponible en la última recolección de Zabbix"
    )
    estado_administrativo = models.IntegerField(
        null=True,
        blank=True,
        choices=[(1, 'ACTIVO'), (2, 'INACTIVO')],
        help_text="Estado administrativo del puerto desde OID .1.3.6.1.2.1.2.2.1.7 (1=ACTIVO, 2=INACTIVO)"
    )
    operativo_noc = models.BooleanField(
        default=False,
        help_text="Si el puerto está operativo según NOC (configuración manual)"
    )
    last_sync = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "zabbix_port_data"
        verbose_name = "Datos de Puerto Zabbix"
        verbose_name_plural = "Datos de Puertos Zabbix"
        unique_together = [('olt', 'snmp_index')]
        ordering = ["olt", "slot", "port"]
        indexes = [
            models.Index(fields=["olt", "slot", "port"]),
            models.Index(fields=["snmp_index"]),
        ]

    def __str__(self):
        return f"{self.olt.abreviatura} - Slot:{self.slot} Port:{self.port} ({self.snmp_index})"
    
    def save(self, *args, **kwargs):
        """
        Guardar puerto y sincronizar estado con hilos ODF relacionados
        """
        # Detectar si cambió el campo 'disponible'
        disponible_cambio = False
        if self.pk:
            try:
                old_instance = ZabbixPortData.objects.get(pk=self.pk)
                disponible_cambio = old_instance.disponible != self.disponible
            except ZabbixPortData.DoesNotExist:
                pass
        
        # Guardar primero
        super().save(*args, **kwargs)
        
        # Si cambió 'disponible', sincronizar con hilos relacionados
        if disponible_cambio:
            hilos_relacionados = self.odfhilos_set.all()
            for hilo in hilos_relacionados:
                if hilo.en_zabbix != self.disponible:
                    hilo.en_zabbix = self.disponible
                    hilo.save()

    @property
    def descripcion_limpia(self):
        """Descripción sin caracteres especiales iniciales"""
        if self.descripcion_zabbix:
            desc = self.descripcion_zabbix.strip()
            if desc.startswith(':'):
                desc = desc[1:].strip()
            return desc
        return ""


class ZabbixCollectionSchedule(models.Model):
    """
    Programación de recolección de datos desde Zabbix.
    Define cada cuántos minutos se ejecuta la recolección.
    """
    INTERVAL_CHOICES = [
        (5, 'Cada 5 minutos (:05, :10, :15, :20...)'),
        (10, 'Cada 10 minutos (:10, :20, :30, :40...)'),
        (15, 'Cada 15 minutos (:15, :30, :45, :00...)'),
        (20, 'Cada 20 minutos (:20, :40, :00...)'),
        (30, 'Cada 30 minutos (:30, :00...)'),
        (60, 'Cada 60 minutos (cada hora)'),
    ]
    
    nombre = models.CharField(
        max_length=100,
        help_text="Nombre descriptivo para esta programación"
    )
    intervalo_minutos = models.IntegerField(
        choices=INTERVAL_CHOICES,
        default=15,
        help_text="Intervalo de recolección en minutos"
    )
    habilitado = models.BooleanField(
        default=True,
        help_text="Si está habilitada la programación"
    )
    proxima_ejecucion = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Próxima ejecución programada"
    )
    ultima_ejecucion = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última ejecución completada"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "zabbix_collection_schedule"
        verbose_name = "Programación de Recolección Zabbix"
        verbose_name_plural = "Programaciones de Recolección Zabbix"
        ordering = ["-created_at"]

    def __str__(self):
        estado = "✅ Activa" if self.habilitado else "❌ Inactiva"
        return f"{self.nombre} - {self.get_intervalo_minutos_display()} ({estado})"

    def clean(self):
        """Validaciones personalizadas"""
        if self.intervalo_minutos not in [choice[0] for choice in self.INTERVAL_CHOICES]:
            raise ValidationError("Intervalo no válido")

    def calcular_proxima_ejecucion(self, primera_vez=False):
        """
        Calcula la próxima ejecución basada en el intervalo configurado.
        
        Args:
            primera_vez (bool): Si es True, programa para 1 minuto después.
        
        Lógica:
        - Primera ejecución: 1 minuto después de crear/guardar
        - Ejecuciones posteriores: Según el intervalo (5, 10, 15, etc. minutos)
        """
        from datetime import datetime, timedelta
        import math
        
        ahora = timezone.now()
        
        if primera_vez or not self.ultima_ejecucion:
            # PRIMERA EJECUCIÓN: En 1 minuto
            self.proxima_ejecucion = ahora + timedelta(minutes=1)
        else:
            # EJECUCIONES POSTERIORES: Según el intervalo configurado
            minuto_actual = ahora.minute
            
            # Calcular el próximo múltiplo del intervalo
            proximo_minuto = math.ceil(minuto_actual / self.intervalo_minutos) * self.intervalo_minutos
            
            if proximo_minuto >= 60:
                # Si pasa de 60, va a la próxima hora
                proxima_hora = ahora.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                proximo_minuto = 0
            else:
                proxima_hora = ahora.replace(minute=proximo_minuto, second=0, microsecond=0)
                
            self.proxima_ejecucion = proxima_hora
            
        return self.proxima_ejecucion

    @property
    def olts_asociadas_count(self):
        """Cuenta las OLTs asociadas a esta programación"""
        return self.zabbixcollectionolt_set.count()

    @property
    def descripcion_intervalo(self):
        """Descripción amigable del intervalo"""
        hora_ejemplo = timezone.now().replace(minute=0, second=0, microsecond=0)
        ejemplos = []
        for i in range(3):
            minuto = (i * self.intervalo_minutos) % 60
            if minuto == 0 and i > 0:
                hora_ejemplo += timedelta(hours=1)
            ejemplos.append(hora_ejemplo.replace(minute=minuto).strftime("%H:%M"))
        return f"Ejemplo: {', '.join(ejemplos)}"


class ZabbixCollectionOLT(models.Model):
    """
    Asociación entre programación de recolección y OLTs específicas.
    """
    schedule = models.ForeignKey(
        ZabbixCollectionSchedule,
        on_delete=models.CASCADE,
        verbose_name="Programación"
    )
    olt = models.ForeignKey(
        "hosts.OLT",
        on_delete=models.CASCADE,
        verbose_name="OLT"
    )
    habilitado = models.BooleanField(
        default=True,
        help_text="Si esta OLT está habilitada para recolección"
    )
    ultima_recoleccion = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última vez que se recolectaron datos de esta OLT"
    )
    ultimo_estado = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Exitoso'),
            ('error', 'Error'),
            ('pending', 'Pendiente'),
        ],
        default='pending',
        help_text="Estado de la última recolección"
    )
    ultimo_error = models.TextField(
        blank=True,
        null=True,
        help_text="Último error encontrado"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "zabbix_collection_olt"
        verbose_name = "OLT en Programación"
        verbose_name_plural = "OLTs en Programación"
        unique_together = [('schedule', 'olt')]
        ordering = ['schedule', 'olt']

    def __str__(self):
        estado_icon = {
            'success': '✅',
            'error': '❌',
            'pending': '⏳'
        }.get(self.ultimo_estado, '❓')
        
        habilitado_text = "" if self.habilitado else " (Deshabilitado)"
        return f"{self.olt.abreviatura} {estado_icon}{habilitado_text}"


class ODF(models.Model):
    """
    Un ODF representa el marco o punto físico de salida de fibras de la OLT.
    Cada ODF tiene un número y un nombre de troncal asociado.
    El número puede repetirse, pero el nombre_troncal debe ser único por OLT.
    """
    olt = models.ForeignKey("hosts.OLT", on_delete=models.CASCADE, db_column="olt_id")
    numero_odf = models.IntegerField(
        help_text="Número del ODF (ej: 1, 2, 3...)"
    )
    nombre_troncal = models.CharField(
        max_length=255,
        help_text="Nombre único de la troncal por OLT (ej: CHOSICA-SANTA EULALIA 2 T-24)"
    )
    descripcion = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "odf"
        verbose_name = "ODF (Marco de Distribución Óptica)"
        verbose_name_plural = "ODFs (Marcos de Distribución Óptica)"
        ordering = ["olt", "numero_odf", "nombre_troncal"]
        indexes = [
            models.Index(fields=["olt"]),
            models.Index(fields=["numero_odf"]),
            models.Index(fields=["nombre_troncal"]),
            models.Index(fields=["olt", "numero_odf"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['olt', 'nombre_troncal'],
                name='unique_troncal_per_olt'
            )
        ]

    def __str__(self):
        return f"{self.olt.abreviatura} - ODF {self.numero_odf} ({self.nombre_troncal})"

    @property
    def identificador_completo(self):
        """Retorna identificador completo del ODF"""
        return f"ODF-{self.numero_odf}: {self.nombre_troncal}"

    def clean(self):
        """Validación personalizada"""
        if self.nombre_troncal:
            # Verificar unicidad del nombre de troncal por OLT
            existing = ODF.objects.filter(
                olt=self.olt, 
                nombre_troncal__iexact=self.nombre_troncal
            ).exclude(pk=self.pk)
            
            if existing.exists():
                raise ValidationError({
                    'nombre_troncal': f'Ya existe una troncal con el nombre "{self.nombre_troncal}" en la OLT {self.olt.abreviatura}'
                })


class ODFHilos(models.Model):
    """
    Cada combinación slot/port de la OLT dentro de un ODF se asocia a un número 
    de hilo y a una VLAN de servicio.
    Solo se habilita (enabled) si aparece en Zabbix. Los hilos manuales quedan disabled.
    """
    ESTADO_CHOICES = [
        ('enabled', 'Habilitado (En Zabbix)'),
        ('disabled', 'Deshabilitado (No en Zabbix)'),
    ]
    
    ORIGEN_CHOICES = [
        ('zabbix', 'Desde Zabbix'),
        ('manual', 'Manual'),
    ]

    odf = models.ForeignKey(ODF, on_delete=models.CASCADE, db_column="odf_id")
    
    # Relación opcional con datos de Zabbix
    zabbix_port = models.ForeignKey(
        ZabbixPortData, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Puerto asociado desde datos de Zabbix (opcional)"
    )
    
    # Campos que pueden venir de Zabbix o definirse manualmente
    slot = models.IntegerField(help_text="Número de slot en la OLT")
    port = models.IntegerField(help_text="Número de puerto en el slot")
    
    # Campos definidos manualmente
    hilo_numero = models.CharField(
        max_length=100,
        help_text="Número o identificador físico del hilo hacia la NAP (puede ser numérico o texto como 'SPLITTER 5')"
    )
    vlan = models.IntegerField(help_text="VLAN de conexión configurada")
    descripcion_manual = models.TextField(
        blank=True, 
        null=True,
        help_text="Descripción manual del hilo/troncal"
    )
    
    # Campos de control de estado y origen
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disabled',
        help_text="Solo 'enabled' si aparece actualmente en Zabbix"
    )
    
    origen = models.CharField(
        max_length=20,
        choices=ORIGEN_CHOICES,
        default='manual',
        help_text="Indica si los datos provienen de Zabbix o son manuales"
    )
    
    en_zabbix = models.BooleanField(
        default=False,
        help_text="Si actualmente aparece en los datos de Zabbix"
    )
    
    # Campos de personal responsable
    personal_proyectos = models.ForeignKey(
        "personal.Personal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hilos_proyectos",
        help_text="Personal de Proyectos responsable"
    )
    
    personal_noc = models.ForeignKey(
        "personal.Personal", 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hilos_noc",
        help_text="Personal NOC responsable"
    )
    
    tecnico_habilitador = models.ForeignKey(
        "personal.Personal",
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name="hilos_habilitados",
        help_text="Técnico que habilitó el hilo"
    )
    
    # Fecha de habilitación (obligatoria, manual)
    fecha_habilitacion = models.DateField(
        default='2024-01-01',
        help_text="Fecha en la que se habilitó el hilo (obligatorio, manual)"
    )
    
    # Hora de habilitación (opcional, manual)
    hora_habilitacion = models.TimeField(
        null=True,
        blank=True,
        help_text="Hora en la que se habilitó el hilo (opcional, manual)"
    )
    operativo_noc = models.BooleanField(
        default=False,
        help_text="Si el hilo está operativo según NOC (configuración manual)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "odf_hilos"
        verbose_name = "Hilo ODF"
        verbose_name_plural = "Hilos ODF"
        unique_together = [('odf', 'slot', 'port', 'hilo_numero')]
        ordering = ["odf", "slot", "port", "hilo_numero"]
        indexes = [
            models.Index(fields=["odf"]),
            models.Index(fields=["slot", "port"]),
            models.Index(fields=["vlan"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["origen"]),
            models.Index(fields=["en_zabbix"]),
        ]

    def __str__(self):
        estado_icon = "🟢" if self.estado == 'enabled' else "🔴"
        origen_icon = "📡" if self.origen == 'zabbix' else "✋"
        return f"{self.odf.nombre_troncal} - S{self.slot}P{self.port}H{self.hilo_numero} {estado_icon}{origen_icon}"

    @property
    def identificador_completo(self):
        """Retorna un identificador completo del hilo"""
        return f"{self.odf.olt.abreviatura}/{self.odf.nombre_troncal}/S{self.slot}P{self.port}H{self.hilo_numero}"
    
    @property
    def descripcion_completa(self):
        """Retorna la descripción más completa disponible"""
        if self.descripcion_manual:
            return self.descripcion_manual
        elif self.zabbix_port and self.zabbix_port.descripcion_zabbix:
            return self.zabbix_port.descripcion_zabbix
        return ""
    
    @property
    def estado_detallado(self):
        """Descripción detallada del estado"""
        if self.estado == 'enabled':
            return f"✅ Habilitado (En Zabbix)"
        else:
            if self.origen == 'manual':
                return f"🔴 Manual (No en Zabbix)"
            else:
                return f"⚠️ Deshabilitado (Ya no en Zabbix)"
    
    def actualizar_desde_zabbix(self, zabbix_port=None):
        """Actualiza el estado basado en la presencia en Zabbix"""
        if zabbix_port:
            # Puerto encontrado en Zabbix
            self.zabbix_port = zabbix_port
            self.slot = zabbix_port.slot
            self.port = zabbix_port.port
            self.estado = 'enabled'
            self.origen = 'zabbix'
            self.en_zabbix = True
        else:
            # Puerto ya no está en Zabbix
            self.estado = 'disabled'
            self.en_zabbix = False
            # Mantener zabbix_port para referencia histórica
    
    def sincronizar_operativo_noc(self, forzar_direccion=None):
        """
        Sincroniza el campo operativo_noc entre ODFHilos y ZabbixPortData
        
        Args:
            forzar_direccion: 'hilo_a_puerto', 'puerto_a_hilo' o None (automático)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.zabbix_port:
            # Intentar encontrar puerto por OLT, slot y port
            try:
                puerto_candidato = ZabbixPortData.objects.get(
                    olt=self.odf.olt,
                    slot=self.slot,
                    port=self.port,
                    disponible=True
                )
                self.zabbix_port = puerto_candidato
                self.save()
                logger.info(f"Puerto Zabbix {puerto_candidato.id} auto-asociado a hilo {self.id}")
            except (ZabbixPortData.DoesNotExist, ZabbixPortData.MultipleObjectsReturned):
                logger.warning(f"No se pudo auto-asociar puerto Zabbix para hilo {self.id}")
                return False
        
        if self.zabbix_port:
            if forzar_direccion == 'hilo_a_puerto':
                # Forzar: Hilo → Puerto
                self.zabbix_port.operativo_noc = self.operativo_noc
                self.zabbix_port.save()
                return True
            elif forzar_direccion == 'puerto_a_hilo':
                # Forzar: Puerto → Hilo  
                self.operativo_noc = self.zabbix_port.operativo_noc
                self.save()
                return True
            else:
                # Automático: sincronizar si hay diferencia
                if self.operativo_noc != self.zabbix_port.operativo_noc:
                    # Por defecto, el hilo tiene prioridad (es manual)
                    self.zabbix_port.operativo_noc = self.operativo_noc
                    self.zabbix_port.save()
                    return True
        
        return False
    
    def save(self, *args, **kwargs):
        """Auto-llenar campos desde ZabbixPortData si está asociado"""
        if self.zabbix_port:
            self.slot = self.zabbix_port.slot
            self.port = self.zabbix_port.port
            # Si tiene puerto de Zabbix, actualizar estado
            self.origen = 'zabbix'
            self.en_zabbix = True
            self.estado = 'enabled'
        
        # Guardar primero para tener el ID
        super().save(*args, **kwargs)
        
        # ✅ CRÍTICO: Relacionar automáticamente todas las ONUs con el mismo slot/port
        # Solo si tenemos slot y port definidos
        if self.slot is not None and self.port is not None:
            self._relacionar_onus_automatico()
    
    def _relacionar_onus_automatico(self):
        """
        Busca y relaciona automáticamente todas las ONUs (OnuIndexMap) que tengan
        el mismo slot/port en la misma OLT con este hilo.
        """
        try:
            from discovery.models import OnuIndexMap
            
            # Buscar todas las ONUs de esta OLT con el mismo slot/port que aún no tengan hilo asignado
            onus_sin_hilo = OnuIndexMap.objects.filter(
                olt=self.odf.olt,
                slot=self.slot,
                port=self.port,
                odf_hilo__isnull=True
            )
            
            cantidad_relacionadas = onus_sin_hilo.update(odf_hilo=self)
            
            if cantidad_relacionadas > 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"✅ Hilo {self.id} ({self.identificador_completo}): "
                    f"{cantidad_relacionadas} ONU(s) relacionada(s) automáticamente"
                )
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"⚠️ Error relacionando ONUs automáticamente para hilo {self.id}: {e}")