"""
Sistema de Backup y Restauración para Facho Deluxe v2

Exporta e importa configuraciones sin depender de IDs, usando nombres únicos.
Excluye OLTs del backup (solo configuración inicial).
"""
import json
import logging
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from drf_spectacular.utils import extend_schema, OpenApiResponse

# Importar modelos
from brands.models import Brand
from olt_models.models import OLTModel
from configuracion_avanzada.models import ConfiguracionSistema, ConfiguracionSNMP
from zabbix_config.models import ZabbixConfiguration
from discovery.models import OnuStateLookup
from oids.models import OID
from snmp_formulas.models import IndexFormula

logger = logging.getLogger(__name__)


# ============================================================================
# SERIALIZERS ESPECIALES PARA BACKUP (sin IDs, usando nombres únicos)
# ============================================================================

def serialize_brand_for_backup(brand):
    """Serializa Brand usando solo nombre (campo único)"""
    return {
        'nombre': brand.nombre,
        'descripcion': brand.descripcion
    }


def serialize_olt_model_for_backup(olt_model):
    """Serializa OLTModel usando nombre y marca_nombre (sin IDs)"""
    return {
        'nombre': olt_model.nombre,
        'marca_nombre': olt_model.marca.nombre,
        'descripcion': olt_model.descripcion,
        'tipo_olt': olt_model.tipo_olt,
        'activo': olt_model.activo,
        'capacidad_puertos': olt_model.capacidad_puertos,
        'capacidad_onus': olt_model.capacidad_onus,
        'slots_disponibles': olt_model.slots_disponibles,
        'version_firmware_minima': olt_model.version_firmware_minima,
        'comunidad_snmp_default': olt_model.comunidad_snmp_default,
        'puerto_snmp_default': olt_model.puerto_snmp_default,
        'url_documentacion': olt_model.url_documentacion,
        'url_manual_usuario': olt_model.url_manual_usuario,
        'notas_tecnicas': olt_model.notas_tecnicas,
        'soporte_tecnico_contacto': olt_model.soporte_tecnico_contacto,
        'fecha_lanzamiento': str(olt_model.fecha_lanzamiento) if olt_model.fecha_lanzamiento else None,
        'fecha_fin_soporte': str(olt_model.fecha_fin_soporte) if olt_model.fecha_fin_soporte else None,
    }


def serialize_configuracion_sistema_for_backup(config):
    """Serializa ConfiguracionSistema usando nombre (campo único)"""
    return {
        'nombre': config.nombre,
        'descripcion': config.descripcion,
        'valor': config.valor,
        'tipo': config.tipo,
        'categoria': config.categoria,
        'activo': config.activo,
        'solo_lectura': config.solo_lectura,
        'modo_prueba': config.modo_prueba,
    }


def serialize_configuracion_snmp_for_backup(config):
    """Serializa ConfiguracionSNMP usando nombre (campo único)"""
    return {
        'nombre': config.nombre,
        'tipo_operacion': config.tipo_operacion,
        'timeout': config.timeout,
        'reintentos': config.reintentos,
        'comunidad': config.comunidad,
        'version': config.version,
        'max_pollers_por_olt': config.max_pollers_por_olt,
        'tamano_lote_inicial': config.tamano_lote_inicial,
        'tamano_subdivision': config.tamano_subdivision,
        'max_reintentos_individuales': config.max_reintentos_individuales,
        'delay_entre_reintentos': config.delay_entre_reintentos,
        'max_consultas_snmp_simultaneas': config.max_consultas_snmp_simultaneas,
        'activo': config.activo,
    }


def serialize_zabbix_config_for_backup(config):
    """Serializa ZabbixConfiguration usando nombre (campo único)"""
    return {
        'nombre': config.nombre,
        'zabbix_url': config.zabbix_url,
        'zabbix_token': config.zabbix_token,  # ⚠️ Token sensible - considerar encriptación
        'item_key': config.item_key,
        'activa': config.activa,
        'timeout': config.timeout,
        'verificar_ssl': config.verificar_ssl,
        'descripcion': config.descripcion,
    }


def serialize_onu_state_lookup_for_backup(lookup):
    """Serializa OnuStateLookup usando value + marca_nombre (único)"""
    return {
        'value': lookup.value,
        'label': lookup.label,
        'description': lookup.description,
        'marca_nombre': lookup.marca.nombre if lookup.marca else None,
    }


def serialize_oid_for_backup(oid):
    """Serializa OID usando nombre, marca_nombre y modelo_nombre (sin IDs)"""
    return {
        'nombre': oid.nombre,
        'oid': oid.oid,
        'marca_nombre': oid.marca.nombre,
        'modelo_nombre': oid.modelo.nombre if oid.modelo else None,
        'espacio': oid.espacio,
        'target_field': oid.target_field,
        'keep_previous_value': oid.keep_previous_value,
        'format_mac': oid.format_mac,
    }


def serialize_index_formula_for_backup(formula):
    """Serializa IndexFormula usando marca_nombre y modelo_nombre (sin IDs)"""
    return {
        'nombre': formula.nombre,
        'marca_nombre': formula.marca.nombre,
        'modelo_nombre': formula.modelo.nombre if formula.modelo else None,
        'descripcion': formula.descripcion,
        'activo': formula.activo,
        'normalized_format': formula.normalized_format,
        'calculation_mode': formula.calculation_mode,
        # Parámetros modo lineal
        'base_index': formula.base_index,
        'step_slot': formula.step_slot,
        'step_port': formula.step_port,
        # Parámetros modo bitshift
        'shift_slot_bits': formula.shift_slot_bits,
        'shift_port_bits': formula.shift_port_bits,
        'mask_slot': formula.mask_slot,
        'mask_port': formula.mask_port,
        # Parámetros adicionales
        'onu_offset': formula.onu_offset,
        'has_dot_notation': formula.has_dot_notation,
        'dot_is_onu_number': formula.dot_is_onu_number,
        # Límites y validación
        'slot_max': formula.slot_max,
        'port_max': formula.port_max,
        'onu_max': formula.onu_max,
    }


