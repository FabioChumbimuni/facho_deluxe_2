"""
Serializers para la API REST de Facho Deluxe v2
"""
from rest_framework import serializers
from django.contrib.auth.models import User

# Importar modelos
from hosts.models import OLT
from brands.models import Brand
from olt_models.models import OLTModel
from snmp_jobs.models import SnmpJob
from executions.models import Execution
from discovery.models import OnuIndexMap, OnuStateLookup, OnuInventory
from oids.models import OID
from snmp_formulas.models import IndexFormula
from odf_management.models import ODF, ODFHilos, ZabbixPortData
from personal.models import Personal, Area
from zabbix_config.models import ZabbixConfiguration


# ============================================================================
# SERIALIZERS DE AUTENTICACIÓN
# ============================================================================

class UserSerializer(serializers.ModelSerializer):
    """Serializer para usuarios"""
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 
                  'is_staff', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined']


# ============================================================================
# SERIALIZERS DE HOSTS Y BRANDS
# ============================================================================

class BrandSerializer(serializers.ModelSerializer):
    """Serializer para marcas de equipos"""
    
    class Meta:
        model = Brand
        fields = ['id', 'nombre']


class OLTModelSerializer(serializers.ModelSerializer):
    """Serializer para modelos de OLT"""
    
    class Meta:
        model = OLTModel
        fields = ['id', 'marca', 'nombre', 'descripcion']


class OLTSerializer(serializers.ModelSerializer):
    """Serializer para OLTs"""
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True)
    modelo_nombre = serializers.SerializerMethodField()
    
    class Meta:
        model = OLT
        fields = ['id', 'abreviatura', 'marca', 'marca_nombre', 'modelo', 
                  'modelo_nombre', 'ip_address', 'descripcion', 'habilitar_olt', 
                  'comunidad']
    
    def get_modelo_nombre(self, obj):
        """Retorna el nombre del modelo formateado"""
        return str(obj.modelo) if obj.modelo else None
        
    def to_representation(self, instance):
        """Personalizar la representación del OLT"""
        data = super().to_representation(instance)
        # Ocultar la comunidad SNMP por seguridad (mostrar solo si está autenticado como staff)
        request = self.context.get('request')
        if request and not (request.user and request.user.is_staff):
            data['comunidad'] = '***'
        return data


class OLTListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listado de OLTs"""
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True)
    estado = serializers.SerializerMethodField()
    
    class Meta:
        model = OLT
        fields = ['id', 'abreviatura', 'marca_nombre', 'ip_address', 
                  'habilitar_olt', 'estado']
    
    def get_estado(self, obj):
        """Obtener el estado actual de la OLT"""
        return 'Activo' if obj.habilitar_olt else 'Inactivo'


# ============================================================================
# SERIALIZERS DE SNMP JOBS Y EJECUCIONES
# ============================================================================

class SNMPJobSerializer(serializers.ModelSerializer):
    """Serializer para trabajos SNMP"""
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True)
    job_type_display = serializers.CharField(source='get_job_type_display', read_only=True)
    
    class Meta:
        model = SnmpJob
        fields = ['id', 'nombre', 'descripcion', 'marca', 'marca_nombre',
                  'job_type', 'job_type_display', 'interval_raw', 'interval_seconds',
                  'cron_expr', 'enabled', 'max_retries', 'retry_delay_seconds',
                  'next_run_at', 'last_run_at', 'run_options']
        read_only_fields = ['next_run_at', 'last_run_at']


class ExecutionSerializer(serializers.ModelSerializer):
    """Serializer para ejecuciones"""
    job_nombre = serializers.CharField(source='snmp_job.nombre', read_only=True, allow_null=True)
    olt_nombre = serializers.CharField(source='olt.abreviatura', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    duracion_segundos = serializers.SerializerMethodField()
    
    class Meta:
        model = Execution
        fields = ['id', 'snmp_job', 'job_nombre', 'olt', 'olt_nombre', 
                  'status', 'status_display', 'started_at', 'finished_at', 
                  'duration_ms', 'duracion_segundos', 'attempt',
                  'result_summary', 'error_message', 'created_at']
        read_only_fields = ['started_at', 'finished_at', 'duration_ms', 'created_at']
    
    def get_duracion_segundos(self, obj):
        """Calcular la duración en segundos"""
        if obj.duration_ms:
            return round(obj.duration_ms / 1000, 2)
        return None


# ============================================================================
# SERIALIZERS DE DISCOVERY
# ============================================================================

class OnuIndexMapSerializer(serializers.ModelSerializer):
    """Serializer para mapeo de índices de ONUs"""
    olt_nombre = serializers.CharField(source='olt.abreviatura', read_only=True)
    odf_hilo_info = serializers.SerializerMethodField()
    tiene_status = serializers.SerializerMethodField()
    tiene_inventory = serializers.SerializerMethodField()
    
    class Meta:
        model = OnuIndexMap
        fields = ['id', 'olt', 'olt_nombre', 'raw_index_key', 'slot', 'port', 
                  'logical', 'normalized_id', 'marca_formula', 'odf_hilo',
                  'odf_hilo_info', 'tiene_status', 'tiene_inventory',
                  'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
    
    def get_odf_hilo_info(self, obj):
        """Obtener información del hilo ODF si existe"""
        if obj.odf_hilo:
            return {
                'id': obj.odf_hilo.id,
                'odf': obj.odf_hilo.odf.numero_odf if obj.odf_hilo.odf else None,
                'hilo': obj.odf_hilo.numero_hilo,
                'estado': obj.odf_hilo.estado
            }
        return None
    
    def get_tiene_status(self, obj):
        """Verificar si tiene información de estado"""
        return hasattr(obj, 'status')
    
    def get_tiene_inventory(self, obj):
        """Verificar si tiene información de inventario"""
        return hasattr(obj, 'onuinventory')


class OnuStateLookupSerializer(serializers.ModelSerializer):
    """Serializer para estados de ONUs"""
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True, allow_null=True)
    
    class Meta:
        model = OnuStateLookup
        fields = ['id', 'value', 'label', 'description', 'marca', 'marca_nombre']


class OnuInventorySerializer(serializers.ModelSerializer):
    """Serializer principal para inventario de ONUs (OnuInventory)"""
    from discovery.models import OnuStatus
    
    # Información de la OLT
    olt_nombre = serializers.CharField(source='olt.abreviatura', read_only=True)
    
    # Información del índice (slot, port, logical) - read_only para mostrar
    slot = serializers.IntegerField(source='onu_index.slot', read_only=True, allow_null=True)
    port = serializers.IntegerField(source='onu_index.port', read_only=True, allow_null=True)
    logical = serializers.IntegerField(source='onu_index.logical', read_only=True, allow_null=True)
    normalized_id = serializers.CharField(source='onu_index.normalized_id', read_only=True)
    raw_index_key = serializers.CharField(source='onu_index.raw_index_key', read_only=True)
    
    # Campos para CREAR la ONU (solo escritura)
    slot_input = serializers.IntegerField(write_only=True, required=False,
                                          help_text="Slot para crear la ONU")
    port_input = serializers.IntegerField(write_only=True, required=False,
                                          help_text="Puerto para crear la ONU")
    logical_input = serializers.IntegerField(write_only=True, required=False,
                                             help_text="ONU lógica para crear la ONU")
    raw_index_key_input = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                                 help_text="Índice SNMP raw (opcional si proporciona slot/port/logical)")
    
    # Campo para especificar el estado administrativo al crear/editar (write-only)
    estado_input = serializers.ChoiceField(
        choices=['ACTIVO', 'SUSPENDIDO'],
        write_only=True,
        required=True,
        help_text="Estado administrativo del servicio: ACTIVO o SUSPENDIDO (OBLIGATORIO)"
    )
    
    # Campo para especificar presence al crear/editar (write-only)
    presence_input = serializers.ChoiceField(
        choices=['ENABLED', 'DISABLED'],
        write_only=True,
        required=False,
        default='ENABLED',
        help_text="Presencia física de la ONU: ENABLED (detectada) o DISABLED (no detectada)"
    )
    
    # Información del estado (read-only)
    presence = serializers.SerializerMethodField()  # ENABLED o DISABLED (desde OnuStatus)
    estado = serializers.SerializerMethodField()  # ACTIVO o SUSPENDIDO (desde OnuStatus)
    last_seen_at = serializers.SerializerMethodField()  # Desde OnuStatus
    
    class Meta:
        model = OnuInventory
        fields = [
            'id', 
            # OLT
            'olt', 'olt_nombre',
            # Índice (slot/port/logical) - lectura
            'slot', 'port', 'logical', 'normalized_id', 'raw_index_key',
            # Campos de entrada para crear ONU - escritura
            'slot_input', 'port_input', 'logical_input', 'raw_index_key_input', 'estado_input', 'presence_input',
            # Identificación
            'serial_number', 'mac_address', 'subscriber_id',
            # Configuración
            'plan_onu', 'distancia_onu', 'modelo_onu',
            # SNMP
            'snmp_description', 'snmp_metadata', 'snmp_last_collected_at',
            # Estado (salida)
            'presence', 'estado', 'last_seen_at',
            # Timestamps
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'snmp_last_collected_at']
    
    def validate_snmp_description(self, value):
        """Validar que snmp_description sea proporcionado"""
        if not value or value.strip() == '':
            raise serializers.ValidationError(
                'El campo "snmp_description" es obligatorio. Debe contener el DNI, nombre o código del cliente.'
            )
        return value
    
    def create(self, validated_data):
        """
        Crear ONU con las 3 tablas automáticamente:
        1. OnuIndexMap (usando la fórmula de la OLT)
        2. OnuStatus
        3. OnuInventory
        
        NOTA: Si no proporciona raw_index_key_input, lo generará automáticamente
        desde slot/port/logical usando la fórmula SNMP de la OLT.
        """
        from snmp_formulas.models import IndexFormula
        from discovery.models import OnuStatus
        
        # Extraer campos de entrada (write-only)
        raw_index_key_input = validated_data.pop('raw_index_key_input', None)
        slot_input = validated_data.pop('slot_input', None)
        port_input = validated_data.pop('port_input', None)
        logical_input = validated_data.pop('logical_input', None)
        estado_input = validated_data.pop('estado_input')  # OBLIGATORIO
        presence_input = validated_data.pop('presence_input', 'ENABLED')  # ENABLED por defecto
        
        olt = validated_data.get('olt')
        
        if not olt:
            raise serializers.ValidationError({'olt': 'Se requiere especificar la OLT'})
        
        # 1. Si no proporciona raw_index_key, generarlo automáticamente
        if not raw_index_key_input:
            # Usar los campos _input
            slot = slot_input
            port = port_input
            logical = logical_input
            
            if not all([slot is not None, port is not None, logical is not None]):
                raise serializers.ValidationError({
                    'non_field_errors': 'Se requiere slot, port y logical (o raw_index_key_input) para crear una ONU'
                })
            
            # Buscar la fórmula de esta OLT con prioridad:
            # 1. Marca + Modelo específico
            # 2. Solo Marca (modelo=None)
            # 3. Fórmula universal (marca=None, modelo=None)
            formula = None
            
            # Intento 1: Buscar fórmula específica de marca + modelo
            if olt.modelo:
                formula = IndexFormula.objects.filter(
                    marca=olt.marca,
                    modelo=olt.modelo,
                    activo=True
                ).first()
            
            # Intento 2: Buscar fórmula genérica de la marca (sin modelo específico)
            if not formula and olt.marca:
                formula = IndexFormula.objects.filter(
                    marca=olt.marca,
                    modelo__isnull=True,
                    activo=True
                ).first()
            
            # Intento 3: Buscar fórmula universal (sin marca ni modelo)
            if not formula:
                formula = IndexFormula.objects.filter(
                    marca__isnull=True,
                    modelo__isnull=True,
                    activo=True
                ).first()
            
            if not formula:
                error_msg = f'No se encontró fórmula SNMP activa para '
                if olt.modelo:
                    error_msg += f'{olt.marca.nombre} {olt.modelo.nombre}'
                else:
                    error_msg += f'{olt.marca.nombre}'
                raise serializers.ValidationError({'olt': error_msg})
            
            # Generar raw_index_key usando la fórmula inversa
            raw_index_key_input = formula.generate_raw_index_key(
                slot=int(slot),
                port=int(port),
                logical=int(logical)
            )
            
            if not raw_index_key_input:
                raise serializers.ValidationError({
                    'non_field_errors': f'Error al generar raw_index_key con la fórmula de {formula.nombre}'
                })
        
        # 2. Crear o buscar OnuIndexMap
        onu_index, created = OnuIndexMap.objects.get_or_create(
            olt=olt,
            raw_index_key=raw_index_key_input
        )
        
        # 3. Sincronizar active con presence_input ANTES de crear OnuInventory
        # active debe reflejar presence: ENABLED=true, DISABLED=false
        validated_data['active'] = (presence_input == 'ENABLED')
        
        # 4. Crear OnuInventory
        onu_inventory = OnuInventory.objects.create(
            onu_index=onu_index,
            **validated_data
        )
        
        # 5. Crear OnuStatus si no existe
        if not hasattr(onu_index, 'status'):
            # Usar presence_input (puede ser ENABLED o DISABLED según lo especificado)
            initial_presence = presence_input
            
            # Determinar estado según estado_input
            initial_state_label = estado_input  # 'ACTIVO' o 'SUSPENDIDO'
            initial_state_value = 1 if estado_input == 'ACTIVO' else 2
            
            OnuStatus.objects.create(
                onu_index=onu_index,
                olt=olt,
                presence=initial_presence,
                last_state_label=initial_state_label,
                last_state_value=initial_state_value
            )
        
        return onu_inventory
    
    def update(self, instance, validated_data):
        """Actualizar ONU - solo campos editables"""
        # Remover campos de índice si vienen (no se pueden editar)
        validated_data.pop('raw_index_key_input', None)
        validated_data.pop('slot_input', None)
        validated_data.pop('port_input', None)
        validated_data.pop('logical_input', None)
        
        # Extraer campos de entrada si se están actualizando
        estado_input = validated_data.pop('estado_input', None)
        presence_input = validated_data.pop('presence_input', None)
        
        # SINCRONIZAR: Si se proporcionó presence_input, actualizar active y presence
        if presence_input:
            # Sincronizar active con presence_input
            validated_data['active'] = (presence_input == 'ENABLED')
            
            # Actualizar presence en OnuStatus
            if hasattr(instance.onu_index, 'status'):
                status = instance.onu_index.status
                status.presence = presence_input
                status.save(update_fields=['presence', 'updated_at'])
        
        # Verificar si se está actualizando 'active' directamente (sin presence_input)
        elif 'active' in validated_data:
            new_active_value = validated_data.get('active')
            # Sincronizar presence con active
            if hasattr(instance.onu_index, 'status'):
                status = instance.onu_index.status
                status.presence = 'ENABLED' if new_active_value else 'DISABLED'
                status.save(update_fields=['presence', 'updated_at'])
        
        # Actualizar campos permitidos
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # ACTUALIZAR ESTADO: Si se proporcionó estado_input
        if estado_input and hasattr(instance.onu_index, 'status'):
            status = instance.onu_index.status
            status.last_state_label = estado_input
            status.last_state_value = 1 if estado_input == 'ACTIVO' else 2
            status.save(update_fields=['last_state_label', 'last_state_value', 'updated_at'])
        
        return instance
    
    def get_presence(self, obj):
        """Obtener el presence desde OnuStatus"""
        if hasattr(obj, 'onu_index') and hasattr(obj.onu_index, 'status'):
            return obj.onu_index.status.presence
        return None
    
    def get_estado(self, obj):
        """Obtener estado administrativo desde OnuStatus (ACTIVO o SUSPENDIDO)"""
        if hasattr(obj, 'onu_index') and hasattr(obj.onu_index, 'status'):
            estado = obj.onu_index.status.last_state_label
            # Si el estado es None (ONUs antiguas), asignar ACTIVO por defecto
            return estado if estado else "ACTIVO"
        return "ACTIVO"
    
    def get_last_seen_at(self, obj):
        """Obtener último visto desde OnuStatus"""
        if hasattr(obj, 'onu_index') and hasattr(obj.onu_index, 'status'):
            return obj.onu_index.status.last_seen_at
        return None


class OnuInventoryListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listado de ONUs"""
    olt_nombre = serializers.CharField(source='olt.abreviatura', read_only=True)
    slot = serializers.IntegerField(source='onu_index.slot', read_only=True, allow_null=True)
    port = serializers.IntegerField(source='onu_index.port', read_only=True, allow_null=True)
    logical = serializers.IntegerField(source='onu_index.logical', read_only=True, allow_null=True)
    presence = serializers.SerializerMethodField()
    estado = serializers.SerializerMethodField()
    
    class Meta:
        model = OnuInventory
        fields = ['id', 'olt_nombre', 'slot', 'port', 'logical', 
                  'serial_number', 'plan_onu', 'modelo_onu', 'distancia_onu',
                  'snmp_description', 'presence', 'estado']
    
    def get_presence(self, obj):
        """Obtener el presence desde OnuStatus"""
        if hasattr(obj, 'onu_index') and hasattr(obj.onu_index, 'status'):
            return obj.onu_index.status.presence
        return None
    
    def get_estado(self, obj):
        """Obtener estado administrativo desde OnuStatus (ACTIVO o SUSPENDIDO)"""
        if hasattr(obj, 'onu_index') and hasattr(obj.onu_index, 'status'):
            estado = obj.onu_index.status.last_state_label
            return estado if estado else "ACTIVO"
        return "ACTIVO"


