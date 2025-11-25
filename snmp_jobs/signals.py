"""
Signals para gestionar eventos en SnmpJob y SnmpJobHost

Cuando se habilita un SnmpJob:
- Inicializa next_run_at en TODOS los SnmpJobHost
- Primera ejecución en 1 minuto
- Sin catch-up (no ejecuta las pasadas)

Cuando se crea un WorkflowNode con OID:
- Crea automáticamente un SnmpJob si no existe para ese OID
- Crea SnmpJobHost para la OLT del workflow

Cuando se modifica una WorkflowTemplate o WorkflowTemplateNode:
- Sincroniza automáticamente los workflows vinculados con auto_sync=True
"""

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from .models import SnmpJob, SnmpJobHost, WorkflowNode, WorkflowTemplate, WorkflowTemplateNode, TaskTemplate
from hosts.models import OLT
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
            # TAREA EXISTENTE: next_run = now + intervalo COMPLETO
            # CRÍTICO: Asegurar que el intervalo completo se respete ANTES de aplicar desfase
            next_time = now + timedelta(seconds=interval_seconds)
            
            # DESFASE INTENCIONAL según tipo de tarea
            # IMPORTANTE: El desfase solo alinea al segundo, NO reduce el intervalo
            # CRÍTICO: Asegurar que el intervalo mínimo se respete (no usar desfase si reduce el tiempo)
            if instance.job_type == 'descubrimiento':
                aligned_time = next_time.replace(second=0, microsecond=0)
                # Solo usar el desfase si NO reduce el intervalo
                if aligned_time > next_time:
                    next_time = aligned_time
                elif aligned_time < next_time:
                    # El alineamiento redujo el tiempo, NO usar el desfase, mantener el tiempo original
                    pass  # next_time ya tiene el valor correcto
            elif instance.job_type == 'get':
                aligned_time = next_time.replace(second=10, microsecond=0)
                # Solo usar el desfase si NO reduce el intervalo
                if aligned_time > next_time:
                    next_time = aligned_time
                elif aligned_time < next_time:
                    # El alineamiento redujo el tiempo, NO usar el desfase, mantener el tiempo original
                    pass  # next_time ya tiene el valor correcto
            
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


@receiver(pre_save, sender=SnmpJobHost)
def detect_job_host_enabled(sender, instance, **kwargs):
    """
    Detecta cuando se habilita un SnmpJobHost y marca para inicialización
    """
    if instance.pk:
        try:
            old_instance = SnmpJobHost.objects.get(pk=instance.pk)
            # Detectar si se está habilitando (estaba disabled, ahora enabled)
            if not old_instance.enabled and instance.enabled:
                instance._just_enabled = True
            else:
                instance._just_enabled = False
        except SnmpJobHost.DoesNotExist:
            instance._just_enabled = False
    else:
        # Es nuevo (se está creando)
        instance._just_enabled = False


