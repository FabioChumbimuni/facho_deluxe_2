"""
Tareas de Celery para la recolección automática de datos desde Zabbix.
"""

import os
import django
from celery import shared_task
from django.utils import timezone
from django.conf import settings
import logging

# Configurar Django para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_single_olt_ports(self, olt_id, schedule_id=None):
    """
    Sincroniza puertos de una OLT específica desde Zabbix.
    
    Args:
        olt_id: ID de la OLT a sincronizar
        schedule_id: ID de la programación (opcional)
    """
    try:
        from hosts.models import OLT
        from .models import ZabbixCollectionOLT, ZabbixCollectionSchedule
        from .services.zabbix_service import ZabbixService
        
        # Obtener OLT
        try:
            olt = OLT.objects.get(id=olt_id)
        except OLT.DoesNotExist:
            logger.error(f"OLT con ID {olt_id} no encontrada")
            return {'success': False, 'error': f'OLT {olt_id} no encontrada'}
        
        # Obtener configuración de la OLT en la programación
        olt_config = None
        if schedule_id:
            try:
                schedule = ZabbixCollectionSchedule.objects.get(id=schedule_id)
                olt_config = ZabbixCollectionOLT.objects.get(schedule=schedule, olt=olt)
            except (ZabbixCollectionSchedule.DoesNotExist, ZabbixCollectionOLT.DoesNotExist):
                logger.warning(f"No se encontró configuración para OLT {olt.abreviatura} en schedule {schedule_id}")
        
        # Actualizar estado a 'pending'
        if olt_config:
            olt_config.ultimo_estado = 'pending'
            olt_config.save()
        
        # Ejecutar sincronización
        logger.info(f"Iniciando sincronización de OLT {olt.abreviatura}")
        
        # Obtener configuración activa de Zabbix desde BD
        from zabbix_config.models import ZabbixConfiguration
        
        zabbix_config = ZabbixConfiguration.get_active_config()
        if not zabbix_config:
            error_msg = "No hay configuración activa de Zabbix"
            logger.error(error_msg)
            if olt_config:
                olt_config.ultimo_estado = 'error'
                olt_config.ultimo_error = error_msg
                olt_config.ultima_recoleccion = timezone.now()
                olt_config.save()
            return {'success': False, 'error': error_msg}
        
        # Usar configuración de BD
        zabbix_service = ZabbixService(zabbix_config.zabbix_url, zabbix_config.zabbix_token)
        item_key = zabbix_config.item_key
        
        # Obtener datos específicos para esta OLT
        olt_data = zabbix_service.get_item_master_data(item_key, olt.abreviatura)
        
        if not olt_data:
            error_msg = f"No se encontraron datos en Zabbix para OLT {olt.abreviatura}"
            logger.warning(error_msg)
            
            if olt_config:
                olt_config.ultimo_estado = 'error'
                olt_config.ultimo_error = error_msg
                olt_config.ultima_recoleccion = timezone.now()
                olt_config.save()
            
            return {'success': False, 'error': error_msg, 'olt': olt.abreviatura}
        
        # Parsear datos de puertos
        ports_data = []
        for item in olt_data:
            if item.get('lastvalue'):
                parsed_ports = zabbix_service.parse_odf_data(item['lastvalue'], olt)
                ports_data.extend(parsed_ports)
        
        if not ports_data:
            error_msg = f"No se parsearon puertos para OLT {olt.abreviatura}"
            logger.warning(error_msg)
            
            if olt_config:
                olt_config.ultimo_estado = 'error'
                olt_config.ultimo_error = error_msg
                olt_config.ultima_recoleccion = timezone.now()
                olt_config.save()
            
            return {'success': False, 'error': error_msg, 'olt': olt.abreviatura}
        
        # Sincronizar puertos
        stats = zabbix_service._sync_olt_ports(olt, ports_data)
        
        # Actualizar estado a 'success'
        if olt_config:
            olt_config.ultimo_estado = 'success'
            olt_config.ultimo_error = ''
            olt_config.ultima_recoleccion = timezone.now()
            olt_config.save()
        
        logger.info(f"Sincronización completada para OLT {olt.abreviatura}: {stats}")
        
        return {
            'success': True,
            'olt': olt.abreviatura,
            'stats': stats
        }
        
    except Exception as e:
        error_msg = f"Error sincronizando OLT {olt_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Actualizar estado de error
        if olt_config:
            olt_config.ultimo_estado = 'error'
            olt_config.ultimo_error = str(e)[:500]  # Limitar longitud del error
            olt_config.ultima_recoleccion = timezone.now()
            olt_config.save()
        
        # Reintentar si no hemos alcanzado el máximo
        if self.request.retries < self.max_retries:
            logger.info(f"Reintentando sincronización de OLT {olt_id} (intento {self.request.retries + 1})")
            raise self.retry(countdown=60 * (self.request.retries + 1))  # Esperar más tiempo en cada reintento
        
        return {'success': False, 'error': error_msg, 'olt_id': olt_id}


