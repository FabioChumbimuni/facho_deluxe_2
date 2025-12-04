"""
Sistema de Backup y Restauración para ODF y Hilos ODF

Importa/Exporta desde formato JSON externo que contiene información de ODFs y Hilos.
Formato JSON: { "OLT_ABREV": { "SLOT/PORT": { datos } } }
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
from hosts.models import OLT
from odf_management.models import ODF, ODFHilos

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES DE EXPORTACIÓN
# ============================================================================

def export_odf_data():
    """
    Exporta todos los ODFs y Hilos a formato JSON externo.
    Formato: { "OLT_ABREV": { "SLOT/PORT": { datos } } }
    """
    export_data = {}
    
    # Obtener todos los ODFs con sus hilos
    odfs = ODF.objects.all().select_related('olt').prefetch_related('odfhilos_set')
    
    for odf in odfs:
        olt_abrev = odf.olt.abreviatura
        
        # Inicializar estructura para esta OLT si no existe
        if olt_abrev not in export_data:
            export_data[olt_abrev] = {}
        
        # Procesar cada hilo del ODF
        for hilo in odf.odfhilos_set.all():
            # Formato de clave: "OLT/SLOT/PORT" (ej: "SD-4/14/2")
            key = f"{olt_abrev}/{hilo.slot}/{hilo.port}"
            
            export_data[olt_abrev][key] = {
                "nro_puerto": str(hilo.port) if hilo.port else "",
                "nro_slot": str(hilo.slot) if hilo.slot else "",
                "odf": str(odf.numero_odf) if odf.numero_odf else "",
                "troncal": odf.nombre_troncal,
                "hilo": str(hilo.hilo_numero) if hilo.hilo_numero else "",  # Puede ser numérico o texto
                "vlan": str(hilo.vlan) if hilo.vlan else ""
            }
    
    return export_data


# ============================================================================
# FUNCIONES DE COMPARACIÓN
# ============================================================================

def parse_external_json(json_data):
    """
    Parsea el JSON externo y retorna estructura normalizada.
    
    Args:
        json_data: JSON en formato { "OLT": { "SLOT/PORT": { datos } } }
    
    Returns:
        dict: {
            'olts': { 'OLT_ABREV': OLT_instance },
            'odfs': { ('OLT_ABREV', 'nombre_troncal'): { 'olt': OLT, 'numero_odf': int, 'nombre_troncal': str } },
            'hilos': [ { 'olt_abrev': str, 'slot': int, 'port': int, 'odf_numero': int, 'troncal': str, 'hilo': int, 'vlan': int } ]
        }
    """
    parsed = {
        'olts': {},
        'odfs': {},
        'hilos': []
    }
    
    for olt_abrev, ports_data in json_data.items():
        # Obtener o crear referencia a OLT
        try:
            olt = OLT.objects.get(abreviatura=olt_abrev, is_deleted=False)
            parsed['olts'][olt_abrev] = olt
        except OLT.DoesNotExist:
            logger.warning(f"⚠️ OLT '{olt_abrev}' no existe en el sistema")
            continue
        
        # Procesar cada puerto/hilo
        for port_key, port_data in ports_data.items():
            try:
                # Parsear slot y port desde la clave (ej: "SD-4/14/2") o desde los datos
                parts = port_key.split('/')
                if len(parts) >= 3:
                    slot = int(parts[1]) if parts[1] and parts[1].isdigit() else None
                    port_str = parts[2] if len(parts) > 2 else ""
                    port = int(port_str) if port_str and port_str.isdigit() else None
                else:
                    slot = int(port_data.get('nro_slot', 0)) if port_data.get('nro_slot') and str(port_data.get('nro_slot')).isdigit() else None
                    port_str = port_data.get('nro_puerto', '')
                    port = int(port_str) if port_str and str(port_str).isdigit() else None
                
                # Si no se pudo obtener slot desde la clave, intentar desde los datos
                if slot is None:
                    slot_str = port_data.get('nro_slot', '')
                    slot = int(slot_str) if slot_str and str(slot_str).isdigit() else None
                
                # Validar que slot y port sean válidos (port puede ser 0 si está vacío en el JSON)
                if slot is None:
                    logger.warning(f"⚠️ Hilo sin slot válido en {port_key}")
                    continue
                
                # Si port está vacío, usar 0 como valor por defecto
                if port is None:
                    port = 0
                
                odf_numero = int(port_data.get('odf', 0)) if port_data.get('odf') and str(port_data.get('odf')).isdigit() else None
                troncal = port_data.get('troncal', '').strip()
                # hilo_numero puede ser numérico o texto (ej: "SPLITTER 5")
                hilo_value = port_data.get('hilo', '')
                hilo_numero = str(hilo_value).strip() if hilo_value else None
                vlan = int(port_data.get('vlan', 0)) if port_data.get('vlan') and str(port_data.get('vlan')).isdigit() else None
                
                if not troncal:
                    logger.warning(f"⚠️ Hilo sin troncal en {port_key}")
                    continue
                
                if not hilo_numero:
                    logger.warning(f"⚠️ Hilo sin número de hilo válido en {port_key}")
                    continue
                
                # Crear clave única para ODF (OLT + nombre_troncal)
                odf_key = (olt_abrev, troncal)
                if odf_key not in parsed['odfs']:
                    parsed['odfs'][odf_key] = {
                        'olt': olt,
                        'numero_odf': odf_numero,
                        'nombre_troncal': troncal
                    }
                
                # Agregar hilo
                parsed['hilos'].append({
                    'olt_abrev': olt_abrev,
                    'slot': slot,
                    'port': port,
                    'odf_numero': odf_numero,
                    'troncal': troncal,
                    'hilo_numero': hilo_numero,
                    'vlan': vlan
                })
                
            except (ValueError, KeyError) as e:
                logger.warning(f"⚠️ Error parseando puerto {port_key}: {str(e)}")
                continue
    
    return parsed


def compare_odf_data(json_data):
    """
    Compara el JSON externo con los datos actuales de ODF y Hilos.
    Retorna análisis detallado sin realizar cambios.
    """
    parsed = parse_external_json(json_data)
    
    comparison = {
        'odfs': {'new': [], 'existing': [], 'existing_no_changes': []},
        'hilos': {'new': [], 'existing': [], 'existing_no_changes': []},
        'missing_olts': [],
        'errors': []
    }
    
    # Comparar ODFs
    for odf_key, odf_data in parsed['odfs'].items():
        olt_abrev, nombre_troncal = odf_key
        olt = odf_data['olt']
        numero_odf = odf_data['numero_odf']
        
        try:
            existing_odf = ODF.objects.get(olt=olt, nombre_troncal=nombre_troncal)
            
            # Comparar si hay cambios
            has_changes = False
            differences = {}
            
            if existing_odf.numero_odf != numero_odf:
                has_changes = True
                differences['numero_odf'] = {
                    'current': existing_odf.numero_odf,
                    'new': numero_odf
                }
            
            if has_changes:
                comparison['odfs']['existing'].append({
                    'olt_abrev': olt_abrev,
                    'nombre_troncal': nombre_troncal,
                    'current': {
                        'numero_odf': existing_odf.numero_odf,
                        'nombre_troncal': existing_odf.nombre_troncal
                    },
                    'new': {
                        'numero_odf': numero_odf,
                        'nombre_troncal': nombre_troncal
                    },
                    'has_changes': True,
                    'differences': differences
                })
            else:
                comparison['odfs']['existing_no_changes'].append({
                    'olt_abrev': olt_abrev,
                    'nombre_troncal': nombre_troncal,
                    'numero_odf': numero_odf
                })
                
        except ODF.DoesNotExist:
            comparison['odfs']['new'].append({
                'olt_abrev': olt_abrev,
                'numero_odf': numero_odf,
                'nombre_troncal': nombre_troncal
            })
    
    # Comparar Hilos
    for hilo_data in parsed['hilos']:
        olt_abrev = hilo_data['olt_abrev']
        troncal = hilo_data['troncal']
        slot = hilo_data['slot']
        port = hilo_data['port']
        hilo_numero = hilo_data['hilo_numero']
        vlan = hilo_data['vlan']
        
        # Buscar ODF
        try:
            olt = parsed['olts'][olt_abrev]
            odf = ODF.objects.get(olt=olt, nombre_troncal=troncal)
        except (KeyError, ODF.DoesNotExist):
            # ODF no existe aún, se creará junto con el hilo
            comparison['hilos']['new'].append({
                'olt_abrev': olt_abrev,
                'troncal': troncal,
                'slot': slot,
                'port': port,
                'hilo_numero': hilo_numero,
                'vlan': vlan,
                'odf_numero': hilo_data['odf_numero']
            })
            continue
        
        # Buscar hilo existente
        try:
            existing_hilo = ODFHilos.objects.get(
                odf=odf,
                slot=slot,
                port=port,
                hilo_numero=hilo_numero
            )
            
            # Comparar si hay cambios
            has_changes = False
            differences = {}
            
            if existing_hilo.vlan != vlan:
                has_changes = True
                differences['vlan'] = {
                    'current': existing_hilo.vlan,
                    'new': vlan
                }
            
            if has_changes:
                comparison['hilos']['existing'].append({
                    'olt_abrev': olt_abrev,
                    'troncal': troncal,
                    'slot': slot,
                    'port': port,
                    'hilo_numero': hilo_numero,
                    'current': {
                        'vlan': existing_hilo.vlan,
                        'slot': existing_hilo.slot,
                        'port': existing_hilo.port,
                        'hilo_numero': existing_hilo.hilo_numero
                    },
                    'new': {
                        'vlan': vlan,
                        'slot': slot,
                        'port': port,
                        'hilo_numero': hilo_numero
                    },
                    'has_changes': True,
                    'differences': differences
                })
            else:
                comparison['hilos']['existing_no_changes'].append({
                    'olt_abrev': olt_abrev,
                    'troncal': troncal,
                    'slot': slot,
                    'port': port,
                    'hilo_numero': hilo_numero,
                    'vlan': vlan
                })
                
        except ODFHilos.DoesNotExist:
            comparison['hilos']['new'].append({
                'olt_abrev': olt_abrev,
                'troncal': troncal,
                'slot': slot,
                'port': port,
                'hilo_numero': hilo_numero,
                'vlan': vlan,
                'odf_numero': hilo_data['odf_numero']
            })
    
    # Verificar OLTs faltantes
    for olt_abrev in json_data.keys():
        if olt_abrev not in parsed['olts']:
            comparison['missing_olts'].append(olt_abrev)
    
    return comparison


# ============================================================================
# FUNCIONES DE IMPORTACIÓN
# ============================================================================

@transaction.atomic
def import_odf_data(json_data, replace_existing=False):
    """
    Importa ODFs y Hilos desde JSON externo.
    Crea ODFs si no existen y crea/actualiza hilos.
    
    Args:
        json_data: JSON con los datos a importar
        replace_existing: Si es True, elimina todos los ODFs y Hilos existentes antes de importar
    """
    parsed = parse_external_json(json_data)
    
    results = {
        'odfs_created': [],
        'odfs_updated': [],
        'odfs_deleted': [],
        'hilos_created': [],
        'hilos_updated': [],
        'hilos_deleted': [],
        'errors': []
    }
    
    # Si replace_existing es True, eliminar todos los ODFs y Hilos existentes
    if replace_existing:
        # Obtener OLTs que aparecen en el JSON
        olt_ids = [olt.id for olt in parsed['olts'].values()]
        
        # Eliminar hilos de esas OLTs
        hilos_deleted = ODFHilos.objects.filter(odf__olt_id__in=olt_ids).delete()
        results['hilos_deleted'] = [f"{hilos_deleted[0]} hilos eliminados"]
        
        # Eliminar ODFs de esas OLTs
        odfs_deleted = ODF.objects.filter(olt_id__in=olt_ids).delete()
        results['odfs_deleted'] = [f"{odfs_deleted[0]} ODFs eliminados"]
        
        logger.info(f"🔄 Modo reemplazo: Eliminados {hilos_deleted[0]} hilos y {odfs_deleted[0]} ODFs")
    
    # 1. Crear/actualizar ODFs
    for odf_key, odf_data in parsed['odfs'].items():
        olt_abrev, nombre_troncal = odf_key
        olt = odf_data['olt']
        numero_odf = odf_data['numero_odf']
        
        try:
            odf, created = ODF.objects.get_or_create(
                olt=olt,
                nombre_troncal=nombre_troncal,
                defaults={
                    'numero_odf': numero_odf,
                    'descripcion': f'Importado desde backup - {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
                }
            )
            
            if created:
                results['odfs_created'].append(f"{olt_abrev} - {nombre_troncal}")
            else:
                # Solo actualizar si hay cambios
                if odf.numero_odf != numero_odf:
                    odf.numero_odf = numero_odf
                    odf.save()
                    results['odfs_updated'].append(f"{olt_abrev} - {nombre_troncal}")
                    
        except Exception as e:
            results['errors'].append(f"Error importando ODF '{nombre_troncal}' de OLT '{olt_abrev}': {str(e)}")
    
    # 2. Crear/actualizar Hilos
    for hilo_data in parsed['hilos']:
        olt_abrev = hilo_data['olt_abrev']
        troncal = hilo_data['troncal']
        slot = hilo_data['slot']
        port = hilo_data['port']
        hilo_numero = hilo_data['hilo_numero']
        vlan = hilo_data['vlan']
        
        try:
            # Obtener ODF (debe existir después del paso 1)
            olt = parsed['olts'][olt_abrev]
            odf = ODF.objects.get(olt=olt, nombre_troncal=troncal)
            
            # Crear o actualizar hilo
            hilo, created = ODFHilos.objects.get_or_create(
                odf=odf,
                slot=slot,
                port=port,
                hilo_numero=hilo_numero,
                defaults={
                    'vlan': vlan,
                    'estado': 'disabled',  # Por defecto disabled, se activará si aparece en Zabbix
                    'origen': 'manual',
                    'en_zabbix': False
                }
            )
            
            if created:
                results['hilos_created'].append(f"{olt_abrev}/{slot}/{port} - Hilo {hilo_numero}")
            else:
                # Solo actualizar si hay cambios
                if hilo.vlan != vlan:
                    hilo.vlan = vlan
                    hilo.save()
                    results['hilos_updated'].append(f"{olt_abrev}/{slot}/{port} - Hilo {hilo_numero}")
                    
        except ODF.DoesNotExist:
            results['errors'].append(f"ODF '{troncal}' no existe para OLT '{olt_abrev}'")
        except Exception as e:
            results['errors'].append(f"Error importando hilo {olt_abrev}/{slot}/{port}: {str(e)}")
    
    return results


# ============================================================================
# VISTAS DE API
# ============================================================================

@extend_schema(
    summary="Exportar ODF y Hilos",
    description="Exporta todos los ODFs y Hilos ODF a formato JSON externo.",
    responses={
        200: OpenApiResponse(
            description="Archivo JSON de backup",
            response={'application/json': {}}
        )
    },
    tags=['ODF Backup']
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def export_odf_backup(request):
    """
    Exporta backup de ODFs y Hilos en formato JSON externo.
    """
    try:
        export_data = export_odf_data()
        
        # Crear respuesta con archivo JSON
        from django.http import HttpResponse
        response = HttpResponse(
            json.dumps(export_data, indent=2, ensure_ascii=False),
            content_type='application/json; charset=utf-8'
        )
        
        # Nombre del archivo con timestamp
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        filename = f'odf_hilos_backup_{timestamp}.json'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Error exportando backup ODF: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al exportar backup ODF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="Comparar ODF y Hilos",
    description="Compara un archivo JSON externo con los ODFs y Hilos actuales sin realizar cambios.",
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'file': {
                    'type': 'string',
                    'format': 'binary',
                    'description': 'Archivo JSON de backup ODF'
                }
            }
        }
    },
    responses={
        200: OpenApiResponse(description="Comparación exitosa"),
        400: OpenApiResponse(description="Error en formato o datos"),
    },
    tags=['ODF Backup']
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def compare_odf_backup(request):
    """
    Compara backup de ODFs y Hilos con la configuración actual sin realizar cambios.
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
            json_data = json.loads(content)
        except json.JSONDecodeError as e:
            return Response(
                {'error': f'Error parseando JSON: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Comparar datos
        comparison = compare_odf_data(json_data)
        
        # Calcular resumen
        total_odfs_new = len(comparison['odfs']['new'])
        total_odfs_existing = len(comparison['odfs']['existing'])
        total_odfs_no_changes = len(comparison['odfs']['existing_no_changes'])
        total_hilos_new = len(comparison['hilos']['new'])
        total_hilos_existing = len(comparison['hilos']['existing'])
        total_hilos_no_changes = len(comparison['hilos']['existing_no_changes'])
        
        response_data = {
            'success': True,
            'summary': {
                'odfs': {
                    'new': total_odfs_new,
                    'existing': total_odfs_existing,
                    'existing_no_changes': total_odfs_no_changes
                },
                'hilos': {
                    'new': total_hilos_new,
                    'existing': total_hilos_existing,
                    'existing_no_changes': total_hilos_no_changes
                },
                'missing_olts': len(comparison.get('missing_olts', [])),
                'errors': len(comparison.get('errors', []))
            },
            'details': comparison
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ Error comparando backup ODF: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al comparar backup ODF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    summary="Importar ODF y Hilos",
    description="Importa ODFs y Hilos desde un archivo JSON externo. Crea ODFs si no existen.",
    request={
        'multipart/form-data': {
            'type': 'object',
            'properties': {
                'file': {
                    'type': 'string',
                    'format': 'binary',
                    'description': 'Archivo JSON de backup ODF'
                }
            }
        }
    },
    responses={
        200: OpenApiResponse(description="Importación exitosa"),
        400: OpenApiResponse(description="Error en formato o datos"),
    },
    tags=['ODF Backup']
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def import_odf_backup(request):
    """
    Importa backup de ODFs y Hilos desde un archivo JSON externo.
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
            json_data = json.loads(content)
        except json.JSONDecodeError as e:
            return Response(
                {'error': f'Error parseando JSON: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Obtener parámetro replace_existing
        replace_existing = request.POST.get('replace_existing', 'false').lower() == 'true'
        
        # Importar datos
        results = import_odf_data(json_data, replace_existing=replace_existing)
        
        # Preparar respuesta
        total_odfs_created = len(results['odfs_created'])
        total_odfs_updated = len(results['odfs_updated'])
        total_odfs_deleted = len(results.get('odfs_deleted', []))
        total_hilos_created = len(results['hilos_created'])
        total_hilos_updated = len(results['hilos_updated'])
        total_hilos_deleted = len(results.get('hilos_deleted', []))
        total_errors = len(results['errors'])
        
        # Construir mensaje
        message_parts = []
        if replace_existing:
            if total_odfs_deleted > 0:
                message_parts.append(f"{results['odfs_deleted'][0]}")
            if total_hilos_deleted > 0:
                message_parts.append(f"{results['hilos_deleted'][0]}")
        if total_odfs_created > 0:
            message_parts.append(f"{total_odfs_created} ODFs creados")
        if total_odfs_updated > 0:
            message_parts.append(f"{total_odfs_updated} ODFs actualizados")
        if total_hilos_created > 0:
            message_parts.append(f"{total_hilos_created} hilos creados")
        if total_hilos_updated > 0:
            message_parts.append(f"{total_hilos_updated} hilos actualizados")
        if total_errors > 0:
            message_parts.append(f"{total_errors} errores")
        
        message = 'Importación completada: ' + ', '.join(message_parts) if message_parts else 'Importación completada'
        
        response_data = {
            'success': True,
            'message': message,
            'summary': {
                'odfs_created': total_odfs_created,
                'odfs_updated': total_odfs_updated,
                'odfs_deleted': total_odfs_deleted,
                'hilos_created': total_hilos_created,
                'hilos_updated': total_hilos_updated,
                'hilos_deleted': total_hilos_deleted,
                'errors': total_errors,
                'replace_existing': replace_existing
            },
            'details': results
        }
        
        if total_errors > 0:
            response_data['warning'] = f'Se encontraron {total_errors} errores durante la importación. Revisa los detalles.'
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"❌ Error importando backup ODF: {str(e)}", exc_info=True)
        return Response(
            {'error': f'Error al importar backup ODF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

