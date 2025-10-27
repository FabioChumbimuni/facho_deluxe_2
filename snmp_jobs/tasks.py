import logging
from datetime import timedelta, datetime
from django.utils import timezone
from django.db import transaction
from celery import shared_task
from redis.lock import Lock
from redis import Redis
from django.conf import settings
from easysnmp import Session, EasySNMPError
from croniter import croniter
from configuracion_avanzada.services import get_snmp_timeout, get_snmp_retries

from .models import SnmpJob, SnmpJobHost
from executions.models import Execution
from configuracion_avanzada.services import get_dispatcher_interval, get_max_concurrent_executions, is_retry_system_enabled

logger = logging.getLogger(__name__)
redis_client = Redis.from_url(settings.CELERY_BROKER_URL)

def get_redis_lock(olt_id, timeout=300):
    """
    Obtiene un lock de Redis para una OLT específica
    
    IMPORTANTE: Usa la MISMA clave que el coordinator para consistencia
    """
    lock_key = f"lock:execution:olt:{olt_id}"
    return Lock(redis_client, lock_key, timeout=timeout)

def calculate_next_run(interval_raw):
    """
    Calcula el próximo tiempo de ejecución basado en interval_raw
    Usa timezone de Perú (America/Lima)
    """
    now = timezone.now()
    
    if not interval_raw:
        return now + timedelta(minutes=5)  # Default 5 minutos
    
    # Parsear interval_raw (ej: "30s", "5m", "1h", "1d")
    value = int(''.join(filter(str.isdigit, interval_raw)))
    unit = ''.join(filter(str.isalpha, interval_raw)).lower()
    
    if unit == 's':
        next_run = now + timedelta(seconds=value)
    elif unit == 'm':
        next_run = now + timedelta(minutes=value)
    elif unit == 'h':
        next_run = now + timedelta(hours=value)
    elif unit == 'd':
        next_run = now + timedelta(days=value)
    else:
        next_run = now + timedelta(minutes=value)  # Default a minutos
    
    logger.debug(f"⏰ Calculando next_run: {now.strftime('%H:%M:%S')} + {interval_raw} = {next_run.strftime('%H:%M:%S')}")
    return next_run

def parse_interval(interval_raw: str) -> int:
    """
    Convierte un string de intervalo en segundos.
    Soporta sufijos: s (segundos), m (minutos), h (horas), d (días).
    
    Args:
        interval_raw (str): String con formato "30s", "5m", "2h", "1d"
        
    Returns:
        int: Número de segundos
        
    Raises:
        ValueError: Si el formato no es válido
        
    Examples:
        >>> parse_interval("30s")
        30
        >>> parse_interval("5m")
        300
        >>> parse_interval("2h")
        7200
        >>> parse_interval("1d")
        86400
    """
    if not interval_raw or not interval_raw.strip():
        raise ValueError("Intervalo no puede estar vacío")
    
    # Limpiar y normalizar el string
    interval_str = interval_raw.strip().lower()
    
    # Extraer número y unidad usando regex
    import re
    match = re.match(r'^(\d+)([smhd])$', interval_str)
    if not match:
        raise ValueError(f"Formato de intervalo inválido: '{interval_raw}'. Use formato: 30s, 5m, 2h, 1d")
    
    value = int(match.group(1))
    unit = match.group(2)
    
    # Multiplicadores para convertir a segundos
    multipliers = {
        's': 1,           # segundos
        'm': 60,          # minutos
        'h': 3600,        # horas (60 * 60)
        'd': 86400,       # días (24 * 60 * 60)
    }
    
    seconds = value * multipliers[unit]
    logger.debug(f"🕐 Parseado intervalo: '{interval_raw}' → {seconds} segundos")
    return seconds

