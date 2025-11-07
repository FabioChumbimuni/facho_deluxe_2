# snmp_get/tasks.py
import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from easysnmp import Session, EasySNMPTimeoutError, EasySNMPConnectionError
import time
import hashlib
from threading import Semaphore
from collections import defaultdict

logger = logging.getLogger(__name__)

# Configuración de control de carga y subdivisión (alineado con facho_deluxe)
MAX_POLLERS_PER_OLT = 10   # Máximo número de pollers concurrentes por OLT (igual que MAX_POLLERS_PER_TASK)
INITIAL_BATCH_SIZE = 200   # Tamaño inicial del lote (igual que CHUNK_SIZE en facho_deluxe)
SUBDIVISION_SIZE = 50      # Tamaño al subdividir (200 → 4 lotes de 50, igual que PROTOCOL ANTI-TIMEOUT)
LOCK_TIMEOUT = 300         # 5 minutos timeout para locks
RETRY_DELAY = 5            # Segundos entre reintentos individuales
MAX_INDIVIDUAL_RETRIES = 2 # Máximo número de reintentos por ONU individual

# Control de concurrencia por OLT usando Semaphore (igual que facho_deluxe)
# El límite se configura dinámicamente desde BD, default 5 consultas SNMP simultáneas
olt_semaphores = {}  # Se crea dinámicamente con límite desde configuración


# =========================================
# FUNCIONES AUXILIARES DE CONTROL DE CARGA
# =========================================

def acquire_olt_poller_slot(olt_id, timeout=LOCK_TIMEOUT):
    """
    Intenta adquirir un slot de poller para la OLT.
    Usa Redis/cache para controlar que no se excedan MAX_POLLERS_PER_OLT.
    
    Returns:
        bool: True si se adquirió el slot, False si no hay slots disponibles
    """
    cache_key = f"olt_pollers:{olt_id}"
    
    # Obtener contador actual de pollers activos
    current_pollers = cache.get(cache_key, 0)
    
    if current_pollers >= MAX_POLLERS_PER_OLT:
        logger.warning(f"⚠️ OLT {olt_id} alcanzó límite de pollers ({current_pollers}/{MAX_POLLERS_PER_OLT})")
        return False
    
    # Incrementar contador con timeout
    cache.set(cache_key, current_pollers + 1, timeout)
    logger.debug(f"✅ Slot adquirido para OLT {olt_id}: {current_pollers + 1}/{MAX_POLLERS_PER_OLT}")
    return True


def release_olt_poller_slot(olt_id):
    """
    Libera un slot de poller para la OLT.
    """
    cache_key = f"olt_pollers:{olt_id}"
    current_pollers = cache.get(cache_key, 0)
    
    if current_pollers > 0:
        cache.set(cache_key, current_pollers - 1, LOCK_TIMEOUT)
        logger.debug(f"🔓 Slot liberado para OLT {olt_id}: {current_pollers - 1}/{MAX_POLLERS_PER_OLT}")


def wait_for_olt_slot(olt_id, max_wait=60):
    """
    Espera hasta que haya un slot disponible para la OLT.
    
    Args:
        olt_id: ID de la OLT
        max_wait: Tiempo máximo de espera en segundos
        
    Returns:
        bool: True si se adquirió el slot, False si timeout
    """
    start_time = time.time()
    wait_interval = 2  # Revisar cada 2 segundos
    
    while (time.time() - start_time) < max_wait:
        if acquire_olt_poller_slot(olt_id):
            return True
        
        logger.info(f"⏳ Esperando slot disponible para OLT {olt_id}... ({int(time.time() - start_time)}s)")
        time.sleep(wait_interval)
    
    logger.error(f"❌ Timeout esperando slot para OLT {olt_id} después de {max_wait}s")
    return False


def subdivide_batch(batch, subdivision_size=SUBDIVISION_SIZE):
    """
    Subdivide un lote en lotes más pequeños.
    
    Args:
        batch: Lista de ONUs
        subdivision_size: Tamaño de cada sublote
        
    Returns:
        List[List]: Lista de sublotes
    """
    return [batch[i:i + subdivision_size] for i in range(0, len(batch), subdivision_size)]