@receiver(post_save, sender=SnmpJobHost)
def initialize_new_job_host(sender, instance, created, **kwargs):
    """
    Cuando se crea o habilita un SnmpJobHost, inicializa next_run_at
    
    GARANTIZA que siempre tenga next_run_at configurado al crearse o habilitarse
    
    Reglas:
    - Si es NUEVO: Primera ejecución en 1 minuto
    - Si se REACTIVA (habilitado después de estar deshabilitado): now + intervalo completo
    - NUNCA permite que next_run_at quede en None o en el pasado cuando se reactiva
    """
    from django.utils import timezone
    from datetime import timedelta
    
    # Si se acaba de habilitar (reactivación)
    if hasattr(instance, '_just_enabled') and instance._just_enabled:
        logger.info(f"🔄 SnmpJobHost REACTIVADO: {instance.olt.abreviatura} - {instance.snmp_job.nombre}, inicializando con intervalo COMPLETO...")
        
        now = timezone.now()
        interval_seconds = instance.snmp_job.interval_seconds or 300  # Default 5 min
        
        # TAREA REACTIVADA: next_run = now + intervalo COMPLETO
        next_time = now + timedelta(seconds=interval_seconds)
        
        # DESFASE INTENCIONAL según tipo de tarea
        # IMPORTANTE: El desfase solo alinea al segundo, NO reduce el intervalo
        if instance.snmp_job.job_type == 'descubrimiento':
            aligned_time = next_time.replace(second=0, microsecond=0)
            if aligned_time <= now:
                aligned_time = (next_time + timedelta(minutes=1)).replace(second=0, microsecond=0)
            next_time = max(next_time, aligned_time)
        elif instance.snmp_job.job_type == 'get':
            aligned_time = next_time.replace(second=10, microsecond=0)
            if aligned_time <= now:
                aligned_time = (next_time + timedelta(minutes=1)).replace(second=10, microsecond=0)
            next_time = max(next_time, aligned_time)
        
        instance.next_run_at = next_time
        instance.last_run_at = None  # Resetear
        instance.save(update_fields=['next_run_at', 'last_run_at'])
        
        logger.info(f"   ✅ Reactivado: próxima ejecución en {interval_seconds}s ({next_time.strftime('%H:%M:%S')})")
    
    # Si es nuevo (recién creado)
    elif created:
        # SIEMPRE inicializar next_run_at cuando se crea, sin importar enabled
        if not instance.next_run_at:
            # Para tarea nueva desde plantilla: usar el intervalo del NODO, no del SnmpJob
            # Esto permite que cada nodo de la plantilla tenga su propio intervalo
            from datetime import timedelta
            now = timezone.now()
            
            # Obtener intervalo del WorkflowNode asociado (si existe)
            # Buscar el WorkflowNode que creó este SnmpJobHost
            from snmp_jobs.models import WorkflowNode
            workflow_node = WorkflowNode.objects.filter(
                workflow__olt=instance.olt,
                template_node__oid=instance.snmp_job.oid
            ).first()
            
            # Usar intervalo del nodo si existe, sino del job
            if workflow_node and workflow_node.interval_seconds:
                interval_seconds = workflow_node.interval_seconds
                logger.info(f"🆕 SnmpJobHost creado desde plantilla (ACTIVO): {instance.olt.abreviatura} - {instance.snmp_job.nombre} (próxima en {interval_seconds}s - intervalo del nodo '{workflow_node.name}')")
            else:
                interval_seconds = instance.snmp_job.interval_seconds or 300
                logger.info(f"🆕 SnmpJobHost creado desde plantilla (ACTIVO): {instance.olt.abreviatura} - {instance.snmp_job.nombre} (próxima en {interval_seconds}s - intervalo del job)")
            
            # Tarea nueva desde plantilla: usar intervalo completo configurado
            # Ejemplo: nodo con intervalo 5 min → primera ejecución en 5 min
            next_time = now + timedelta(seconds=interval_seconds)
            
            # Aplicar desfase según tipo de tarea
            # IMPORTANTE: El desfase solo alinea, NO reduce el intervalo
            if instance.snmp_job.job_type == 'descubrimiento':
                aligned_time = next_time.replace(second=0, microsecond=0)
                # Solo usar el desfase si NO reduce el intervalo
                if aligned_time > next_time:
                    next_time = aligned_time
            elif instance.snmp_job.job_type == 'get':
                aligned_time = next_time.replace(second=10, microsecond=0)
                # Solo usar el desfase si NO reduce el intervalo
                if aligned_time > next_time:
                    next_time = aligned_time
            
            instance.next_run_at = next_time
            instance.save(update_fields=['next_run_at'])
            
            if not (instance.enabled and instance.snmp_job.enabled):
                logger.info(f"🆕 SnmpJobHost creado (INACTIVO): {instance.olt.abreviatura} - {instance.snmp_job.nombre} (next_run_at inicializado)")


