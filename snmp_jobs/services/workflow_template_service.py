# snmp_jobs/services/workflow_template_service.py
"""
Servicios para gestionar plantillas de workflow tipo Zabbix.
Maneja la aplicación de plantillas a OLTs y la vinculación automática por key.
"""
from django.db import transaction
from django.utils import timezone
from snmp_jobs.models import (
    WorkflowTemplate,
    WorkflowTemplateNode,
    WorkflowTemplateLink,
    OLTWorkflow,
    WorkflowNode,
    TaskTemplate,
    TaskFunction,
)
from hosts.models import OLT
from brands.models import Brand
from olt_models.models import OLTModel
import logging

logger = logging.getLogger(__name__)


def _get_task_template_for_oid(oid):
    """
    Obtiene o crea un TaskTemplate apropiado para un OID dado.
    
    Lógica:
    - Si espacio == 'descubrimiento' → Buscar TaskTemplate con función tipo 'descubrimiento'
    - Si espacio != 'descubrimiento' → Buscar TaskTemplate con función tipo 'get'
    
    Args:
        oid: Instancia de OID
        
    Returns:
        TaskTemplate apropiado
    """
    if not oid:
        # Fallback: buscar cualquier TaskTemplate activo
        return TaskTemplate.objects.filter(is_active=True).first()
    
    # Determinar tipo de función según espacio
    if oid.espacio == 'descubrimiento':
        function_type = 'descubrimiento'
    else:
        function_type = 'get'
    
    # Buscar TaskFunction del tipo apropiado
    task_function = TaskFunction.objects.filter(
        function_type=function_type,
        is_active=True
    ).first()
    
    if not task_function:
        # Si no hay función, buscar cualquier TaskTemplate activo
        return TaskTemplate.objects.filter(is_active=True).first()
    
    # Buscar TaskTemplate con esa función
    task_template = TaskTemplate.objects.filter(
        function=task_function,
        is_active=True
    ).first()
    
    if not task_template:
        # Si no hay template, buscar cualquier TaskTemplate activo
        return TaskTemplate.objects.filter(is_active=True).first()
    
    return task_template


def _is_oid_compatible_with_olt(oid, olt):
    """
    Verifica si un OID es compatible con una OLT según marca y modelo.
    
    Lógica de compatibilidad (cascada):
    1. Marca específica + Modelo específico → Compatible si coincide exactamente
    2. Marca específica + Modelo genérico → Compatible si la marca coincide
    3. Marca genérica + Modelo genérico → Siempre compatible
    
    Args:
        oid: Instancia de OID
        olt: Instancia de OLT
        
    Returns:
        bool: True si el OID es compatible con la OLT
    """
    if not oid:
        # Si no hay OID, no es compatible (necesitamos OID para ejecutar)
        return False
    
    # Obtener marca y modelo genéricos
    try:
        generic_brand = Brand.objects.get(nombre='🌐 Genérico')
        generic_model = OLTModel.objects.get(nombre='Genérico', marca=generic_brand)
    except (Brand.DoesNotExist, OLTModel.DoesNotExist):
        logger.warning("No se encontraron marca/modelo genéricos. Usando comparación directa.")
        generic_brand = None
        generic_model = None
    
    # Caso 1: OID con marca genérica + modelo genérico → Siempre compatible
    if oid.marca == generic_brand and oid.modelo == generic_model:
        return True
    
    # Caso 2: OID con marca específica + modelo genérico → Compatible si marca coincide
    if oid.marca == olt.marca and oid.modelo == generic_model:
        return True
    
    # Caso 3: OID con marca específica + modelo específico → Compatible si ambos coinciden
    if oid.marca == olt.marca:
        # Si la OLT no tiene modelo definido, solo comparar marca
        if not olt.modelo:
            return True
        # Si ambos tienen modelo, deben coincidir
        if oid.modelo == olt.modelo:
            return True
    
    # Si no cumple ninguna condición, no es compatible
    return False


