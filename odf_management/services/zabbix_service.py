import requests
import json
import logging
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.utils import timezone
from ..models import ODF, ODFHilos

logger = logging.getLogger(__name__)


class ZabbixService:
    """
    Servicio para conectar con Zabbix y obtener información de hilos ODF.
    Utiliza token de autenticación para consultar un item master.
    """
    
    def __init__(self, zabbix_url: str, token: str):
        """
        Inicializa el servicio de Zabbix.
        
        Args:
            zabbix_url: URL del servidor Zabbix (ej: http://zabbix.example.com/api_jsonrpc.php)
            token: Token de autenticación de Zabbix
        """
        self.zabbix_url = zabbix_url
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
        })

    def _make_request(self, method: str, params: Dict[str, Any]) -> Optional[Dict]:
        """
        Hace una petición a la API de Zabbix.
        Intenta diferentes formatos de autenticación según la versión de Zabbix.
        
        Args:
            method: Método de la API de Zabbix
            params: Parámetros de la petición
            
        Returns:
            Respuesta de Zabbix o None si hay error
        """
        # Intentar primero con token en headers (Zabbix 6.0+)
        headers_payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }
        
        headers_with_token = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
        
        try:
            # Intento 1: Token en headers
            response = self.session.post(
                self.zabbix_url,
                data=json.dumps(headers_payload),
                headers=headers_with_token,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if 'error' not in result:
                return result.get('result')
            
            logger.debug(f"Intento con headers falló: {result.get('error')}")
            
        except Exception as e:
            logger.debug(f"Intento con headers falló: {e}")
        
        # Intento 2: Token en parámetros (Zabbix 5.x+)
        params_with_token = params.copy()
        params_with_token['auth'] = self.token
        
        params_payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params_with_token,
            "id": 1
        }
        
        try:
            response = self.session.post(
                self.zabbix_url,
                data=json.dumps(params_payload),
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if 'error' not in result:
                return result.get('result')
            
            logger.debug(f"Intento con params falló: {result.get('error')}")
            
        except Exception as e:
            logger.debug(f"Intento con params falló: {e}")
        
        # Intento 3: Token en campo auth (Zabbix 4.x)
        auth_payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "auth": self.token,
            "id": 1
        }
        
        try:
            response = self.session.post(
                self.zabbix_url,
                data=json.dumps(auth_payload),
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if 'error' in result:
                logger.error(f"Error en Zabbix API (todos los métodos fallaron): {result['error']}")
                return None
                
            return result.get('result')
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de conexión con Zabbix: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando respuesta JSON: {e}")
            return None

    def get_item_master_data(self, item_key: str, host_name: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Obtiene datos del item master de Zabbix.
        Para items master sin historial, obtiene el valor actual.
        
        Args:
            item_key: Clave del item en Zabbix (ej: "port.descover.walk")
            host_name: Nombre del host (opcional, si no se especifica busca en todos)
            
        Returns:
            Lista de datos del item o None si hay error
        """
        params = {
            "output": ["itemid", "name", "key_", "hostid", "lastvalue", "lastclock"],
            "search": {
                "key_": item_key
            },
            "searchWildcards": True,
            "selectHosts": ["host", "name"]
        }
        
        if host_name:
            params["host"] = host_name
            
        items = self._make_request("item.get", params)
        
        if not items:
            logger.warning(f"No se encontraron items con clave: {item_key}")
            return None
        
        # Para items master, SIEMPRE intentar obtener valor del historial reciente
        for item in items:
            logger.info(f"Item {item['itemid']}: Intentando obtener datos del historial reciente...")
            current_value = self.get_current_item_value(item['itemid'])
            
            if current_value:
                # Verificar si los datos del historial son más completos
                current_admin_lines = len([line for line in current_value.split('\n') if '.1.3.6.1.2.1.2.2.1.7.' in line])
                
                if item.get('lastvalue'):
                    cached_admin_lines = len([line for line in item['lastvalue'].split('\n') if '.1.3.6.1.2.1.2.2.1.7.' in line])
                    
                    if current_admin_lines > cached_admin_lines:
                        logger.info(f"✅ Historial más completo: {current_admin_lines} vs {cached_admin_lines} líneas admin")
                        item['lastvalue'] = current_value
                        item['lastclock'] = str(int(timezone.now().timestamp()))
                    elif current_admin_lines > 0 and cached_admin_lines == 0:
                        logger.info(f"✅ Historial tiene estados admin, cache no: {current_admin_lines} líneas")
                        item['lastvalue'] = current_value
                        item['lastclock'] = str(int(timezone.now().timestamp()))
                    else:
                        logger.info(f"ℹ️ Usando cache: {cached_admin_lines} líneas admin (historial: {current_admin_lines})")
                else:
                    logger.info(f"✅ Sin cache, usando historial: {current_admin_lines} líneas admin")
                    item['lastvalue'] = current_value
                    item['lastclock'] = str(int(timezone.now().timestamp()))
            elif not item.get('lastvalue'):
                logger.warning(f"❌ Sin datos en historial ni cache para item {item['itemid']}")
            
        return items

    def get_current_item_value(self, item_id: str) -> Optional[str]:
        """
        Obtiene el valor actual de un item master ejecutándolo en tiempo real.
        Para items sin historial, fuerza la ejecución y obtiene el resultado.
        
        Args:
            item_id: ID del item en Zabbix
            
        Returns:
            Valor actual del item o None si no hay datos
        """
        try:
            logger.info(f"Ejecutando item master {item_id} en tiempo real...")
            
            # Método 1: Intentar ejecutar el item usando task.create (Zabbix 6.0+)
            try:
                task_params = {
                    "type": 6,  # Task type: check now
                    "request": {
                        "itemid": item_id
                    }
                }
                
                task_result = self._make_request("task.create", task_params)
                
                if task_result:
                    logger.info(f"Tarea de ejecución creada para item {item_id}")
                    
                    # Esperar un poco y luego intentar obtener el resultado
                    import time
                    time.sleep(3)  # Esperar 3 segundos
                    
                    # Intentar obtener el valor después de la ejecución
                    params = {
                        "output": ["itemid", "lastvalue", "prevvalue", "lastclock"],
                        "itemids": [item_id]
                    }
                    
                    items = self._make_request("item.get", params)
                    
                    if items and len(items) > 0:
                        item = items[0]
                        value = item.get('lastvalue') or item.get('prevvalue')
                        if value:
                            logger.info(f"Valor obtenido después de ejecución: {len(value)} caracteres")
                            return value
                            
            except Exception as e:
                logger.debug(f"Método task.create falló: {e}")
            
            # Método 2: PRIORIZAR HISTORIAL RECIENTE (últimas 24 horas)
            try:
                from django.utils import timezone as django_timezone
                from datetime import timedelta
                
                # Calcular timestamp de hace 24 horas
                time_from = int((django_timezone.now() - timedelta(hours=24)).timestamp())
                
                params = {
                    "output": "extend",
                    "itemids": [item_id],
                    "sortfield": "clock", 
                    "sortorder": "DESC",
                    "limit": 20,  # Obtener más registros para encontrar datos válidos
                    "history": 4,  # Tipo 4 = text
                    "time_from": time_from
                }
                
                history = self._make_request("history.get", params)
                
                if history and len(history) > 0:
                    logger.info(f"Encontrados {len(history)} registros en historial reciente")
                    
                    # Buscar el valor más reciente con datos de estado administrativo
                    for record in history:
                        value = record.get('value')
                        if value and value.strip():
                            # Verificar que contiene datos de estado administrativo
                            if '.1.3.6.1.2.1.2.2.1.7.' in value and 'GPON' in value:
                                clock = record.get('clock', 0)
                                from datetime import datetime
                                timestamp = datetime.fromtimestamp(int(clock)) if clock else 'desconocido'
                                logger.info(f"✅ Valor con estados admin encontrado en historial: {len(value)} chars, timestamp: {timestamp}")
                                return value
                            else:
                                logger.debug(f"Registro sin estados administrativos completos, continuando...")
                                
                    # Si no encontramos con estados administrativos, usar el más reciente
                    if history[0].get('value'):
                        value = history[0]['value']
                        clock = history[0].get('clock', 0)
                        from datetime import datetime
                        timestamp = datetime.fromtimestamp(int(clock)) if clock else 'desconocido'
                        logger.info(f"ℹ️ Usando valor más reciente sin filtro: {len(value)} chars, timestamp: {timestamp}")
                        return value
                        
            except Exception as e:
                logger.debug(f"Método history.get reciente falló: {e}")
                
            # Método 2b: Intentar con history.get simple (fallback)
            try:
                params = {
                    "output": "extend",
                    "itemids": [item_id],
                    "sortfield": "clock", 
                    "sortorder": "DESC",
                    "limit": 10,  # Obtener más registros
                    "history": 4  # Tipo 4 = text
                }
                
                history = self._make_request("history.get", params)
                
                if history and len(history) > 0:
                    # Buscar el valor más reciente no vacío
                    for record in history:
                        value = record.get('value')
                        if value and value.strip():
                            logger.info(f"Valor encontrado en history (fallback): {len(value)} caracteres")
                            return value
                            
            except Exception as e:
                logger.debug(f"Método history.get falló: {e}")
            
            # Método 3: Intentar con diferentes tipos de history
            for history_type in [0, 1, 3, 4]:  # numeric float, character, numeric unsigned, text
                try:
                    params = {
                        "output": "extend",
                        "itemids": [item_id],
                        "sortfield": "clock",
                        "sortorder": "DESC", 
                        "limit": 1,
                        "history": history_type
                    }
                    
                    history = self._make_request("history.get", params)
                    
                    if history and len(history) > 0:
                        value = history[0].get('value')
                        if value:
                            logger.info(f"Valor encontrado con history type {history_type}: {len(str(value))} caracteres")
                            return str(value)
                            
                except Exception as e:
                    logger.debug(f"History type {history_type} falló: {e}")
                    continue
            
            logger.warning(f"No se pudo obtener valor para item master {item_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error obteniendo valor del item master {item_id}: {e}")
            return None

    def get_history_data(self, item_id: str, time_from: Optional[int] = None) -> Optional[List[Dict]]:
        """
        Obtiene el historial de datos de un item específico.
        
        Args:
            item_id: ID del item en Zabbix
            time_from: Timestamp desde cuando obtener datos (opcional)
            
        Returns:
            Lista de datos históricos o None si hay error
        """
        params = {
            "output": "extend",
            "itemids": [item_id],
            "sortfield": "clock",
            "sortorder": "DESC",
            "limit": 100
        }
        
        if time_from:
            params["time_from"] = time_from
            
        history = self._make_request("history.get", params)
        return history

    def parse_odf_data(self, zabbix_data: str, olt=None) -> List[Dict]:
        """
        Parsea los datos completos del item master desde Zabbix.
        Procesa interfaces GPON, descripciones y estados administrativos.
        
        El OID de estado administrativo se obtiene dinámicamente según la OLT.
        
        Args:
            zabbix_data: Datos en formato texto crudo desde Zabbix (SNMP walk completo)
            olt: Instancia de OLT (necesaria para obtener la fórmula y OID)
            
        Returns:
            Lista de diccionarios con información completa de puertos
        """
        try:
            # Obtener los 3 OIDs de Zabbix para esta OLT
            from oids.models import OID
            
            # OIDs por defecto (estándar)
            interface_name_oid = ".1.3.6.1.2.1.31.1.1.1.1"
            description_oid = ".1.3.6.1.2.1.31.1.1.1.18"
            admin_status_oid = ".1.3.6.1.2.1.2.2.1.7"
            
            if olt:
                zabbix_oids = OID.get_zabbix_oids_for_olt(olt)
                
                if zabbix_oids['interface']:
                    interface_name_oid = zabbix_oids['interface'].oid
                    logger.debug(f"OID Interface para {olt.abreviatura}: {interface_name_oid}")
                
                if zabbix_oids['description']:
                    description_oid = zabbix_oids['description'].oid
                    logger.debug(f"OID Description para {olt.abreviatura}: {description_oid}")
                
                if zabbix_oids['state']:
                    admin_status_oid = zabbix_oids['state'].oid
                    logger.debug(f"OID Admin State para {olt.abreviatura}: {admin_status_oid}")
            
            # Diccionarios para almacenar datos por SNMP index
            interfaces = {}      # OID dinámico - Nombres de interfaz
            descriptions = {}    # OID dinámico - Descripciones
            admin_states = {}    # OID dinámico - Estados administrativos
            
            # Procesar líneas del SNMP walk
            lines = zabbix_data.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or '=' not in line:
                    continue
                
                try:
                    oid_part = line.split('=')[0].strip()
                    value_part = line.split('=')[1].strip()
                    
                    # Extraer SNMP index
                    snmp_index = oid_part.split('.')[-1]
                    
                    # Solo procesar interfaces GPON (índices grandes, típicamente > 4194000000)
                    if not snmp_index.isdigit() or int(snmp_index) < 4194000000:
                        continue
                    
                    # Interface names (OID dinámico) - Solo GPON
                    if interface_name_oid in oid_part and 'STRING:' in value_part and 'GPON' in value_part:
                        interface_name = value_part.replace('STRING:', '').strip().strip('"')
                        interfaces[snmp_index] = interface_name
                        
                    # Descriptions (OID dinámico)
                    elif description_oid in oid_part and 'STRING:' in value_part:
                        desc = value_part.replace('STRING:', '').strip().strip('"')
                        descriptions[snmp_index] = desc
                        
                    # Administrative status (OID dinámico)
                    elif admin_status_oid in oid_part and 'INTEGER:' in value_part:
                        admin_status = int(value_part.split('INTEGER:')[1].strip())
                        admin_states[snmp_index] = admin_status
                        
                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parseando línea SNMP: {line} - {e}")
                    continue
            
            # Combinar datos y crear lista de puertos
            parsed_ports = []
            
            for snmp_index, interface_name in interfaces.items():
                try:
                    # Obtener descripción y estado administrativo para este puerto
                    description = descriptions.get(snmp_index, "")
                    admin_status = admin_states.get(snmp_index)
                    
                    # Parsear información básica del puerto
                    port_info = self._parse_interface_description(description, snmp_index, olt)
                    
                    if port_info:
                        # Agregar interface_name real desde Zabbix
                        port_info['interface_name'] = interface_name
                        # Agregar estado administrativo
                        port_info['estado_administrativo'] = admin_status
                        
                        parsed_ports.append(port_info)
                        
                except Exception as e:
                    logger.debug(f"Error procesando puerto {snmp_index}: {e}")
                    continue
                    
            logger.info(f"Parseados {len(parsed_ports)} puertos desde datos SNMP (interfaces: {len(interfaces)}, descripciones: {len(descriptions)}, estados admin: {len(admin_states)})")
            return parsed_ports
            
        except Exception as e:
            logger.error(f"Error parseando datos SNMP desde Zabbix: {e}")
            return []

    def _parse_interface_description(self, description: str, snmp_index: str, olt=None) -> Optional[Dict]:
        """
        Parsea datos básicos de una interfaz GPON desde Zabbix.
        Solo extrae slot, port y descripción cruda.
        
        Args:
            description: Descripción de la interfaz desde Zabbix
            snmp_index: Índice SNMP de la interfaz
            olt: Instancia de OLT (necesaria para obtener la fórmula)
            
        Returns:
            Diccionario con datos básicos o None si no se puede parsear
        """
        try:
            # Obtener fórmula desde la OLT según su marca/modelo
            if not olt:
                logger.debug(f"No se proporcionó OLT para calcular slot/port del índice {snmp_index}")
                return None
                
            formula = self._get_formula_from_olt(olt)
            
            if not formula:
                logger.debug(f"No hay fórmula para OLT {olt.abreviatura} (marca: {olt.marca}, modelo: {olt.modelo})")
                return None
            
            components = formula.calculate_components(snmp_index)
            
            if not components or components['slot'] is None:
                logger.debug(f"No se pudo calcular slot/port para índice {snmp_index}")
                return None
                
            slot = components['slot']
            port = components['port']
            
            # Limpiar descripción básica
            desc_limpia = description.strip() if description else ""
            
            return {
                'snmp_index': snmp_index,
                'slot': slot,
                'port': port,
                'descripcion_zabbix': desc_limpia,
                'interface_name': f"GPON 0/{slot}/{port}"  # Formato estándar
            }
            
        except Exception as e:
            logger.error(f"Error parseando datos básicos para índice '{snmp_index}': {e}")
            return None

    def sync_zabbix_ports(self, item_key: str = "port.descover.walk") -> Dict[str, int]:
        """
        Sincroniza los datos básicos de puertos desde Zabbix.
        Solo captura SNMP index, slot, port y descripción cruda.
        
        Args:
            item_key: Clave del item master en Zabbix
            
        Returns:
            Diccionario con estadísticas de sincronización
        """
        stats = {
            'ports_created': 0,
            'ports_updated': 0,
            'ports_made_available': 0,
            'ports_disabled': 0,
            'hilos_enabled': 0,
            'hilos_disabled': 0,
            'errors': 0
        }
        
        logger.info(f"Iniciando sincronización de puertos desde Zabbix (item: {item_key})")
        
        # Obtener datos desde Zabbix
        items = self.get_item_master_data(item_key)
        
        if not items:
            logger.error("No se pudieron obtener datos del item master")
            stats['errors'] += 1
            return stats
            
        # Procesar cada item encontrado
        for item in items:
            try:
                last_value = item.get('lastvalue')
                if not last_value:
                    continue
                
                # Obtener el host/OLT desde el item de Zabbix PRIMERO
                hosts = item.get('hosts', [])
                if not hosts:
                    logger.warning(f"Item {item['itemid']} no tiene hosts asociados")
                    continue
                    
                host_name = hosts[0].get('host', '')
                
                # Buscar la OLT en Django por nombre de host
                from hosts.models import OLT
                try:
                    olt = OLT.objects.get(abreviatura=host_name)
                except OLT.DoesNotExist:
                    logger.warning(f"No se encontró OLT con abreviatura '{host_name}'")
                    continue
                    
                # Parsear datos del item con la OLT
                ports_data = self.parse_odf_data(last_value, olt)
                
                if not ports_data:
                    logger.warning(f"No se pudieron parsear datos del item {item['itemid']} para OLT {olt.abreviatura}")
                    continue
                
                # Procesar cada puerto
                port_stats = self._sync_olt_ports(olt, ports_data)
                
                # Acumular estadísticas
                for key, value in port_stats.items():
                    stats[key] += value
                        
            except Exception as e:
                logger.error(f"Error procesando item {item.get('itemid')}: {e}")
                stats['errors'] += 1
                
        logger.info(f"Sincronización de puertos completada: {stats}")
        return stats

    def _sync_olt_ports(self, olt, ports_data: List[Dict]) -> Dict[str, int]:
        """
        Sincroniza los puertos de una OLT específica con lógica inteligente:
        - No borra puertos, solo los marca como no disponibles
        - Actualiza solo descripcion_zabbix si cambia
        - Mantiene configuración completa al reactivar
        
        Args:
            olt: Instancia de la OLT
            ports_data: Lista de datos de puertos básicos
            
        Returns:
            Estadísticas de sincronización para esta OLT
        """
        stats = {
            'ports_created': 0,
            'ports_updated': 0,
            'ports_made_available': 0,
            'ports_disabled': 0,
            'hilos_enabled': 0,
            'hilos_disabled': 0,
            'errors': 0
        }
        
        try:
            from ..models import ZabbixPortData
            
            # 1. Obtener puertos existentes en BD para esta OLT
            existing_ports = ZabbixPortData.objects.filter(olt=olt)
            existing_snmp_indexes = set(existing_ports.values_list('snmp_index', flat=True))
            
            # Los estados administrativos ya están incluidos en ports_data
            
            # 2. Procesar puertos actuales de Zabbix
            current_snmp_indexes = []
            
            for port_data in ports_data:
                try:
                    current_snmp_indexes.append(port_data['snmp_index'])
                    
                    # El estado administrativo ya viene en port_data
                    admin_status = port_data.get('estado_administrativo')
                    
                    # Obtener o crear puerto
                    port, created = ZabbixPortData.objects.get_or_create(
                        olt=olt,
                        snmp_index=port_data['snmp_index'],
                        defaults={
                            'slot': port_data['slot'],
                            'port': port_data['port'],
                            'descripcion_zabbix': port_data['descripcion_zabbix'],
                            'interface_name': port_data['interface_name'],
                            'disponible': True,
                            'estado_administrativo': admin_status,
                            'last_sync': timezone.now()
                        }
                    )
                    
                    if created:
                        stats['ports_created'] += 1
                        logger.debug(f"Puerto creado: {port}")
                    else:
                        # Puerto existente - verificar cambios
                        updated = False
                        reactivated = False
                        
                        # SOLO marcar como disponible si realmente estaba deshabilitado
                        if not port.disponible:
                            port.disponible = True
                            reactivated = True
                            stats['ports_made_available'] += 1
                            logger.info(f"Puerto vuelve a estar disponible: {port}")
                        
                        # SOLO actualizar descripcion_zabbix si cambió
                        if port.descripcion_zabbix != port_data['descripcion_zabbix']:
                            port.descripcion_zabbix = port_data['descripcion_zabbix']
                            updated = True
                            logger.debug(f"Descripción actualizada: {port}")
                        
                        # Actualizar estado administrativo si cambió
                        if port.estado_administrativo != admin_status:
                            port.estado_administrativo = admin_status
                            updated = True
                            logger.debug(f"Estado administrativo actualizado: {port} -> {admin_status}")
                        
                        # Slot, port e interface_name NUNCA cambian (son fijos)
                        # Solo actualizar last_sync
                        if updated or reactivated:
                            port.last_sync = timezone.now()
                            port.save()
                            if updated:
                                stats['ports_updated'] += 1
                            
                except Exception as e:
                    logger.error(f"Error procesando puerto {port_data}: {e}")
                    stats['errors'] += 1
            
            # 3. Marcar como no disponibles solo los puertos que desaparecieron de Zabbix
            current_snmp_indexes_set = set(current_snmp_indexes)
            disappeared_indexes = existing_snmp_indexes - current_snmp_indexes_set
            
            if disappeared_indexes:
                # Marcar como no disponibles solo los que desaparecieron
                ZabbixPortData.objects.filter(
                    olt=olt, 
                    snmp_index__in=disappeared_indexes
                ).update(disponible=False)
                
                stats['ports_disabled'] = len(disappeared_indexes)
                logger.info(f"Puertos marcados como no disponibles (desaparecieron de Zabbix): {len(disappeared_indexes)}")
            else:
                stats['ports_disabled'] = 0
            
            # 4. Actualizar estado de ODFHilos basado en disponibilidad
            self._update_odf_hilos_status(olt, current_snmp_indexes, stats)
            
            # 5. Sincronizar operativo_noc después de actualizar
            self._sync_operativo_noc_states(olt, stats)
                    
        except Exception as e:
            logger.error(f"Error sincronizando puertos de OLT {olt.abreviatura}: {e}")
            stats['errors'] += 1
            
        return stats
    
    def _update_odf_hilos_status(self, olt, current_snmp_indexes: List[str], stats: Dict[str, int]):
        """
        Actualiza el estado enabled/disabled de ODFHilos basado en presencia en Zabbix.
        
        Args:
            olt: Instancia del modelo OLT
            current_snmp_indexes: Lista de SNMP indexes actualmente en Zabbix
            stats: Diccionario de resultados para actualizar contadores
        """
        try:
            from ..models import ZabbixPortData, ODFHilos
            
            # Obtener todos los hilos relacionados con esta OLT
            hilos_olt = ODFHilos.objects.filter(odf__olt=olt).select_related('zabbix_port', 'odf')
            
            logger.info(f"Actualizando estado de {hilos_olt.count()} hilos para OLT {olt.abreviatura}")
            
            for hilo in hilos_olt:
                try:
                    # Buscar puerto correspondiente por slot/port
                    matching_port = ZabbixPortData.objects.filter(
                        olt=olt,
                        slot=hilo.slot,
                        port=hilo.port
                    ).first()
                    
                    if matching_port and matching_port.disponible:
                        # Puerto disponible en Zabbix - HABILITAR Y VINCULAR
                        if not hilo.en_zabbix:
                            hilo.en_zabbix = True
                            hilo.zabbix_port = matching_port
                            
                            # IMPORTANTE: Al vincular, sincronizar operativo_noc del hilo al puerto
                            # (el hilo mantiene su configuración manual, el puerto se actualiza)
                            matching_port.operativo_noc = hilo.operativo_noc
                            matching_port.save()
                            
                            hilo.save()
                            stats['hilos_enabled'] = stats.get('hilos_enabled', 0) + 1
                            logger.info(f"Hilo habilitado y vinculado: {hilo.identificador_completo}")
                        else:
                            # Ya estaba habilitado, solo actualizar referencia si cambió
                            if hilo.zabbix_port != matching_port:
                                hilo.zabbix_port = matching_port
                                
                                # Sincronizar operativo_noc al cambiar vinculación
                                matching_port.operativo_noc = hilo.operativo_noc
                                matching_port.save()
                                
                                hilo.save()
                    else:
                        # Puerto NO disponible en Zabbix - DESHABILITAR
                        # IMPORTANTE: NO cambiar operativo_noc, solo disponibilidad
                        if hilo.en_zabbix:
                            hilo.en_zabbix = False
                            # Mantener zabbix_port para referencia histórica
                            # Mantener operativo_noc sin cambios (solo manual)
                            hilo.save()
                            stats['hilos_disabled'] = stats.get('hilos_disabled', 0) + 1
                            logger.info(f"Hilo deshabilitado (no en Zabbix): {hilo.identificador_completo}")
                        
                except Exception as e:
                    logger.error(f"Error actualizando estado de hilo {hilo.pk}: {e}")
                    stats['errors'] += 1
                    
        except Exception as e:
            logger.error(f"Error actualizando estado de hilos para OLT {olt.abreviatura}: {e}")
            stats['errors'] += 1
    
    def _sync_operativo_noc_states(self, olt, stats: Dict[str, int]):
        """
        Sincroniza estados operativo_noc SOLO de hilos a puertos Zabbix.
        
        IMPORTANTE: operativo_noc es SOLO MANUAL - nunca se modifica automáticamente.
        Solo sincronizamos del hilo (manual) hacia el puerto (cache) para mantener coherencia.
        """
        try:
            from ..models import ODFHilos
            
            # Obtener hilos de esta OLT que tienen puerto Zabbix asociado
            hilos_con_puerto = ODFHilos.objects.filter(
                odf__olt=olt,
                zabbix_port__isnull=False
            ).select_related('zabbix_port')
            
            sincronizados = 0
            
            for hilo in hilos_con_puerto:
                # SOLO sincronizar del hilo al puerto (nunca al revés)
                # El hilo es la fuente de verdad para operativo_noc (configuración manual NOC)
                 if hilo.operativo_noc != hilo.zabbix_port.operativo_noc:
                    hilo.zabbix_port.operativo_noc = hilo.operativo_noc
                    hilo.zabbix_port.save()
                    sincronizados += 1
                    
                    logger.debug(f"Operativo NOC sincronizado (hilo→puerto): Hilo {hilo.id} → Puerto {hilo.zabbix_port.id} = {hilo.operativo_noc}")
            
            if sincronizados > 0:
                stats['operativo_noc_sincronizados'] = stats.get('operativo_noc_sincronizados', 0) + sincronizados
                logger.info(f"Estados operativo_noc sincronizados (hilo→puerto): {sincronizados} para OLT {olt.abreviatura}")
                
        except Exception as e:
            logger.error(f"Error sincronizando estados operativo_noc para OLT {olt.abreviatura}: {e}")
            stats['errors'] += 1

    def get_administrative_status(self, host_name: str, item_key: str = 'port.descover.walk') -> Dict[str, int]:
        """
        Obtiene el estado administrativo de interfaces desde el item master que contiene
        el OID de estado administrativo configurado para la OLT.
        
        El OID se obtiene dinámicamente según la marca y modelo de la OLT:
        1. Marca + Modelo específico
        2. Solo Marca (genérico de marca)
        3. Genérico universal (🌐 Genérico)
        
        Args:
            host_name: Nombre del host en Zabbix
            item_key: Clave del item master (default: 'port.descover.walk')
            
        Returns:
            Diccionario con snmp_index -> estado_administrativo (1=ACTIVO, 2=INACTIVO)
        """
        # Obtener OLT para determinar el OID correcto
        from hosts.models import OLT
        from oids.models import OID
        
        try:
            olt = OLT.objects.get(abreviatura=host_name)
        except OLT.DoesNotExist:
            logger.error(f"OLT con abreviatura '{host_name}' no encontrada")
            return {}
        
        # Obtener OID de Zabbix específico para esta OLT
        zabbix_oid = OID.get_zabbix_oid_for_olt(olt)
        
        if not zabbix_oid:
            logger.warning(f"No se encontró OID de Zabbix para OLT {olt.abreviatura} (marca: {olt.marca}, modelo: {olt.modelo})")
            # Fallback al OID estándar
            admin_status_oid = ".1.3.6.1.2.1.2.2.1.7"
            logger.info(f"Usando OID estándar como fallback: {admin_status_oid}")
        else:
            admin_status_oid = zabbix_oid.oid
            logger.info(f"Usando OID configurado para {olt.abreviatura}: {admin_status_oid} [{zabbix_oid.nombre}]")
        
        # Usar el item master que ya contiene todos los datos SNMP
        items_data = self.get_item_master_data(item_key, host_name)
        
        admin_states = {}
        
        if not items_data:
            logger.warning(f"No se encontraron datos del item master para {host_name}")
            return admin_states
            
        for item_data in items_data:
            try:
                # Obtener datos SNMP del item master
                snmp_data = item_data.get('data', '')
                
                if not snmp_data:
                    continue
                    
                # Parsear formato: .1.3.6.1.2.1.2.2.1.7.4194312192 = INTEGER: 1
                for line in snmp_data.split('\n'):
                    if admin_status_oid in line and '=' in line:
                        try:
                            oid_part = line.split('=')[0].strip()
                            value_part = line.split('=')[1].strip()
                            
                            # Extraer SNMP index del OID
                            snmp_index = oid_part.split('.')[-1]
                            
                            # Extraer valor administrativo (INTEGER: 1 o 2)
                            if 'INTEGER:' in value_part:
                                admin_status = int(value_part.split('INTEGER:')[1].strip())
                                admin_states[snmp_index] = admin_status
                                
                        except (ValueError, IndexError) as e:
                            logger.debug(f"Error parseando línea de estado administrativo: {line} - {e}")
                            continue
                            
            except Exception as e:
                logger.error(f"Error procesando datos del item master: {e}")
                continue
                
        logger.info(f"Estados administrativos obtenidos para {host_name}: {len(admin_states)} interfaces")
        return admin_states
        
    def _get_host_id(self, host_name: str) -> str:
        """Obtiene el ID del host por su nombre"""
        params = {
            "output": ["hostid"],
            "filter": {
                "host": [host_name]
            }
        }
        
        hosts = self._make_request("host.get", params)
        if hosts:
            return hosts[0]['hostid']
        return None
    
    def _get_formula_from_olt(self, olt):
        """
        Obtiene la fórmula SNMP desde la OLT según su marca/modelo.
        
        Args:
            olt: Instancia de OLT
            
        Returns:
            IndexFormula instance o None si no hay fórmula para esta marca/modelo
        """
        try:
            from snmp_formulas.models import IndexFormula
            
            # Buscar fórmula específica para esta marca y modelo
            formula = IndexFormula.objects.filter(
                marca=olt.marca,
                modelo=olt.modelo,
                activo=True
            ).first()
            
            if formula:
                logger.debug(f"Fórmula encontrada para OLT {olt.abreviatura}: {formula.nombre}")
                return formula
            
            # Si no hay fórmula específica, buscar por marca solamente
            formula = IndexFormula.objects.filter(
                marca=olt.marca,
                modelo__isnull=True,
                activo=True
            ).first()
            
            if formula:
                logger.debug(f"Fórmula genérica de marca encontrada para OLT {olt.abreviatura}: {formula.nombre}")
                return formula
            
            # Fórmula universal (sin marca ni modelo)
            formula = IndexFormula.objects.filter(
                marca__isnull=True,
                modelo__isnull=True,
                activo=True
            ).first()
            
            if formula:
                logger.debug(f"Fórmula universal encontrada para OLT {olt.abreviatura}: {formula.nombre}")
                return formula
            
            logger.warning(f"No se encontró fórmula para OLT {olt.abreviatura} (marca: {olt.marca}, modelo: {olt.modelo})")
            return None
                
        except Exception as e:
            logger.error(f"Error obteniendo fórmula para OLT {olt.abreviatura}: {e}")
            return None