@receiver(post_save, sender=WorkflowNode)
def auto_create_snmp_job_for_workflow_node(sender, instance, created, **kwargs):
    """
    ⚠️ DESACTIVADO - Sistema Legacy
    
    Este signal creaba automáticamente SnmpJobHost cuando se creaba un WorkflowNode.
    Ahora el sistema es independiente y crea SnmpJob/SnmpJobHost bajo demanda
    en _execute_task_now() solo para compatibilidad con tareas Celery.
    
    El WorkflowNode ahora gestiona su propio next_run_at y last_run_at directamente.
    """
    # DESACTIVADO - El sistema ahora es independiente
    # SnmpJob se crea bajo demanda en _execute_task_now() solo para compatibilidad
    return
    
    oid = instance.template_node.oid
    workflow = instance.workflow
    olt = workflow.olt
    
    # Determinar tipo de job según el espacio del OID
    # Si el OID es de descubrimiento → job_type = 'descubrimiento'
    # Si el OID es de otro espacio → job_type = 'get'
    if oid.espacio == 'descubrimiento':
        job_type = 'descubrimiento'
    else:
        job_type = 'get'
    
    # Buscar si ya existe un SnmpJob para este OID y tipo
    existing_job = SnmpJob.objects.filter(
        oid=oid,
        job_type=job_type
    ).first()
    
    if existing_job:
        job = existing_job
        # IMPORTANTE: Actualizar intervalo del SnmpJob si el nodo tiene uno diferente
        # Esto asegura que cada nodo use su propio intervalo configurado
        node_interval = instance.interval_seconds or 300
        if job.interval_seconds != node_interval:
            job.interval_seconds = node_interval
            job.interval_raw = f"{node_interval}s"
            job.save(update_fields=['interval_seconds', 'interval_raw'])
            logger.info(f"🔄 SnmpJob actualizado con intervalo del nodo: {job.nombre} → {node_interval}s")
        logger.debug(f"✅ SnmpJob existente encontrado: {job.nombre} (ID: {job.id}) para OID {oid.nombre}")
    else:
        # Crear nuevo SnmpJob
        from brands.models import Brand
        
        # Obtener marca del OID o usar genérica
        marca = oid.marca if oid.marca else Brand.objects.filter(nombre='🌐 Genérico').first()
        if not marca:
            marca = Brand.objects.first()  # Fallback a primera marca
        
        # Nombre del job basado en el nodo
        job_nombre = f"{instance.name} - {oid.nombre}"
        
        # Intervalo del nodo
        interval_seconds = instance.interval_seconds or 300
        
        job = SnmpJob.objects.create(
            nombre=job_nombre,
            descripcion=f"Auto-creado desde WorkflowNode: {instance.name}",
            marca=marca,
            oid=oid,
            job_type=job_type,
            interval_seconds=interval_seconds,
            interval_raw=f"{interval_seconds}s",
            enabled=instance.enabled,  # Mismo estado que el nodo
            max_retries=2,
            retry_delay_seconds=30
        )
        logger.info(f"🆕 SnmpJob creado automáticamente: {job.nombre} (ID: {job.id}) para OID {oid.nombre}")
    
    # Crear o actualizar SnmpJobHost para esta OLT
    job_host, created_host = SnmpJobHost.objects.get_or_create(
        snmp_job=job,
        olt=olt,
        defaults={
            'enabled': instance.enabled,  # Mismo estado que el nodo
        }
    )
    
    # IMPORTANTE: Usar el intervalo del nodo (WorkflowNode), no del SnmpJob
    # Esto permite que cada nodo de la plantilla tenga su propio intervalo
    node_interval_seconds = instance.interval_seconds or 300
    
    if created_host:
        logger.info(f"🆕 SnmpJobHost creado: {job.nombre} → {olt.abreviatura} (intervalo del nodo: {node_interval_seconds}s)")
    else:
        # Actualizar estado si ya existía
        if job_host.enabled != instance.enabled:
            job_host.enabled = instance.enabled
            # Si se está habilitando, reinicializar next_run_at con intervalo del NODO
            if instance.enabled and not job_host.next_run_at:
                from datetime import timedelta
                now = timezone.now()
                # Usar intervalo del nodo, no del job
                job_host.next_run_at = now + timedelta(seconds=node_interval_seconds)
                # Aplicar desfase
                if job.job_type == 'descubrimiento':
                    aligned_time = job_host.next_run_at.replace(second=0, microsecond=0)
                    if aligned_time > job_host.next_run_at:
                        job_host.next_run_at = aligned_time
                elif job.job_type == 'get':
                    aligned_time = job_host.next_run_at.replace(second=10, microsecond=0)
                    if aligned_time > job_host.next_run_at:
                        job_host.next_run_at = aligned_time
                job_host.save(update_fields=['enabled', 'next_run_at'])
                logger.info(f"🔄 SnmpJobHost habilitado y reinicializado: {job.nombre} → {olt.abreviatura} (próxima en {node_interval_seconds}s - intervalo del nodo)")
            else:
                job_host.save(update_fields=['enabled'])
                logger.info(f"🔄 SnmpJobHost actualizado: {job.nombre} → {olt.abreviatura} (enabled={instance.enabled})")