@shared_task(queue='get_main', bind=True, time_limit=300, autoretry_for=(Exception,), retry_kwargs={'max_retries': 0})
def get_main_task(self, snmp_job_id, olt_id, execution_id):
    """
    Tarea principal GET SNMP.
    Divide el trabajo en pollers para procesar múltiples ONUs en paralelo.
    NO usa reintentos automáticos de Celery (max_retries=0)
    """
    from executions.models import Execution
    
    logger.info(f"🚀 get_main_task: Iniciando para job {snmp_job_id}, OLT {olt_id}, execution {execution_id}")
    
    # Verificar que la ejecución no esté INTERRUPTED o ya completada
    try:
        execution = Execution.objects.get(pk=execution_id)
        
        if execution.status in ['INTERRUPTED', 'SUCCESS', 'FAILED']:
            logger.warning(f"⚠️ Ejecución {execution_id} tiene estado {execution.status}, cancelando tarea")
            return {
                'status': 'cancelled',
                'reason': f'Ejecución ya está en estado {execution.status}'
            }
    except Execution.DoesNotExist:
        logger.error(f"❌ Ejecución {execution_id} no existe")
        return {'status': 'error', 'reason': 'Ejecución no existe'}
    
    try:
        execute_get_main(snmp_job_id, olt_id, execution_id, queue_name='get_main')
        logger.info(f"✅ get_main_task: Completada exitosamente")
    except Exception as exc:
        logger.error(f"❌ get_main_task: {str(exc)}")
        raise


@shared_task(queue='get_retry', bind=True, time_limit=300)
def get_retry_task(self, snmp_job_id, olt_id, execution_id, attempt):
    """
    Tarea de reintento GET SNMP.
    Se ejecuta en cola separada para reintentos.
    """
    logger.info(f"🔁 get_retry_task: Reintento {attempt} para job {snmp_job_id}, OLT {olt_id}")
    
    try:
        execute_get_main(snmp_job_id, olt_id, execution_id, queue_name='get_retry', attempt=attempt)
        logger.info(f"✅ get_retry_task: Completada exitosamente")
    except Exception as exc:
        logger.error(f"❌ get_retry_task: {str(exc)}")
        raise


@shared_task(queue='get_manual', bind=True, time_limit=300)
def get_manual_task(self, snmp_job_id, olt_id, execution_id):
    """
    Tarea de ejecución manual GET con máxima prioridad.
    NO tiene reintentos automáticos.
    """
    from executions.models import Execution
    
    logger.info(f"🚀 get_manual_task: Ejecución manual para job {snmp_job_id}, OLT {olt_id}, execution {execution_id}")
    
    # Verificar que la ejecución no esté INTERRUPTED o ya completada
    try:
        execution = Execution.objects.get(pk=execution_id)
        
        if execution.status in ['INTERRUPTED', 'SUCCESS', 'FAILED']:
            logger.warning(f"⚠️ Ejecución {execution_id} tiene estado {execution.status}, cancelando tarea")
            return {
                'status': 'cancelled',
                'reason': f'Ejecución ya está en estado {execution.status}'
            }
    except Execution.DoesNotExist:
        logger.error(f"❌ Ejecución {execution_id} no existe")
        return {'status': 'error', 'reason': 'Ejecución no existe'}
    
    try:
        execute_get_main(snmp_job_id, olt_id, execution_id, queue_name='get_manual')
        logger.info(f"✅ get_manual_task: Completada exitosamente")
    except Exception as exc:
        logger.error(f"❌ get_manual_task: {str(exc)}")
        
        # Marcar como fallida la ejecución manual
        try:
            from executions.models import Execution
            execution = Execution.objects.get(pk=execution_id)
            
            if execution.status != 'FAILED':
                execution.status = 'FAILED'
                execution.error_message = str(exc)
                execution.finished_at = timezone.now()
                if not execution.started_at:
                    execution.started_at = timezone.now()
                if execution.started_at and execution.finished_at:
                    execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                execution.save()
                logger.info(f"❌ Ejecución manual {execution_id} marcada como FAILED")
        except Exception as save_error:
            logger.error(f"❌ Error guardando estado de ejecución: {save_error}")
        
        raise


