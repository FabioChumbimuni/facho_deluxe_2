"""
Signals para el modelo OLT
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import OLT


@receiver(post_save, sender=OLT)
def olt_post_save_handler(sender, instance, created, **kwargs):
    """
    Signal que se ejecuta después de guardar una OLT
    Aborta ejecuciones PENDING si se desactiva la OLT
    """
    if not created:  # Solo para OLTs existentes, no nuevas
        # Usar una transacción separada para evitar deadlocks
        def abort_executions():
            try:
                # Verificar si la OLT está deshabilitada
                if not instance.habilitar_olt:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"🔄 OLT DESACTIVADA: {instance.abreviatura} (ID: {instance.id})")
                    
                    # Abortar ejecuciones PENDING para esta OLT
                    from snmp_jobs.models import SnmpJob
                    aborted_count = SnmpJob.abort_pending_executions_for_olt(
                        instance.id, 
                        f"OLT {instance.abreviatura} deshabilitada"
                    )
                    
                    if aborted_count == 0:
                        logger.info(f"ℹ️ No había ejecuciones PENDING para abortar en OLT {instance.abreviatura}")
                        
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"❌ Error abortando ejecuciones para OLT {instance.abreviatura}: {e}")
        
        # Ejecutar en una transacción separada después del commit
        transaction.on_commit(abort_executions)