@receiver(post_save, sender=WorkflowTemplateNode)
def sync_workflows_on_template_node_change(sender, instance, created, **kwargs):
    """
    Cuando se crea o modifica un WorkflowTemplateNode, sincroniza automáticamente
    todos los workflows vinculados que tengan auto_sync=True
    """
    # Solo sincronizar si no es creación nueva (para evitar loops en creación inicial)
    if created:
        return
    
    try:
        from .services.workflow_template_service import WorkflowTemplateService
        
        # Sincronizar cambios de la plantilla a los workflows vinculados
        logger.info(f"🔄 Cambio detectado en template_node '{instance.key}', sincronizando workflows...")
        stats = WorkflowTemplateService.sync_template_changes(instance.template_id)
        
        logger.info(
            f"✅ Sincronización completada: {stats['workflows_synced']} workflows, "
            f"{stats['nodes_synced']} nodos actualizados"
        )
    except Exception as e:
        logger.error(f"❌ Error sincronizando workflows tras cambio en template_node '{instance.key}': {e}")


@receiver(pre_save, sender=WorkflowTemplate)
def detect_workflow_template_activation(sender, instance, **kwargs):
    """
    Detecta cuando se activa o desactiva una WorkflowTemplate
    """
    if instance.pk:
        try:
            old_instance = WorkflowTemplate.objects.get(pk=instance.pk)
            # Detectar si se está desactivando (estaba activa, ahora inactiva)
            if old_instance.is_active and not instance.is_active:
                instance._just_deactivated = True
                instance._was_active = True
            # Detectar si se está activando (estaba inactiva, ahora activa)
            elif not old_instance.is_active and instance.is_active:
                instance._just_activated = True
                instance._was_inactive = True
            else:
                instance._just_deactivated = False
                instance._just_activated = False
        except WorkflowTemplate.DoesNotExist:
            instance._just_deactivated = False
            instance._just_activated = False
    else:
        # Es nuevo (se está creando)
        instance._just_deactivated = False
        instance._just_activated = False