# ============================================================================
# FUNCIONES DE EXPORTACIÓN
# ============================================================================

def export_backup_data():
    """
    Exporta todos los datos de configuración a un diccionario JSON.
    Orden: Brand → OLTModel → Configuraciones → Lookups → OIDs → Formulas
    """
    backup_data = {
        'metadata': {
            'version': '1.0',
            'fecha_creacion': timezone.now().isoformat(),
            'sistema': 'Facho Deluxe v2',
            'descripcion': 'Backup de configuración inicial (sin OLTs)'
        },
        'data': {}
    }
    
    # 1. Brands (sin dependencias)
    logger.info("📦 Exportando Brands...")
    backup_data['data']['brands'] = [
        serialize_brand_for_backup(brand) 
        for brand in Brand.objects.all().order_by('nombre')
    ]
    
    # 2. OLT Models (depende de Brand)
    logger.info("📦 Exportando OLT Models...")
    backup_data['data']['olt_models'] = [
        serialize_olt_model_for_backup(model)
        for model in OLTModel.objects.all().select_related('marca').order_by('marca__nombre', 'nombre')
    ]
    
    # 3. ConfiguracionSistema (sin dependencias)
    logger.info("📦 Exportando ConfiguracionSistema...")
    backup_data['data']['configuracion_sistema'] = [
        serialize_configuracion_sistema_for_backup(config)
        for config in ConfiguracionSistema.objects.all().order_by('categoria', 'nombre')
    ]
    
    # 4. ConfiguracionSNMP (sin dependencias)
    logger.info("📦 Exportando ConfiguracionSNMP...")
    backup_data['data']['configuracion_snmp'] = [
        serialize_configuracion_snmp_for_backup(config)
        for config in ConfiguracionSNMP.objects.all().order_by('tipo_operacion', 'nombre')
    ]
    
    # 5. ZabbixConfiguration (sin dependencias)
    logger.info("📦 Exportando ZabbixConfiguration...")
    backup_data['data']['zabbix_configuration'] = [
        serialize_zabbix_config_for_backup(config)
        for config in ZabbixConfiguration.objects.all().order_by('nombre')
    ]
    
    # 6. OnuStateLookup (depende de Brand)
    logger.info("📦 Exportando OnuStateLookup...")
    backup_data['data']['onu_state_lookup'] = [
        serialize_onu_state_lookup_for_backup(lookup)
        for lookup in OnuStateLookup.objects.all().select_related('marca').order_by('marca__nombre', 'value')
    ]
    
    # 7. OIDs (depende de Brand y OLTModel)
    logger.info("📦 Exportando OIDs...")
    backup_data['data']['oids'] = [
        serialize_oid_for_backup(oid)
        for oid in OID.objects.all().select_related('marca', 'modelo').order_by('marca__nombre', 'modelo__nombre', 'nombre')
    ]
    
    # 8. IndexFormula (depende de Brand y OLTModel)
    logger.info("📦 Exportando IndexFormula...")
    backup_data['data']['index_formulas'] = [
        serialize_index_formula_for_backup(formula)
        for formula in IndexFormula.objects.all().select_related('marca', 'modelo').order_by('marca__nombre', 'modelo__nombre', 'nombre')
    ]
    
    logger.info("✅ Exportación completada")
    return backup_data


# ============================================================================
# FUNCIONES DE IMPORTACIÓN
# ============================================================================

def import_brand(data):
    """Importa o actualiza Brand por nombre. Solo actualiza si hay cambios."""
    brand, created = Brand.objects.get_or_create(
        nombre=data['nombre'],
        defaults={'descripcion': data.get('descripcion', '')}
    )
    if not created:
        # Solo actualizar si hay cambios
        new_descripcion = data.get('descripcion', '')
        if brand.descripcion != new_descripcion:
            brand.descripcion = new_descripcion
            brand.save()
    return brand, created


def import_olt_model(data):
    """Importa o actualiza OLTModel por nombre y marca_nombre"""
    try:
        marca = Brand.objects.get(nombre=data['marca_nombre'])
    except Brand.DoesNotExist:
        raise ValueError(f"Marca '{data['marca_nombre']}' no existe. Importa Brands primero.")
    
    defaults = {
        'descripcion': data.get('descripcion', ''),
        'tipo_olt': data.get('tipo_olt'),
        'activo': data.get('activo', True),
        'capacidad_puertos': data.get('capacidad_puertos'),
        'capacidad_onus': data.get('capacidad_onus'),
        'slots_disponibles': data.get('slots_disponibles'),
        'version_firmware_minima': data.get('version_firmware_minima'),
        'comunidad_snmp_default': data.get('comunidad_snmp_default'),
        'puerto_snmp_default': data.get('puerto_snmp_default', 161),
        'url_documentacion': data.get('url_documentacion'),
        'url_manual_usuario': data.get('url_manual_usuario'),
        'notas_tecnicas': data.get('notas_tecnicas'),
        'soporte_tecnico_contacto': data.get('soporte_tecnico_contacto'),
    }
    
    # Manejar fechas
    if data.get('fecha_lanzamiento'):
        from django.utils.dateparse import parse_date
        parsed_date = parse_date(data['fecha_lanzamiento'])
        if parsed_date:
            defaults['fecha_lanzamiento'] = parsed_date
    if data.get('fecha_fin_soporte'):
        from django.utils.dateparse import parse_date
        parsed_date = parse_date(data['fecha_fin_soporte'])
        if parsed_date:
            defaults['fecha_fin_soporte'] = parsed_date
    
            model, created = OLTModel.objects.get_or_create(
                nombre=data['nombre'],
                marca=marca,
                defaults=defaults
            )
            
            if not created:
                # Solo actualizar si hay cambios reales
                has_changes = False
                for key, value in defaults.items():
                    current_value = getattr(model, key)
                    if current_value != value:
                        setattr(model, key, value)
                        has_changes = True
                
                if has_changes:
                    model.save()
            
            return model, created


