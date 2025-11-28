from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from brands.models import Brand


class OLTManager(models.Manager):
    """Manager que excluye OLTs eliminadas por defecto"""
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    
    def all_with_deleted(self):
        """Retornar todas las OLTs, incluyendo eliminadas"""
        return super().get_queryset()
    
    def deleted_only(self):
        """Retornar solo OLTs eliminadas"""
        return super().get_queryset().filter(is_deleted=True)
    
    def get_by_abreviatura(self, abreviatura):
        """Obtener OLT por abreviatura (solo activas)"""
        return self.get(abreviatura=abreviatura, is_deleted=False)


class OLT(models.Model):
    abreviatura = models.CharField(max_length=255)
    marca = models.ForeignKey(Brand, models.CASCADE, db_column='marca_id')
    modelo = models.ForeignKey(
        'olt_models.OLTModel',
        on_delete=models.SET_NULL,
        db_column='modelo_id',
        blank=True,
        null=True,
        verbose_name='Modelo',
        help_text='Modelo específico de la OLT. Opcional.'
    )
    ip_address = models.CharField(max_length=255)
    descripcion = models.TextField()
    habilitar_olt = models.BooleanField(
        default=True,
        help_text="Indica si la OLT está habilitada para consultas SNMP"
    )
    comunidad = models.CharField(max_length=255)
    
    # ✅ SOFT DELETE
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indica si la OLT está eliminada (soft delete)"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora de eliminación"
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_olts',
        help_text="Usuario que eliminó la OLT"
    )
    deletion_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Razón de la eliminación"
    )
    
    # ✅ TIMESTAMPS
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha de creación"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Fecha de última actualización"
    )
    
    # Managers
    objects = OLTManager()  # Por defecto excluye eliminadas
    all_objects = models.Manager()  # Incluye todas (para admin)

    class Meta:
        db_table = 'olt'
        managed = True
        verbose_name = 'OLT'
        verbose_name_plural = 'OLTs'
        ordering = ['abreviatura']
        
        # ✅ Índices optimizados
        indexes = [
            models.Index(
                fields=['is_deleted', 'habilitar_olt'],
                name='olt_active_idx'
            ),
            models.Index(
                fields=['abreviatura', 'is_deleted'],
                name='olt_abrev_unique_idx'
            ),
            models.Index(
                fields=['marca', 'is_deleted'],
                name='olt_marca_active_idx'
            ),
            models.Index(
                fields=['ip_address'],
                name='olt_ip_idx'
            ),
        ]
        
        # ✅ Constraint de unicidad condicional (PostgreSQL)
        constraints = [
            models.UniqueConstraint(
                fields=['abreviatura'],
                condition=models.Q(is_deleted=False),
                name='unique_abreviatura_when_not_deleted'
            )
        ]

    def __str__(self):
        status = "❌ [ELIMINADA] " if self.is_deleted else ""
        return f"{status}{self.abreviatura} - {self.ip_address}"
    
    def clean(self):
        """Validación personalizada"""
        # Validar que no haya OLTs activas con la misma abreviatura
        if not self.is_deleted:
            existing = OLT.all_objects.filter(
                abreviatura=self.abreviatura,
                is_deleted=False
            ).exclude(pk=self.pk if self.pk else None)
            if existing.exists():
                raise ValidationError({
                    'abreviatura': f'Ya existe una OLT activa con la abreviatura "{self.abreviatura}"'
                })
    
    def soft_delete(self, user=None, reason=None):
        """
        Eliminar la OLT de forma suave (soft delete)
        
        Args:
            user: Usuario que realiza la eliminación
            reason: Razón de la eliminación
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.deletion_reason = reason
        self.habilitar_olt = False  # También deshabilitar
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'deletion_reason', 'habilitar_olt'])
    
    def restore(self, user=None, rename_on_conflict=True):
        """
        Restaurar una OLT eliminada (undo soft delete)
        
        Si ya existe una OLT activa con la misma abreviatura, la renombra automáticamente
        agregando un sufijo "_RESTORED_YYYYMMDD_HHMMSS" para evitar conflictos.
        
        Args:
            user: Usuario que restaura la OLT
            rename_on_conflict: Si True, renombra automáticamente si hay conflicto (default: True)
        
        Returns:
            dict: Información sobre la restauración con las claves:
                - 'restored': bool - Si se restauró exitosamente
                - 'original_abreviatura': str - Abreviatura original antes de restaurar
                - 'new_abreviatura': str - Nueva abreviatura (si fue renombrada)
                - 'renamed': bool - Si fue renombrada automáticamente
                - 'message': str - Mensaje descriptivo
        
        Raises:
            ValidationError: Si rename_on_conflict=False y hay conflicto
        """
        original_abreviatura = self.abreviatura
        
        # Verificar que no haya otra OLT activa con la misma abreviatura
        existing = OLT.objects.filter(
            abreviatura=self.abreviatura,
            is_deleted=False
        ).exclude(pk=self.pk)
        
        renamed = False
        new_abreviatura = None
        
        if existing.exists():
            if rename_on_conflict:
                # Renombrar automáticamente agregando un sufijo con timestamp
                timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
                new_abreviatura = f"{self.abreviatura}_RESTORED_{timestamp}"
                
                # Asegurarse de que el nuevo nombre no existe
                counter = 1
                while OLT.objects.filter(
                    abreviatura=new_abreviatura,
                    is_deleted=False
                ).exclude(pk=self.pk).exists():
                    new_abreviatura = f"{self.abreviatura}_RESTORED_{timestamp}_{counter}"
                    counter += 1
                
                self.abreviatura = new_abreviatura
                renamed = True
            else:
                raise ValidationError(
                    f'No se puede restaurar: ya existe una OLT activa con la abreviatura "{self.abreviatura}". '
                    f'Puede restaurar con rename_on_conflict=True para renombrar automáticamente.'
                )
        
        # Restaurar la OLT
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.deletion_reason = None
        
        # Actualizar campos según si fue renombrada
        if renamed:
            self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'deletion_reason', 'abreviatura'])
        else:
            self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'deletion_reason'])
        
        # Preparar mensaje informativo
        if renamed:
            message = f'OLT restaurada exitosamente. Abreviatura cambiada de "{original_abreviatura}" a "{new_abreviatura}" porque ya existe una OLT activa con ese nombre.'
        else:
            message = f'OLT "{original_abreviatura}" restaurada exitosamente.'
        
        return {
            'restored': True,
            'original_abreviatura': original_abreviatura,
            'new_abreviatura': new_abreviatura if renamed else original_abreviatura,
            'renamed': renamed,
            'message': message
        }