@shared_task(
    queue='get_poller', 
    bind=True, 
    time_limit=180,
    soft_time_limit=120,
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True
)
def get_poller_task(self, onu_batch, olt_id, oid_string, snmp_config, execution_id, oid_config=None, depth=0):
    """
    Tarea poller con subdivisión progresiva y control de hilos por OLT.
    
    Estrategia de subdivisión (alineada con facho_deluxe PROTOCOL ANTI-TIMEOUT):
    1. Lote de 200 ONUs → Si falla, dividir en 4 lotes de 50
    2. Lote de 50 ONUs → Si falla, procesar individualmente
    3. ONU individual → Si falla, reintentar hasta MAX_INDIVIDUAL_RETRIES
    
    Control de concurrencia:
    - Semaphore por OLT (max 5 consultas SNMP simultáneas)
    - Cache counter por OLT (max 10 pollers concurrentes)
    
    Args:
        onu_batch: Lista de diccionarios con información de ONUs
        olt_id: ID de la OLT
        oid_string: OID base a consultar
        snmp_config: Configuración SNMP (community, version, timeout)
        execution_id: ID de la ejecución
        oid_config: Configuración del OID (target_field, keep_previous_value, format_mac)
        depth: Profundidad de subdivisión (0=inicial, 1=subdividido, 2=individual)
    """
    from discovery.models import OnuInventory
    from hosts.models import OLT
    
    # Configuración por defecto del OID
    if oid_config is None:
        oid_config = {
            'target_field': 'snmp_description',
            'keep_previous_value': True,
            'format_mac': False,
            'espacio': 'descripcion'
        }
    
    batch_size = len(onu_batch)
    logger.info(f"📡 get_poller_task [depth={depth}]: Procesando {batch_size} ONUs para OLT {olt_id}")
    
    # Esperar y adquirir slot de poller para la OLT (control de pollers concurrentes)
    if not wait_for_olt_slot(olt_id, max_wait=60):
        logger.error(f"❌ No se pudo adquirir slot de poller para OLT {olt_id}, reencolando...")
        # Reencolar con retraso
        self.retry(countdown=30, max_retries=3)
        return
    
    # Variable para rastrear el semáforo
    semaphore = None
    
    try:
        # Obtener OLT para obtener su IP
        olt = OLT.objects.get(id=olt_id)
        
        # Obtener límite de semáforo desde configuración
        max_snmp_queries = snmp_config.get('max_consultas_snmp_simultaneas', 5)
        
        # Obtener o crear semáforo para esta OLT con límite dinámico
        olt_key = f"{olt.ip_address}_{max_snmp_queries}"
        if olt_key not in olt_semaphores:
            olt_semaphores[olt_key] = Semaphore(max_snmp_queries)
            logger.debug(f"🔧 Semáforo creado para OLT {olt.abreviatura} con límite {max_snmp_queries}")
        
        semaphore = olt_semaphores[olt_key]
        
        # Intentar adquirir el semáforo con timeout (como en facho_deluxe)
        if not semaphore.acquire(timeout=30):
            error_msg = f"Timeout esperando semáforo SNMP para OLT {olt.abreviatura}"
            logger.error(error_msg)
            return {
                'status': 'error',
                'error': error_msg,
                'success_count': 0,
                'error_count': 0
            }
        
        try:
            # Crear sesión SNMP
            session = Session(
                hostname=olt.ip_address,
                community=snmp_config.get('community', 'public'),
                version=snmp_config.get('version', 2),
                timeout=snmp_config.get('timeout', 3),
                retries=snmp_config.get('retries', 1)
            )
            
            success_count = 0
            error_count = 0
            failed_onus = []
            results = []
            
            # Procesar cada ONU en el lote
            for onu_data in onu_batch:
                # Inicializar variables para evitar error en except si falla antes
                normalized_id = onu_data.get('normalized_id', 'UNKNOWN')
                raw_index_key = onu_data.get('raw_index_key', 'UNKNOWN')
                
                try:
                    onu_index_id = onu_data['onu_index_id']
                    raw_index_key = onu_data['raw_index_key']
                    normalized_id = onu_data['normalized_id']
                    retry_count = onu_data.get('retry_count', 0)
                    
                    # Construir OID completo
                    full_oid = f"{oid_string}.{raw_index_key}"
                    
                    logger.debug(f"   🔍 Consultando OID: {full_oid} para ONU {normalized_id}")
                    
                    # Realizar consulta SNMP GET
                    start_time = time.time()
                    result = session.get(full_oid)
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    # Extraer valor
                    value = result.value if hasattr(result, 'value') else str(result)
                    value_str = str(value).strip().strip('"')
                    
                    # Verificar si es NOSUCHINSTANCE (ONU no existe o desconectada)
                    if (value_str.lower() in ['no such instance currently exists at this oid', 
                                              'no such instance', 
                                              'nosuchinstance', 
                                              'nosuchobject'] or 
                        'no such' in value_str.lower()):
                        
                        logger.warning(f"   ⚠️ ONU {normalized_id}: NOSUCHINSTANCE - Marcando como DISABLED/Inactive")
                        
                        # Actualizar AMBAS tablas para que concuerden
                        from discovery.models import OnuStatus
                        try:
                            # 1. Actualizar onu_status.presence = 'DISABLED'
                            onu_status = OnuStatus.objects.get(onu_index_id=onu_index_id)
                            onu_status.presence = 'DISABLED'
                            onu_status.updated_at = timezone.now()
                            onu_status.save(update_fields=['presence', 'updated_at'])
                            
                            # 2. Actualizar onu_inventory.active = False
                            onu_inventory, created = OnuInventory.objects.get_or_create(
                                onu_index_id=onu_index_id,
                                olt_id=olt_id,
                                defaults={'active': False}
                            )
                            
                            # Si ya existía, actualizar active a False
                            if not created:
                                onu_inventory.active = False
                                onu_inventory.save(update_fields=['active', 'updated_at'])
                            
                            logger.info(f"   🔴 ONU {normalized_id} marcada: onu_status.presence=DISABLED + onu_inventory.active=False")
                            
                            success_count += 1  # Procesada correctamente aunque sea NOSUCHINSTANCE
                            results.append({
                                'onu_index': normalized_id,
                                'status': 'disabled',
                                'reason': 'NOSUCHINSTANCE',
                                'depth': depth
                            })
                        except OnuStatus.DoesNotExist:
                            logger.warning(f"   ⚠️ OnuStatus no existe para onu_index_id {onu_index_id} - Creando como DISABLED")
                            
                            # FALLBACK: Crear OnuStatus si no existe
                            try:
                                from discovery.models import OnuIndexMap
                                onu_index_obj = OnuIndexMap.objects.get(id=onu_index_id)
                                
                                OnuStatus.objects.create(
                                    onu_index=onu_index_obj,
                                    olt_id=olt_id,
                                    presence='DISABLED',
                                    last_state_value=0,
                                    last_state_label='UNKNOWN',
                                    consecutive_misses=1,
                                    last_seen_at=None
                                )
                                
                                # También actualizar inventario
                                onu_inventory, created = OnuInventory.objects.get_or_create(
                                    onu_index_id=onu_index_id,
                                    olt_id=olt_id,
                                    defaults={'active': False}
                                )
                                if not created:
                                    onu_inventory.active = False
                                    onu_inventory.save(update_fields=['active', 'updated_at'])
                                
                                logger.info(f"   ✅ OnuStatus creado como DISABLED (fallback GET)")
                                success_count += 1
                            except Exception as e:
                                logger.error(f"   ❌ Error creando OnuStatus fallback: {e}")
                                error_count += 1
                        
                        continue  # No guardar NOSUCHINSTANCE en snmp_description
                    
                    # Valor válido: actualizar onu_inventory con lógica inteligente
                    onu_inventory, created = OnuInventory.objects.get_or_create(
                        onu_index_id=onu_index_id,
                        olt_id=olt_id,
                        defaults={'active': True}
                    )
                    
                    # FALLBACK: Verificar que tenga OnuStatus, si no crearlo como ENABLED
                    try:
                        from discovery.models import OnuIndexMap
                        onu_index_obj = OnuIndexMap.objects.get(id=onu_index_id)
                        
                        if not hasattr(onu_index_obj, 'status'):
                            logger.warning(f"   ⚠️ GET encontró ONU sin OnuStatus: {normalized_id} - Creando como ENABLED")
                            OnuStatus.objects.create(
                                onu_index=onu_index_obj,
                                olt_id=olt_id,
                                presence='ENABLED',
                                last_state_value=1,
                                last_state_label='ACTIVO',
                                consecutive_misses=0,
                                last_seen_at=timezone.now()
                            )
                            logger.info(f"   ✅ OnuStatus creado como ENABLED (fallback GET)")
                    except Exception as e:
                        logger.warning(f"   ⚠️ No se pudo verificar/crear OnuStatus: {e}")
                    
                    # Obtener configuración del campo a actualizar
                    target_field = oid_config.get('target_field', 'snmp_description')
                    keep_previous = oid_config.get('keep_previous_value', False)
                    format_mac = oid_config.get('format_mac', False)
                    espacio = oid_config.get('espacio', 'descripcion')
                    
                    # Procesar valor según el tipo de campo
                    valor_a_guardar = value_str
                    campo_actualizado = False
                    
                    # 1. FORMATEAR MAC si está habilitado (AC:DC:SD → ACDCSD)
                    if format_mac and valor_a_guardar:
                        valor_a_guardar = valor_a_guardar.replace(':', '').replace(' ', '').upper()
                        logger.debug(f"   🔧 MAC formateada: {value_str} → {valor_a_guardar}")
                    
                    # 2. LÓGICA SEGÚN EL CAMPO
                    if target_field == 'distancia_onu':
                        # Lógica especial para distancia (conversión m→km + mantener previo)
                        valor_actual = getattr(onu_inventory, target_field, None)
                        
                        if valor_a_guardar == "-1":
                            # Valor -1: No hay distancia medida
                            if not valor_actual:
                                setattr(onu_inventory, target_field, "No Distancia")
                                campo_actualizado = True
                                logger.debug(f"   📏 Distancia: Sin medición (primera vez)")
                            else:
                                # MANTENER valor previo
                                logger.debug(f"   📏 Distancia: Valor -1, manteniendo '{valor_actual}'")
                        elif valor_a_guardar:
                            # Convertir metros → kilómetros
                            try:
                                if '.' in valor_a_guardar:
                                    # Ya está en km
                                    nuevo_valor = f"{valor_a_guardar} km"
                                else:
                                    # Convertir metros a km
                                    metros = float(valor_a_guardar)
                                    km = metros / 1000
                                    nuevo_valor = f"{km:.3f} km"
                                
                                # SOLO actualizar si no hay valor o es "No Distancia"
                                if not valor_actual or valor_actual == "No Distancia":
                                    setattr(onu_inventory, target_field, nuevo_valor)
                                    campo_actualizado = True
                                    logger.debug(f"   📏 Distancia actualizada: {nuevo_valor}")
                                else:
                                    # MANTENER valor previo (distancia no cambia)
                                    logger.debug(f"   📏 Distancia: Manteniendo '{valor_actual}'")
                            except ValueError:
                                logger.error(f"   ❌ Error convirtiendo distancia: {valor_a_guardar}")
                    
                    elif target_field in ['plan_onu', 'modelo_onu']:
                        # Lógica para plan_onu y modelo_onu (mantener valor previo)
                        valor_actual = getattr(onu_inventory, target_field, None)
                        
                        if valor_a_guardar:
                            # HAY VALOR NUEVO → SIEMPRE SOBREESCRIBIR ✅
                            setattr(onu_inventory, target_field, valor_a_guardar)
                            campo_actualizado = True
                            logger.debug(f"   ✅ {target_field} actualizado: {valor_a_guardar}")
                        elif valor_actual:
                            # NO HAY VALOR NUEVO PERO HAY VALOR PREVIO → MANTENER ✅
                            logger.debug(f"   🔄 {target_field}: Manteniendo '{valor_actual}'")
                        else:
                            # NO HAY VALOR NUEVO NI PREVIO → Poner "No Plan" o "No Modelo"
                            default_value = "No Plan" if target_field == 'plan_onu' else "No Modelo"
                            setattr(onu_inventory, target_field, default_value)
                            campo_actualizado = True
                            logger.debug(f"   ⚠️ {target_field}: Sin valor, guardando '{default_value}'")
                    
                    else:
                        # Lógica para otros campos (snmp_description, mac_address, etc.)
                        valor_actual = getattr(onu_inventory, target_field, None) if hasattr(onu_inventory, target_field) else None
                        
                        if valor_a_guardar:
                            # HAY VALOR NUEVO → SIEMPRE SOBREESCRIBIR ✅
                            setattr(onu_inventory, target_field, valor_a_guardar)
                            campo_actualizado = True
                            logger.debug(f"   ✅ {target_field} actualizado: {valor_a_guardar[:50]}...")
                        elif keep_previous and valor_actual:
                            # NO HAY VALOR NUEVO PERO keep_previous=True → MANTENER ✅
                            logger.debug(f"   🔄 {target_field}: Manteniendo valor previo")
                        else:
                            # NO HAY VALOR → Guardar vacío
                            setattr(onu_inventory, target_field, valor_a_guardar)
                            campo_actualizado = True
                            logger.debug(f"   ⚠️ {target_field}: Guardando valor vacío")
                    
                    # Actualizar metadatos de última colecta
                    onu_inventory.snmp_last_collected_at = timezone.now()
                    onu_inventory.snmp_last_execution_id = execution_id
                    
                    # Guardar en BD
                    fields_to_update = ['snmp_last_collected_at', 'snmp_last_execution_id', 'updated_at']
                    if campo_actualizado:
                        fields_to_update.append(target_field)
                    
                    onu_inventory.save(update_fields=fields_to_update)
                    
                    success_count += 1
                    results.append({
                        'onu_index': normalized_id,
                        'status': 'success',
                        'field': target_field,
                        'duration_ms': duration_ms,
                        'depth': depth,
                        'retry_count': retry_count
                    })
                    
                    logger.debug(f"   ✅ ONU {normalized_id} procesada correctamente")
                    
                except (EasySNMPTimeoutError, EasySNMPConnectionError) as e:
                    error_count += 1
                    retry_count = onu_data.get('retry_count', 0)
                    
                    logger.warning(f"   ⚠️ Error SNMP para ONU {normalized_id} (intento {retry_count + 1}): {str(e)}")
                    
                    # Agregar a lista de fallos para procesamiento posterior
                    failed_onus.append({
                        **onu_data,
                        'retry_count': retry_count + 1,
                        'error': str(e)
                    })
                    
                    results.append({
                        'onu_index': normalized_id,
                        'status': 'failed',
                        'error': str(e),
                        'depth': depth,
                        'retry_count': retry_count
                    })
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"   ❌ Error inesperado para ONU {normalized_id}: {str(e)}")
                    
                    failed_onus.append({
                        **onu_data,
                        'retry_count': onu_data.get('retry_count', 0) + 1,
                        'error': str(e)
                    })
                    
                    results.append({
                        'onu_index': normalized_id,
                        'status': 'failed',
                        'error': str(e),
                        'depth': depth
                    })
            
            # Estrategia de subdivisión basada en errores
            # Obtener parámetros de configuración desde snmp_config
            subdivision_size = snmp_config.get('tamano_subdivision', SUBDIVISION_SIZE)
            max_retries_individual = snmp_config.get('max_reintentos_individuales', MAX_INDIVIDUAL_RETRIES)
            retry_delay = snmp_config.get('delay_entre_reintentos', RETRY_DELAY)
            
            if failed_onus:
                logger.warning(f"⚠️ {len(failed_onus)} ONUs fallaron en lote de {batch_size}")
                
                # DEPTH 0: Lote inicial (200) → Subdividir en lotes de 50
                if depth == 0 and batch_size > subdivision_size:
                    logger.info(f"🔀 Subdividiendo {len(failed_onus)} ONUs en lotes de {subdivision_size}")
                    sublotes = subdivide_batch(failed_onus, subdivision_size)
                    
                    for idx, sublote in enumerate(sublotes, 1):
                        logger.info(f"   📤 Encolando sublote {idx}/{len(sublotes)} ({len(sublote)} ONUs)")
                        get_poller_task.apply_async(
                            args=[sublote, olt_id, oid_string, snmp_config, execution_id],
                            kwargs={'oid_config': oid_config, 'depth': 1},  # Profundidad 1 = subdividido
                            countdown=retry_delay
                        )
                
                # DEPTH 1: Lote subdividido (50) → Procesar individualmente
                elif depth == 1 and batch_size > 1:
                    logger.info(f"🔀 Procesando {len(failed_onus)} ONUs individualmente")
                    
                    for onu_data in failed_onus:
                        retry_count = onu_data.get('retry_count', 0)
                        
                        # Verificar si aún puede reintentar
                        if retry_count <= max_retries_individual:
                            logger.info(f"   📤 Encolando ONU individual {onu_data['normalized_id']} (intento {retry_count})")
                            get_poller_task.apply_async(
                                args=[[onu_data], olt_id, oid_string, snmp_config, execution_id],
                                kwargs={'oid_config': oid_config, 'depth': 2},  # Profundidad 2 = individual
                                countdown=retry_delay * retry_count  # Backoff exponencial
                            )
                        else:
                            logger.error(f"   ❌ ONU {onu_data['normalized_id']} alcanzó máximo de reintentos ({max_retries_individual})")
                
                # DEPTH 2: Individual → Máximo de reintentos alcanzado
                elif depth == 2:
                    for onu_data in failed_onus:
                        retry_count = onu_data.get('retry_count', 0)
                        if retry_count <= max_retries_individual:
                            logger.info(f"   🔁 Reintentando ONU individual {onu_data['normalized_id']} (intento {retry_count})")
                            get_poller_task.apply_async(
                                args=[[onu_data], olt_id, oid_string, snmp_config, execution_id],
                                kwargs={'oid_config': oid_config, 'depth': 2},
                                countdown=retry_delay * retry_count
                            )
                        else:
                            logger.error(f"   ❌ ONU {onu_data['normalized_id']} DEFINITIVAMENTE FALLÓ después de {retry_count} intentos")
            
            logger.info(f"✅ get_poller_task [depth={depth}] completado: {success_count}/{batch_size} exitosos, {error_count} errores")
            
            return {
                'status': 'completed',
                'success_count': success_count,
                'error_count': error_count,
                'total_processed': batch_size,
                'failed_onus': len(failed_onus),
                'depth': depth,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"❌ Error crítico en get_poller_task [depth={depth}]: {str(e)}")
            raise
        finally:
            # SIEMPRE liberar el semáforo SNMP (como en facho_deluxe)
            if semaphore:
                semaphore.release()
                logger.debug(f"🔓 Semáforo SNMP liberado para OLT {olt_id}")
    
    except Exception as e:
        logger.error(f"❌ Error general en get_poller_task [depth={depth}]: {str(e)}")
        raise
    finally:
        # SIEMPRE liberar el slot de poller (contador de pollers concurrentes)
        release_olt_poller_slot(olt_id)
        logger.debug(f"🔓 Slot de poller liberado para OLT {olt_id}")