class WorkflowTemplateService:
    """
    Servicio para gestionar plantillas de workflow y su aplicación a OLTs.
    Implementa la lógica tipo Zabbix de vinculación por key.
    """
    
    @staticmethod
    def apply_template_to_olts(template_id, olt_ids, auto_sync=True, create_custom_nodes=True):
        """
        Aplica una plantilla a múltiples OLTs.
        
        Lógica de vinculación por key:
        - Si un workflow ya tiene un nodo con la misma key que un nodo de la plantilla:
          → Se vincula automáticamente (no se duplica)
        - Si un workflow tiene un nodo con key diferente:
          → Se mantiene como nodo separado (aunque sea redundante)
        - Si un workflow no tiene un nodo con esa key:
          → Se crea un nuevo nodo desde la plantilla
        
        Args:
            template_id: ID de la WorkflowTemplate
            olt_ids: Lista de IDs de OLTs
            auto_sync: Si True, los cambios en la plantilla se propagan automáticamente
            create_custom_nodes: Si True, permite crear nodos custom además de los de plantilla
        
        Returns:
            dict con estadísticas de la operación
        """
        template = WorkflowTemplate.objects.get(id=template_id)
        template_nodes = template.template_nodes.filter(enabled=True)
        
        stats = {
            'olts_processed': 0,
            'nodes_linked': 0,
            'nodes_created': 0,
            'nodes_skipped': 0,
            'nodes_incompatible': 0,
            'errors': [],
        }
        
        with transaction.atomic():
            for olt_id in olt_ids:
                try:
                    olt = OLT.objects.select_related('marca', 'modelo').get(id=olt_id)
                    
                    # Crear o obtener workflow de la OLT
                    workflow, created = OLTWorkflow.objects.get_or_create(
                        olt=olt,
                        defaults={
                            'name': f'Workflow SNMP - {olt.abreviatura}',
                            'is_active': True,
                        }
                    )
                    
                    # Crear o actualizar vinculación con la plantilla
                    link, link_created = WorkflowTemplateLink.objects.get_or_create(
                        template=template,
                        workflow=workflow,
                        defaults={'auto_sync': auto_sync}
                    )
                    if not link_created:
                        link.auto_sync = auto_sync
                        link.save()
                    
                    # Filtrar nodos compatibles con la OLT antes de procesarlos
                    compatible_nodes = []
                    incompatible_nodes = []
                    
                    for template_node in template_nodes:
                        # Verificar compatibilidad del OID con la OLT
                        if template_node.oid and _is_oid_compatible_with_olt(template_node.oid, olt):
                            compatible_nodes.append(template_node)
                        elif not template_node.oid:
                            # Si no tiene OID, no es compatible (necesitamos OID para ejecutar)
                            incompatible_nodes.append(template_node)
                            logger.warning(
                                f"⚠️ Nodo '{template_node.key}' sin OID - no compatible con OLT {olt.abreviatura}"
                            )
                        else:
                            incompatible_nodes.append(template_node)
                            logger.warning(
                                f"⚠️ Nodo '{template_node.key}' con OID incompatible "
                                f"(OID: {template_node.oid.marca.nombre}/{template_node.oid.modelo.nombre}, "
                                f"OLT: {olt.marca.nombre}/{olt.modelo.nombre if olt.modelo else 'N/A'})"
                            )
                    
                    # Procesar solo nodos compatibles
                    for template_node in compatible_nodes:
                        result = WorkflowTemplateService._process_template_node(
                            workflow, template_node, create_custom_nodes
                        )
                        stats[result['action']] += 1
                    
                    # Contar nodos incompatibles
                    stats['nodes_incompatible'] += len(incompatible_nodes)
                    
                    stats['olts_processed'] += 1
                    logger.info(
                        f"✅ Plantilla '{template.name}' aplicada a OLT {olt.abreviatura}. "
                        f"Vinculados: {stats['nodes_linked']}, Creados: {stats['nodes_created']}, "
                        f"Incompatibles: {len(incompatible_nodes)}"
                    )
                    
                except OLT.DoesNotExist:
                    stats['errors'].append(f"OLT ID {olt_id} no existe")
                except Exception as e:
                    stats['errors'].append(f"Error en OLT ID {olt_id}: {str(e)}")
                    logger.error(f"Error aplicando plantilla a OLT {olt_id}: {e}", exc_info=True)
        
        return stats
    
    @staticmethod
    def _process_template_node(workflow, template_node, create_custom_nodes=True):
        """
        Procesa un nodo de plantilla para un workflow específico.
        
        Lógica:
        1. Buscar si existe un nodo con la misma key en el workflow
        2. Si existe:
           - Si NO está vinculado a ninguna plantilla → Vincularlo a esta plantilla
           - Si YA está vinculado a otra plantilla → Mantenerlo separado (skip) - permite múltiples plantillas
           - Si YA está vinculado a esta plantilla → Sincronizar
        3. Si NO existe:
           - Crear nuevo nodo desde la plantilla (permite múltiples plantillas con diferentes keys)
        
        Returns:
            dict con 'action': 'linked' | 'created' | 'skipped' | 'synced'
        """
        existing_node = WorkflowNode.objects.filter(
            workflow=workflow,
            key=template_node.key
        ).first()
        
        if existing_node:
            # Nodo con la misma key ya existe
            if existing_node.template_node is None:
                # No está vinculado → Vincularlo automáticamente
                existing_node.link_to_template_node(template_node)
                logger.info(
                    f"🔗 Nodo '{template_node.key}' vinculado a plantilla '{template_node.template.name}' "
                    f"en workflow {workflow.olt.abreviatura}"
                )
                return {'action': 'nodes_linked'}
            elif existing_node.template_node.template == template_node.template:
                # Ya está vinculado a esta plantilla → Sincronizar
                if existing_node.workflow.template_links.filter(
                    template=template_node.template,
                    auto_sync=True
                ).exists():
                    existing_node.sync_from_template(template_node)
                    return {'action': 'nodes_synced'}
                else:
                    return {'action': 'nodes_skipped'}
            else:
                # Está vinculado a otra plantilla → Mantener separado (permite múltiples plantillas)
                logger.info(
                    f"⏭️ Nodo '{template_node.key}' ya existe vinculado a otra plantilla "
                    f"('{existing_node.template_node.template.name}'). "
                    f"Se mantiene separado para permitir múltiples plantillas."
                )
                return {'action': 'nodes_skipped'}
        else:
            # No existe nodo con esa key → Crear nuevo desde plantilla
            # Esto permite que múltiples plantillas coexistan con diferentes keys
            logger.info(
                f"🆕 Creando nodo '{template_node.key}' desde plantilla '{template_node.template.name}' "
                f"en workflow {workflow.olt.abreviatura}"
            )
            
            # Validar que el OID sea compatible con la OLT antes de crear
            if template_node.oid:
                if not _is_oid_compatible_with_olt(template_node.oid, workflow.olt):
                    logger.warning(
                        f"⚠️ Nodo '{template_node.key}' no compatible con OLT {workflow.olt.abreviatura}. "
                        f"OID: {template_node.oid.marca.nombre}/{template_node.oid.modelo.nombre}, "
                        f"OLT: {workflow.olt.marca.nombre}/{workflow.olt.modelo.nombre if workflow.olt.modelo else 'N/A'}"
                    )
                    return {'action': 'nodes_skipped'}
            else:
                logger.warning(
                    f"⚠️ Nodo '{template_node.key}' sin OID - no se puede crear en workflow {workflow.olt.abreviatura}"
                )
                return {'action': 'nodes_skipped'}
            
            # Obtener TaskTemplate apropiado desde el OID
            task_template = _get_task_template_for_oid(template_node.oid)
            
            if not task_template:
                logger.error(f"No se pudo encontrar TaskTemplate para OID {template_node.oid}")
                return {'action': 'nodes_skipped'}
            
            new_node = WorkflowNode.objects.create(
                workflow=workflow,
                template=task_template,
                template_node=template_node,
                key=template_node.key,
                name=template_node.name,
                interval_seconds=template_node.interval_seconds,
                priority=template_node.priority,
                enabled=template_node.enabled,
                parameters=template_node.parameters.copy(),
                retry_policy=template_node.retry_policy.copy(),
                position_x=template_node.position_x,
                position_y=template_node.position_y,
                color_override=template_node.color_override or '',
                icon_override=template_node.icon_override or '',
                metadata=template_node.metadata.copy(),
                # IMPORTANTE: Los campos override deben ser False por defecto para permitir sincronización
                override_interval=False,
                override_priority=False,
                override_enabled=False,
                override_parameters=False,
            )
            logger.info(
                f"✅ Nodo '{new_node.key}' creado desde plantilla '{template_node.template.name}' "
                f"en workflow {workflow.olt.abreviatura} con intervalo {new_node.interval_seconds}s"
            )
            return {'action': 'nodes_created'}
    
    @staticmethod
    def sync_template_changes(template_id):
        """
        Sincroniza cambios de una plantilla a todos los workflows vinculados.
        La sincronización es automática: cuando cambia la plantilla, todos los workflows
        vinculados se actualizan automáticamente desde la plantilla.
        
        Busca nodos por template_node Y por key para asegurar que todos los nodos
        vinculados se sincronicen correctamente.
        
        Args:
            template_id: ID de la WorkflowTemplate
        
        Returns:
            dict con estadísticas de sincronización
        """
        template = WorkflowTemplate.objects.get(id=template_id)
        links = template.workflow_links.filter(auto_sync=True)
        
        stats = {
            'workflows_synced': 0,
            'nodes_synced': 0,
            'nodes_skipped': 0,
            'nodes_not_found': 0,
        }
        
        for link in links:
            workflow = link.workflow
            template_nodes = template.template_nodes.all()
            
            for template_node in template_nodes:
                # Buscar nodos vinculados a este template_node por template_node
                workflow_nodes_by_template = WorkflowNode.objects.filter(
                    workflow=workflow,
                    template_node=template_node
                )
                
                # También buscar por key (por si acaso no están vinculados por template_node)
                workflow_nodes_by_key = WorkflowNode.objects.filter(
                    workflow=workflow,
                    key=template_node.key
                ).exclude(template_node=template_node)
                
                # Combinar ambos querysets
                all_workflow_nodes = list(workflow_nodes_by_template) + list(workflow_nodes_by_key)
                
                # Eliminar duplicados
                seen_ids = set()
                unique_nodes = []
                for node in all_workflow_nodes:
                    if node.id not in seen_ids:
                        seen_ids.add(node.id)
                        unique_nodes.append(node)
                
                if not unique_nodes:
                    stats['nodes_not_found'] += 1
                    logger.warning(
                        f"⚠️ No se encontraron nodos vinculados para template_node '{template_node.key}' "
                        f"en workflow {workflow.olt.abreviatura}"
                    )
                    continue
                
                for workflow_node in unique_nodes:
                    # Si el nodo no está vinculado por template_node, vincularlo primero
                    if workflow_node.template_node != template_node:
                        workflow_node.link_to_template_node(template_node)
                        logger.info(
                            f"🔗 Nodo '{workflow_node.key}' vinculado a template_node '{template_node.key}' "
                            f"en workflow {workflow.olt.abreviatura}"
                        )
                    
                    # Sincronizar solo si auto_sync está activo
                    if link.auto_sync:
                        # Verificar diferencias antes de sincronizar
                        differences = []
                        if workflow_node.interval_seconds != template_node.interval_seconds:
                            differences.append(f"intervalo: {workflow_node.interval_seconds}s ≠ {template_node.interval_seconds}s")
                        if workflow_node.priority != template_node.priority:
                            differences.append(f"prioridad: {workflow_node.priority} ≠ {template_node.priority}")
                        if workflow_node.enabled != template_node.enabled:
                            differences.append(f"enabled: {workflow_node.enabled} ≠ {template_node.enabled}")
                        
                        if differences:
                            logger.info(
                                f"🔄 Sincronizando nodo '{workflow_node.key}' en workflow {workflow.olt.abreviatura}. "
                                f"Diferencias detectadas: {', '.join(differences)}"
                            )
                        
                        # Sincronizar automáticamente desde la plantilla
                        workflow_node.sync_from_template(template_node)
                        stats['nodes_synced'] += 1
                    else:
                        stats['nodes_skipped'] += 1
            
            stats['workflows_synced'] += 1
        
        logger.info(
            f"✅ Plantilla '{template.name}' sincronizada: "
            f"{stats['workflows_synced']} workflows, {stats['nodes_synced']} nodos actualizados, "
            f"{stats['nodes_not_found']} nodos no encontrados"
        )
        
        return stats
    
    @staticmethod
    def unlink_template_from_workflow(template_id, workflow_id, delete_nodes=False):
        """
        Desvincula una plantilla de un workflow.
        
        Args:
            template_id: ID de la WorkflowTemplate
            workflow_id: ID del OLTWorkflow
            delete_nodes: Si True, elimina los nodos vinculados. Si False, los mantiene como custom.
        
        Returns:
            dict con estadísticas
        """
        template = WorkflowTemplate.objects.get(id=template_id)
        workflow = OLTWorkflow.objects.get(id=workflow_id)
        
        stats = {
            'nodes_unlinked': 0,
            'nodes_deleted': 0,
        }
        
        with transaction.atomic():
            # Obtener nodos vinculados a esta plantilla
            template_nodes = template.template_nodes.all()
            workflow_nodes = WorkflowNode.objects.filter(
                workflow=workflow,
                template_node__in=template_nodes
            )
            
            if delete_nodes:
                # Eliminar nodos vinculados
                count = workflow_nodes.count()
                workflow_nodes.delete()
                stats['nodes_deleted'] = count
            else:
                # Desvincular nodos (mantenerlos como custom)
                for node in workflow_nodes:
                    node.template_node = None
                    node.save()
                    stats['nodes_unlinked'] += 1
            
            # Eliminar vinculación
            WorkflowTemplateLink.objects.filter(
                template=template,
                workflow=workflow
            ).delete()
        
        logger.info(
            f"✅ Plantilla '{template.name}' desvinculada de workflow {workflow.olt.abreviatura}. "
            f"Desvinculados: {stats['nodes_unlinked']}, Eliminados: {stats['nodes_deleted']}"
        )
        
        return stats