# ============================================================================
# SERIALIZERS DE OIDS Y FORMULAS
# ============================================================================

class OIDSerializer(serializers.ModelSerializer):
    """Serializer para OIDs SNMP"""
    espacio_display = serializers.CharField(source='get_espacio_display', read_only=True)
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True)
    modelo_nombre = serializers.SerializerMethodField()
    
    class Meta:
        model = OID
        fields = ['id', 'nombre', 'oid', 'marca', 'marca_nombre', 'modelo', 'modelo_nombre',
                  'espacio', 'espacio_display', 'target_field', 'keep_previous_value', 'format_mac']
    
    def get_modelo_nombre(self, obj):
        """Retorna el nombre del modelo o None si no existe"""
        return str(obj.modelo) if obj.modelo else None


class IndexFormulaSerializer(serializers.ModelSerializer):
    """Serializer para fórmulas de índices"""
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True)
    modelo_nombre = serializers.SerializerMethodField()
    
    class Meta:
        model = IndexFormula
        fields = ['id', 'nombre', 'marca', 'marca_nombre', 'modelo', 'modelo_nombre',
                  'descripcion', 'activo', 'normalized_format', 'calculation_mode',
                  'base_index', 'slot_max', 'port_max', 'onu_max', 
                  'created_at', 'updated_at']
    
    def get_modelo_nombre(self, obj):
        """Retorna el nombre del modelo formateado"""
        return str(obj.modelo) if obj.modelo else None


