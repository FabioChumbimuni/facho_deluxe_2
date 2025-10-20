from django.db import models


class Brand(models.Model):
    nombre = models.CharField(max_length=255, unique=True)
    descripcion = models.TextField()

    class Meta:
        db_table = 'marcas'
        managed = True

    def __str__(self):
        return self.nombre