def import_configuracion_sistema(data):
    """Importa o actualiza ConfiguracionSistema por nombre"""
    defaults = {
        'descripcion': data.get('descripcion', ''),
        'valor': data.get('valor', ''),
        'tipo': data.get('tipo', 'string'),
        'categoria': data.get('categoria', 'general'),
        'activo': data.get('activo', True),
        'solo_lectura': data.get('solo_lectura', False),
        'modo_prueba': data.get('modo_prueba', False),
    }
    
    config, created = ConfiguracionSistema.objects.get_or_create(
        nombre=data['nombre'],
        defaults=defaults
    )
    
    if not created:
        # Solo actualizar si hay cambios reales
        has_changes = False
        for key, value in defaults.items():
            current_value = getattr(config, key)
            if current_value != value:
                setattr(config, key, value)
                has_changes = True
        
        if has_changes:
            config.save()
    
    return config, created


def import_configuracion_snmp(data):
    """Importa o actualiza ConfiguracionSNMP por nombre"""
    defaults = {
        'tipo_operacion': data.get('tipo_operacion', 'general'),
        'timeout': data.get('timeout', 5),
        'reintentos': data.get('reintentos', 0),
        'comunidad': data.get('comunidad', 'public'),
        'version': data.get('version', '2c'),
        'max_pollers_por_olt': data.get('max_pollers_por_olt', 10),
        'tamano_lote_inicial': data.get('tamano_lote_inicial', 200),
        'tamano_subdivision': data.get('tamano_subdivision', 50),
        'max_reintentos_individuales': data.get('max_reintentos_individuales', 2),
        'delay_entre_reintentos': data.get('delay_entre_reintentos', 5),
        'max_consultas_snmp_simultaneas': data.get('max_consultas_snmp_simultaneas', 10),
        'activo': data.get('activo', True),
    }
    
    config, created = ConfiguracionSNMP.objects.get_or_create(
        nombre=data['nombre'],
        defaults=defaults
    )
    
    if not created:
        # Solo actualizar si hay cambios reales
        has_changes = False
        for key, value in defaults.items():
            current_value = getattr(config, key)
            if current_value != value:
                setattr(config, key, value)
                has_changes = True
        
        if has_changes:
            config.save()
    
    return config, created


def import_zabbix_config(data):
    """Importa o actualiza ZabbixConfiguration por nombre"""
    defaults = {
        'zabbix_url': data.get('zabbix_url', ''),
        'zabbix_token': data.get('zabbix_token', ''),
        'item_key': data.get('item_key', 'port.descover.walk'),
        'activa': data.get('activa', False),  # Por defecto inactiva para evitar conflictos
        'timeout': data.get('timeout', 30),
        'verificar_ssl': data.get('verificar_ssl', True),
        'descripcion': data.get('descripcion', ''),
    }
    
    config, created = ZabbixConfiguration.objects.get_or_create(
        nombre=data['nombre'],
        defaults=defaults
    )
    
    if not created:
        # Solo actualizar si hay cambios reales
        has_changes = False
        for key, value in defaults.items():
            current_value = getattr(config, key)
            if current_value != value:
                setattr(config, key, value)
                has_changes = True
        
        if has_changes:
            config.save()
    
    return config, created


def import_onu_state_lookup(data):
    """Importa o actualiza OnuStateLookup por value + marca_nombre"""
    marca = None
    if data.get('marca_nombre'):
        try:
            marca = Brand.objects.get(nombre=data['marca_nombre'])
        except Brand.DoesNotExist:
            raise ValueError(f"Marca '{data['marca_nombre']}' no existe. Importa Brands primero.")
    
    defaults = {
        'label': data.get('label', ''),
        'description': data.get('description', ''),
        'marca': marca,
    }
    
    lookup, created = OnuStateLookup.objects.get_or_create(
        value=data['value'],
        marca=marca,
        defaults=defaults
    )
    
    if not created:
        # Solo actualizar si hay cambios reales
        has_changes = False
        for key, value in defaults.items():
            current_value = getattr(lookup, key)
            if current_value != value:
                setattr(lookup, key, value)
                has_changes = True
        
        if has_changes:
            lookup.save()
    
    return lookup, created