def calculate_next_run(job: SnmpJob) -> datetime:
    """
    Calcula el próximo tiempo de ejecución (next_run_at) para un SnmpJob.
    
    Prioridad de cálculo:
    1. Si job.cron_expr está definido → usar croniter para calcular próxima ejecución
    2. Si job.interval_seconds está definido → sumar a last_run_at o now
    3. Si job.interval_raw está definido → parsear y usar como interval_seconds
    4. Si no hay nada definido → retornar now + 1 hora (fallback)
    
    Args:
        job (SnmpJob): Job para calcular próxima ejecución
        
    Returns:
        datetime: Próxima fecha/hora de ejecución en timezone aware
        
    Examples:
        # Job con cron: "0 2 * * *" (diario a las 2:00 AM)
        >>> calculate_next_run(job_with_cron)
        datetime(2025-09-10, 2, 0, 0, tzinfo=timezone.utc)
        
        # Job con intervalo: 30 segundos
        >>> calculate_next_run(job_with_interval)
        datetime(2025-09-09, 0, 36, 30, tzinfo=timezone.utc)
    """
    now = timezone.now()
    
    # 1. PRIORIDAD: Cron expression (más preciso y flexible)
    if job.cron_expr and job.cron_expr.strip():
        try:
            # Usar last_run_at como base, o now si no hay last_run_at
            base_time = job.last_run_at if job.last_run_at else now
            
            # Crear iterador de cron
            cron = croniter(job.cron_expr, base_time)
            next_run = cron.get_next(datetime)
            
            logger.debug(f"📅 Cron '{job.cron_expr}': {base_time} → {next_run}")
            return next_run
            
        except Exception as e:
            logger.error(f"❌ Error calculando cron '{job.cron_expr}': {e}")
            # Fallback a intervalo si cron falla
            pass
    
    # 2. SEGUNDA PRIORIDAD: interval_seconds (ya calculado)
    if job.interval_seconds and job.interval_seconds > 0:
        # CORRECCIÓN: Usar now como base para evitar ejecuciones en cadena
        base_time = now
        next_run = base_time + timedelta(seconds=job.interval_seconds)
        
        logger.debug(f"⏱️ Intervalo {job.interval_seconds}s: {base_time} → {next_run}")
        return next_run
    
    # 3. TERCERA PRIORIDAD: interval_raw (parsear y usar)
    if job.interval_raw and job.interval_raw.strip():
        try:
            seconds = parse_interval(job.interval_raw)
            # CORRECCIÓN: Usar now como base para evitar ejecuciones en cadena
            base_time = now
            next_run = base_time + timedelta(seconds=seconds)
            
            logger.debug(f"🕐 Intervalo raw '{job.interval_raw}': {base_time} → {next_run}")
            return next_run
            
        except ValueError as e:
            logger.error(f"❌ Error parseando intervalo '{job.interval_raw}': {e}")
            # Fallback a 1 hora
            pass
    
    # 4. FALLBACK: 1 hora por defecto
    next_run = now + timedelta(hours=1)
    logger.warning(f"⚠️ Job '{job.nombre}' sin intervalo válido, usando fallback: {next_run}")
    return next_run

# Funciones de deshabilitación automática eliminadas - ya no se usa esta funcionalidad


@shared_task(
    bind=True,
    name='snmp_jobs.tasks.delete_history_records',
    queue='background_deletes',
    time_limit=600,  # 10 minutos máximo
    soft_time_limit=300  # 5 minutos soft limit
)
def delete_history_records(self, record_ids):
    """
    Borra registros de Execution usando procesamiento por lotes optimizado.
    Evita locks prolongados procesando en lotes pequeños con commits frecuentes.
    
    Args:
        record_ids: Puede ser una lista de IDs específicos o un entero indicando
                   el número de registros antiguos a borrar
    """
    import time
    from django.db import connection, transaction
    from executions.models import Execution
    
    start_time = time.time()
    
    # Si record_ids es un entero, obtener los registros más antiguos
    if isinstance(record_ids, int):
        num_records = record_ids
        logger.info(f"🗑️ delete_history_records: borrando {num_records} registros más antiguos")
        
        # Obtener los IDs de los registros más antiguos
        old_executions = Execution.objects.order_by('created_at')[:num_records]
        record_ids = list(old_executions.values_list('id', flat=True))
        
        if not record_ids:
            logger.warning("❌ No hay registros antiguos para borrar")
            return {"status": "error", "message": "No hay registros antiguos para borrar"}
    else:
        # Si es una lista, usar directamente
        record_ids = list(record_ids) if record_ids else []
        if not record_ids:
            logger.warning("❌ No hay IDs para borrar")
            return {"status": "error", "message": "No hay IDs para borrar"}
    
    total = len(record_ids)
    logger.info(f"🗑️ delete_history_records: comenzando borrado de {total} registros")
    logger.info(f"⚙️ Método: Procesamiento por lotes optimizado, timeout=5min")

    try:
        # Procesamiento por lotes optimizado para velocidad
        batch_size = 500  # Lotes más grandes para mayor velocidad
        total_deleted = 0
        batches_processed = 0
        
        # Dividir en lotes
        for i in range(0, total, batch_size):
            batch_ids = record_ids[i:i + batch_size]
            batch_start = time.time()
            
            logger.info(f"🔄 Procesando lote {batches_processed + 1}: {len(batch_ids)} registros")
            
            # Procesar lote en transacción separada
            with transaction.atomic():
                # PRIMERO: Actualizar referencias de clave foránea a NULL
                # Esto evita la violación de restricción de clave foránea
                with connection.cursor() as cursor:
                    ids_str = ','.join(str(id) for id in batch_ids)
                    
                    # Actualizar onu_inventory.snmp_last_execution_id a NULL
                    cursor.execute(f"""
                        UPDATE onu_inventory 
                        SET snmp_last_execution_id = NULL 
                        WHERE snmp_last_execution_id IN ({ids_str})
                    """)
                    onu_inventory_updated = cursor.rowcount
                    
                    # Actualizar onu_status.last_change_execution_id a NULL
                    cursor.execute(f"""
                        UPDATE onu_status 
                        SET last_change_execution_id = NULL 
                        WHERE last_change_execution_id IN ({ids_str})
                    """)
                    onu_status_updated = cursor.rowcount
                    
                    if onu_inventory_updated > 0 or onu_status_updated > 0:
                        logger.info(f"   🔗 Referencias FK actualizadas: onu_inventory={onu_inventory_updated}, onu_status={onu_status_updated}")
                    
                    # AHORA: Borrar los registros de snmp_executions
                    sql_query = f"DELETE FROM snmp_executions WHERE id IN ({ids_str})"
                    cursor.execute(sql_query)
                    batch_deleted = cursor.rowcount
                    total_deleted += batch_deleted
                    
                    logger.info(f"   📊 Lote {batches_processed + 1}: {batch_deleted}/{len(batch_ids)} borrados")
            
            batches_processed += 1
            batch_time = time.time() - batch_start
            logger.info(f"   ⏱️ Lote completado en {batch_time:.2f}s")
            
            # Pausa mínima solo cada 10 lotes para mayor velocidad
            if batches_processed % 10 == 0:  # Cada 10 lotes
                time.sleep(0.05)  # Pausa más corta
                logger.info(f"   💤 Pausa preventiva después de {batches_processed} lotes")
        
        total_time = time.time() - start_time
        logger.info(f"✅ delete_history_records: terminado en {total_time:.3f}s")
        logger.info(f"📊 Total borrados: {total_deleted}/{total} registros en {batches_processed} lotes")
        
        return {
            "status": "success",
            "deleted_count": total_deleted,
            "total_processed": total,
            "execution_time": total_time,
            "batches_processed": batches_processed,
            "method": "optimized_batch_processing"
        }
        
    except Exception as e:
        logger.error(f"❌ Error en delete_history_records: {e}")
        return {
            "status": "error",
            "error": str(e),
            "deleted_count": total_deleted if 'total_deleted' in locals() else 0,
            "total_processed": total,
            "batches_processed": batches_processed if 'batches_processed' in locals() else 0
        }

