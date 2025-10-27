"""
Servicios para lógica de descubrimiento SNMP Walk
"""
import logging
import time
from typing import Dict, List, Tuple, Optional
from django.db import transaction
from django.utils import timezone
from easysnmp import Session
from django.conf import settings

from .models import OnuIndexMap, OnuStatus, OnuInventory, OnuStateLookup
from executions.models import Execution
from hosts.models import OLT
from configuracion_avanzada.services import get_snmp_timeout, get_snmp_retries

logger = logging.getLogger(__name__)

# El OID se obtiene de la tarea, no se hardcodea

# Configuraciones 
CONSECUTIVE_MISSES_THRESHOLD = 1  # Basta que no aparezca UNA VEZ para marcarla como DISABLED


class DiscoveryService:
    """
    Servicio principal para ejecutar descubrimiento SNMP Walk
    """
    
    def __init__(self, execution_id: int):
        self.execution = Execution.objects.get(pk=execution_id)
        self.olt = self.execution.olt
        self.job = self.execution.snmp_job
        self.logger = logging.getLogger(f"{__name__}.{self.olt.abreviatura}")
        
    def execute_discovery_walk(self) -> Dict:
        """
        Ejecuta el walk completo de descubrimiento para la OLT
        SOLO actualiza la base de datos si la tarea es SUCCESS
        """
        self.logger.info(f"🔍 Iniciando descubrimiento SNMP Walk para OLT {self.olt.abreviatura}")
        
        start_time = timezone.now()
        results = {
            'total_found': 0,
            'new_index_created': 0,
            'enabled_count': 0,
            'disabled_count': 0,
            'errors': [],
            'duration_ms': 0,
            'walk_successful': False,
            'memory_data': []
        }
        
        try:
            # Verificar que la OLT esté habilitada antes de continuar
            if not self.olt.habilitar_olt:
                raise Exception(f"OLT {self.olt.abreviatura} está deshabilitada")
                
            # Ejecutar SNMP Walk y guardar en memoria
            walk_results = self._execute_snmp_walk()
            self.logger.info(f"📊 Walk completado: {len(walk_results)} resultados obtenidos")
            
            # Guardar resultados en memoria (sin procesar aún) - convertir a tipos básicos
            # Asegurar que memory_data sea serializable (solo strings e ints)
            memory_data = []
            for raw_index_key, state_value in walk_results:
                memory_data.append([str(raw_index_key), int(state_value)])
            
            results['memory_data'] = memory_data
            results['total_found'] = len(walk_results)
            results['walk_successful'] = True
            
            # Log innecesario removido
            
        except Exception as e:
            # Log del error sin traceback para mantener logs limpios
            self.logger.error(f"❌ Error en SNMP Walk: {str(e)}")
            results['errors'].append(str(e))
            results['walk_successful'] = False
            # IMPORTANTE: Re-lanzar la excepción para que execute_discovery la capture
            raise
        
        finally:
            # Calcular duración
            end_time = timezone.now()
            results['duration_ms'] = int((end_time - start_time).total_seconds() * 1000)
            
        return results
    
    def process_successful_walk(self, walk_results: List[List]) -> Dict:
        """
        Procesa los resultados del walk SOLO cuando la tarea es SUCCESS
        """
        # Log innecesario removido
        
        results = {
            'new_index_created': 0,
            'enabled_count': 0,
            'disabled_count': 0,
            'errors': []
        }
        
        try:
            # Procesar resultados en transacción atómica
            with transaction.atomic():
                processed_indices = set()
                
                for item in walk_results:
                    raw_index_key, state_value = item[0], item[1]
                    try:
                        self._process_walk_result(raw_index_key, state_value, results)
                        processed_indices.add(raw_index_key)
                    except Exception as e:
                        self.logger.error(f"❌ Error procesando {raw_index_key}: {e}")
                        results['errors'].append(f"{raw_index_key}: {str(e)}")
                
                # Post-proceso: marcar ausentes
                self._mark_missing_onus(processed_indices, results)
                
            self.logger.info(f"✅ Procesamiento completado: {results}")
                
        except Exception as e:
            self.logger.error(f"❌ Error procesando resultados: {e}")
            results['errors'].append(str(e))
            raise
        
        return results
    
    def _execute_snmp_walk(self) -> List[Tuple[str, int]]:
        """
        Ejecuta el SNMP Walk y retorna lista de (raw_index_key, state_value)
        Usa el OID de la tarea, no un OID hardcodeado
        """
        try:
            session = Session(
                hostname=self.olt.ip_address,
                community=self.olt.comunidad,
                version=2,
                timeout=get_snmp_timeout(),
                retries=get_snmp_retries()
            )
            
            # Usar el OID de la tarea
            task_oid = self.job.oid.oid
            # Logs innecesarios removidos - solo mantener resultado final
            raw_results = session.walk(task_oid)
            self.logger.info(f"🔍 DESPUÉS DEL WALK - Resultados: {len(raw_results)}")
            
            # Log innecesario removido
            
            results = []
            for i, item in enumerate(raw_results):
                try:
                    # Extraer índice del OID completo usando el OID de la tarea
                    # Ejemplo: .1.3.6.1.4.1.2011.6.128.1.1.2.46.1.1.4194312192.2 -> 4194312192.2
                    full_oid = str(item.oid)  # Convertir a string para evitar problemas
                    self.logger.debug(f"   Elemento {i+1}: {full_oid} = {item.value}")
                    
                    # Para job tipo 'descubrimiento', solo extraer el snmpindexonu
                    # Los OIDs vienen como: iso.3.6.1.4.1.2011.6.128.1.1.2.46.1.1.4194338304.6
                    # Solo necesitamos: 4194338304.6
                    
                    # Buscar el patrón del OID base y extraer lo que viene después
                    oid_parts = full_oid.split('.')
                    if len(oid_parts) >= 2:
                        # Tomar los últimos 2 elementos como snmpindexonu (ej: 4194338304.6)
                        raw_index_key = f"{oid_parts[-2]}.{oid_parts[-1]}"
                        
                        # Convertir value a int de forma segura
                        try:
                            state_value = int(str(item.value))
                            results.append((raw_index_key, state_value))
                            self.logger.debug(f"   ✅ Procesado: {raw_index_key} = {state_value}")
                        except (ValueError, TypeError):
                            # Si no se puede convertir a int, saltar este resultado
                            self.logger.warning(f"⚠️ Valor SNMP no es entero: {item.value}")
                            continue
                    else:
                        self.logger.warning(f"⚠️ OID con formato inesperado: {full_oid}")
                        
                except (ValueError, AttributeError) as e:
                    self.logger.warning(f"⚠️ Error parseando resultado SNMP {item}: {e}")
                    continue
                    
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Error en SNMP Walk: {e}")
            raise
    
    def _process_walk_result(self, raw_index_key: str, state_value: int, results: Dict):
        """
        Procesa un resultado individual del walk
        """
        # 1. Crear/obtener OnuIndexMap
        onu_index_map = self._get_or_create_index_map(raw_index_key, results)
        
        # 2. Crear/obtener OnuInventory
        onu_inventory = self._get_or_create_inventory(onu_index_map)
        
        # 3. Actualizar OnuStatus
        self._update_onu_status(onu_index_map, state_value, results)
    
    def _get_or_create_index_map(self, raw_index_key: str, results: Dict) -> OnuIndexMap:
        """
        Obtiene o crea el mapeo de índice para la ONU
        """
        onu_index_map, created = OnuIndexMap.objects.get_or_create(
            olt=self.olt,
            raw_index_key=raw_index_key,
            defaults={
                'normalized_id': f"OLT{self.olt.id}-{raw_index_key}",
                'marca_formula': f'marca_{self.job.marca.nombre}',  # Usar marca del job
            }
        )
        
        if created:
            results['new_index_created'] += 1
            self.logger.debug(f"📝 Nuevo índice creado: {raw_index_key}")
            
        return onu_index_map
    
    def _get_or_create_inventory(self, onu_index_map: OnuIndexMap) -> OnuInventory:
        """
        Obtiene o crea el inventario para la ONU
        """
        onu_inventory, created = OnuInventory.objects.get_or_create(
            onu_index=onu_index_map,
            defaults={
                'olt': self.olt,
                'active': True,
                'snmp_last_execution': self.execution,
            }
        )
        
        if created:
            self.logger.debug(f"📦 Nuevo inventario creado: {onu_index_map.normalized_id}")
        else:
            # SINCRONIZAR: Si la ONU apareció en el walk, debe estar activa
            if not onu_inventory.active:
                onu_inventory.active = True
                onu_inventory.snmp_last_execution = self.execution
                onu_inventory.save()
                self.logger.info(f"📦 Inventario reactivado (ONU volvió a aparecer): {onu_index_map.normalized_id}")
            
        return onu_inventory
    
    def _update_onu_status(self, onu_index_map: OnuIndexMap, state_value: int, results: Dict):
        """
        Actualiza el estado actual de la ONU
        """
        # Obtener label del estado usando prioridad: específico por marca → general
        state_label = 'UNKNOWN'
        
        # PRIORIDAD 1: Estado específico por marca del job
        try:
            state_lookup = OnuStateLookup.objects.get(value=state_value, marca=self.job.marca)
            state_label = state_lookup.label
            self.logger.debug(f"📊 Estado específico encontrado: {state_value} → {state_label} ({self.job.marca.nombre})")
        except OnuStateLookup.DoesNotExist:
            # PRIORIDAD 2: Estado general (sin marca)
            try:
                state_lookup = OnuStateLookup.objects.get(value=state_value, marca__isnull=True)
                state_label = state_lookup.label
                self.logger.debug(f"📊 Estado general encontrado: {state_value} → {state_label} (General)")
            except OnuStateLookup.DoesNotExist:
                state_label = 'UNKNOWN'
                self.logger.warning(f"⚠️ Estado desconocido: {state_value} para marca {self.job.marca.nombre}")
        
        # Actualizar o crear estado
        onu_status, created = OnuStatus.objects.get_or_create(
            onu_index=onu_index_map,
            defaults={
                'olt': self.olt,
            }
        )
        
        # Detectar cambio de estado
        state_changed = (
            onu_status.last_state_value != state_value or 
            onu_status.presence != 'ENABLED'
        )
        
        # Actualizar campos
        onu_status.last_seen_at = timezone.now()
        onu_status.last_state_value = state_value
        onu_status.last_state_label = state_label
        onu_status.presence = 'ENABLED'  # Si aparece en walk, está habilitado
        onu_status.consecutive_misses = 0  # Reset contador de faltas
        
        if state_changed:
            onu_status.last_change_execution = self.execution
            
        onu_status.save()
        
        # Contabilizar
        if state_value == 1:  # ACTIVO
            results['enabled_count'] += 1
        elif state_value == 2:  # SUSPENDIDO
            results['disabled_count'] += 1
            
        if created:
            self.logger.debug(f"📊 Nuevo estado creado: {onu_index_map.normalized_id}")
    
    def _mark_missing_onus(self, processed_indices: set, results: Dict):
        """
        Marca ONUs que no aparecieron en este walk como ausentes
        """
        # Obtener todos los índices conocidos para esta OLT con la marca del job
        existing_maps = OnuIndexMap.objects.filter(
            olt=self.olt,
            marca_formula=f'marca_{self.job.marca.nombre}'
        ).select_related('status')
        
        missing_count = 0
        disabled_count = 0
        
        for onu_map in existing_maps:
            if onu_map.raw_index_key not in processed_indices:
                # Esta ONU no apareció en el walk
                try:
                    status = onu_map.status
                    status.consecutive_misses += 1
                    
                    # Basta que no aparezca UNA VEZ para marcarla como DISABLED
                    if status.presence == 'ENABLED':
                        status.presence = 'DISABLED'
                        status.last_change_execution = self.execution
                        disabled_count += 1
                        self.logger.info(f"🔴 ONU marcada como DISABLED (no apareció): {onu_map.normalized_id}")
                        
                        # SINCRONIZAR: También marcar el inventario como inactivo
                        try:
                            inventory = OnuInventory.objects.get(onu_index=onu_map)
                            if inventory.active:
                                inventory.active = False
                                inventory.snmp_last_execution = self.execution
                                inventory.save()
                                self.logger.info(f"📦 Inventario marcado como inactivo: {onu_map.normalized_id}")
                        except OnuInventory.DoesNotExist:
                            # No tiene inventario, no hay problema
                            pass
                    
                    status.save()
                    missing_count += 1
                    
                except OnuStatus.DoesNotExist:
                    # No tiene estado, probablemente es muy antigua
                    continue
        
        if missing_count > 0:
            self.logger.info(f"👻 ONUs ausentes en walk: {missing_count} (nuevas DISABLED: {disabled_count})")