def import_oid(data):
    """Importa o actualiza OID por nombre, marca_nombre y modelo_nombre"""
    try:
        marca = Brand.objects.get(nombre=data['marca_nombre'])
    except Brand.DoesNotExist:
        raise ValueError(f"Marca '{data['marca_nombre']}' no existe. Importa Brands primero.")
    
    modelo = None
    if data.get('modelo_nombre'):
        modelo_nombre = data['modelo_nombre']
        marca_nombre = data['marca_nombre']
        
        # Si el modelo es "Genérico" y la marca no es "🌐 Genérico",
        # usar el modelo genérico universal de la marca genérica
        if modelo_nombre == 'Genérico' and marca_nombre != '🌐 Genérico':
            try:
                generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                modelo = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
            except (Brand.DoesNotExist, OLTModel.DoesNotExist):
                raise ValueError(f"Modelo genérico universal no existe. Asegúrate de que exista la marca '🌐 Genérico' con modelo 'Genérico'.")
        else:
            try:
                modelo = OLTModel.objects.get(nombre=modelo_nombre, marca=marca)
            except OLTModel.DoesNotExist:
                raise ValueError(f"Modelo '{modelo_nombre}' de marca '{marca_nombre}' no existe. Importa OLTModels primero.")
    
    defaults = {
        'oid': data.get('oid', ''),
        'espacio': data.get('espacio', 'descubrimiento'),
        'target_field': data.get('target_field'),
        'keep_previous_value': data.get('keep_previous_value', False),
        'format_mac': data.get('format_mac', False),
    }
    
    oid, created = OID.objects.get_or_create(
        nombre=data['nombre'],
        marca=marca,
        modelo=modelo,
        defaults=defaults
    )
    
    if not created:
        # Solo actualizar si hay cambios reales
        has_changes = False
        for key, value in defaults.items():
            current_value = getattr(oid, key)
            if current_value != value:
                setattr(oid, key, value)
                has_changes = True
        
        if has_changes:
            oid.save()
    
    return oid, created


def import_index_formula(data):
    """Importa o actualiza IndexFormula por marca_nombre y modelo_nombre"""
    try:
        marca = Brand.objects.get(nombre=data['marca_nombre'])
    except Brand.DoesNotExist:
        raise ValueError(f"Marca '{data['marca_nombre']}' no existe. Importa Brands primero.")
    
    modelo = None
    if data.get('modelo_nombre'):
        modelo_nombre = data['modelo_nombre']
        marca_nombre = data['marca_nombre']
        
        # Si el modelo es "Genérico" y la marca no es "🌐 Genérico",
        # usar el modelo genérico universal de la marca genérica
        if modelo_nombre == 'Genérico' and marca_nombre != '🌐 Genérico':
            try:
                generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                modelo = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
            except (Brand.DoesNotExist, OLTModel.DoesNotExist):
                raise ValueError(f"Modelo genérico universal no existe. Asegúrate de que exista la marca '🌐 Genérico' con modelo 'Genérico'.")
        else:
            try:
                modelo = OLTModel.objects.get(nombre=modelo_nombre, marca=marca)
            except OLTModel.DoesNotExist:
                raise ValueError(f"Modelo '{modelo_nombre}' de marca '{marca_nombre}' no existe. Importa OLTModels primero.")
    
    defaults = {
        'nombre': data.get('nombre', ''),
        'descripcion': data.get('descripcion', ''),
        'activo': data.get('activo', True),
        'normalized_format': data.get('normalized_format', '{slot}/{port}'),
        'calculation_mode': data.get('calculation_mode', 'linear'),
        'base_index': data.get('base_index', 0),
        'step_slot': data.get('step_slot', 0),
        'step_port': data.get('step_port', 0),
        'shift_slot_bits': data.get('shift_slot_bits', 0),
        'shift_port_bits': data.get('shift_port_bits', 0),
        'mask_slot': data.get('mask_slot'),
        'mask_port': data.get('mask_port'),
        'onu_offset': data.get('onu_offset', 0),
        'has_dot_notation': data.get('has_dot_notation', False),
        'dot_is_onu_number': data.get('dot_is_onu_number', True),
        'slot_max': data.get('slot_max', 64),
        'port_max': data.get('port_max', 64),
        'onu_max': data.get('onu_max', 128),
    }
    
    formula, created = IndexFormula.objects.get_or_create(
        marca=marca,
        modelo=modelo,
        defaults=defaults
    )
    
    if not created:
        # Solo actualizar si hay cambios reales
        has_changes = False
        for key, value in defaults.items():
            current_value = getattr(formula, key)
            if current_value != value:
                setattr(formula, key, value)
                has_changes = True
        
        if has_changes:
            formula.save()
    
    return formula, created


def compare_objects(obj1, obj2, exclude_fields=None):
    """
    Compara dos objetos/diccionarios y retorna las diferencias.
    
    Args:
        obj1: Objeto/diccionario actual
        obj2: Objeto/diccionario nuevo
        exclude_fields: Lista de campos a excluir de la comparación
    
    Returns:
        dict: {
            'has_changes': bool,
            'differences': dict con los campos que difieren
        }
    """
    if exclude_fields is None:
        exclude_fields = ['id', 'created_at', 'updated_at', 'fecha_creacion', 'fecha_modificacion']
    
    differences = {}
    has_changes = False
    
    # Obtener todas las claves únicas
    all_keys = set(obj1.keys()) | set(obj2.keys())
    
    for key in all_keys:
        if key in exclude_fields:
            continue
        
        val1 = obj1.get(key)
        val2 = obj2.get(key)
        
        # Normalizar valores None y strings vacíos para comparación
        # Pero mantener el valor original para mostrar en diferencias
        val1_normalized = val1 if val1 is not None else ''
        val2_normalized = val2 if val2 is not None else ''
        
        # Convertir a string para comparación si son diferentes tipos
        if type(val1_normalized) != type(val2_normalized):
            val1_normalized = str(val1_normalized) if val1_normalized is not None else ''
            val2_normalized = str(val2_normalized) if val2_normalized is not None else ''
        
        # Comparar valores normalizados
        if val1_normalized != val2_normalized:
            differences[key] = {
                'current': val1,
                'new': val2
            }
            has_changes = True
    
    return {
        'has_changes': has_changes,
        'differences': differences
    }