@shared_task(queue='cleanup', bind=True, time_limit=120)
def cleanup_old_executions_task(self, days_old=7, batch_size=1000):
    """
    Tarea de limpieza de ejecuciones antiguas usando SQL nativo
    Elimina ejecuciones más antiguas que X días usando DELETE directo
    """
    import time
    from django.db import connection
    
    logger.info(f"🧹 Iniciando limpieza de ejecuciones antiguas (más de {days_old} días)")
    
    try:
        cutoff_date = timezone.now() - timedelta(days=days_old)
        start_time = time.time()
        
        # Usar SQL nativo para contar y borrar
        with connection.cursor() as cursor:
            # Contar registros antiguos
            cursor.execute(
                "SELECT COUNT(*) FROM snmp_executions WHERE created_at < %s",
                [cutoff_date]
            )
            total_old = cursor.fetchone()[0]
            
            logger.info(f"📋 Total de ejecuciones antiguas encontradas: {total_old}")
            
            if total_old == 0:
                logger.info("✅ No hay ejecuciones antiguas para limpiar")
                return {"status": "success", "message": "No hay ejecuciones antiguas"}
            
            # Borrar registros antiguos usando SQL directo
            cursor.execute(
                "DELETE FROM snmp_executions WHERE created_at < %s",
                [cutoff_date]
            )
            deleted_count = cursor.rowcount
            
            # Commit de la transacción
            connection.commit()
        
        total_time = time.time() - start_time
        logger.info(f"✅ Limpieza completada en {total_time:.3f}s. Total eliminadas: {deleted_count}")
        return {
            "status": "success", 
            "deleted_count": deleted_count,
            "total_processed": total_old,
            "execution_time": total_time,
            "method": "native_sql"
        }
        
    except Exception as e:
        logger.error(f"❌ Error durante la limpieza de ejecuciones antiguas: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

@shared_task
def dispatcher_check_and_enqueue():
    """
    Dispatcher inteligente que respeta intervalos y expresiones cron.
    
    Funcionamiento:
    1. Se ejecuta cada X segundos via Celery Beat (configurable)
    2. Solo procesa jobs que están listos (next_run_at <= now)
    3. Respeta intervalos (30s, 5m, 1h, 1d) y expresiones cron
    4. Actualiza next_run_at SOLO después de encolar la tarea
    5. Soporta job_type: 'descubrimiento' y 'get'
    """
    logger.info("🔍 Dispatcher Inteligente: Revisando tareas habilitadas...")
    
    now = timezone.now()
    # Mostrar hora en zona horaria de Perú
    import pytz
    lima_tz = pytz.timezone('America/Lima')
    now_lima = now.astimezone(lima_tz)
    logger.info(f"⏰ Hora actual (Perú): {now_lima.strftime('%Y-%m-%d %H:%M:%S')} (UTC: {now.strftime('%Y-%m-%d %H:%M:%S')})")
    
    # Buscar jobs listos para ejecutar (SOLO automáticos, NO manuales)
    # Incluir tanto 'descubrimiento' como 'get'
    all_ready_jobs = SnmpJob.objects.filter(
        enabled=True,  # ← CRÍTICO: Solo jobs habilitados
        job_type__in=['descubrimiento', 'get'],  # Soportar ambos tipos
        next_run_at__lte=now
    )
    
    # Filtrar manualmente para excluir jobs con ejecuciones manuales pendientes
    ready_jobs = []
    for job in all_ready_jobs:
        # Verificar si tiene ejecuciones manuales pendientes
        manual_pending = Execution.objects.filter(
            snmp_job=job,
            status__in=['PENDING', 'RUNNING'],
            requested_by__isnull=False
        ).exists()
        
        if not manual_pending:
            ready_jobs.append(job)
    
    logger.info(f"📊 Jobs listos para ejecutar: {len(ready_jobs)}")
    
    total_created = 0
    for job in ready_jobs:
        logger.info(f"📋 Procesando job: {job.nombre} (Tipo: {job.job_type})")
        logger.info(f"   Intervalo raw: {job.interval_raw}")
        logger.info(f"   Cron expr: {job.cron_expr}")
        logger.info(f"   Next run actual: {job.next_run_at}")
        
        # Obtener job_hosts habilitados para este job
        job_hosts = job.job_hosts.filter(enabled=True)
        logger.info(f"📡 Job hosts habilitados: {job_hosts.count()}")
        
        executions_created = 0
        for job_host in job_hosts:
            if job_host.olt.habilitar_olt:
                # Crear registro de ejecución (AUTOMÁTICA - sin requested_by)
                execution = Execution.objects.create(
                    snmp_job=job,
                    job_host=job_host,
                    olt=job_host.olt,
                    status='PENDING',
                    attempt=0  # Tarea principal siempre es attempt 0
                    # requested_by=None (implícito) - Ejecución automática
                )
                
                logger.info(f"✅ Creada ejecución: {execution.id} para OLT {job_host.olt.abreviatura}")
                
                # Encolar la tarea según el tipo de job
                if job.job_type == 'descubrimiento':
                    task_result = discovery_main_task.delay(job.id, job_host.olt.id, execution.id)
                    logger.info(f"🔍 Tarea DISCOVERY encolada: {task_result.id} en cola discovery_main")
                elif job.job_type == 'get':
                    from snmp_get.tasks import get_main_task
                    task_result = get_main_task.delay(job.id, job_host.olt.id, execution.id)
                    logger.info(f"📥 Tarea GET encolada: {task_result.id} en cola get_main")
                
                executions_created += 1
                total_created += 1
            else:
                logger.warning(f"⚠️ OLT {job_host.olt.abreviatura} está deshabilitada, saltando")
        
        # ACTUALIZAR last_run_at y next_run_at DESPUÉS de encolar
        job.last_run_at = now
        job.next_run_at = calculate_next_run(job)  # Usar la nueva función inteligente
        job.save(update_fields=['last_run_at', 'next_run_at'])
        
        logger.info(f"⏰ Próxima ejecución de {job.nombre}: {job.next_run_at.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"📊 Ejecuciones creadas para {job.nombre}: {executions_created}")
    
    logger.info(f"✅ Dispatcher completado. Total ejecuciones creadas: {total_created}")

@shared_task(queue='discovery_main', bind=True, time_limit=180, autoretry_for=(Exception,), retry_kwargs={'max_retries': 0})
def discovery_main_task(self, snmp_job_id, olt_id, execution_id):
    """
    Tarea principal de descubrimiento SNMP
    Si falla, envía reintentos a cola separada (discovery_retry)
    NO usa reintentos automáticos de Celery (max_retries=0)
    """
    # Log simplificado - solo información esencial
    
    try:
        execute_discovery(snmp_job_id, olt_id, execution_id, queue_name='discovery_main')
        logger.info(f"✅ discovery_main_task: Completada exitosamente")
    except Exception as exc:
        # Log del error sin traceback para mantener logs limpios
        logger.error(f"❌ discovery_main_task: {str(exc)}")
        
        # Marcar como fallida la ejecución principal
        try:
            from executions.models import Execution
            execution = Execution.objects.get(pk=execution_id)
            
            # Solo actualizar si no está ya marcada como fallida
            if execution.status != 'FAILED':
                execution.status = 'FAILED'
                execution.error_message = str(exc)
                execution.finished_at = timezone.now()
                # Si no tiene started_at, asignarlo ahora
                if not execution.started_at:
                    execution.started_at = timezone.now()
                # Calcular duración
                if execution.started_at and execution.finished_at:
                    execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                execution.save()
            
            # SOLO enviar reintentos si NO es ejecución manual
            if execution.requested_by is None:  # Ejecución automática (sin usuario)
                # MARCAR OLT EN REINTENTO: Bloquear nuevas ejecuciones
                from redis import Redis
                from django.conf import settings
                redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
                retry_key = f"olt:retrying:{olt_id}"
                redis_client.set(retry_key, '1', ex=600)  # Expira en 10 min (por si falla el cleanup)
                
                logger.info(f"⏸️ OLT {olt_id} marcada EN REINTENTO - bloqueadas nuevas ejecuciones")
                
                # Enviar reintento con delay de 30s
                discovery_retry_task.apply_async(
                    args=[snmp_job_id, olt_id, execution_id, 1],
                    countdown=30  # 30 segundos de delay
                )
                logger.info(f"🔄 Enviado reintento 1 a cola discovery_retry (en 30s)")
            else:
                logger.info(f"🚫 Ejecución manual - NO se envían reintentos")
            
        except Exception as retry_exc:
            logger.error(f"❌ Error enviando reintento: {str(retry_exc)}")
        
        # La tarea principal termina aquí (no usa self.retry)
        return


@shared_task(queue='discovery_manual', bind=True, time_limit=180)
def discovery_manual_task(self, snmp_job_id, olt_id, execution_id):
    """
    Tarea de ejecución manual con máxima prioridad
    NO tiene reintentos automáticos
    """
    logger.info(f"🚀 discovery_manual_task: Ejecución manual para job {snmp_job_id}, OLT {olt_id}, execution {execution_id}")
    
    try:
        execute_discovery(snmp_job_id, olt_id, execution_id, queue_name='discovery_manual')
        logger.info(f"✅ discovery_manual_task: Completada exitosamente")
    except Exception as exc:
        logger.error(f"❌ discovery_manual_task: {str(exc)}")
        
        # Marcar como fallida la ejecución manual
        try:
            from executions.models import Execution
            execution = Execution.objects.get(pk=execution_id)
            
            if execution.status != 'FAILED':
                execution.status = 'FAILED'
                execution.error_message = str(exc)
                execution.finished_at = timezone.now()
                # Si no tiene started_at, asignarlo ahora
                if not execution.started_at:
                    execution.started_at = timezone.now()
                # Calcular duración
                if execution.started_at and execution.finished_at:
                    execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                execution.save()
            
            logger.info(f"🚫 Ejecución manual fallida - NO se envían reintentos")
            
        except Exception as retry_exc:
            logger.error(f"❌ Error manejando fallo de ejecución manual: {str(retry_exc)}")
        
        return


@shared_task(queue='discovery_retry', bind=True, time_limit=180)
def discovery_retry_task(self, snmp_job_id, olt_id, execution_id, retry_number):
    """
    Tarea de reintento para descubrimiento SNMP
    Verifica estado de OLT y tarea antes de ejecutar
    NO usa reintentos automáticos de Celery (max_retries=0)
    """
    logger.info(f"🔄 discovery_retry_task: Reintento {retry_number} para job {snmp_job_id}, OLT {olt_id}, execution {execution_id}")
    
    # VERIFICAR ESTADO ANTES DE EJECUTAR
    try:
        from snmp_jobs.models import SnmpJob
        from hosts.models import OLT
        from executions.models import Execution
        
        # Verificar si la tarea está deshabilitada
        job = SnmpJob.objects.get(pk=snmp_job_id)
        if not job.enabled:
            logger.info(f"🛑 Reintento {retry_number} cancelado: tarea '{job.nombre}' deshabilitada")
            execution = Execution.objects.get(pk=execution_id)
            execution.status = 'INTERRUPTED'
            execution.error_message = f"Tarea deshabilitada durante reintento {retry_number}"
            from django.utils import timezone
            execution.finished_at = timezone.now()
            execution.save()
            return
        
        # Verificar si la OLT está deshabilitada
        olt = OLT.objects.get(pk=olt_id)
        if not olt.habilitar_olt:
            logger.info(f"🛑 Reintento {retry_number} cancelado: OLT '{olt.abreviatura}' deshabilitada")
            execution = Execution.objects.get(pk=execution_id)
            execution.status = 'INTERRUPTED'
            execution.error_message = f"OLT {olt.abreviatura} deshabilitada durante reintento {retry_number}"
            from django.utils import timezone
            execution.finished_at = timezone.now()
            execution.save()
            return
            
    except Exception as check_exc:
        logger.error(f"❌ Error verificando estado en reintento {retry_number}: {check_exc}")
        return
    
    # Si llegamos aquí, todo está habilitado, proceder con el reintento
    try:
        # Crear una nueva ejecución para el reintento
        from executions.models import Execution
        from django.utils import timezone
        
        # Obtener la ejecución original para referencia
        original_execution = Execution.objects.get(pk=execution_id)
        
        # Crear nueva ejecución para el reintento
        retry_execution = Execution.objects.create(
            snmp_job=original_execution.snmp_job,
            job_host=original_execution.job_host,
            olt=original_execution.olt,
            status='PENDING',
            attempt=retry_number,
            requested_by=original_execution.requested_by,
            created_at=timezone.now()
        )
        
        logger.info(f"🔄 Creada nueva ejecución {retry_execution.id} para reintento {retry_number}")
        
        execute_discovery(snmp_job_id, olt_id, retry_execution.id, queue_name='discovery_retry')
        
        # Verificar el estado real de la nueva ejecución después de execute_discovery
        retry_execution.refresh_from_db()
        if retry_execution.status == 'SUCCESS':
            # DESMARCAR OLT: Reanudar ejecuciones normales
            from redis import Redis
            from django.conf import settings
            redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
            retry_key = f"olt:retrying:{olt_id}"
            redis_client.delete(retry_key)
            logger.info(f"✅ OLT {olt_id} desbloqueada - reinicio exitoso, ejecuciones reanudadas")
            logger.info(f"✅ discovery_retry_task: Reintento {retry_number} completado exitosamente")
            return  # Salir si fue exitoso
        
        # Si llegamos aquí, el reintento falló
        logger.error(f"❌ discovery_retry_task: Reintento {retry_number} falló - Estado: {retry_execution.status}, Error: {retry_execution.error_message}")
        
    except Exception as exc:
        # Log del error sin traceback para mantener logs limpios
        logger.error(f"❌ discovery_retry_task: Reintento {retry_number} falló - {str(exc)}")
        
        # Marcar como fallida
        try:
            if 'retry_execution' in locals():
                retry_execution.refresh_from_db()
                # Solo actualizar si no está ya marcada como fallida
                if retry_execution.status != 'FAILED':
                    retry_execution.status = 'FAILED'
                    retry_execution.error_message = f"Reintento {retry_number}: {str(exc)}"
                    retry_execution.finished_at = timezone.now()
                    # Si no tiene started_at, asignarlo ahora
                    if not retry_execution.started_at:
                        retry_execution.started_at = timezone.now()
                    # Calcular duración
                    if retry_execution.started_at and retry_execution.finished_at:
                        retry_execution.duration_ms = int((retry_execution.finished_at - retry_execution.started_at).total_seconds() * 1000)
                    retry_execution.save()
                
        except Exception as retry_exc:
            logger.error(f"❌ Error manejando fallo de reintento: {str(retry_exc)}")
    
    # Lógica de reintentos (se ejecuta siempre, tanto si falló execute_discovery como si hubo excepción)
    try:
        # Si es el primer reintento, enviar el segundo
        if retry_number == 1:
            logger.info(f"🔄 Enviando reintento 2 a cola discovery_retry")
            # Enviar segundo reintento con delay de 30s usando la ejecución original
            discovery_retry_task.apply_async(
                args=[snmp_job_id, olt_id, execution_id, 2],
                countdown=30  # 30 segundos de delay
            )
        else:
            # DESMARCAR OLT: Reintentos agotados, reanudar ejecuciones normales
            from redis import Redis
            from django.conf import settings
            redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
            retry_key = f"olt:retrying:{olt_id}"
            redis_client.delete(retry_key)
            logger.info(f"⚠️ OLT {olt_id} desbloqueada - reintentos agotados, ejecuciones reanudadas")
            logger.info(f"❌ Todos los reintentos agotados para execution {execution_id}")
            
    except Exception as retry_exc:
        logger.error(f"❌ Error enviando siguiente reintento: {str(retry_exc)}")


def execute_discovery(snmp_job_id, olt_id, execution_id, queue_name='discovery_main'):
    """
    Ejecuta el descubrimiento SNMP para una OLT específica
    Maneja diferentes tipos de job: descubrimiento, walk, get, etc.
    
    Args:
        queue_name: 'discovery_main', 'discovery_retry', o 'manual_execution'
                   Si es 'manual_execution', NO se envían reintentos
    """
    try:
        logger.info(f"🔍 execute_discovery INICIO - Job: {snmp_job_id}, OLT: {olt_id}, Exec: {execution_id}, Queue: {queue_name}")
        
        with transaction.atomic():
            execution = Execution.objects.select_for_update().get(pk=execution_id)
            
            # Log simplificado - solo información esencial
            
            # Si ya está completada, salir
            if execution.status in ['SUCCESS', 'FAILED']:
                logger.info(f"🔍 execute_discovery SALIDA - Ejecución ya completada: {execution.status}")
                return
            
            olt = execution.olt
            job = execution.snmp_job
            
            # Obtener job_host si no existe
            if not execution.job_host:
                job_host, created = SnmpJobHost.objects.get_or_create(
                    snmp_job=job,
                    olt=olt,
                    defaults={'enabled': True, 'consecutive_failures': 0}
                )
                execution.job_host = job_host
                execution.save()
            else:
                job_host = execution.job_host

            # Verificar que la OLT esté habilitada ANTES y DURANTE la ejecución
            if not job_host.enabled or not olt.habilitar_olt:
                logger.info(f"🔍 execute_discovery OLT DESHABILITADA - {olt.abreviatura}")
                execution.status = 'FAILED'
                execution.error_message = f"OLT {olt.abreviatura} deshabilitada"
                execution.finished_at = timezone.now()
                execution.save()
                return

            # Intentar obtener lock de Redis
            lock = get_redis_lock(olt.id)
            if not lock.acquire(blocking=False):
                logger.warning(f"🔍 execute_discovery LOCK NO DISPONIBLE - {olt.abreviatura}")
                raise Exception("Lock no disponible")
            
            # Lock obtenido - log innecesario removido
            lock_released = False  # Bandera para controlar liberación del lock
            
            try:
                # Marcar como en ejecución
                execution.status = 'RUNNING'
                execution.started_at = timezone.now()
                execution.worker_name = queue_name
                # NO modificar attempt aquí - ya fue establecido correctamente:
                # - Ejecuciones principales: attempt=0 (dispatcher)
                # - Reintentos: attempt=retry_number (discovery_retry_task)
                execution.save()
                
                logger.info(f"🔍 execute_discovery EJECUTANDO - Status: RUNNING, Attempt: {execution.attempt}")

                # Verificar nuevamente que la OLT siga habilitada durante la ejecución
                olt.refresh_from_db()
                if not olt.habilitar_olt:
                    logger.info(f"OLT {olt.abreviatura} fue deshabilitada durante la ejecución, cancelando")
                    execution.status = 'FAILED'
                    execution.error_message = f"OLT {olt.abreviatura} deshabilitada durante ejecución"
                    execution.finished_at = timezone.now()
                    execution.save()
                    return

                # Ejecutar según el tipo de job
                if job.job_type == 'descubrimiento':
                    # Usar la nueva lógica de descubrimiento
                    from discovery.services import execute_discovery_task, process_successful_discovery
                    
                    # Ejecutar walk y obtener resultados en memoria
                    discovery_results = execute_discovery_task(execution_id)
                    
                    # Verificar si el walk fue exitoso
                    if discovery_results.get('walk_successful', False) and not discovery_results.get('errors'):
                        # SOLO si es exitoso, procesar y actualizar base de datos
                        memory_data = discovery_results.get('memory_data', [])
                        if memory_data:
                            processing_results = process_successful_discovery(execution_id, memory_data)
                            # Combinar resultados
                            discovery_results.update(processing_results)
                        
                        # Marcar ejecución como exitosa
                        execution.status = 'SUCCESS'
                        logger.info(f"✅ Tarea descubrimiento SUCCESS - Datos procesados y guardados")
                    else:
                        # Si hay errores, marcar como FAILED
                        execution.status = 'FAILED'
                        execution.error_message = '; '.join(discovery_results.get('errors', ['Error desconocido en walk']))
                        logger.error(f"❌ Tarea descubrimiento FAILED - No se procesaron datos")
                    
                    # Crear resumen serializable (solo tipos básicos)
                    safe_summary = {
                        'walk_successful': discovery_results.get('walk_successful', False),
                        'total_found': discovery_results.get('total_found', 0),
                        'enabled_count': discovery_results.get('enabled_count', 0),
                        'disabled_count': discovery_results.get('disabled_count', 0),
                        'new_index_created': discovery_results.get('new_index_created', 0),
                        'errors': discovery_results.get('errors', []),
                        'duration_ms': discovery_results.get('duration_ms', 0)
                    }
                    
                    execution.result_summary = safe_summary
                    execution.raw_output = {
                        'job_type': 'descubrimiento',
                        'olt_id': olt.id,
                        'olt_name': olt.abreviatura,
                        'task_oid': job.oid.oid,
                        'discovery_results': safe_summary  # Solo datos serializables
                    }
                else:
                    # Lógica tradicional para otros tipos de job (walk, get, etc.)
                    session = Session(
                        hostname=olt.ip_address, 
                        community=olt.comunidad, 
                        version=2,
                        timeout=get_snmp_timeout(),
                        retries=get_snmp_retries()
                    )
                    
                    # Realizar SNMP walk tradicional
                    results = session.walk(job.oid.oid)
                    
                    # Procesar resultados (lógica tradicional simplificada)
                    records_processed = len(results)
                    
                    # Marcar ejecución como exitosa
                    execution.status = 'SUCCESS'
                    execution.result_summary = {
                        'total_records': records_processed,
                        'job_type': job.job_type,
                        'queue_used': queue_name
                    }
                    execution.raw_output = {
                        'job_type': job.job_type,
                        'olt_id': olt.id,
                        'olt_name': olt.abreviatura,
                        'total_results': records_processed
                    }
                
                execution.finished_at = timezone.now()
                execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                execution.save()
                
                # Actualizar estadísticas del job_host
                job_host.consecutive_failures = 0
                job_host.last_success_at = timezone.now()
                job_host.save()
                
                logger.info(f"Descubrimiento exitoso para OLT {olt.abreviatura}")
                
                # LIBERAR LOCK ANTES del callback (para que callback pueda ejecutar siguiente tarea)
                lock.release()
                lock_released = True  # Marcar como liberado
                
                # CALLBACK AL COORDINATOR: Notificar que la tarea terminó
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

            except EasySNMPError as e:
                # Manejar errores SNMP específicos con mensajes más claros
                error_msg = str(e).lower()
                if 'timeout' in error_msg or 'timed out' in error_msg:
                    friendly_error = f"Timeout SNMP - OLT {olt.abreviatura} ({olt.ip_address}) no responde"
                elif 'no such name' in error_msg or 'no such object' in error_msg:
                    friendly_error = f"OID no encontrado - OLT {olt.abreviatura} ({olt.ip_address})"
                elif 'authentication' in error_msg or 'community' in error_msg:
                    friendly_error = f"Error de autenticación - Comunidad SNMP incorrecta para OLT {olt.abreviatura} ({olt.ip_address})"
                elif 'connection' in error_msg or 'refused' in error_msg:
                    friendly_error = f"Conexión rechazada - OLT {olt.abreviatura} ({olt.ip_address}) no disponible"
                else:
                    friendly_error = f"Error SNMP - OLT {olt.abreviatura} ({olt.ip_address}): {str(e)}"
                
                logger.error(f"❌ {friendly_error}")
                
                # Marcar ejecución como fallida
                execution.status = 'FAILED'
                execution.error_message = friendly_error
                execution.finished_at = timezone.now()
                execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                execution.save()
                
                # Incrementar fallos consecutivos
                job_host.consecutive_failures += 1
                job_host.last_failure_at = timezone.now()
                job_host.save()
                
                # Re-lanzar con mensaje amigable
                raise Exception(friendly_error)
                
            except Exception as e:
                # Manejar otros errores con mensaje genérico
                friendly_error = f"Error interno - OLT {olt.abreviatura} ({olt.ip_address}): {str(e)}"
                logger.error(f"❌ {friendly_error}")
                
                execution.status = 'FAILED'
                execution.error_message = friendly_error
                execution.finished_at = timezone.now()
                execution.duration_ms = int((execution.finished_at - execution.started_at).total_seconds() * 1000)
                execution.save()
                
                # Incrementar fallos consecutivos
                job_host.consecutive_failures += 1
                job_host.last_failure_at = timezone.now()
                job_host.save()
                
                # CALLBACK AL COORDINATOR: Notificar fallo
                try:
                    from execution_coordinator.callbacks import on_task_failed
                    on_task_failed(
                        olt_id=olt.id,
                        task_name=job.nombre,
                        task_type=job.job_type,
                        error_message=friendly_error
                    )
                except Exception as callback_error:
                    logger.warning(f"Error en callback coordinator: {callback_error}")
                
                # Re-lanzar con mensaje amigable
                raise Exception(friendly_error)
                
            finally:
                # Liberar lock solo si NO fue liberado antes
                if not lock_released:
                    try:
                        lock.release()
                    except Exception:
                        pass  # Lock ya fue liberado o no se pudo liberar
    
    except Exception as e:
        # NO usar logger.exception para evitar traceback en logs
        # El error ya fue manejado en los bloques EasySNMPError o Exception anteriores
        # Solo re-lanzar para que discovery_main_task/discovery_retry_task lo capture
        raise

# Tarea de debug para testing
@shared_task
def debug_task():
    """
    Tarea de debug para verificar que Celery funciona
    """
    logger.info("Debug task ejecutada correctamente")
    return "Debug task completed"