def execute_get_main(snmp_job_id, olt_id, execution_id, queue_name='get_main', attempt=0):
    """
    Función principal que ejecuta la lógica GET.
    
    1. Lee configuración específica para GET desde BD
    2. Obtiene todas las ONUs con presence='ENABLED' para la OLT
    3. Divide el trabajo en lotes (pollers)
    4. Encola tareas poller para procesamiento paralelo
    5. Actualiza el estado de la ejecución
    """
    from snmp_jobs.models import SnmpJob
    from discovery.models import OnuStatus, OnuIndexMap
    from hosts.models import OLT
    from executions.models import Execution
    from configuracion_avanzada.models import ConfiguracionSNMP
    
    logger.info(f"📋 execute_get_main: Iniciando ejecución {execution_id}")
    
    start_time = time.time()
    
    try:
        # Obtener la tarea SNMP
        job = SnmpJob.objects.select_related('oid', 'marca').get(id=snmp_job_id)
        olt = OLT.objects.get(id=olt_id)
        execution = Execution.objects.get(id=execution_id)
        
        # Obtener configuración específica para GET desde BD
        config_snmp = ConfiguracionSNMP.get_config_for_tipo('get')
        
        if config_snmp:
            logger.info(f"📋 Usando configuración SNMP: {config_snmp.nombre}")
            logger.info(f"   Timeout: {config_snmp.timeout}s | Reintentos SNMP: {config_snmp.reintentos}")
            logger.info(f"   Pollers: {config_snmp.max_pollers_por_olt} | Lote: {config_snmp.tamano_lote_inicial} | Subdivisión: {config_snmp.tamano_subdivision}")
            logger.info(f"   Semáforo: {config_snmp.max_consultas_snmp_simultaneas} consultas simultáneas")
        else:
            logger.warning(f"⚠️ No hay configuración SNMP para GET, usando valores por defecto")
            config_snmp = None
        
        # Validar que sea tipo GET
        if job.job_type != 'get':
            raise ValueError(f"Esta tarea no es de tipo GET: {job.job_type}")
        
        # Validar que el OID sea de tipo 'descripcion'
        if job.oid.espacio != 'descripcion':
            logger.warning(f"⚠️ OID no es de tipo 'descripcion': {job.oid.espacio}")
        
        # Actualizar estado de ejecución a RUNNING
        execution.status = 'RUNNING'
        execution.started_at = timezone.now()
        execution.attempt = attempt
        execution.worker_name = queue_name
        execution.celery_task_id = execute_get_main.__name__
        execution.save(update_fields=['status', 'started_at', 'attempt', 'worker_name', 'celery_task_id'])
        
        logger.info(f"🔍 Consultando ONUs activas para OLT {olt.abreviatura}")
        
        # Obtener todas las ONUs con presence='ENABLED' para esta OLT
        active_onus_raw = OnuStatus.objects.filter(
            olt_id=olt_id,
            presence='ENABLED'
        ).select_related('onu_index').values(
            'onu_index_id',
            'onu_index__raw_index_key',
            'onu_index__normalized_id'
        )
        
        # Renombrar claves para que el poller pueda accederlas correctamente
        active_onus = [
            {
                'onu_index_id': onu['onu_index_id'],
                'raw_index_key': onu['onu_index__raw_index_key'],
                'normalized_id': onu['onu_index__normalized_id']
            }
            for onu in active_onus_raw
        ]
        
        total_onus = len(active_onus)
        logger.info(f"📊 Total de ONUs activas encontradas: {total_onus}")
        
        if total_onus == 0:
            logger.warning(f"⚠️ No hay ONUs activas para consultar en OLT {olt.abreviatura}")
            execution.status = 'SUCCESS'
            execution.finished_at = timezone.now()
            execution.duration_ms = int((time.time() - start_time) * 1000)
            execution.result_summary = {
                'total_onus': 0,
                'message': 'No hay ONUs activas para consultar'
            }
            execution.save(update_fields=['status', 'finished_at', 'duration_ms', 'result_summary'])
            return
        
        # Dividir en lotes para pollers (usar configuración de BD si existe)
        batch_size = job.run_options.get(
            'batch_size', 
            config_snmp.tamano_lote_inicial if config_snmp else INITIAL_BATCH_SIZE
        )
        
        # active_onus ya es una lista con claves renombradas
        onu_list = active_onus
        
        # Dividir en lotes
        batches = [onu_list[i:i + batch_size] for i in range(0, len(onu_list), batch_size)]
        total_batches = len(batches)
        
        logger.info(f"📦 Dividiendo trabajo en {total_batches} lotes de ~{batch_size} ONUs")
        
        # Configuración SNMP (PRIORIDAD: OLT > run_options > config BD > defaults)
        if config_snmp:
            snmp_config = {
                'community': olt.comunidad or job.run_options.get('community', config_snmp.comunidad),
                'version': 2 if config_snmp.version == '2c' else int(config_snmp.version),
                'timeout': job.run_options.get('timeout', config_snmp.timeout),
                'retries': job.run_options.get('retries', config_snmp.reintentos),
                # Parámetros de pollers
                'max_pollers_por_olt': config_snmp.max_pollers_por_olt,
                'tamano_subdivision': config_snmp.tamano_subdivision,
                'max_reintentos_individuales': config_snmp.max_reintentos_individuales,
                'delay_entre_reintentos': config_snmp.delay_entre_reintentos,
                'max_consultas_snmp_simultaneas': config_snmp.max_consultas_snmp_simultaneas,
            }
        else:
            # Fallback a valores por defecto
            snmp_config = {
                'community': olt.comunidad or job.run_options.get('community', 'public'),
                'version': job.run_options.get('snmp_version', 2),
                'timeout': job.run_options.get('timeout', 3),
                'retries': job.run_options.get('retries', 1),
                'max_pollers_por_olt': MAX_POLLERS_PER_OLT,
                'tamano_subdivision': SUBDIVISION_SIZE,
                'max_reintentos_individuales': MAX_INDIVIDUAL_RETRIES,
                'delay_entre_reintentos': RETRY_DELAY,
                'max_consultas_snmp_simultaneas': 5,
            }
        
        # Extraer configuración del OID para los pollers
        oid_config = {
            'target_field': job.oid.target_field or 'snmp_description',
            'keep_previous_value': job.oid.keep_previous_value,
            'format_mac': job.oid.format_mac,
            'espacio': job.oid.espacio
        }
        logger.info(f"🔧 Configuración OID: Campo='{oid_config['target_field']}', Mantener previo={oid_config['keep_previous_value']}, Formatear MAC={oid_config['format_mac']}")
        
        # Encolar tareas poller
        poller_tasks = []
        for idx, batch in enumerate(batches, 1):
            logger.info(f"   📤 Encolando lote {idx}/{total_batches} ({len(batch)} ONUs)")
            
            task_result = get_poller_task.delay(
                onu_batch=batch,
                olt_id=olt_id,
                oid_string=job.oid.oid,
                snmp_config=snmp_config,
                execution_id=execution_id,
                oid_config=oid_config
            )
            
            poller_tasks.append({
                'task_id': task_result.id,
                'batch_number': idx,
                'onu_count': len(batch)
            })
        
        # Actualizar ejecución con información de pollers
        execution.result_summary = {
            'total_onus': total_onus,
            'total_batches': total_batches,
            'batch_size': batch_size,
            'poller_tasks': poller_tasks,
            'oid': job.oid.oid,
            'oid_name': job.oid.nombre
        }
        execution.save(update_fields=['result_summary'])
        
        logger.info(f"✅ Pollers encolados exitosamente. Total: {total_batches} lotes")
        
        # Marcar como SUCCESS (los pollers se encargan de actualizar las ONUs)
        execution.status = 'SUCCESS'
        execution.finished_at = timezone.now()
        execution.duration_ms = int((time.time() - start_time) * 1000)
        execution.save(update_fields=['status', 'finished_at', 'duration_ms'])
        
        logger.info(f"✅ execute_get_main completado en {execution.duration_ms}ms")
        
        # CALLBACK AL COORDINATOR: Notificar que GET terminó exitosamente
        try:
            from execution_coordinator.callbacks import on_task_completed
            on_task_completed(
                olt_id=olt.id,
                task_name=job.nombre,
                task_type=job.job_type,
                duration_ms=execution.duration_ms,
                status='SUCCESS'
            )
        except Exception as callback_error:
            logger.warning(f"Error en callback coordinator: {callback_error}")
        
    except Exception as e:
        logger.error(f"❌ Error en execute_get_main: {str(e)}")
        
        # Actualizar ejecución con error
        try:
            execution.status = 'FAILED'
            execution.finished_at = timezone.now()
            execution.duration_ms = int((time.time() - start_time) * 1000)
            execution.error_message = str(e)
            execution.save(update_fields=['status', 'finished_at', 'duration_ms', 'error_message'])
        except Exception as save_error:
            logger.error(f"❌ Error guardando estado de ejecución: {save_error}")
        
        # CALLBACK AL COORDINATOR: Notificar que GET falló
        try:
            from execution_coordinator.callbacks import on_task_failed
            on_task_failed(
                olt_id=olt_id,
                task_name=job.nombre,
                task_type=job.job_type,
                error_message=str(e)
            )
        except Exception as callback_error:
            logger.warning(f"Error en callback coordinator: {callback_error}")
        
        # Programar reintento si corresponde
        if attempt < job.max_retries:
            logger.info(f"🔁 Programando reintento {attempt + 1}/{job.max_retries}")
            get_retry_task.apply_async(
                args=[snmp_job_id, olt_id, execution_id, attempt + 1],
                countdown=job.retry_delay_seconds
            )
        else:
            logger.error(f"❌ Máximo de reintentos alcanzado ({job.max_retries})")
        
        raise