@receiver(post_save, sender=WorkflowTemplate)
def handle_workflow_template_activation(sender, instance, created, **kwargs):
    """
    Maneja la activación/desactivación de WorkflowTemplate:
    
    - Al DESACTIVAR: Aborta todas las ejecuciones PENDING y RUNNING de los nodos vinculados
    - Al ACTIVAR: Recalcula next_run_at desde la hora de activación + intervalo
                  (solo para nodos con intervalo >= 300s, los menores no se mueven)
    """
    from executions.models import Execution
    
    # Si se desactivó la plantilla
    if hasattr(instance, '_just_deactivated') and instance._just_deactivated:
        logger.info(f"🛑 Plantilla '{instance.name}' DESACTIVADA, abortando ejecuciones de nodos vinculados...")
        
        def abort_executions():
            try:
                # Buscar todos los WorkflowNodes que pertenecen a esta plantilla
                # (a través de WorkflowTemplateNode que referencia esta plantilla)
                from .models import WorkflowTemplateNode, WorkflowTemplateLink
                
                # Obtener todos los workflows vinculados a esta plantilla
                template_links = WorkflowTemplateLink.objects.filter(template=instance)
                workflows = [link.workflow for link in template_links]
                
                # Obtener todos los WorkflowNodes que usan nodos de esta plantilla
                template_nodes = WorkflowTemplateNode.objects.filter(template=instance)
                workflow_nodes = WorkflowNode.objects.filter(
                    template_node__in=template_nodes,
                    workflow__in=workflows
                ).select_related('workflow', 'workflow__olt')
                
                total_aborted = 0
                nodes_affected = 0
                
                for workflow_node in workflow_nodes:
                    # Abortar ejecuciones PENDING y RUNNING de este nodo
                    pending_executions = Execution.objects.filter(
                        workflow_node=workflow_node,
                        status__in=['PENDING', 'RUNNING']
                    )
                    
                    aborted_count = pending_executions.update(
                        status='INTERRUPTED',
                        finished_at=timezone.now(),
                        error_message=f"Plantilla '{instance.name}' desactivada"
                    )
                    
                    # Limpiar next_run_at para que no se ejecute más
                    workflow_node.next_run_at = None
                    workflow_node.save(update_fields=['next_run_at'])
                    
                    total_aborted += aborted_count
                    if aborted_count > 0 or workflow_node.next_run_at is None:
                        nodes_affected += 1
                        logger.info(
                            f"   🛑 Nodo '{workflow_node.name}' (OLT: {workflow_node.workflow.olt.abreviatura}): "
                            f"{aborted_count} ejecución(es) abortada(s), next_run_at limpiado"
                        )
                
                logger.info(
                    f"✅ Total: {total_aborted} ejecución(es) abortada(s), {nodes_affected} nodo(s) afectado(s) "
                    f"por desactivación de plantilla '{instance.name}'"
                )
                
            except Exception as e:
                logger.error(f"❌ Error abortando ejecuciones al desactivar plantilla '{instance.name}': {e}", exc_info=True)
        
        transaction.on_commit(abort_executions)
    
    # Si se activó la plantilla
    elif hasattr(instance, '_just_activated') and instance._just_activated:
        logger.info(f"✅ Plantilla '{instance.name}' ACTIVADA, recalculando tiempos de ejecución...")
        
        def recalculate_executions():
            try:
                from .models import WorkflowTemplateNode, WorkflowTemplateLink
                import pytz
                
                # Obtener todos los workflows vinculados a esta plantilla
                template_links = WorkflowTemplateLink.objects.filter(template=instance)
                workflows = [link.workflow for link in template_links]
                
                # Obtener todos los WorkflowNodes que usan nodos de esta plantilla
                template_nodes = WorkflowTemplateNode.objects.filter(template=instance)
                workflow_nodes = WorkflowNode.objects.filter(
                    template_node__in=template_nodes,
                    workflow__in=workflows,
                    enabled=True  # Solo nodos habilitados
                ).select_related('workflow', 'workflow__olt', 'template_node')
                
                now = timezone.now()
                peru_tz = pytz.timezone('America/Lima')
                now_peru = timezone.localtime(now, peru_tz)
                recalculated_count = 0
                skipped_count = 0
                
                for workflow_node in workflow_nodes:
                    interval_seconds = workflow_node.interval_seconds or 0
                    
                    # ✅ REGLA: Solo recalcular nodos con intervalo >= 300s (5 minutos)
                    # Los nodos con intervalo < 300s mantienen su horario actual
                    if interval_seconds < 300:
                        skipped_count += 1
                        logger.debug(
                            f"   ⏭️  Nodo '{workflow_node.name}' (OLT: {workflow_node.workflow.olt.abreviatura}) "
                            f"NO recalculado: intervalo {interval_seconds}s < 300s (mantiene horario actual)"
                        )
                        continue
                    
                    # Calcular próxima ejecución desde la hora de activación + intervalo
                    # Nada se ejecuta de inmediato, siempre después de su intervalo
                    next_run = now + timedelta(seconds=interval_seconds)
                    next_run_peru = timezone.localtime(next_run, peru_tz)
                    
                    # Actualizar next_run_at y resetear last_run_at
                    old_next_run = workflow_node.next_run_at
                    workflow_node.next_run_at = next_run
                    workflow_node.last_run_at = None  # Resetear para recalcular desde ahora
                    workflow_node.save(update_fields=['next_run_at', 'last_run_at'])
                    recalculated_count += 1
                    
                    # Log detallado del motivo del recálculo
                    old_time_str = "N/A"
                    if old_next_run:
                        old_time_peru = timezone.localtime(old_next_run, peru_tz)
                        old_time_str = old_time_peru.strftime('%H:%M:%S')
                    
                    logger.info(
                        f"   ✅ Nodo '{workflow_node.name}' (OLT: {workflow_node.workflow.olt.abreviatura}) "
                        f"recalculado: {old_time_str} → {next_run_peru.strftime('%H:%M:%S')} PERÚ "
                        f"(intervalo: {interval_seconds//60}min, desde hora de activación: {now_peru.strftime('%H:%M:%S')})",
                        extra={
                            'node_id': workflow_node.id,
                            'node_name': workflow_node.name,
                            'olt_abreviatura': workflow_node.workflow.olt.abreviatura,
                            'interval_seconds': interval_seconds,
                            'old_next_run': old_next_run.isoformat() if old_next_run else None,
                            'new_next_run': next_run.isoformat(),
                            'activation_time': now.isoformat(),
                            'reason': 'template_reactivated_recalculate_from_activation_time'
                        }
                    )
                
                logger.info(
                    f"✅ Total: {recalculated_count} nodo(s) recalculado(s), {skipped_count} nodo(s) omitido(s) "
                    f"(intervalo < 300s) por activación de plantilla '{instance.name}'"
                )
                
            except Exception as e:
                logger.error(f"❌ Error recalculando ejecuciones al activar plantilla '{instance.name}': {e}", exc_info=True)
        
        transaction.on_commit(recalculate_executions)
    
    # Sincronizar cambios de la plantilla a los workflows vinculados (lógica original)
    if not created:
        try:
            from .services.workflow_template_service import WorkflowTemplateService
            
            # Solo sincronizar si no es activación/desactivación (para evitar doble procesamiento)
            if not (hasattr(instance, '_just_deactivated') and instance._just_deactivated) and \
               not (hasattr(instance, '_just_activated') and instance._just_activated):
                # Sincronizar cambios de la plantilla a los workflows vinculados
                logger.info(f"🔄 Cambio detectado en plantilla '{instance.name}', sincronizando workflows...")
                stats = WorkflowTemplateService.sync_template_changes(instance.id)
                
                logger.info(
                    f"✅ Sincronización completada: {stats['workflows_synced']} workflows, "
                    f"{stats['nodes_synced']} nodos actualizados"
                )
        except Exception as e:
            logger.error(f"❌ Error sincronizando workflows tras cambio en plantilla '{instance.name}': {e}")


