from django.db import models
from brands.models import Brand


class IndexFormula(models.Model):
    """
    Configuración de fórmulas para calcular slot/port/logical desde índices SNMP.
    Permite soportar múltiples marcas sin tocar código.
    """
    
    CALCULATION_MODE_CHOICES = [
        ('linear', 'Lineal (Base + Pasos)'),
        ('bitshift', 'Desplazamiento de Bits'),
    ]
    
    # Identificación
    marca = models.ForeignKey(
        Brand, 
        on_delete=models.CASCADE, 
        db_column='marca_id',
        verbose_name='Marca',
        help_text='Marca del equipo. Use "🌐 Genérico" para fórmula universal.'
    )
    modelo = models.ForeignKey(
        'olt_models.OLTModel',
        on_delete=models.CASCADE,
        db_column='modelo_id',
        verbose_name='Modelo OLT',
        help_text='Modelo del equipo. Use "🌐 Genérico" si aplica a todos los modelos de la marca.'
    )
    nombre = models.CharField(
        max_length=255,
        verbose_name='Nombre descriptivo',
        help_text='Ej: "Huawei MA5800 - Fórmula estándar"'
    )
    activo = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Si está desactivado, no se usará esta fórmula'
    )
    
    # Parámetros de cálculo
    calculation_mode = models.CharField(
        max_length=20,
        choices=CALCULATION_MODE_CHOICES,
        default='linear',
        verbose_name='Modo de cálculo',
        help_text='Cómo se calcula el slot/port desde el índice'
    )
    
    # === MODO LINEAL ===
    base_index = models.BigIntegerField(
        default=0,
        verbose_name='Base del índice',
        help_text='Valor base que se resta del índice SNMP. Ej: 4194304000 para Huawei'
    )
    step_slot = models.IntegerField(
        default=0,
        verbose_name='Paso por slot',
        help_text='Incremento del índice por cada slot. Ej: 8192 para Huawei'
    )
    step_port = models.IntegerField(
        default=0,
        verbose_name='Paso por puerto',
        help_text='Incremento del índice por cada puerto. Ej: 256 para Huawei'
    )
    
    # === MODO BITSHIFT ===
    shift_slot_bits = models.IntegerField(
        default=0,
        verbose_name='Bits de desplazamiento para slot',
        help_text='Cuántos bits desplazar para extraer slot (modo bitshift)'
    )
    shift_port_bits = models.IntegerField(
        default=0,
        verbose_name='Bits de desplazamiento para puerto',
        help_text='Cuántos bits desplazar para extraer puerto (modo bitshift)'
    )
    mask_slot = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Máscara para slot',
        help_text='Máscara hexadecimal para slot (ej: 0xFF). Opcional.'
    )
    mask_port = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Máscara para puerto',
        help_text='Máscara hexadecimal para puerto (ej: 0xFF). Opcional.'
    )
    
    # === PARÁMETROS ADICIONALES ===
    onu_offset = models.IntegerField(
        default=0,
        verbose_name='Offset de ONU',
        help_text='Si la numeración de ONU empieza en 0 o 1 (o cualquier otro número)'
    )
    has_dot_notation = models.BooleanField(
        default=False,
        verbose_name='Usa notación con punto',
        help_text='Si el índice incluye ".ONU" al final (ej: "4194312448.2")'
    )
    dot_is_onu_number = models.BooleanField(
        default=True,
        verbose_name='Punto es número ONU',
        help_text='Si la parte después del punto es el número de ONU lógico'
    )
    
    # === LÍMITES Y VALIDACIÓN ===
    slot_max = models.IntegerField(
        default=64,
        verbose_name='Slot máximo',
        help_text='Rango máximo esperado de slots (para validación)'
    )
    port_max = models.IntegerField(
        default=64,
        verbose_name='Puerto máximo',
        help_text='Rango máximo esperado de puertos (para validación)'
    )
    onu_max = models.IntegerField(
        default=128,
        verbose_name='ONU máximo',
        help_text='Rango máximo esperado de ONUs por puerto (para validación)'
    )
    
    # === FORMATO DE SALIDA ===
    normalized_format = models.CharField(
        max_length=50,
        default='{slot}/{port}',
        verbose_name='Formato normalizado',
        help_text='Formato de salida. Variables: {slot}, {port}, {logical}. Ej: "{slot}/{port}" o "{slot}/{port}/{logical}"'
    )
    
    # Metadata
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name='Descripción',
        help_text='Notas adicionales sobre esta fórmula'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        db_table = 'index_formulas'
        verbose_name = 'Fórmula de Índice SNMP'
        verbose_name_plural = 'Fórmulas de Índice SNMP'
        unique_together = [('marca', 'modelo')]  # Una fórmula por marca-modelo
        ordering = ['marca__nombre', 'modelo']
        indexes = [
            models.Index(fields=['marca', 'activo']),
            models.Index(fields=['activo']),
        ]
    
    def clean(self):
        """Validaciones personalizadas"""
        from django.core.exceptions import ValidationError
        
        # Validar que marca esté presente
        if not self.marca_id and not self.marca:
            raise ValidationError({'marca': 'Marca es obligatoria. Use "🌐 Genérico" si aplica universalmente.'})
        
        # Validar que modelo esté presente
        if not self.modelo_id and not self.modelo:
            raise ValidationError({'modelo': 'Modelo es obligatorio. Use "🌐 Genérico" si aplica universalmente.'})
        
        # REGLA: Solo puede haber UNA fórmula completamente genérica (🌐 Genérico + Genérico)
        if self.marca and self.modelo:
            if self.marca.nombre == '🌐 Genérico' and self.modelo.nombre == 'Genérico':
                # Verificar si ya existe otra genérica
                existing_generic = IndexFormula.objects.filter(
                    marca__nombre='🌐 Genérico',
                    modelo__nombre='Genérico'
                ).exclude(pk=self.pk)
                
                if existing_generic.exists():
                    raise ValidationError(
                        'Ya existe una fórmula completamente genérica (🌐 Genérico + Genérico). '
                        'Solo puede haber UNA fórmula universal.'
                    )
    
    def save(self, *args, **kwargs):
        """Guardar con validaciones"""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.marca:
            if self.modelo:
                return f"{self.marca.nombre} - {self.modelo.nombre} ({self.nombre})"
            return f"{self.marca.nombre} ({self.nombre})"
        else:
            return f"🌐 Genérica Universal ({self.nombre})"
    
    def calculate_components(self, raw_index_key: str) -> dict:
        """
        Calcula slot, port y logical desde el índice crudo usando esta fórmula.
        
        Args:
            raw_index_key: Índice SNMP crudo (ej: "4194312448.2" o "268566784")
        
        Returns:
            dict: {'slot': int, 'port': int, 'logical': int, 'onu_number': int, 'snmp_index': int}
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 1. Parsear el índice
        snmp_index, onu_number = self._parse_index(raw_index_key)
        
        if snmp_index is None:
            return {
                'slot': None, 
                'port': None, 
                'logical': None, 
                'onu_number': None, 
                'snmp_index': None
            }
        
        # 2. Calcular según el modo
        if self.calculation_mode == 'linear':
            slot, port, onu_id = self._calculate_linear(snmp_index)
        elif self.calculation_mode == 'bitshift':
            slot, port, onu_id = self._calculate_bitshift(snmp_index)
        else:
            logger.error(f"❌ Modo de cálculo desconocido: {self.calculation_mode}")
            return {
                'slot': None, 
                'port': None, 
                'logical': None, 
                'onu_number': None, 
                'snmp_index': snmp_index
            }
        
        # 3. Aplicar offset de ONU si existe
        if onu_id is not None and self.onu_offset:
            onu_id += self.onu_offset
        
        # 4. Validar rangos
        if not self._validate_ranges(slot, port, onu_id):
            logger.warning(f"⚠️ Valores fuera de rango: slot={slot}, port={port}, onu_id={onu_id}")
        
        return {
            'slot': slot,
            'port': port,
            'logical': onu_number if self.dot_is_onu_number else onu_id,
            'onu_id': onu_id,
            'onu_number': onu_number,
            'snmp_index': snmp_index
        }
    
    def _parse_index(self, raw_index_key: str) -> tuple:
        """Parsea el índice crudo"""
        try:
            if self.has_dot_notation and '.' in raw_index_key:
                snmp_index_str, onu_number_str = raw_index_key.split('.', 1)
                snmp_index = int(snmp_index_str)
                onu_number = int(onu_number_str)
            else:
                snmp_index = int(raw_index_key.split('.')[0])  # Por si acaso tiene punto
                onu_number = 0
            
            return snmp_index, onu_number
            
        except (ValueError, IndexError) as e:
            import logging
            logging.getLogger(__name__).error(f"❌ Error parseando índice '{raw_index_key}': {e}")
            return None, None
    
    def _calculate_linear(self, snmp_index: int) -> tuple:
        """Calcula usando modo lineal (BASE + STEPS)"""
        # Restar la base
        delta = snmp_index - self.base_index
        
        # Calcular slot
        slot = delta // self.step_slot if self.step_slot > 0 else 0
        
        # Resto después de sacar slot
        resto = delta % self.step_slot if self.step_slot > 0 else delta
        
        # Calcular puerto
        port = resto // self.step_port if self.step_port > 0 else 0
        
        # Calcular ONU ID
        onu_id = resto % self.step_port if self.step_port > 0 else 0
        
        return slot, port, onu_id
    
    def _calculate_bitshift(self, snmp_index: int) -> tuple:
        """Calcula usando modo bitshift"""
        # Extraer slot
        slot = (snmp_index >> self.shift_slot_bits)
        if self.mask_slot:
            slot &= int(self.mask_slot, 16)
        
        # Extraer puerto
        port = (snmp_index >> self.shift_port_bits)
        if self.mask_port:
            port &= int(self.mask_port, 16)
        
        # ONU ID es lo que queda
        onu_id = snmp_index & 0xFF  # Asumimos 8 bits por defecto
        
        return slot, port, onu_id
    
    def _validate_ranges(self, slot, port, onu_id) -> bool:
        """Valida que los valores estén en rangos esperados"""
        if slot is not None and (slot < 0 or slot > self.slot_max):
            return False
        if port is not None and (port < 0 or port > self.port_max):
            return False
        if onu_id is not None and (onu_id < 0 or onu_id > self.onu_max):
            return False
        return True
    
    def get_normalized_id(self, slot, port, logical) -> str:
        """Genera el ID normalizado usando el formato configurado"""
        try:
            return self.normalized_format.format(
                slot=slot if slot is not None else '?',
                port=port if port is not None else '?',
                logical=logical if logical is not None else '?'
            )
        except KeyError as e:
            import logging
            logging.getLogger(__name__).error(f"❌ Error en formato normalizado: {e}")
            return f"{slot}/{port}"
    
    def generate_raw_index_key(self, slot: int, port: int, logical: int) -> str:
        """
        FUNCIÓN INVERSA: Genera el raw_index_key desde slot/port/logical.
        
        Args:
            slot: Número de slot
            port: Número de puerto
            logical: Número de ONU lógico
        
        Returns:
            str: raw_index_key en formato SNMP (ej: "4194312448.2" o "268566784")
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 1. Calcular ONU ID (considerando offset)
        onu_id = logical - self.onu_offset if self.onu_offset else logical
        
        # 2. Calcular el índice SNMP según el modo
        if self.calculation_mode == 'linear':
            snmp_index = self._generate_linear(slot, port, onu_id)
        elif self.calculation_mode == 'bitshift':
            snmp_index = self._generate_bitshift(slot, port, onu_id)
        else:
            logger.error(f"❌ Modo de cálculo desconocido: {self.calculation_mode}")
            return None
        
        # 3. Formatear según si usa notación con punto
        if self.has_dot_notation:
            # Si dot_is_onu_number, el punto contiene el logical
            onu_number = logical if self.dot_is_onu_number else onu_id
            return f"{snmp_index}.{onu_number}"
        else:
            return str(snmp_index)
    
    def _generate_linear(self, slot: int, port: int, onu_id: int) -> int:
        """Genera índice SNMP usando modo lineal (inverso de _calculate_linear)"""
        snmp_index = self.base_index
        snmp_index += slot * self.step_slot
        snmp_index += port * self.step_port
        snmp_index += onu_id
        return snmp_index
    
    def _generate_bitshift(self, slot: int, port: int, onu_id: int) -> int:
        """Genera índice SNMP usando modo bitshift (inverso de _calculate_bitshift)"""
        snmp_index = 0
        snmp_index |= (slot << self.shift_slot_bits)
        snmp_index |= (port << self.shift_port_bits)
        snmp_index |= onu_id
        return snmp_index