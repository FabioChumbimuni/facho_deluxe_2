# snmp_jobs/models.py - Nuevos modelos para sistema tipo Zabbix

# ... (código existente hasta TaskTemplate) ...

class WorkflowTemplate(models.Model):
    """
    Plantilla maestra de workflow que puede aplicarse a múltiples OLTs.
    Similar a Templates en Zabbix.
    """
    name = models.CharField(max_length=150, unique=True, help_text="Nombre único de la plantilla")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_workflow_templates"
        verbose_name = "Plantilla de Workflow"
        verbose_name_plural = "Plantillas de Workflow"
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkflowTemplateNode(models.Model):
    """
    Nodo dentro de una plantilla de workflow.
    Cada nodo tiene una 'key' única dentro de la plantilla (como items en Zabbix).
    """
    PRIORITY_CHOICES = TaskTemplate.PRIORITY_CHOICES

    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="template_nodes",
    )
    task_template = models.ForeignKey(
        TaskTemplate,
        on_delete=models.PROTECT,
        related_name="workflow_template_nodes",
    )
    
    # KEY ÚNICA (como en Zabbix) - identifica el nodo de forma única
    key = models.CharField(
        max_length=150,
        help_text="Identificador único del nodo (ej: discover.60min, get.description.10min)"
    )
    name = models.CharField(
        max_length=150,
        help_text="Nombre descriptivo del nodo"
    )
    
    interval_seconds = models.PositiveIntegerField(default=300)
    priority = models.PositiveSmallIntegerField(
        choices=PRIORITY_CHOICES,
        default=3,
    )
    parameters = models.JSONField(default=dict, blank=True)
    retry_policy = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    color_override = models.CharField(max_length=16, blank=True)
    icon_override = models.CharField(max_length=8, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "snmp_workflow_template_nodes"
        unique_together = [("template", "key")]  # Key única dentro de cada plantilla
        verbose_name = "Nodo de Plantilla"
        verbose_name_plural = "Nodos de Plantilla"
        ordering = ["template", "priority", "name"]

    def __str__(self):
        return f"{self.template.name} → {self.name} ({self.key})"


class WorkflowTemplateLink(models.Model):
    """
    Relación ManyToMany entre WorkflowTemplate y OLTWorkflow.
    Define si un workflow está vinculado a una plantilla y si se sincroniza automáticamente.
    """
    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="workflow_links",
    )
    workflow = models.ForeignKey(
        'OLTWorkflow',
        on_delete=models.CASCADE,
        related_name="template_links",
    )
    auto_sync = models.BooleanField(
        default=True,
        help_text="Si True, los cambios en la plantilla se propagan automáticamente"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_workflow_template_links"
        unique_together = [("template", "workflow")]
        verbose_name = "Vinculación Plantilla-Workflow"
        verbose_name_plural = "Vinculaciones Plantilla-Workflow"

    def __str__(self):
        return f"{self.template.name} → {self.workflow.olt.abreviatura}"


# Modificar WorkflowNode existente para agregar campos nuevos
# (Esto se hará en una migración, aquí solo documentamos los cambios)

"""
CAMBIOS EN WorkflowNode:
1. Agregar campo 'key' (CharField, único dentro del workflow)
2. Agregar campo 'template_node' (ForeignKey a WorkflowTemplateNode, nullable)
3. Agregar campos de override:
   - override_interval (BooleanField)
   - override_priority (BooleanField)
   - override_enabled (BooleanField)
   - override_parameters (BooleanField)
4. Modificar unique_together para incluir (workflow, key)
5. Agregar método para vincular automáticamente por key
"""

