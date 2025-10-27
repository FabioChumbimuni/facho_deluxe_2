"""
Signals para gestionar eventos en SnmpJob y SnmpJobHost

Cuando se habilita un SnmpJob:
- Inicializa next_run_at en TODOS los SnmpJobHost
- Primera ejecución en 1 minuto
- Sin catch-up (no ejecuta las pasadas)
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from .models import SnmpJob, SnmpJobHost
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=SnmpJob)
def detect_job_enabled(sender, instance, **kwargs):
    """
    Detecta cuando se habilita un SnmpJob y marca para inicialización
    """
    if instance.pk:
        try:
            old_instance = SnmpJob.objects.get(pk=instance.pk)
            # Detectar si se está habilitando (estaba disabled, ahora enabled)
            if not old_instance.enabled and instance.enabled:
                instance._just_enabled = True
                instance._is_existing = True  # Ya existía antes
            else:
                instance._just_enabled = False
                instance._is_existing = False
        except SnmpJob.DoesNotExist:
            instance._just_enabled = False
            instance._is_existing = False
    else:
        # Es nuevo (se está creando)
        instance._is_new = True
        instance._is_existing = False


@receiver(post_save, sender=SnmpJob)
def initialize_job_hosts_on_enable(sender, instance, created, **kwargs):
    """
    Inicializa next_run_at en SnmpJobHost según el caso:
    
    TAREA NUEVA (recién creada):
      - Primera ejecución: now + 1 minuto
      - Siguiente: now + intervalo
    
    TAREA EXISTENTE (ya creada, solo habilitada):
      - Primera ejecución: now + intervalo completo
      - Ejemplo: Intervalo 10 min, habilitas a 10:50 → ejecuta a 11:00
    """
    # Si se acaba de habilitar (tarea EXISTENTE)
    if hasattr(instance, '_just_enabled') and instance._just_enabled and hasattr(instance, '_is_existing') and instance._is_existing:
        logger.info(f"✅ Tarea EXISTENTE '{instance.nombre}' habilitada, inicializando con intervalo COMPLETO...")
        
        # Inicializar todos los job_hosts
        job_hosts = SnmpJobHost.objects.filter(snmp_job=instance, enabled=True)
        
        now = timezone.now()
        interval_seconds = instance.interval_seconds or 300  # Default 5 min
        initialized = 0
        
        for jh in job_hosts:
            # TAREA EXISTENTE: next_run = now + intervalo COMPLETO + DESFASE
            next_time = now + timedelta(seconds=interval_seconds)
            
            # DESFASE INTENCIONAL según tipo de tarea
            if instance.job_type == 'descubrimiento':
                next_time = next_time.replace(second=0, microsecond=0)
            elif instance.job_type == 'get':
                next_time = next_time.replace(second=10, microsecond=0)
            
            jh.next_run_at = next_time
            jh.last_run_at = None  # Resetear
            jh.save(update_fields=['next_run_at', 'last_run_at'])
            initialized += 1
        
        logger.info(f"   Inicializados {initialized} SnmpJobHost (próxima ejecución en {interval_seconds}s)")
    
    # Si es tarea NUEVA (recién creada)
    elif created and instance.enabled:
        logger.info(f"🆕 Tarea NUEVA '{instance.nombre}', inicializando con 1 minuto...")
        
        # Para tareas nuevas, esperar a que se creen los job_hosts
        # (se crean después en el admin)


@receiver(post_save, sender=SnmpJobHost)
def initialize_new_job_host(sender, instance, created, **kwargs):
    """
    Cuando se crea un SnmpJobHost nuevo, inicializa next_run_at
    
    Regla TAREA NUEVA: Primera ejecución en 1 minuto
    """
    if created and instance.enabled and instance.snmp_job.enabled:
        if not instance.next_run_at:
            # Para tarea nueva: ejecutar en 1 minuto
            instance.initialize_next_run(is_new=True)
            instance.save(update_fields=['next_run_at'])
            
            logger.info(f"🆕 SnmpJobHost creado (TAREA NUEVA): {instance.olt.abreviatura} - {instance.snmp_job.nombre} (próxima en 1 min)")