@shared_task
def sync_scheduled_olts():
    """
    Tarea principal que ejecuta la sincronización según las programaciones habilitadas.
    Esta tarea es llamada por Celery Beat según la configuración de cron.
    """
    from .models import ZabbixCollectionSchedule, ZabbixCollectionOLT
    from datetime import timedelta
    
    logger.info("Ejecutando sincronización programada de OLTs")
    
    now = timezone.now()
    results = {
        'schedules_processed': 0,
        'olts_queued': 0,
        'errors': 0
    }
    
    try:
        # Obtener programaciones que deben ejecutarse
        schedules = ZabbixCollectionSchedule.objects.filter(
            habilitado=True,
            proxima_ejecucion__lte=now
        )
        
        for schedule in schedules:
            try:
                # Obtener OLTs habilitadas para esta programación
                olt_configs = ZabbixCollectionOLT.objects.filter(
                    schedule=schedule,
                    habilitado=True
                ).select_related('olt')
                
                # Encolar tareas para cada OLT
                for olt_config in olt_configs:
                    sync_single_olt_ports.delay(olt_config.olt.id, schedule.id)
                    results['olts_queued'] += 1
                
                # Actualizar próxima ejecución (NO es primera vez)
                schedule.ultima_ejecucion = now
                schedule.calcular_proxima_ejecucion(primera_vez=False)
                schedule.save()
                
                results['schedules_processed'] += 1
                
                logger.info(f"Programación '{schedule.nombre}' procesada: {olt_configs.count()} OLTs encoladas")
                
            except Exception as e:
                logger.error(f"Error procesando programación {schedule.id}: {e}")
                results['errors'] += 1
        
        logger.info(f"Sincronización programada completada: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Error en sincronización programada: {e}", exc_info=True)
        results['errors'] += 1
        return results


@shared_task
def cleanup_old_sync_logs():
    """
    Limpia logs antiguos de sincronización para evitar acumulación excesiva de datos.
    """
    from .models import ZabbixCollectionOLT
    from datetime import timedelta
    
    logger.info("Iniciando limpieza de logs antiguos")
    
    try:
        # Limpiar errores antiguos (más de 30 días)
        cutoff_date = timezone.now() - timedelta(days=30)
        
        updated = ZabbixCollectionOLT.objects.filter(
            ultima_recoleccion__lt=cutoff_date,
            ultimo_estado='error'
        ).update(
            ultimo_error='',
            ultimo_estado='pending'
        )
        
        logger.info(f"Limpieza completada: {updated} logs antiguos limpiados")
        return {'cleaned_logs': updated}
        
    except Exception as e:
        logger.error(f"Error en limpieza de logs: {e}", exc_info=True)
        return {'error': str(e)}

@shared_task
def sync_all_odf_hilos():
    """
    Lanza subtareas de sincronización por cada OLT registrada.
    Basado en NUEVO METODO.md para sincronización masiva eficiente.
    """
    from hosts.models import OLT
    
    logger.info("Iniciando sincronización masiva de odf_hilos con zabbix_port_data")
    
    olts_procesadas = 0
    for olt_id in OLT.objects.filter(habilitar_olt=True).values_list("id", flat=True):
        sync_odf_hilos_for_olt.delay(olt_id)
        olts_procesadas += 1
    
    logger.info(f"Sincronización masiva iniciada para {olts_procesadas} OLTs")
    return {'olts_encoladas': olts_procesadas}

@shared_task
def sync_odf_hilos_for_olt(olt_id):
    """
    Sincroniza los registros de odf_hilos con zabbix_port_data para una OLT específica.
    Usa SQL batch para máxima eficiencia según NUEVO METODO.md.
    """
    from django.db import connection
    from django.utils import timezone
    from hosts.models import OLT
    
    try:
        olt = OLT.objects.get(id=olt_id)
        logger.info(f"Iniciando sincronización batch para OLT {olt.abreviatura}")
        
        now = timezone.now()
        stats = {'hilos_habilitados': 0, 'hilos_deshabilitados': 0, 'errores': 0}
        
        with connection.cursor() as cursor:
            # 1️⃣ Marcar como presentes en Zabbix y vincular puerto
            cursor.execute("""
                UPDATE odf_hilos h
                SET en_zabbix = TRUE,
                    estado = CASE WHEN z.disponible THEN 'enabled' ELSE 'disabled' END,
                    zabbix_port_id = z.id,
                    updated_at = %s
                FROM zabbix_port_data z, odf o
                WHERE o.id = h.odf_id
                  AND o.olt_id = %s
                  AND h.slot = z.slot
                  AND h.port = z.port
                  AND z.olt_id = o.olt_id;
            """, [now, olt_id])
            
            stats['hilos_habilitados'] = cursor.rowcount
            
            # 2️⃣ Marcar como ausentes (no existen en Zabbix)
            cursor.execute("""
                UPDATE odf_hilos h
                SET en_zabbix = FALSE,
                    estado = 'disabled',
                    zabbix_port_id = NULL,
                    updated_at = %s
                FROM odf o
                WHERE o.id = h.odf_id
                  AND o.olt_id = %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM zabbix_port_data z
                      WHERE z.olt_id = o.olt_id
                        AND z.slot = h.slot
                        AND z.port = h.port
                  );
            """, [now, olt_id])
            
            stats['hilos_deshabilitados'] = cursor.rowcount
            
            # 3️⃣ Sincronizar operativo_noc del hilo al puerto Zabbix
            cursor.execute("""
                UPDATE zabbix_port_data z
                SET operativo_noc = h.operativo_noc
                FROM odf_hilos h, odf o
                WHERE o.id = h.odf_id
                  AND z.olt_id = o.olt_id
                  AND z.slot = h.slot
                  AND z.port = h.port
                  AND h.zabbix_port_id = z.id
                  AND z.operativo_noc != h.operativo_noc;
            """, [])
            
            stats['operativo_noc_sincronizados'] = cursor.rowcount
        
        logger.info(f"Sincronización batch completada para OLT {olt.abreviatura}: {stats}")
        return {'success': True, 'olt': olt.abreviatura, 'stats': stats}
        
    except OLT.DoesNotExist:
        error_msg = f"OLT con ID {olt_id} no encontrada"
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}
    except Exception as e:
        error_msg = f"Error sincronizando OLT {olt_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {'success': False, 'error': error_msg}