def compare_backup_data(backup_data):
    """
    Compara los datos del backup con los datos actuales en la BD.
    Retorna un análisis detallado sin realizar cambios.
    """
    if 'data' not in backup_data:
        raise ValueError("Formato de backup inválido: falta clave 'data'")
    
    data = backup_data['data']
    comparison = {
        'brands': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'olt_models': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'configuracion_sistema': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'configuracion_snmp': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'zabbix_configuration': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'onu_state_lookup': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'oids': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'index_formulas': {'new': [], 'existing': [], 'existing_no_changes': [], 'conflicts': []},
        'missing_dependencies': []
    }
    
    # 1. Brands
    for brand_data in data.get('brands', []):
        nombre = brand_data.get('nombre')
        try:
            existing = Brand.objects.get(nombre=nombre)
            current_data = serialize_brand_for_backup(existing)
            diff_result = compare_objects(current_data, brand_data)
            
            item_data = {
                'nombre': nombre,
                'current': current_data,
                'new': brand_data,
                'has_changes': diff_result['has_changes'],
                'differences': diff_result['differences']
            }
            
            if diff_result['has_changes']:
                comparison['brands']['existing'].append(item_data)
            else:
                comparison['brands']['existing_no_changes'].append(item_data)
        except Brand.DoesNotExist:
            comparison['brands']['new'].append(brand_data)
    
    # 2. OLT Models
    for model_data in data.get('olt_models', []):
        nombre = model_data.get('nombre')
        marca_nombre = model_data.get('marca_nombre')
        try:
            marca = Brand.objects.get(nombre=marca_nombre)
            try:
                existing = OLTModel.objects.get(nombre=nombre, marca=marca)
                current_data = serialize_olt_model_for_backup(existing)
                diff_result = compare_objects(current_data, model_data)
                
                item_data = {
                    'nombre': nombre,
                    'marca_nombre': marca_nombre,
                    'current': current_data,
                    'new': model_data,
                    'has_changes': diff_result['has_changes'],
                    'differences': diff_result['differences']
                }
                
                if diff_result['has_changes']:
                    comparison['olt_models']['existing'].append(item_data)
                else:
                    comparison['olt_models']['existing_no_changes'].append(item_data)
            except OLTModel.DoesNotExist:
                comparison['olt_models']['new'].append(model_data)
        except Brand.DoesNotExist:
            comparison['missing_dependencies'].append({
                'type': 'olt_model',
                'item': nombre,
                'missing': f"Marca '{marca_nombre}' no existe"
            })
            comparison['olt_models']['conflicts'].append(model_data)
    
    # 3. ConfiguracionSistema
    for config_data in data.get('configuracion_sistema', []):
        nombre = config_data.get('nombre')
        try:
            existing = ConfiguracionSistema.objects.get(nombre=nombre)
            current_data = serialize_configuracion_sistema_for_backup(existing)
            diff_result = compare_objects(current_data, config_data)
            
            item_data = {
                'nombre': nombre,
                'current': current_data,
                'new': config_data,
                'has_changes': diff_result['has_changes'],
                'differences': diff_result['differences']
            }
            
            if diff_result['has_changes']:
                comparison['configuracion_sistema']['existing'].append(item_data)
            else:
                comparison['configuracion_sistema']['existing_no_changes'].append(item_data)
        except ConfiguracionSistema.DoesNotExist:
            comparison['configuracion_sistema']['new'].append(config_data)
    
    # 4. ConfiguracionSNMP
    for config_data in data.get('configuracion_snmp', []):
        nombre = config_data.get('nombre')
        try:
            existing = ConfiguracionSNMP.objects.get(nombre=nombre)
            current_data = serialize_configuracion_snmp_for_backup(existing)
            diff_result = compare_objects(current_data, config_data)
            
            item_data = {
                'nombre': nombre,
                'current': current_data,
                'new': config_data,
                'has_changes': diff_result['has_changes'],
                'differences': diff_result['differences']
            }
            
            if diff_result['has_changes']:
                comparison['configuracion_snmp']['existing'].append(item_data)
            else:
                comparison['configuracion_snmp']['existing_no_changes'].append(item_data)
        except ConfiguracionSNMP.DoesNotExist:
            comparison['configuracion_snmp']['new'].append(config_data)
    
    # 5. ZabbixConfiguration
    for config_data in data.get('zabbix_configuration', []):
        nombre = config_data.get('nombre')
        try:
            existing = ZabbixConfiguration.objects.get(nombre=nombre)
            current_data = serialize_zabbix_config_for_backup(existing)
            diff_result = compare_objects(current_data, config_data)
            
            item_data = {
                'nombre': nombre,
                'current': current_data,
                'new': config_data,
                'has_changes': diff_result['has_changes'],
                'differences': diff_result['differences']
            }
            
            if diff_result['has_changes']:
                comparison['zabbix_configuration']['existing'].append(item_data)
            else:
                comparison['zabbix_configuration']['existing_no_changes'].append(item_data)
        except ZabbixConfiguration.DoesNotExist:
            comparison['zabbix_configuration']['new'].append(config_data)
    
    # 6. OnuStateLookup
    for lookup_data in data.get('onu_state_lookup', []):
        value = lookup_data.get('value')
        marca_nombre = lookup_data.get('marca_nombre')
        marca = None
        if marca_nombre:
            try:
                marca = Brand.objects.get(nombre=marca_nombre)
            except Brand.DoesNotExist:
                comparison['missing_dependencies'].append({
                    'type': 'onu_state_lookup',
                    'item': f"Value {value}",
                    'missing': f"Marca '{marca_nombre}' no existe"
                })
                comparison['onu_state_lookup']['conflicts'].append(lookup_data)
                continue
        
        try:
            existing = OnuStateLookup.objects.get(value=value, marca=marca)
            current_data = serialize_onu_state_lookup_for_backup(existing)
            diff_result = compare_objects(current_data, lookup_data)
            
            item_data = {
                'value': value,
                'marca_nombre': marca_nombre,
                'current': current_data,
                'new': lookup_data,
                'has_changes': diff_result['has_changes'],
                'differences': diff_result['differences']
            }
            
            if diff_result['has_changes']:
                comparison['onu_state_lookup']['existing'].append(item_data)
            else:
                comparison['onu_state_lookup']['existing_no_changes'].append(item_data)
        except OnuStateLookup.DoesNotExist:
            comparison['onu_state_lookup']['new'].append(lookup_data)
    
    # 7. OIDs
    for oid_data in data.get('oids', []):
        nombre = oid_data.get('nombre')
        marca_nombre = oid_data.get('marca_nombre')
        modelo_nombre = oid_data.get('modelo_nombre')
        
        try:
            marca = Brand.objects.get(nombre=marca_nombre)
            modelo = None
            if modelo_nombre:
                # Si el modelo es "Genérico" y la marca no es "🌐 Genérico",
                # usar el modelo genérico universal de la marca genérica
                if modelo_nombre == 'Genérico' and marca_nombre != '🌐 Genérico':
                    try:
                        generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                        modelo = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
                    except (Brand.DoesNotExist, OLTModel.DoesNotExist):
                        comparison['missing_dependencies'].append({
                            'type': 'oid',
                            'item': nombre,
                            'missing': f"Modelo genérico universal no existe (marca '🌐 Genérico' con modelo 'Genérico')"
                        })
                        comparison['oids']['conflicts'].append(oid_data)
                        continue
                else:
                    try:
                        modelo = OLTModel.objects.get(nombre=modelo_nombre, marca=marca)
                    except OLTModel.DoesNotExist:
                        comparison['missing_dependencies'].append({
                            'type': 'oid',
                            'item': nombre,
                            'missing': f"Modelo '{modelo_nombre}' de marca '{marca_nombre}' no existe"
                        })
                        comparison['oids']['conflicts'].append(oid_data)
                        continue
            
            # Buscar OID existente
            # Si el modelo es genérico, buscar también con el modelo genérico universal
            existing = None
            try:
                existing = OID.objects.get(nombre=nombre, marca=marca, modelo=modelo)
            except OID.DoesNotExist:
                # Si no se encuentra y el modelo es genérico, intentar con el modelo genérico universal
                if modelo_nombre == 'Genérico' and marca_nombre != '🌐 Genérico':
                    try:
                        generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                        generic_model = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
                        existing = OID.objects.filter(nombre=nombre, marca=marca, modelo=generic_model).first()
                    except (Brand.DoesNotExist, OLTModel.DoesNotExist):
                        pass
            
            if existing:
                current_data = serialize_oid_for_backup(existing)
                diff_result = compare_objects(current_data, oid_data)
                
                item_data = {
                    'nombre': nombre,
                    'marca_nombre': marca_nombre,
                    'modelo_nombre': modelo_nombre,
                    'current': current_data,
                    'new': oid_data,
                    'has_changes': diff_result['has_changes'],
                    'differences': diff_result['differences']
                }
                
                if diff_result['has_changes']:
                    comparison['oids']['existing'].append(item_data)
                else:
                    comparison['oids']['existing_no_changes'].append(item_data)
            else:
                comparison['oids']['new'].append(oid_data)
        except Brand.DoesNotExist:
            comparison['missing_dependencies'].append({
                'type': 'oid',
                'item': nombre,
                'missing': f"Marca '{marca_nombre}' no existe"
            })
            comparison['oids']['conflicts'].append(oid_data)
    
    # 8. IndexFormula
    for formula_data in data.get('index_formulas', []):
        marca_nombre = formula_data.get('marca_nombre')
        modelo_nombre = formula_data.get('modelo_nombre')
        
        try:
            marca = Brand.objects.get(nombre=marca_nombre)
            modelo = None
            if modelo_nombre:
                # Si el modelo es "Genérico" y la marca no es "🌐 Genérico",
                # usar el modelo genérico universal de la marca genérica
                if modelo_nombre == 'Genérico' and marca_nombre != '🌐 Genérico':
                    try:
                        generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                        modelo = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
                    except (Brand.DoesNotExist, OLTModel.DoesNotExist):
                        comparison['missing_dependencies'].append({
                            'type': 'index_formula',
                            'item': formula_data.get('nombre', 'Sin nombre'),
                            'missing': f"Modelo genérico universal no existe (marca '🌐 Genérico' con modelo 'Genérico')"
                        })
                        comparison['index_formulas']['conflicts'].append(formula_data)
                        continue
                else:
                    try:
                        modelo = OLTModel.objects.get(nombre=modelo_nombre, marca=marca)
                    except OLTModel.DoesNotExist:
                        comparison['missing_dependencies'].append({
                            'type': 'index_formula',
                            'item': formula_data.get('nombre', 'Sin nombre'),
                            'missing': f"Modelo '{modelo_nombre}' de marca '{marca_nombre}' no existe"
                        })
                        comparison['index_formulas']['conflicts'].append(formula_data)
                        continue
            
            # Buscar fórmula existente
            # Si el modelo es genérico, buscar también con el modelo genérico universal
            existing = None
            try:
                existing = IndexFormula.objects.get(marca=marca, modelo=modelo)
            except IndexFormula.DoesNotExist:
                # Si no se encuentra y el modelo es genérico, intentar con el modelo genérico universal
                if modelo_nombre == 'Genérico' and marca_nombre != '🌐 Genérico':
                    try:
                        generic_brand = Brand.objects.get(nombre='🌐 Genérico')
                        generic_model = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
                        existing = IndexFormula.objects.filter(marca=marca, modelo=generic_model).first()
                    except (Brand.DoesNotExist, OLTModel.DoesNotExist):
                        pass
            
            if existing:
                current_data = serialize_index_formula_for_backup(existing)
                diff_result = compare_objects(current_data, formula_data)
                
                item_data = {
                    'marca_nombre': marca_nombre,
                    'modelo_nombre': modelo_nombre,
                    'current': current_data,
                    'new': formula_data,
                    'has_changes': diff_result['has_changes'],
                    'differences': diff_result['differences']
                }
                
                if diff_result['has_changes']:
                    comparison['index_formulas']['existing'].append(item_data)
                else:
                    comparison['index_formulas']['existing_no_changes'].append(item_data)
            else:
                comparison['index_formulas']['new'].append(formula_data)
        except Brand.DoesNotExist:
            comparison['missing_dependencies'].append({
                'type': 'index_formula',
                'item': formula_data.get('nombre', 'Sin nombre'),
                'missing': f"Marca '{marca_nombre}' no existe"
            })
            comparison['index_formulas']['conflicts'].append(formula_data)
    
    return comparison


