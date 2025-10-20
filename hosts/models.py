from django.db import models
from brands.models import Brand


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

    class Meta:
        db_table = 'olt'
        managed = True
        verbose_name = 'OLT'
        verbose_name_plural = 'OLTs'

    def __str__(self):
        return f"{self.abreviatura} - {self.ip_address}"