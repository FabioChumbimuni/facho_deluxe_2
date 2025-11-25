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
            'errors': [],
            'workflow_ids': [],
        }
        workflow_map = {}
        
        # Crear workflows fuera de la transacción para asegurar que se creen siempre
        for olt_id in olt_ids:
            try:
                olt = OLT.objects.select_related('marca', 'modelo').get(id=olt_id)
                
                # Crear o obtener workflow de la OLT (fuera de transacción para asegurar creación)
                workflow, workflow_created = OLTWorkflow.objects.get_or_create(
                    olt=olt,
                    defaults={
                        'name': f'Workflow SNMP - {olt.abreviatura}',
                        'is_active': True,
                    }
                )
                workflow_map[olt_id] = workflow
                stats['workflow_ids'].append(workflow.id)
                
                if workflow_created:
                    logger.info(f"✅ Workflow creado para OLT {olt.abreviatura} (ID: {workflow.id})")
                else:
                    logger.info(f"✅ Workflow existente para OLT {olt.abreviatura} (ID: {workflow.id})")
                
                # Crear o actualizar vinculación con la plantilla
                link, link_created = WorkflowTemplateLink.objects.get_or_create(
                    template=template,
                    workflow=workflow,
                    defaults={'auto_sync': auto_sync}
                )
                if not link_created:
                    link.auto_sync = auto_sync
                    link.save()
                
                logger.info(
                    f"🔗 Vinculación creada/actualizada entre plantilla '{template.name}' "
                    f"y workflow {workflow.id} (OLT: {olt.abreviatura})"
                )
                
                # Marcar que el workflow se creó exitosamente
                stats['olts_processed'] += 1
                
            except OLT.DoesNotExist:
                error_msg = f"OLT ID {olt_id} no existe"
                stats['errors'].append(error_msg)
                logger.error(error_msg)
            except Exception as e:
                error_msg = f"Error creando workflow para OLT {olt_id}: {str(e)}"
                stats['errors'].append(error_msg)
                logger.error(error_msg, exc_info=True)
        
        # Procesar nodos dentro de transacción
        with transaction.atomic():
            for olt_id in olt_ids:
                olt_processed = False
                olt_stats = {
                    'nodes_linked': 0,
                    'nodes_created': 0,
                }
                
                try:
                    # Usar el workflow previamente creado/obtenido
                    workflow = workflow_map.get(olt_id)
                    if not workflow:
                        olt = OLT.objects.select_related('marca', 'modelo').get(id=olt_id)
                        workflow = OLTWorkflow.objects.filter(olt=olt).first()
                    
                    if not workflow:
                        error_msg = f"No se pudo obtener workflow para OLT {olt_id}"
                        stats['errors'].append(error_msg)
                        logger.error(error_msg)
                        continue
                    
                    # Procesar TODOS los nodos sin restricciones de marca/modelo
                    # Ordenar nodos: primero los masters (no están en cadena), luego los nodos en cadena
                    # Esto asegura que cuando se procese un nodo en cadena, su master ya exista
                    sorted_template_nodes = sorted(
                        template_nodes,
                        key=lambda n: (n.is_chain_node, n.priority if n.is_chain_node else 0)
                            )
                    
                    # Procesar todos los nodos (sin filtro de compatibilidad)
                    for template_node in sorted_template_nodes:
                        result = WorkflowTemplateService._process_template_node(
                            workflow, template_node, create_custom_nodes
                        )
                        action = result['action']
                        if action == 'nodes_linked':
                            olt_stats['nodes_linked'] += 1
                            stats['nodes_linked'] += 1
                        elif action == 'nodes_created':
                            olt_stats['nodes_created'] += 1
                            stats['nodes_created'] += 1
                        elif action == 'nodes_synced':
                            # Contar como actualizado, no como creado
                            stats['nodes_synced'] = stats.get('nodes_synced', 0) + 1
                        else:
                            stats['nodes_skipped'] += 1
                    
                    # Después de procesar todos los nodos, actualizar master_nodes de nodos en cadena
                    # que no pudieron encontrar su master durante la creación
                    for template_node in sorted_template_nodes:
                        if template_node.is_chain_node and template_node.master_node:
                            # Buscar nodos en cadena que no tienen master asignado
                            chain_workflow_nodes = WorkflowNode.objects.filter(
                                workflow=workflow,
                                template_node=template_node,
                                is_chain_node=True,
                                master_node__isnull=True
                            )
                            
                            for chain_node in chain_workflow_nodes:
                                # Buscar el master_node correspondiente
                                master_workflow_node = WorkflowNode.objects.filter(
                                    workflow=workflow,
                                    template_node=template_node.master_node
                                ).first()
                                
                                if master_workflow_node:
                                    chain_node.master_node = master_workflow_node
                                    chain_node.save()
                                    logger.info(
                                        f"🔗 Master actualizado para nodo en cadena '{chain_node.key}' "
                                        f"con master '{master_workflow_node.key}' en workflow {workflow.olt.abreviatura}"
                                    )
                    
                    # El contador ya se incrementó cuando se creó el workflow
                    # Solo registrar el resumen final
                    logger.info(
                        f"✅ Plantilla '{template.name}' aplicada a OLT {olt.abreviatura} (ID: {olt_id}). "
                        f"Workflow: {workflow.id}, Vinculados: {olt_stats['nodes_linked']}, "
                        f"Creados: {olt_stats['nodes_created']}"
                    )
                    
                except OLT.DoesNotExist:
                    # Ya se manejó arriba, solo registrar
                    logger.warning(f"⚠️ OLT {olt_id} no existe, saltando procesamiento de nodos")
                except Exception as e:
                    error_msg = f"Error procesando nodos para OLT {olt_id}: {str(e)}"
                    stats['errors'].append(error_msg)
                    logger.error(f"Error procesando nodos para OLT {olt_id}: {e}", exc_info=True)
                    # El workflow ya se creó arriba, así que no revertir nada
        
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
            
            # Verificar que tenga OID (necesario para ejecutar)
            if not template_node.oid:
                logger.warning(
                    f"⚠️ Nodo '{template_node.key}' sin OID - no se puede crear en workflow {workflow.olt.abreviatura}"
                )
                return {'action': 'nodes_skipped'}
            
            # Obtener TaskTemplate apropiado desde el OID
            task_template = _get_task_template_for_oid(template_node.oid)
            
            if not task_template:
                logger.error(f"No se pudo encontrar TaskTemplate para OID {template_node.oid}")
                return {'action': 'nodes_skipped'}
            
            # ✅ CRÍTICO: Lógica de intervalos para nodos master vs encadenados
            # - Los nodos MASTER: usan el intervalo definido en la plantilla
            # - Los nodos ENCADENADOS: SIEMPRE interval_seconds = 0 (NO tienen intervalo propio)
            #   Los nodos encadenados se ejecutan DESPUÉS del master según prioridad,
            #   NO según intervalo. Se almacena 0 solo para satisfacer la columna NOT NULL.
            if template_node.is_chain_node:
                # ✅ FORZAR: Nodos encadenados SIEMPRE tienen intervalo 0
                interval_seconds = 0
            else:
                # Nodos master: usar intervalo de la plantilla
                interval_seconds = template_node.interval_seconds if template_node.interval_seconds is not None else 0
            
            node_metadata = template_node.metadata.copy() if template_node.metadata else {}
            node_metadata['origin_template_id'] = template_node.template_id
            
            new_node = WorkflowNode.objects.create(
                workflow=workflow,
                template=task_template,
                template_node=template_node,
                key=template_node.key,
                name=template_node.name,
                interval_seconds=interval_seconds,
                priority=template_node.priority,
                enabled=template_node.enabled,
                parameters=template_node.parameters.copy(),
                retry_policy=template_node.retry_policy.copy(),
                position_x=template_node.position_x,
                position_y=template_node.position_y,
                color_override=template_node.color_override or '',
                icon_override=template_node.icon_override or '',
                metadata=node_metadata,
                is_chain_node=template_node.is_chain_node,
                master_node=None,  # Se establecerá después si es necesario
                # IMPORTANTE: Los campos override deben ser False por defecto para permitir sincronización
                override_interval=False,
                override_priority=False,
                override_enabled=False,
                override_parameters=False,
            )
            
            # Si el template_node está en cadena, buscar el master_node correspondiente
            if template_node.is_chain_node and template_node.master_node:
                # Buscar el workflow_node correspondiente al master_node del template
                master_workflow_node = WorkflowNode.objects.filter(
                    workflow=workflow,
                    template_node=template_node.master_node
                ).first()
                
                if master_workflow_node:
                    new_node.master_node = master_workflow_node
                    new_node.save()
                    logger.info(
                        f"🔗 Nodo en cadena '{new_node.key}' creado con master "
                        f"'{master_workflow_node.key}' en workflow {workflow.olt.abreviatura}"
                    )
                else:
                    logger.warning(
                        f"⚠️ No se encontró master_node '{template_node.master_node.key}' "
                        f"para nodo en cadena '{template_node.key}' en workflow {workflow.olt.abreviatura}. "
                        f"El master se establecerá cuando esté disponible."
            )
            
            # ✅ CRÍTICO: Inicializar next_run_at SOLO para nodos MASTER
            # - Nodos MASTER: tienen intervalo propio → inicializar next_run_at
            # - Nodos ENCADENADOS: NO tienen intervalo → NO inicializar next_run_at
            #   Los nodos encadenados se ejecutan cuando el master termine exitosamente
            if new_node.enabled and not new_node.is_chain_node:
                # ✅ SOLO nodos master: inicializar next_run_at con su intervalo
                new_node.initialize_next_run()
                new_node.save(update_fields=['next_run_at'])
                logger.info(
                    f"✅ Nodo MASTER '{new_node.key}' creado desde plantilla '{template_node.template.name}' "
                    f"en workflow {workflow.olt.abreviatura} con intervalo {new_node.interval_seconds}s "
                    f"(próxima ejecución: {new_node.next_run_at})"
                )
            elif new_node.is_chain_node:
                # ✅ Nodos encadenados: NO inicializar next_run_at (dependen del master)
                # Asegurar que next_run_at sea None y interval_seconds sea 0
                if new_node.next_run_at is not None:
                    new_node.next_run_at = None
                if new_node.interval_seconds != 0:
                    new_node.interval_seconds = 0
                new_node.save(update_fields=['next_run_at', 'interval_seconds'])
                master_info = f" (master: {new_node.master_node.key})" if new_node.master_node else " (master pendiente)"
                logger.info(
                    f"✅ Nodo ENCADENADO '{new_node.key}' creado desde plantilla '{template_node.template.name}' "
                    f"en workflow {workflow.olt.abreviatura}{master_info} - "
                    f"Se ejecutará después del master (sin intervalo propio)"
                )
            else:
                logger.info(
                    f"✅ Nodo '{new_node.key}' creado desde plantilla '{template_node.template.name}' "
                    f"en workflow {workflow.olt.abreviatura} con intervalo {new_node.interval_seconds}s (deshabilitado)"
                )
            
            return {'action': 'nodes_created'}
    
    @staticmethod
    def sync_template_changes(template_id, workflow_ids=None):
        """
        Sincroniza cambios de una plantilla a todos los workflows vinculados.
        La sincronización es automática: cuando cambia la plantilla, todos los workflows
        vinculados se actualizan automáticamente desde la plantilla.
        
        Busca nodos por template_node Y por key para asegurar que todos los nodos
        vinculados se sincronicen correctamente.
        
        Args:
            template_id: ID de la WorkflowTemplate
            workflow_ids: Lista opcional de workflows específicos a sincronizar
        
        Returns:
            dict con estadísticas de sincronización
        """
        template = WorkflowTemplate.objects.get(id=template_id)
        
        links = template.workflow_links.filter(auto_sync=True)
        if workflow_ids:
            links = links.filter(workflow_id__in=workflow_ids)
        
        stats = {
            'workflows_synced': 0,
            'nodes_synced': 0,
            'nodes_skipped': 0,
            'nodes_not_found': 0,
            'nodes_deleted': 0,
        }
        
        for link in links:
            workflow = link.workflow
            template_nodes = template.template_nodes.all()
            template_node_keys = set(template_nodes.values_list('key', flat=True))
            template_node_ids = set(template_nodes.values_list('id', flat=True))
            
            # Eliminar nodos huérfanos: nodos vinculados a esta plantilla que ya no existen en la plantilla
            # Método 1: Nodos que tienen template_node que apunta a un nodo que ya no existe en la plantilla
            orphaned_by_template = WorkflowNode.objects.filter(
                workflow=workflow,
                template_node__template=template
            ).exclude(
                template_node__id__in=template_node_ids
            )
            
            # Método 2: Nodos que tienen template_node=None (fueron eliminados y SET_NULL los puso en None)
            # y tienen una key que no está en la plantilla actual
            # Esto es más complejo porque necesitamos saber qué keys pertenecían a esta plantilla
            # Por ahora, confiamos en que la señal post_delete maneje esto directamente
            
            # Método 3: Buscar nodos administrados por esta plantilla (metadata) cuya key ya no existe
            orphaned_by_metadata = WorkflowNode.objects.filter(
                workflow=workflow,
                metadata__origin_template_id=template.id
            ).exclude(
                key__in=template_node_keys
            )
            
            # Método 4: Nodos con template_node todavía apuntando a la plantilla pero cuya key ya no existe
            orphaned_by_key = WorkflowNode.objects.filter(
                workflow=workflow,
                template_node__template=template
            ).exclude(
                key__in=template_node_keys
            )
            
            # Combinar todos los métodos de detección
            orphaned_node_ids = set(
                list(orphaned_by_template.values_list('id', flat=True)) +
                list(orphaned_by_metadata.values_list('id', flat=True)) +
                list(orphaned_by_key.values_list('id', flat=True))
            )
            
            if orphaned_node_ids:
                orphaned_nodes = WorkflowNode.objects.filter(id__in=orphaned_node_ids)
                orphaned_count = orphaned_nodes.count()
                
                if orphaned_count > 0:
                    logger.info(
                        f"🗑️ Eliminando {orphaned_count} nodo(s) huérfano(s) de workflow {workflow.olt.abreviatura} "
                        f"(ya no existen en la plantilla)"
                    )
                    orphaned_nodes.delete()
                    stats['nodes_deleted'] += orphaned_count
            
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
                    # No existe nodo en el workflow para este template_node
                    # Crear nuevo nodo desde la plantilla si auto_sync está activo
                    if link.auto_sync:
                        try:
                            # Usar _process_template_node para crear el nodo correctamente
                            result = WorkflowTemplateService._process_template_node(
                                workflow, template_node, create_custom_nodes=True
                            )
                            
                            if result['action'] == 'nodes_created':
                                # Si se creó el nodo, buscar el nodo creado para establecer master si es necesario
                                new_workflow_node = WorkflowNode.objects.filter(
                                    workflow=workflow,
                                    template_node=template_node
                                ).first()
                                
                                if new_workflow_node:
                                    # Si el template_node está en cadena, buscar el master_node correspondiente
                                    if template_node.is_chain_node and template_node.master_node:
                                        # Buscar el workflow_node correspondiente al master_node del template
                                        master_workflow_node = WorkflowNode.objects.filter(
                                            workflow=workflow,
                                            template_node=template_node.master_node
                                        ).first()
                                        
                                        if master_workflow_node:
                                            new_workflow_node.master_node = master_workflow_node
                                            new_workflow_node.is_chain_node = True
                                            new_workflow_node.save()
                                            logger.info(
                                                f"🔗 Nodo en cadena '{new_workflow_node.key}' creado con master "
                                                f"'{master_workflow_node.key}' en workflow {workflow.olt.abreviatura}"
                                            )
                                        else:
                                            logger.warning(
                                                f"⚠️ No se encontró master_node '{template_node.master_node.key}' "
                                                f"para nodo en cadena '{template_node.key}' en workflow {workflow.olt.abreviatura}"
                                            )
                                    
                                    stats['nodes_synced'] += 1
                                    logger.info(
                                        f"✅ Nuevo nodo '{template_node.key}' creado desde plantilla "
                                        f"en workflow {workflow.olt.abreviatura}"
                                    )
                                else:
                                    stats['nodes_not_found'] += 1
                            elif result['action'] == 'nodes_skipped':
                                stats['nodes_not_found'] += 1
                                logger.warning(
                                    f"⚠️ Nodo '{template_node.key}' no se pudo crear en workflow {workflow.olt.abreviatura} "
                                    f"(sin OID o error al crear)"
                                )
                            else:
                                stats['nodes_not_found'] += 1
                        except Exception as e:
                            logger.error(
                                f"❌ Error creando nodo '{template_node.key}' en workflow {workflow.olt.abreviatura}: {e}",
                                exc_info=True
                            )
                            stats['nodes_not_found'] += 1
                    else:
                        stats['nodes_not_found'] += 1
                        logger.info(
                            f"ℹ️ Nodo '{template_node.key}' no encontrado en workflow {workflow.olt.abreviatura} "
                            f"y auto_sync está desactivado"
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
                    
                    # Garantizar metadata de origen plantilla
                    metadata = workflow_node.metadata or {}
                    if metadata.get('origin_template_id') != template.id:
                        metadata['origin_template_id'] = template.id
                        workflow_node.metadata = metadata
                        workflow_node.save(update_fields=['metadata'])
                    
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
            f"{stats['workflows_synced']} workflows, {stats['nodes_synced']} nodos actualizados/creados, "
            f"{stats['nodes_deleted']} nodos eliminados, {stats['nodes_not_found']} nodos no encontrados"
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