# ============================================================================
# SERIALIZERS DE ODF
# ============================================================================

class ODFSerializer(serializers.ModelSerializer):
    """Serializer para ODFs"""
    olt_nombre = serializers.CharField(source='olt.abreviatura', read_only=True, allow_null=True)
    total_hilos = serializers.SerializerMethodField()
    hilos_ocupados = serializers.SerializerMethodField()
    hilos_disponibles = serializers.SerializerMethodField()
    
    class Meta:
        model = ODF
        fields = ['id', 'numero_odf', 'nombre_troncal', 'descripcion', 'olt', 
                  'olt_nombre', 'created_at', 'updated_at',
                  'total_hilos', 'hilos_ocupados', 'hilos_disponibles']
        read_only_fields = ['created_at', 'updated_at']
    
    def get_total_hilos(self, obj):
        """Obtener total de hilos"""
        return obj.odfhilos_set.count()
    
    def get_hilos_ocupados(self, obj):
        """Obtener hilos ocupados"""
        return obj.odfhilos_set.filter(estado='ocupado').count()
    
    def get_hilos_disponibles(self, obj):
        """Obtener hilos disponibles"""
        return obj.odfhilos_set.filter(estado='disponible').count()


class ODFHilosSerializer(serializers.ModelSerializer):
    """Serializer para hilos de ODF"""
    odf_nombre = serializers.CharField(source='odf.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    
    class Meta:
        model = ODFHilos
        fields = ['id', 'odf', 'odf_nombre', 'slot', 'port', 'hilo_numero', 
                  'vlan', 'estado', 'estado_display', 'descripcion_manual', 
                  'origen', 'en_zabbix', 'operativo_noc',
                  'fecha_habilitacion', 'hora_habilitacion', 
                  'personal_proyectos', 'personal_noc', 'tecnico_habilitador',
                  'created_at', 'updated_at']
        read_only_fields = ['estado', 'origen', 'en_zabbix', 'created_at', 'updated_at']  # Gestionados por scripts


class ZabbixPortDataSerializer(serializers.ModelSerializer):
    """Serializer para datos de puertos de Zabbix"""
    olt_nombre = serializers.CharField(source='olt.abreviatura', read_only=True, allow_null=True)
    
    class Meta:
        model = ZabbixPortData
        fields = ['id', 'olt', 'olt_nombre', 'snmp_index', 'slot', 'port', 
                  'descripcion_zabbix', 'interface_name', 'disponible', 
                  'estado_administrativo', 'operativo_noc', 
                  'last_sync', 'created_at']
        read_only_fields = ['last_sync', 'created_at']


# ============================================================================
# SERIALIZERS DE PERSONAL
# ============================================================================

class AreaSerializer(serializers.ModelSerializer):
    """Serializer para áreas"""
    
    class Meta:
        model = Area
        fields = ['id', 'nombre', 'descripcion']


class PersonalSerializer(serializers.ModelSerializer):
    """Serializer para personal"""
    area_nombre = serializers.CharField(source='area.nombre', read_only=True, allow_null=True)
    
    class Meta:
        model = Personal
        fields = ['id', 'nombres', 'apellidos', 'documento_identidad', 'email', 
                  'telefono', 'codigo_empleado', 'area', 'area_nombre', 
                  'cargo', 'estado', 'fecha_ingreso', 'observaciones',
                  'created_at', 'updated_at']


# ============================================================================
# SERIALIZERS DE CONFIGURACIÓN
# ============================================================================

class ZabbixConfigSerializer(serializers.ModelSerializer):
    """Serializer para configuración de Zabbix"""
    estado = serializers.SerializerMethodField()
    
    class Meta:
        model = ZabbixConfiguration
        fields = ['id', 'nombre', 'zabbix_url', 'zabbix_token', 'item_key',
                  'activa', 'timeout', 'verificar_ssl', 'descripcion',
                  'created_at', 'updated_at', 'estado']
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'zabbix_token': {'write_only': True}  # No mostrar el token en las respuestas
        }
    
    def get_estado(self, obj):
        """Obtener el estado de la configuración"""
        return "✅ ACTIVA" if obj.activa else "⏸️ Inactiva"


# ============================================================================
# SERIALIZERS PARA ESTADÍSTICAS
# ============================================================================

class DashboardStatsSerializer(serializers.Serializer):
    """Serializer para estadísticas del dashboard"""
    total_olts = serializers.IntegerField()
    olts_activas = serializers.IntegerField()
    total_jobs = serializers.IntegerField()
    jobs_activos = serializers.IntegerField()
    total_ejecuciones_hoy = serializers.IntegerField()
    ejecuciones_exitosas_hoy = serializers.IntegerField()
    ejecuciones_fallidas_hoy = serializers.IntegerField()
    total_onus = serializers.IntegerField()
    total_odfs = serializers.IntegerField()
    hilos_ocupados = serializers.IntegerField()
    hilos_disponibles = serializers.IntegerField()