@receiver(post_delete, sender=WorkflowTemplateNode)
def sync_workflows_on_template_node_delete(sender, instance, **kwargs):
    """
    Cuando se elimina un WorkflowTemplateNode, elimina automáticamente
    los nodos correspondientes en los workflows vinculados (sin importar auto_sync)
    """
    try:
        from .models import WorkflowTemplateLink, WorkflowNode
        
        # Guardar información antes de que se pierda (el objeto ya no existe en la BD)
        deleted_key = instance.key
        template_id = instance.template_id
        deleted_template_node_id = instance.id  # Guardar el ID antes de que se pierda
        
        logger.info(f"🗑️ Eliminación detectada en template_node '{deleted_key}' (ID: {deleted_template_node_id}, template_id: {template_id})")
        
        # Buscar todos los workflows vinculados a esta plantilla (sin importar auto_sync)
        links = WorkflowTemplateLink.objects.filter(
            template_id=template_id
        ).select_related('workflow')
        
        nodes_deleted = 0
        workflows_processed = 0
        
        for link in links:
            workflow = link.workflow
            workflows_processed += 1
            
            # Recolectar IDs de nodos a eliminar para evitar el error de .distinct().delete()
            node_ids_to_delete = set()
            
            # Método 1: Buscar nodos por key (la forma más confiable)
            orphaned_by_key = WorkflowNode.objects.filter(
                workflow=workflow,
                key=deleted_key
            ).values_list('id', flat=True)
            node_ids_to_delete.update(orphaned_by_key)
            
            # Método 2: Buscar por template_node_id (por si acaso todavía está referenciado)
            orphaned_by_template = WorkflowNode.objects.filter(
                workflow=workflow,
                template_node_id=deleted_template_node_id
            ).values_list('id', flat=True)
            node_ids_to_delete.update(orphaned_by_template)
            
            # Método 3: Buscar por metadata.origin_template_id + key
            # (para nodos que ya fueron desvinculados pero conservan el origin)
            orphaned_by_metadata = WorkflowNode.objects.filter(
                workflow=workflow,
                key=deleted_key,
                metadata__origin_template_id=template_id
            ).values_list('id', flat=True)
            node_ids_to_delete.update(orphaned_by_metadata)
            
            # Eliminar los nodos huérfanos usando los IDs recolectados
            if node_ids_to_delete:
                orphaned_count = len(node_ids_to_delete)
                logger.info(
                    f"🗑️ Eliminando {orphaned_count} nodo(s) huérfano(s) con key '{deleted_key}' "
                    f"de workflow {workflow.olt.abreviatura} (template_node eliminado)"
                )
                WorkflowNode.objects.filter(id__in=node_ids_to_delete).delete()
                nodes_deleted += orphaned_count
        
        logger.info(
            f"✅ Eliminación completada: {workflows_processed} workflows procesados, "
            f"{nodes_deleted} nodos eliminados"
        )
        
        # No se ejecuta sincronización adicional; la eliminación se aplicó inmediatamente.
    except Exception as e:
        logger.error(f"❌ Error sincronizando workflows tras eliminación de template_node '{instance.key if hasattr(instance, 'key') else 'N/A'}': {e}", exc_info=True)