@transaction.atomic
def import_backup_data(backup_data):
    """
    Importa datos desde un diccionario de backup.
    Procesa en orden correcto respetando dependencias.
    """
    if 'data' not in backup_data:
        raise ValueError("Formato de backup inválido: falta clave 'data'")
    
    data = backup_data['data']
    results = {
        'created': {},
        'updated': {},
        'errors': []
    }
    
    # 1. Brands (sin dependencias)
    logger.info("📥 Importando Brands...")
    for brand_data in data.get('brands', []):
        try:
            brand, created = import_brand(brand_data)
            key = 'brands'
            if created:
                results['created'].setdefault(key, []).append(brand.nombre)
            else:
                results['updated'].setdefault(key, []).append(brand.nombre)
        except Exception as e:
            results['errors'].append(f"Error importando Brand '{brand_data.get('nombre')}': {str(e)}")
    
    # 2. OLT Models (depende de Brand)
    logger.info("📥 Importando OLT Models...")
    for model_data in data.get('olt_models', []):
        try:
            model, created = import_olt_model(model_data)
            key = 'olt_models'
            if created:
                results['created'].setdefault(key, []).append(f"{model.marca.nombre} - {model.nombre}")
            else:
                results['updated'].setdefault(key, []).append(f"{model.marca.nombre} - {model.nombre}")
        except Exception as e:
            results['errors'].append(f"Error importando OLTModel '{model_data.get('nombre')}': {str(e)}")
    
    # 3. ConfiguracionSistema
    logger.info("📥 Importando ConfiguracionSistema...")
    for config_data in data.get('configuracion_sistema', []):
        try:
            config, created = import_configuracion_sistema(config_data)
            key = 'configuracion_sistema'
            if created:
                results['created'].setdefault(key, []).append(config.nombre)
            else:
                results['updated'].setdefault(key, []).append(config.nombre)
        except Exception as e:
            results['errors'].append(f"Error importando ConfiguracionSistema '{config_data.get('nombre')}': {str(e)}")
    
    # 4. ConfiguracionSNMP
    logger.info("📥 Importando ConfiguracionSNMP...")
    for config_data in data.get('configuracion_snmp', []):
        try:
            config, created = import_configuracion_snmp(config_data)
            key = 'configuracion_snmp'
            if created:
                results['created'].setdefault(key, []).append(config.nombre)
            else:
                results['updated'].setdefault(key, []).append(config.nombre)
        except Exception as e:
            results['errors'].append(f"Error importando ConfiguracionSNMP '{config_data.get('nombre')}': {str(e)}")
    
    # 5. ZabbixConfiguration
    logger.info("📥 Importando ZabbixConfiguration...")
    for config_data in data.get('zabbix_configuration', []):
        try:
            config, created = import_zabbix_config(config_data)
            key = 'zabbix_configuration'
            if created:
                results['created'].setdefault(key, []).append(config.nombre)
            else:
                results['updated'].setdefault(key, []).append(config.nombre)
        except Exception as e:
            results['errors'].append(f"Error importando ZabbixConfiguration '{config_data.get('nombre')}': {str(e)}")
    
    # 6. OnuStateLookup (depende de Brand)
    logger.info("📥 Importando OnuStateLookup...")
    for lookup_data in data.get('onu_state_lookup', []):
        try:
            lookup, created = import_onu_state_lookup(lookup_data)
            key = 'onu_state_lookup'
            if created:
                results['created'].setdefault(key, []).append(f"{lookup.value} - {lookup.label}")
            else:
                results['updated'].setdefault(key, []).append(f"{lookup.value} - {lookup.label}")
        except Exception as e:
            results['errors'].append(f"Error importando OnuStateLookup '{lookup_data.get('value')}': {str(e)}")
    
    # 7. OIDs (depende de Brand y OLTModel)
    logger.info("📥 Importando OIDs...")
    for oid_data in data.get('oids', []):
        try:
            oid, created = import_oid(oid_data)
            key = 'oids'
            if created:
                results['created'].setdefault(key, []).append(oid.nombre)
            else:
                results['updated'].setdefault(key, []).append(oid.nombre)
        except Exception as e:
            results['errors'].append(f"Error importando OID '{oid_data.get('nombre')}': {str(e)}")
    
    # 8. IndexFormula (depende de Brand y OLTModel)
    logger.info("📥 Importando IndexFormula...")
    for formula_data in data.get('index_formulas', []):
        try:
            formula, created = import_index_formula(formula_data)
            key = 'index_formulas'
            if created:
                results['created'].setdefault(key, []).append(formula.nombre)
            else:
                results['updated'].setdefault(key, []).append(formula.nombre)
        except Exception as e:
            results['errors'].append(f"Error importando IndexFormula '{formula_data.get('nombre')}': {str(e)}")
    
    logger.info("✅ Importación completada")
    return results