def execute_discovery_task(execution_id: int) -> Dict:
    """
    Función principal para ejecutar tarea de descubrimiento
    Retorna los resultados del walk para que la tarea decida si es SUCCESS o FAILED
    """
    service = DiscoveryService(execution_id)
    return service.execute_discovery_walk()


def process_successful_discovery(execution_id: int, walk_results: List[List]) -> Dict:
    """
    Procesa los resultados del walk SOLO cuando la tarea es marcada como SUCCESS
    y SOLO si el OID tiene espacio 'descubrimiento'
    """
    service = DiscoveryService(execution_id)
    
    # Verificar que el OID tenga espacio 'descubrimiento'
    if service.job.oid.espacio != 'descubrimiento':
        logger.info(f"⚠️ OID {service.job.oid.nombre} tiene espacio '{service.job.oid.espacio}', no se procesarán las tablas de discovery")
        return {
            'status': 'skipped',
            'reason': f'OID no es de tipo descubrimiento (espacio: {service.job.oid.espacio})',
            'processed_records': 0,
            'updated_records': 0,
            'disabled_records': 0
        }
    
    logger.info(f"✅ OID {service.job.oid.nombre} tiene espacio 'descubrimiento', procesando tablas de discovery")
    return service.process_successful_walk(walk_results)