@receiver(pre_save, sender=TaskTemplate)
def detect_task_template_status_change(sender, instance, **kwargs):
    """
    Detecta cuando se desactiva o activa una TaskTemplate
    """
    if instance.pk:
        try:
            old_instance = TaskTemplate.objects.get(pk=instance.pk)
            # Detectar si se está desactivando (estaba activa, ahora inactiva)
            if old_instance.is_active and not instance.is_active:
                instance._just_deactivated = True
            # Detectar si se está activando (estaba inactiva, ahora activa)
            elif not old_instance.is_active and instance.is_active:
                instance._just_activated = True
            else:
                instance._just_deactivated = False
                instance._just_activated = False
        except TaskTemplate.DoesNotExist:
            instance._just_deactivated = False
            instance._just_activated = False
    else:
        instance._just_deactivated = False
        instance._just_activated = False


@receiver(post_save, sender=TaskTemplate)
def handle_task_template_status_change(sender, instance, created, **kwargs):
    """
    Maneja la desactivación/activación de TaskTemplate:
    - Al desactivar: Cancela todas las ejecuciones PENDING y RUNNING de nodos que usan esta plantilla
    - Al activar: Reinicia next_run_at de los nodos con el intervalo configurado
    """
    from executions.models import Execution
    
    # Si se desactivó la plantilla
    if hasattr(instance, '_just_deactivated') and instance._just_deactivated:
        logger.info(f"🛑 Plantilla '{instance.name}' DESACTIVADA, cancelando ejecuciones...")
        
        def cancel_executions():
            try:
                # Buscar todos los WorkflowNodes que usan esta plantilla
                # (a través de WorkflowTemplateNode que referencia esta TaskTemplate)
                from .models import WorkflowTemplateNode
                template_nodes = WorkflowTemplateNode.objects.filter(template=instance)
                
                # Obtener todos los WorkflowNodes que usan estos template_nodes
                workflow_nodes = WorkflowNode.objects.filter(
                    template_node__in=template_nodes
                ).select_related('workflow', 'workflow__olt')
                
                total_canceled = 0
                
                for workflow_node in workflow_nodes:
                    # Cancelar ejecuciones PENDING y RUNNING de este nodo
                    pending_executions = Execution.objects.filter(
                        workflow_node=workflow_node,
                        status__in=['PENDING', 'RUNNING']
                    )
                    
                    canceled_count = pending_executions.update(
                        status='INTERRUPTED',
                        finished_at=timezone.now(),
                        error_message=f"Plantilla '{instance.name}' desactivada"
                    )
                    
                    total_canceled += canceled_count
                    
                    if canceled_count > 0:
                        logger.info(
                            f"   🛑 {canceled_count} ejecución(es) cancelada(s) para nodo "
                            f"'{workflow_node.name}' (OLT: {workflow_node.workflow.olt.abreviatura})"
                        )
                
                logger.info(f"✅ Total: {total_canceled} ejecución(es) cancelada(s) por desactivación de plantilla '{instance.name}'")
                
            except Exception as e:
                logger.error(f"❌ Error cancelando ejecuciones al desactivar plantilla '{instance.name}': {e}", exc_info=True)
        
        transaction.on_commit(cancel_executions)
    
    # Si se activó la plantilla
    elif hasattr(instance, '_just_activated') and instance._just_activated:
        logger.info(f"✅ Plantilla '{instance.name}' ACTIVADA, reiniciando ejecuciones...")
        
        def restart_executions():
            try:
                from .models import WorkflowTemplateNode
                template_nodes = WorkflowTemplateNode.objects.filter(template=instance)
                
                # Obtener todos los WorkflowNodes que usan estos template_nodes
                workflow_nodes = WorkflowNode.objects.filter(
                    template_node__in=template_nodes,
                    enabled=True  # Solo nodos habilitados
                ).select_related('workflow', 'workflow__olt')
                
                now = timezone.now()
                restarted_count = 0
                
                for workflow_node in workflow_nodes:
                    # Reiniciar next_run_at con el intervalo del nodo
                    if workflow_node.interval_seconds and workflow_node.interval_seconds > 0:
                        # Calcular próxima ejecución: ahora + intervalo
                        next_run = now + timedelta(seconds=workflow_node.interval_seconds)
                        
                        # Aplicar desfase según tipo de operación
                        if workflow_node.template_node and workflow_node.template_node.oid:
                            if workflow_node.template_node.oid.espacio == 'descubrimiento':
                                aligned_time = next_run.replace(second=0, microsecond=0)
                                if aligned_time > next_run:
                                    next_run = aligned_time
                            else:
                                aligned_time = next_run.replace(second=10, microsecond=0)
                                if aligned_time > next_run:
                                    next_run = aligned_time
                        
                        workflow_node.next_run_at = next_run
                        workflow_node.last_run_at = None  # Resetear
                        workflow_node.save(update_fields=['next_run_at', 'last_run_at'])
                        restarted_count += 1
                        
                        logger.info(
                            f"   ✅ Nodo '{workflow_node.name}' reiniciado: próxima ejecución en "
                            f"{workflow_node.interval_seconds}s ({next_run.strftime('%H:%M:%S')})"
                        )
                
                logger.info(f"✅ Total: {restarted_count} nodo(s) reiniciado(s) por activación de plantilla '{instance.name}'")
                
            except Exception as e:
                logger.error(f"❌ Error reiniciando ejecuciones al activar plantilla '{instance.name}': {e}", exc_info=True)
        
        transaction.on_commit(restart_executions)