# ============================================================================
# VISTAS DE API
# ============================================================================

@extend_schema(
    summary="Exportar backup de configuración",
    description="Exporta todas las configuraciones iniciales (Brands, OLTModels, Configuraciones, OIDs, Formulas) a un archivo JSON. NO incluye OLTs.",
    responses={
        200: OpenApiResponse(
            description="Archivo JSON de backup",
            response={'application/json': {}}
        )
    },
    tags=['Backup']
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def export_backup(request):
    """
    Exporta backup de configuración inicial.
    Retorna un archivo JSON descargable.
    """
    try:
        backup_data = export_backup_data()
        
        # Crear respuesta con archivo JSON
        from django.http import HttpResponse
        response = HttpResponse(
            json.dumps(backup_data, indent=2, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
        
        # Nombre del archivo con timestamp
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f'facho_deluxe_backup_{timestamp}.json'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Error exportando backup: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al exportar backup: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="Comparar backup de configuración",
    description="Compara un archivo JSON de backup con la configuración actual sin realizar cambios. Retorna análisis detallado.",
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'file': {
                    'type': 'string',
                    'format': 'binary',
                    'description': 'Archivo JSON de backup'
                }
            }
        }
    },
    responses={
        200: OpenApiResponse(description="Comparación exitosa"),
        400: OpenApiResponse(description="Error en formato o datos"),
    },
    tags=['Backup']
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def compare_backup(request):
    """
    Compara backup de configuración con la configuración actual sin realizar cambios.
    """
    try:
        # Validar que se envió un archivo
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No se proporcionó archivo. Use el campo "file" para subir el JSON de backup.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        # Validar extensión
        if not file.name.endswith('.json'):
            return Response(
                {'error': 'El archivo debe ser un JSON (.json)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Leer y parsear JSON
        try:
            content = file.read().decode('utf-8')
            backup_data = json.loads(content)
        except json.JSONDecodeError as e:
            return Response(
                {'error': f'Error parseando JSON: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar estructura básica
        if 'data' not in backup_data:
            return Response(
                {'error': 'Formato de backup inválido: falta clave "data"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Comparar datos
        comparison = compare_backup_data(backup_data)
        
        # Calcular resumen
        summary = {}
        total_new = 0
        total_existing = 0
        total_existing_no_changes = 0
        total_conflicts = 0
        
        for key, value in comparison.items():
            if key == 'missing_dependencies':
                continue
            if isinstance(value, dict) and 'new' in value:
                new_count = len(value.get('new', []))
                existing_count = len(value.get('existing', []))
                existing_no_changes_count = len(value.get('existing_no_changes', []))
                conflicts_count = len(value.get('conflicts', []))
                summary[key] = {
                    'new': new_count,
                    'existing': existing_count,
                    'existing_no_changes': existing_no_changes_count,
                    'conflicts': conflicts_count
                }
                total_new += new_count
                total_existing += existing_count
                total_existing_no_changes += existing_no_changes_count
                total_conflicts += conflicts_count
        
        response_data = {
            'success': True,
            'summary': {
                'total_new': total_new,
                'total_existing': total_existing,
                'total_existing_no_changes': total_existing_no_changes,
                'total_conflicts': total_conflicts,
                'missing_dependencies': len(comparison.get('missing_dependencies', [])),
                'by_type': summary
            },
            'details': comparison
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ Error comparando backup: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al comparar backup: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="Importar backup de configuración",
    description="Importa configuración desde un archivo JSON de backup. Actualiza existentes y crea nuevos. Usa nombres únicos, no IDs.",
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'file': {
                    'type': 'string',
                    'format': 'binary',
                    'description': 'Archivo JSON de backup'
                }
            }
        }
    },
    responses={
        200: OpenApiResponse(description="Importación exitosa"),
        400: OpenApiResponse(description="Error en formato o datos"),
    },
    tags=['Backup']
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def import_backup(request):
    """
    Importa backup de configuración desde un archivo JSON.
    """
    try:
        # Validar que se envió un archivo
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No se proporcionó archivo. Use el campo "file" para subir el JSON de backup.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        # Validar extensión
        if not file.name.endswith('.json'):
            return Response(
                {'error': 'El archivo debe ser un JSON (.json)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Leer y parsear JSON
        try:
            content = file.read().decode('utf-8')
            backup_data = json.loads(content)
        except json.JSONDecodeError as e:
            return Response(
                {'error': f'Error parseando JSON: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar estructura básica
        if 'data' not in backup_data:
            return Response(
                {'error': 'Formato de backup inválido: falta clave "data"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Importar datos
        results = import_backup_data(backup_data)
        
        # Preparar respuesta
        total_created = sum(len(v) for v in results['created'].values())
        total_updated = sum(len(v) for v in results['updated'].values())
        total_errors = len(results['errors'])
        
        response_data = {
            'success': True,
            'message': f'Importación completada: {total_created} creados, {total_updated} actualizados, {total_errors} errores',
            'summary': {
                'created': total_created,
                'updated': total_updated,
                'errors': total_errors
            },
            'details': results
        }
        
        if total_errors > 0:
            response_data['warning'] = f'Se encontraron {total_errors} errores durante la importación. Revisa los detalles.'
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ Error importando backup: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al importar backup: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

