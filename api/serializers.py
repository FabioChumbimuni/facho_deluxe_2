"""
Serializers para la API REST de Facho Deluxe v2
"""
from rest_framework import serializers
from django.contrib.auth.models import User

# Importar modelos
from hosts.models import OLT
from brands.models import Brand
from olt_models.models import OLTModel
from snmp_jobs.models import SnmpJob, WorkflowTemplate, WorkflowTemplateNode, OLTWorkflow, WorkflowNode
from executions.models import Execution
from discovery.models import OnuIndexMap, OnuStateLookup, OnuInventory
from oids.models import OID
from snmp_formulas.models import IndexFormula
from odf_management.models import ODF, ODFHilos, ZabbixPortData, ZabbixCollectionSchedule, ZabbixCollectionOLT
from personal.models import Personal, Area
from zabbix_config.models import ZabbixConfiguration
from configuracion_avanzada.models import ConfiguracionSistema, ConfiguracionSNMP


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
        fields = ['id', 'nombre', 'descripcion']


class OLTModelSerializer(serializers.ModelSerializer):
    """Serializer para modelos de OLT"""
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True)
    
    class Meta:
        model = OLTModel
        fields = ['id', 'marca', 'marca_nombre', 'nombre', 'descripcion', 'tipo_olt', 
                  'activo', 'capacidad_puertos', 'capacidad_onus', 'slots_disponibles',
                  'created_at', 'updated_at']


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
        if obj.modelo:
            return obj.modelo.nombre
        return None
        
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
    modelo_nombre = serializers.SerializerMethodField()
    estado = serializers.SerializerMethodField()
    
    class Meta:
        model = OLT
        fields = ['id', 'abreviatura', 'marca', 'marca_nombre', 'modelo', 
                  'modelo_nombre', 'ip_address', 'habilitar_olt', 'estado']
    
    def get_modelo_nombre(self, obj):
        """Retorna el nombre del modelo formateado"""
        if obj.modelo:
            return obj.modelo.nombre
        return None
    
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
    olt_ip = serializers.CharField(source='olt.ip_address', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    duracion_segundos = serializers.SerializerMethodField()
    workflow_node_nombre = serializers.SerializerMethodField()
    workflow_nombre = serializers.SerializerMethodField()
    template_nombre = serializers.SerializerMethodField()
    
    class Meta:
        model = Execution
        fields = ['id', 'snmp_job', 'job_nombre', 'olt', 'olt_nombre', 'olt_ip',
                  'workflow_node', 'workflow_node_nombre', 'workflow_nombre', 'template_nombre',
                  'status', 'status_display', 'started_at', 'finished_at', 
                  'duration_ms', 'duracion_segundos', 'attempt',
                  'result_summary', 'error_message', 'created_at']
        read_only_fields = ['started_at', 'finished_at', 'duration_ms', 'created_at']
    
    def get_duracion_segundos(self, obj):
        """Calcular la duración en segundos"""
        if obj.duration_ms:
            return round(obj.duration_ms / 1000, 2)
        return None
    
    def get_workflow_node_nombre(self, obj):
        """Obtener nombre del nodo de workflow"""
        if obj.workflow_node:
            return obj.workflow_node.name
        return None
    
    def get_workflow_nombre(self, obj):
        """Obtener nombre del workflow"""
        if obj.workflow_node and obj.workflow_node.workflow:
            return obj.workflow_node.workflow.name
        return None
    
    def get_template_nombre(self, obj):
        """Obtener nombre de la plantilla si el nodo proviene de una"""
        if obj.workflow_node and obj.workflow_node.template_node:
            return obj.workflow_node.template_node.template.name
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
    snmpindexonu = serializers.CharField(source='onu_index.raw_index_key', read_only=True, help_text="Índice SNMP de la ONU (alias de raw_index_key)")
    
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
            'slot', 'port', 'logical', 'normalized_id', 'raw_index_key', 'snmpindexonu',
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
        from django.utils import timezone
        
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
        
        # 5. Crear OnuStatus si no existe (GARANTIZADO)
        try:
            # Intentar acceder al status
            _ = onu_index.status
        except OnuStatus.DoesNotExist:
            # No existe, crearlo
            initial_presence = presence_input
            initial_state_label = estado_input  # 'ACTIVO' o 'SUSPENDIDO'
            initial_state_value = 1 if estado_input == 'ACTIVO' else 2
            
            OnuStatus.objects.create(
                onu_index=onu_index,
                olt=olt,
                presence=initial_presence,
                last_state_label=initial_state_label,
                last_state_value=initial_state_value,
                consecutive_misses=0,
                last_seen_at=timezone.now() if initial_presence == 'ENABLED' else None
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
    snmpindexonu = serializers.CharField(source='onu_index.raw_index_key', read_only=True, help_text="Índice SNMP de la ONU")
    presence = serializers.SerializerMethodField()
    estado = serializers.SerializerMethodField()
    
    class Meta:
        model = OnuInventory
        fields = ['id', 'olt_nombre', 'slot', 'port', 'logical', 'snmpindexonu',
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
    
    def validate(self, data):
        """Validar y asignar modelo genérico si no se proporciona"""
        from olt_models.models import OLTModel
        from brands.models import Brand
        
        marca = data.get('marca')
        modelo = data.get('modelo')
        
        # Si no se proporciona modelo, buscar el modelo genérico
        if not modelo and marca:
            try:
                # Obtener la instancia de marca si viene como ID
                if isinstance(marca, int):
                    marca_instance = Brand.objects.get(id=marca)
                else:
                    marca_instance = marca
                
                # Siempre usar el modelo genérico de la marca genérica
                # (el modelo genérico puede usarse con cualquier marca)
                generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                generic_model = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
                data['modelo'] = generic_model
                
            except (Brand.DoesNotExist, OLTModel.DoesNotExist) as e:
                # Si no existe modelo genérico, intentar usar el primero disponible de la marca
                try:
                    if isinstance(marca, int):
                        marca_instance = Brand.objects.get(id=marca)
                    else:
                        marca_instance = marca
                    
                    modelo_default = OLTModel.objects.filter(marca=marca_instance).first()
                    if modelo_default:
                        data['modelo'] = modelo_default
                    else:
                        raise serializers.ValidationError({
                            'modelo': 'No se pudo encontrar un modelo por defecto. Por favor selecciona un modelo específico o asegúrate de que exista el modelo "Genérico" de la marca "🌐 Genérico".'
                        })
                except Brand.DoesNotExist:
                    raise serializers.ValidationError({
                        'marca': 'La marca especificada no existe.'
                    })
        
        return data
    
    def create(self, validated_data):
        """Crear OID con validación de modelo"""
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Actualizar OID con validación de modelo"""
        return super().update(instance, validated_data)


class IndexFormulaSerializer(serializers.ModelSerializer):
    """Serializer para fórmulas de índices"""
    marca_nombre = serializers.CharField(source='marca.nombre', read_only=True)
    modelo_nombre = serializers.SerializerMethodField()
    
    class Meta:
        model = IndexFormula
        fields = ['id', 'nombre', 'marca', 'marca_nombre', 'modelo', 'modelo_nombre',
                  'descripcion', 'activo', 'normalized_format', 'calculation_mode',
                  # Parámetros modo lineal
                  'base_index', 'step_slot', 'step_port',
                  # Parámetros modo bitshift
                  'shift_slot_bits', 'shift_port_bits', 'mask_slot', 'mask_port',
                  # Parámetros adicionales
                  'onu_offset', 'has_dot_notation', 'dot_is_onu_number',
                  # Límites y validación
                  'slot_max', 'port_max', 'onu_max',
                  # Metadata
                  'created_at', 'updated_at']
    
    def get_modelo_nombre(self, obj):
        """Retorna el nombre del modelo formateado"""
        if obj.modelo:
            return obj.modelo.nombre
        return None


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
    odf_nombre = serializers.CharField(source='odf.nombre_troncal', read_only=True)
    odf_olt = serializers.CharField(source='odf.olt.abreviatura', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    zabbix_port_estado_administrativo = serializers.IntegerField(
        source='zabbix_port.estado_administrativo', 
        read_only=True, 
        allow_null=True
    )
    en_zabbix_display = serializers.SerializerMethodField()
    personal_proyectos_nombre = serializers.CharField(
        source='personal_proyectos.nombre_completo', 
        read_only=True, 
        allow_null=True
    )
    personal_noc_nombre = serializers.CharField(
        source='personal_noc.nombre_completo', 
        read_only=True, 
        allow_null=True
    )
    tecnico_habilitador_nombre = serializers.CharField(
        source='tecnico_habilitador.nombre_completo', 
        read_only=True, 
        allow_null=True
    )
    
    class Meta:
        model = ODFHilos
        fields = ['id', 'odf', 'odf_nombre', 'odf_olt', 'slot', 'port', 'hilo_numero', 
                  'vlan', 'estado', 'estado_display', 'descripcion_manual', 
                  'origen', 'en_zabbix', 'en_zabbix_display', 'operativo_noc',
                  'zabbix_port_estado_administrativo',
                  'fecha_habilitacion', 'hora_habilitacion', 
                  'personal_proyectos', 'personal_proyectos_nombre',
                  'personal_noc', 'personal_noc_nombre',
                  'tecnico_habilitador', 'tecnico_habilitador_nombre',
                  'created_at', 'updated_at']
        read_only_fields = ['estado', 'origen', 'en_zabbix', 'created_at', 'updated_at']  # Gestionados por scripts
    
    def get_en_zabbix_display(self, obj):
        """Muestra el estado en Zabbix igual que en el admin"""
        if not obj.en_zabbix:
            return {
                'text': 'No presente en Zabbix',
                'color': 'gray',
                'estado': 'no_presente'
            }
        
        # Si está en Zabbix, verificar estado administrativo del puerto asociado
        if obj.zabbix_port and obj.zabbix_port.estado_administrativo is not None:
            if obj.zabbix_port.estado_administrativo == 1:
                return {
                    'text': 'ACTIVO',
                    'color': 'green',
                    'estado': 'activo'
                }
            elif obj.zabbix_port.estado_administrativo == 2:
                return {
                    'text': 'NO ACTIVO',
                    'color': 'orange',
                    'estado': 'no_activo'
                }
        
        # Si está en Zabbix pero no tiene estado administrativo
        return {
            'text': 'Error 1',
            'color': 'red',
            'estado': 'error'
        }


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
    
    def validate(self, data):
        """Validar que olt y snmp_index sean únicos juntos"""
        if self.instance is None:  # Creando nuevo
            if 'olt' in data and 'snmp_index' in data:
                if ZabbixPortData.objects.filter(olt=data['olt'], snmp_index=data['snmp_index']).exists():
                    raise serializers.ValidationError({
                        'snmp_index': 'Ya existe un puerto con este SNMP index para esta OLT.'
                    })
        else:  # Actualizando
            if 'olt' in data or 'snmp_index' in data:
                olt = data.get('olt', self.instance.olt)
                snmp_index = data.get('snmp_index', self.instance.snmp_index)
                if ZabbixPortData.objects.filter(olt=olt, snmp_index=snmp_index).exclude(pk=self.instance.pk).exists():
                    raise serializers.ValidationError({
                        'snmp_index': 'Ya existe un puerto con este SNMP index para esta OLT.'
                    })
        return data


class ZabbixCollectionScheduleSerializer(serializers.ModelSerializer):
    """Serializer para programaciones de recolección Zabbix"""
    intervalo_display = serializers.CharField(source='get_intervalo_minutos_display', read_only=True)
    olts_asociadas_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = ZabbixCollectionSchedule
        fields = ['id', 'nombre', 'intervalo_minutos', 'intervalo_display', 'habilitado',
                  'proxima_ejecucion', 'ultima_ejecucion', 'olts_asociadas_count',
                  'created_at', 'updated_at']
        read_only_fields = ['proxima_ejecucion', 'ultima_ejecucion', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """Crear programación y calcular próxima ejecución si está habilitada"""
        instance = super().create(validated_data)
        if instance.habilitado:
            instance.calcular_proxima_ejecucion(primera_vez=True)
            instance.save()
        return instance
    
    def update(self, instance, validated_data):
        """Actualizar programación y recalcular próxima ejecución si cambió el intervalo"""
        intervalo_cambio = 'intervalo_minutos' in validated_data and \
                          validated_data['intervalo_minutos'] != instance.intervalo_minutos
        
        instance = super().update(instance, validated_data)
        
        # Si cambió el intervalo y está habilitada, recalcular próxima ejecución
        if intervalo_cambio and instance.habilitado:
            instance.calcular_proxima_ejecucion(primera_vez=False)
            instance.save()
        
        return instance


class ZabbixCollectionOLTSerializer(serializers.ModelSerializer):
    """Serializer para OLTs en programación de recolección"""
    schedule_nombre = serializers.CharField(source='schedule.nombre', read_only=True)
    olt_nombre = serializers.CharField(source='olt.abreviatura', read_only=True)
    ultimo_estado_display = serializers.CharField(source='get_ultimo_estado_display', read_only=True)
    
    class Meta:
        model = ZabbixCollectionOLT
        fields = ['id', 'schedule', 'schedule_nombre', 'olt', 'olt_nombre', 'habilitado',
                  'ultima_recoleccion', 'ultimo_estado', 'ultimo_estado_display', 'ultimo_error',
                  'created_at']
        read_only_fields = ['ultima_recoleccion', 'ultimo_estado', 'ultimo_error', 'created_at']
    
    def validate(self, data):
        """Validar que schedule y olt sean únicos juntos"""
        if self.instance is None:  # Creando nuevo
            if 'schedule' in data and 'olt' in data:
                if ZabbixCollectionOLT.objects.filter(schedule=data['schedule'], olt=data['olt']).exists():
                    raise serializers.ValidationError({
                        'olt': 'Esta OLT ya está asociada a esta programación.'
                    })
        else:  # Actualizando
            if 'schedule' in data or 'olt' in data:
                schedule = data.get('schedule', self.instance.schedule)
                olt = data.get('olt', self.instance.olt)
                if ZabbixCollectionOLT.objects.filter(schedule=schedule, olt=olt).exclude(pk=self.instance.pk).exists():
                    raise serializers.ValidationError({
                        'olt': 'Esta OLT ya está asociada a esta programación.'
                    })
        return data


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


# ============================================================================
# SERIALIZERS DE WORKFLOWS
# ============================================================================

class WorkflowTemplateNodeSerializer(serializers.ModelSerializer):
    """Serializer para nodos de plantilla de workflow"""
    oid_nombre = serializers.CharField(source='oid.nombre', read_only=True)
    oid_oid = serializers.CharField(source='oid.oid', read_only=True)
    oid_espacio = serializers.CharField(source='oid.espacio', read_only=True)
    oid_espacio_display = serializers.CharField(source='oid.get_espacio_display', read_only=True)
    oid_id = serializers.IntegerField(write_only=True, required=False, allow_null=True, default=None)
    # Campo adicional para leer el ID del OID (para que el frontend pueda obtenerlo)
    oid_read_id = serializers.IntegerField(source='oid.id', read_only=True, allow_null=True)
    master_node_id = serializers.IntegerField(source='master_node.id', read_only=True, allow_null=True)
    master_node_name = serializers.CharField(source='master_node.name', read_only=True, allow_null=True)
    chain_nodes_count = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowTemplateNode
        fields = ['id', 'template', 'key', 'name', 'oid', 'oid_id', 'oid_read_id', 'oid_nombre', 'oid_oid',
                  'oid_espacio', 'oid_espacio_display',
                  'interval_seconds', 'priority', 'parameters', 'retry_policy', 
                  'enabled', 'position_x', 'position_y', 'color_override', 
                  'icon_override', 'metadata', 'is_chain_node', 'master_node', 'master_node_id', 
                  'master_node_name', 'chain_nodes_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'oid': {'required': False, 'allow_null': True},
            'master_node': {'required': False, 'allow_null': True}
        }
    
    def get_chain_nodes_count(self, obj):
        """Obtener el número de nodos en la cadena"""
        if obj.is_chain_node and obj.master_node:
            return obj.master_node.chain_nodes.count()
        elif not obj.is_chain_node:
            return obj.chain_nodes.count()
        return 0
    
    def create(self, validated_data):
        """Crear nodo con manejo de oid_id y validación de espacio único"""
        import logging
        from snmp_jobs.models import WorkflowTemplateNode
        logger = logging.getLogger(__name__)
        
        # Obtener oid_id de validated_data o initial_data
        oid_id = validated_data.pop('oid_id', None)
        if oid_id is None and hasattr(self, 'initial_data') and 'oid_id' in self.initial_data:
            oid_id = self.initial_data.get('oid_id')
        
        logger.info(f"🔍 WorkflowTemplateNodeSerializer.create - oid_id recibido: {oid_id} (tipo: {type(oid_id)})")
        logger.info(f"📝 initial_data: {getattr(self, 'initial_data', {})}")
        
        # Siempre procesar oid_id si viene en los datos
        from oids.models import OID
        oid_instance = None
        try:
            # Convertir a int si viene como string
            if isinstance(oid_id, str):
                oid_id = int(oid_id) if oid_id.strip() else None
            
            # Si oid_id tiene un valor válido (no None y no 0), obtener el OID
            if oid_id is not None and oid_id != 0:
                oid_instance = OID.objects.get(id=oid_id)
                validated_data['oid'] = oid_instance
                logger.info(f"✅ OID asignado: {validated_data['oid'].id} - {validated_data['oid'].nombre}")
            else:
                # Si es None o 0, establecer oid como None explícitamente
                validated_data['oid'] = None
                logger.info("⚠️ OID establecido como None (opcional)")
        except (OID.DoesNotExist, ValueError, TypeError) as e:
            logger.error(f"❌ Error procesando oid_id {oid_id}: {e}")
            if isinstance(e, OID.DoesNotExist):
                raise serializers.ValidationError({'oid_id': f'OID con id {oid_id} no existe'})
            else:
                raise serializers.ValidationError({'oid_id': f'Valor inválido para oid_id: {oid_id}'})
        
        # Validar que no haya otro nodo con el mismo espacio en la plantilla
        template = validated_data.get('template')
        if template and oid_instance and oid_instance.espacio:
            existing_node = WorkflowTemplateNode.objects.filter(
                template=template,
                oid__espacio=oid_instance.espacio
            ).exclude(id=self.instance.id if hasattr(self, 'instance') and self.instance else None).first()
            
            if existing_node:
                raise serializers.ValidationError({
                    'oid_id': f'Ya existe un nodo con el espacio "{oid_instance.get_espacio_display()}" en esta plantilla. '
                             f'Los espacios deben ser únicos por plantilla.'
                })
        
        # Procesar master_node si viene como ID
        master_node_id = None
        if hasattr(self, 'initial_data') and 'master_node' in self.initial_data:
            master_node_id = self.initial_data.get('master_node')
        elif 'master_node' in validated_data:
            master_node_id = validated_data.get('master_node')
        
        if master_node_id is not None:
            try:
                if isinstance(master_node_id, str):
                    master_node_id = int(master_node_id) if master_node_id.strip() else None
                
                if master_node_id is not None and master_node_id != 0:
                    template = validated_data.get('template')
                    if template:
                        master_node_instance = WorkflowTemplateNode.objects.get(id=master_node_id, template=template)
                        validated_data['master_node'] = master_node_instance
                        logger.info(f"✅ Master node asignado: {master_node_instance.id} - {master_node_instance.name}")
                else:
                    validated_data['master_node'] = None
            except (WorkflowTemplateNode.DoesNotExist, ValueError, TypeError) as e:
                logger.error(f"❌ Error procesando master_node {master_node_id}: {e}")
                if isinstance(e, WorkflowTemplateNode.DoesNotExist):
                    raise serializers.ValidationError({'master_node': f'Nodo master con id {master_node_id} no existe en esta plantilla'})
                else:
                    raise serializers.ValidationError({'master_node': f'Valor inválido para master_node: {master_node_id}'})
        
        # Si está en cadena, no establecer intervalo (se gestiona desde el master)
        if validated_data.get('is_chain_node', False):
            validated_data.pop('interval_seconds', None)
        
        logger.info(f"📝 Datos finales para crear nodo: {list(validated_data.keys())}")
        logger.info(f"📝 OID final: {validated_data.get('oid')}")
        
        # Crear el nodo
        created_instance = super().create(validated_data)
        
        # Sincronizar cambios automáticamente si hay template_id
        template_id = created_instance.template.id if created_instance.template else None
        if template_id:
            try:
                from snmp_jobs.services.workflow_template_service import WorkflowTemplateService
                WorkflowTemplateService.sync_template_changes(template_id)
                logger.info(f"✅ Nodo de plantilla {created_instance.id} creado y sincronizado automáticamente")
            except Exception as e:
                logger.error(f"❌ Error sincronizando cambios de plantilla {template_id}: {e}", exc_info=True)
        
        return created_instance
    
    def update(self, instance, validated_data):
        """Actualizar nodo con manejo de oid_id"""
        import logging
        from snmp_jobs.models import WorkflowTemplateNode
        logger = logging.getLogger(__name__)
        
        # IMPORTANTE: Verificar si oid_id viene en los datos ANTES de hacer pop
        # porque si no viene, no debemos procesarlo (no cambiar el OID existente)
        oid_id = None
        if 'oid_id' in self.initial_data:
            oid_id = validated_data.pop('oid_id', None)
        elif 'oid_id' in validated_data:
            oid_id = validated_data.pop('oid_id', None)
        
        logger.info(f"🔍 WorkflowTemplateNodeSerializer.update - oid_id recibido: {oid_id} (tipo: {type(oid_id)})")
        logger.info(f"📝 Nodo actual: id={instance.id}, oid actual={instance.oid_id if instance.oid else None}")
        logger.info(f"📝 initial_data contiene oid_id: {'oid_id' in self.initial_data}")
        
        # Siempre procesar oid_id si viene en los datos (incluso si es None explícito)
        oid_instance = None
        if 'oid_id' in self.initial_data or oid_id is not None:
            from oids.models import OID
            try:
                # Convertir a int si viene como string
                if isinstance(oid_id, str):
                    oid_id = int(oid_id) if oid_id.strip() else None
                
                # Si oid_id tiene un valor válido (no None y no 0), obtener el OID
                if oid_id is not None and oid_id != 0:
                    oid_instance = OID.objects.get(id=oid_id)
                    validated_data['oid'] = oid_instance
                    logger.info(f"✅ OID actualizado: {validated_data['oid'].id} - {validated_data['oid'].nombre}")
                else:
                    # Si es None o 0, establecer oid como None explícitamente
                    validated_data['oid'] = None
                    logger.info("⚠️ OID establecido como None (eliminando OID del nodo)")
            except (OID.DoesNotExist, ValueError, TypeError) as e:
                logger.error(f"❌ Error procesando oid_id {oid_id}: {e}")
                if isinstance(e, OID.DoesNotExist):
                    raise serializers.ValidationError({'oid_id': f'OID con id {oid_id} no existe'})
                else:
                    raise serializers.ValidationError({'oid_id': f'Valor inválido para oid_id: {oid_id}'})
        
        # Validar que no haya otro nodo con el mismo espacio en la plantilla
        template = validated_data.get('template', instance.template if instance else None)
        if template and oid_instance and oid_instance.espacio:
            existing_node = WorkflowTemplateNode.objects.filter(
                template=template,
                oid__espacio=oid_instance.espacio
            ).exclude(id=instance.id if instance else None).first()
            
            if existing_node:
                raise serializers.ValidationError({
                    'oid_id': f'Ya existe un nodo con el espacio "{oid_instance.get_espacio_display()}" en esta plantilla. '
                             f'Los espacios deben ser únicos por plantilla.'
                })
        
        # Procesar master_node si viene como ID
        master_node_id = None
        if 'master_node' in self.initial_data:
            master_node_id = self.initial_data.get('master_node')
        elif 'master_node' in validated_data:
            master_node_id = validated_data.get('master_node')
        
        if master_node_id is not None:
            try:
                if isinstance(master_node_id, str):
                    master_node_id = int(master_node_id) if master_node_id.strip() else None
                
                if master_node_id is not None and master_node_id != 0:
                    master_node_instance = WorkflowTemplateNode.objects.get(id=master_node_id, template=instance.template)
                    validated_data['master_node'] = master_node_instance
                    logger.info(f"✅ Master node actualizado: {master_node_instance.id} - {master_node_instance.name}")
                else:
                    validated_data['master_node'] = None
                    logger.info("⚠️ Master node establecido como None (removiendo de cadena)")
            except (WorkflowTemplateNode.DoesNotExist, ValueError, TypeError) as e:
                logger.error(f"❌ Error procesando master_node {master_node_id}: {e}")
                if isinstance(e, WorkflowTemplateNode.DoesNotExist):
                    raise serializers.ValidationError({'master_node': f'Nodo master con id {master_node_id} no existe en esta plantilla'})
                else:
                    raise serializers.ValidationError({'master_node': f'Valor inválido para master_node: {master_node_id}'})
        
        # Si está en cadena, no actualizar intervalo (se gestiona desde el master)
        if validated_data.get('is_chain_node', False):
            validated_data.pop('interval_seconds', None)
        
        # No incluir template en la actualización si no viene en los datos
        validated_data.pop('template', None)
        logger.info(f"📝 Datos finales para actualizar nodo: {list(validated_data.keys())}")
        
        # Guardar el template_id antes de actualizar para sincronización
        template_id = instance.template.id if instance.template else None
        
        # Actualizar el nodo
        updated_instance = super().update(instance, validated_data)
        
        # Sincronizar cambios automáticamente si hay template_id
        if template_id:
            try:
                from snmp_jobs.services.workflow_template_service import WorkflowTemplateService
                WorkflowTemplateService.sync_template_changes(template_id)
                logger.info(f"✅ Nodo de plantilla {instance.id} actualizado y sincronizado automáticamente")
            except Exception as e:
                logger.error(f"❌ Error sincronizando cambios de plantilla {template_id}: {e}", exc_info=True)
        
        return updated_instance


class WorkflowTemplateSerializer(serializers.ModelSerializer):
    """Serializer para plantillas de workflow"""
    template_nodes = WorkflowTemplateNodeSerializer(many=True, read_only=True)
    nodes_count = serializers.SerializerMethodField()
    assigned_olts_count = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowTemplate
        fields = ['id', 'name', 'description', 'is_active', 
                  'template_nodes', 'nodes_count', 'assigned_olts_count', 
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_nodes_count(self, obj):
        """Contar nodos de la plantilla"""
        # Verificar si el objeto tiene pk antes de acceder a relaciones
        # Durante la creación, el objeto aún no tiene pk
        if not obj or not hasattr(obj, 'pk') or obj.pk is None:
            return 0
        try:
            return obj.template_nodes.count()
        except (AttributeError, ValueError):
            return 0
    
    def get_assigned_olts_count(self, obj):
        """Contar OLTs asignadas a la plantilla (solo OLTs habilitadas)"""
        # Verificar si el objeto tiene pk antes de acceder a relaciones
        # Durante la creación, el objeto aún no tiene pk
        if not obj or not hasattr(obj, 'pk') or obj.pk is None:
            return 0
        # Usar el método olts_count del modelo que filtra solo OLTs habilitadas
        try:
            return obj.olts_count
        except (AttributeError, ValueError):
            # Si el objeto no tiene pk o no puede acceder a la relación, retornar 0
            return 0


class OLTWorkflowSerializer(serializers.ModelSerializer):
    """Serializer para workflows de OLT"""
    olt_abreviatura = serializers.CharField(source='olt.abreviatura', read_only=True)
    olt_ip = serializers.CharField(source='olt.ip_address', read_only=True)
    nodes_count = serializers.SerializerMethodField()
    linked_templates = serializers.SerializerMethodField()
    
    class Meta:
        model = OLTWorkflow
        fields = ['id', 'olt', 'olt_id', 'olt_abreviatura', 'olt_ip',
                  'name', 'description', 'is_active', 'theme', 'layout',
                  'nodes_count', 'linked_templates', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_nodes_count(self, obj):
        """Contar nodos del workflow"""
        return obj.nodes.count()

    def get_linked_templates(self, obj):
        """Listar plantillas vinculadas al workflow"""
        links = obj.template_links.select_related('template').all()
        return [
            {
                'id': link.template_id,
                'name': link.template.name,
                'auto_sync': link.auto_sync,
                'linked_at': link.created_at,
            }
            for link in links
        ]


class ConfiguracionSistemaSerializer(serializers.ModelSerializer):
    """Serializer para configuraciones del sistema"""
    
    class Meta:
        model = ConfiguracionSistema
        fields = ['id', 'nombre', 'descripcion', 'valor', 'tipo', 'categoria', 
                  'activo', 'solo_lectura', 'modo_prueba', 'fecha_creacion', 'fecha_modificacion']
        read_only_fields = ['id', 'fecha_creacion', 'fecha_modificacion']


class ConfiguracionSNMPSerializer(serializers.ModelSerializer):
    """Serializer para configuraciones SNMP"""
    tipo_operacion_display = serializers.CharField(source='get_tipo_operacion_display', read_only=True)
    version_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ConfiguracionSNMP
        fields = ['id', 'nombre', 'tipo_operacion', 'tipo_operacion_display', 'timeout', 
                  'reintentos', 'comunidad', 'version', 'version_display',
                  'max_pollers_por_olt', 'tamano_lote_inicial', 'tamano_subdivision',
                  'max_reintentos_individuales', 'delay_entre_reintentos',
                  'max_consultas_snmp_simultaneas', 'activo', 'fecha_creacion', 'fecha_modificacion']
        read_only_fields = ['id', 'fecha_creacion', 'fecha_modificacion']
    
    def get_version_display(self, obj):
        """Retorna la versión SNMP formateada"""
        version_map = {
            '1': 'SNMPv1',
            '2c': 'SNMPv2c',
            '3': 'SNMPv3'
        }
        return version_map.get(obj.version, obj.version)


class WorkflowNodeSerializer(serializers.ModelSerializer):
    """Serializer para nodos de workflow"""
    template_name = serializers.CharField(source='template.name', read_only=True)
    workflow_name = serializers.CharField(source='workflow.name', read_only=True)
    template_node_template_name = serializers.CharField(source='template_node.template.name', read_only=True, allow_null=True)
    is_executable = serializers.SerializerMethodField()
    execution_status = serializers.SerializerMethodField()
    master_node_name = serializers.CharField(source='master_node.name', read_only=True, allow_null=True)
    chain_nodes_count = serializers.SerializerMethodField()
    
    # Campo para recibir oid_id directamente desde el frontend
    oid_id = serializers.IntegerField(write_only=True, required=False, allow_null=True, 
                                      help_text="ID del OID para crear nodo independiente (sin plantilla)")
    
    class Meta:
        model = WorkflowNode
        fields = ['id', 'workflow', 'workflow_id', 'workflow_name',
                  'template', 'template_id', 'template_name',
                  'template_node', 'template_node_id', 'template_node_template_name', 'key', 'name',
                  'interval_seconds', 'priority', 'parameters', 'retry_policy',
                  'enabled', 'is_executable', 'execution_status', 'position_x', 'position_y', 'color_override',
                  'icon_override', 'metadata', 'created_at', 'updated_at',
                  'is_chain_node', 'master_node', 'master_node_id', 'master_node_name', 'chain_nodes_count',
                  'next_run_at', 'last_run_at', 'last_success_at', 'last_failure_at', 'oid', 'oid_id']
        read_only_fields = ['id', 'created_at', 'updated_at', 'next_run_at', 'last_run_at', 'last_success_at', 'last_failure_at']
        extra_kwargs = {
            'template': {'required': False, 'allow_null': True},
            'master_node': {'required': False, 'allow_null': True}
        }
    
    def get_chain_nodes_count(self, obj):
        """Obtener el número de nodos en la cadena"""
        if obj.is_chain_node and obj.master_node:
            return obj.master_node.get_chain_nodes().count()
        elif not obj.is_chain_node:
            return obj.get_chain_nodes().count()
        return 0
    
    def get_is_executable(self, obj):
        """Verificar si el nodo puede ejecutarse según la lógica de activación en cascada"""
        return obj.is_executable()
    
    def get_execution_status(self, obj):
        """Obtener el estado de ejecución del nodo"""
        if not obj.is_executable():
            reasons = []
            if not obj.workflow.olt.habilitar_olt:
                reasons.append('OLT deshabilitada')
            if not obj.workflow.is_active:
                reasons.append('Workflow inactivo')
            if obj.template_node and obj.template_node.template and not obj.template_node.template.is_active:
                reasons.append('Plantilla inactiva')
            if not obj.enabled:
                reasons.append('Nodo deshabilitado')
            return {
                'can_execute': False,
                'reasons': reasons
            }
        return {
            'can_execute': True,
            'reasons': []
        }
    
    def create(self, validated_data):
        """Crear nodo simplificado: solo requiere key, oid_id e interval_seconds (si no es cadena)"""
        from oids.models import OID
        
        workflow = validated_data.get('workflow')
        template = validated_data.get('template')
        key = validated_data.get('key')
        is_chain_node = validated_data.get('is_chain_node', False)
        
        # ✅ VALIDACIÓN: Key es obligatoria
        if not key:
            raise serializers.ValidationError({
                'key': 'La key es obligatoria para identificar el nodo'
            })
        
        # ✅ VALIDACIÓN: OID es obligatorio (puede venir de oid_id o template_node)
        oid_id = validated_data.pop('oid_id', None)
        oid_instance = None
        
        if oid_id:
            try:
                oid_instance = OID.objects.get(id=oid_id)
                validated_data['oid'] = oid_instance
            except OID.DoesNotExist:
                raise serializers.ValidationError({
                    'oid_id': f'OID con id {oid_id} no existe'
                })
        else:
            # Si no viene oid_id, verificar si viene de template_node
            template_node = validated_data.get('template_node')
            if template_node and template_node.oid:
                oid_instance = template_node.oid
                validated_data['oid'] = oid_instance
            else:
                raise serializers.ValidationError({
                    'oid_id': 'El OID es obligatorio. Proporcione oid_id o template_node con OID.'
                })
        
        # ✅ VALIDACIÓN: Intervalo es obligatorio si NO es nodo en cadena
        if not is_chain_node:
            interval_seconds = validated_data.get('interval_seconds')
            if not interval_seconds or interval_seconds <= 0:
                raise serializers.ValidationError({
                    'interval_seconds': 'El intervalo es obligatorio para nodos que no son de cadena'
                })
        
        # Validar que la key no esté duplicada en el mismo workflow
        if key and workflow:
            existing_node = WorkflowNode.objects.filter(
                workflow=workflow,
                key=key
            ).first()
            
            if existing_node:
                raise serializers.ValidationError({
                    'key': f'Ya existe un nodo con la key "{key}" en este workflow. Las keys deben ser únicas por workflow.'
                })
        
        # Si no se proporciona template y hay template_node, usar el template del template_node
        template_node = validated_data.get('template_node')
        if not template and template_node:
            template = template_node.template
        
        # Si aún no hay template, buscar o crear uno por defecto
        if not template:
            from snmp_jobs.models import TaskTemplate, TaskFunction
            import logging
            logger = logging.getLogger(__name__)
            
            # Buscar un TaskTemplate por defecto o crear uno básico
            default_template = TaskTemplate.objects.filter(is_active=True).first()
            
            if not default_template:
                # Buscar una TaskFunction por defecto
                default_function = TaskFunction.objects.filter(is_active=True).first()
                
                if default_function:
                    # Crear un TaskTemplate básico
                    default_template, created = TaskTemplate.objects.get_or_create(
                        slug='default-workflow-node',
                        defaults={
                            'name': 'Plantilla por Defecto',
                            'description': 'Plantilla automática para nodos de workflow',
                            'function': default_function,
                            'default_interval_seconds': 300,
                            'default_priority': 3,
                            'is_active': True
                        }
                    )
                    if created:
                        logger.info(f"✅ TaskTemplate por defecto creado: {default_template.slug}")
                else:
                    raise serializers.ValidationError({
                        'template': 'No se encontró ninguna TaskFunction activa. Por favor, crea al menos una TaskFunction antes de crear nodos de workflow.'
                    })
            
            validated_data['template'] = default_template
            logger.info(f"✅ TaskTemplate asignado automáticamente: {default_template.name} (ID: {default_template.id})")
        
        # Validar que no haya otro nodo con el mismo espacio en el workflow
        if oid_instance and oid_instance.espacio and workflow:
            existing_node = WorkflowNode.objects.filter(
                workflow=workflow,
                oid__espacio=oid_instance.espacio
            ).exclude(id=self.instance.id if hasattr(self, 'instance') and self.instance else None).first()
            
            if existing_node:
                raise serializers.ValidationError({
                    'oid_id': f'Ya existe un nodo con el espacio "{oid_instance.get_espacio_display()}" en este workflow. '
                             f'Los espacios deben ser únicos por workflow.'
                })
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Actualizar nodo simplificado: solo requiere key, oid_id e interval_seconds (si no es cadena)"""
        from oids.models import OID
        
        workflow = validated_data.get('workflow', instance.workflow if instance else None)
        key = validated_data.get('key', instance.key if instance else None)
        is_chain_node = validated_data.get('is_chain_node', instance.is_chain_node if instance else False)
        
        # ✅ VALIDACIÓN: OID es obligatorio (puede venir de oid_id o template_node)
        oid_id = validated_data.pop('oid_id', None)
        oid_instance = None
        
        if oid_id:
            try:
                oid_instance = OID.objects.get(id=oid_id)
                validated_data['oid'] = oid_instance
            except OID.DoesNotExist:
                raise serializers.ValidationError({
                    'oid_id': f'OID con id {oid_id} no existe'
                })
        else:
            # Si no viene oid_id, verificar si viene de template_node o usar el existente
            template_node = validated_data.get('template_node', instance.template_node if instance else None)
            if template_node and template_node.oid:
                oid_instance = template_node.oid
                validated_data['oid'] = oid_instance
            elif instance and instance.oid:
                oid_instance = instance.oid
                # Mantener el OID existente
            else:
                raise serializers.ValidationError({
                    'oid_id': 'El OID es obligatorio. Proporcione oid_id o template_node con OID.'
                })
        
        # ✅ VALIDACIÓN: Intervalo es obligatorio si NO es nodo en cadena
        if not is_chain_node:
            interval_seconds = validated_data.get('interval_seconds', instance.interval_seconds if instance else None)
            if not interval_seconds or interval_seconds <= 0:
                raise serializers.ValidationError({
                    'interval_seconds': 'El intervalo es obligatorio para nodos que no son de cadena'
                })
        
        # Validar que la key no esté duplicada en el mismo workflow (excluyendo el nodo actual)
        if key and workflow:
            existing_node = WorkflowNode.objects.filter(
                workflow=workflow,
                key=key
            ).exclude(id=instance.id if instance else None).first()
            
            if existing_node:
                raise serializers.ValidationError({
                    'key': f'Ya existe un nodo con la key "{key}" en este workflow. Las keys deben ser únicas por workflow.'
                })
        
        # Validar que no haya otro nodo con el mismo espacio en el workflow
        if oid_instance and oid_instance.espacio and workflow:
            existing_node = WorkflowNode.objects.filter(
                workflow=workflow,
                oid__espacio=oid_instance.espacio
            ).exclude(id=instance.id if instance else None).first()
            
            if existing_node:
                raise serializers.ValidationError({
                    'oid_id': f'Ya existe un nodo con el espacio "{oid_instance.get_espacio_display()}" en este workflow. '
                             f'Los espacios deben ser únicos por workflow.'
                })
        
        return super().update(instance, validated_data)

