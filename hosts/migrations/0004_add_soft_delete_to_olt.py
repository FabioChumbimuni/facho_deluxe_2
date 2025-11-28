# Generated migration for soft delete support in OLT
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('hosts', '0003_alter_olt_modelo'),
    ]

    operations = [
        # 1. Agregar campos de soft delete
        migrations.AddField(
            model_name='olt',
            name='is_deleted',
            field=models.BooleanField(default=False, db_index=True, help_text='Indica si la OLT está eliminada (soft delete)'),
        ),
        migrations.AddField(
            model_name='olt',
            name='deleted_at',
            field=models.DateTimeField(blank=True, help_text='Fecha y hora de eliminación', null=True),
        ),
        migrations.AddField(
            model_name='olt',
            name='deleted_by',
            field=models.ForeignKey(
                blank=True,
                help_text='Usuario que eliminó la OLT',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='deleted_olts',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='olt',
            name='deletion_reason',
            field=models.TextField(blank=True, help_text='Razón de la eliminación', null=True),
        ),
        
        # 2. Agregar timestamps
        migrations.AddField(
            model_name='olt',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                help_text='Fecha de creación'
            ),
            preserve_default=True,  # Mantener el default para filas existentes
        ),
        migrations.AddField(
            model_name='olt',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, help_text='Fecha de última actualización'),
        ),
        
        # 3. Agregar índices
        migrations.AddIndex(
            model_name='olt',
            index=models.Index(
                fields=['is_deleted', 'habilitar_olt'],
                name='olt_active_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='olt',
            index=models.Index(
                fields=['abreviatura', 'is_deleted'],
                name='olt_abrev_unique_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='olt',
            index=models.Index(
                fields=['marca', 'is_deleted'],
                name='olt_marca_active_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='olt',
            index=models.Index(
                fields=['ip_address'],
                name='olt_ip_idx'
            ),
        ),
        
        # 4. Agregar constraint de unicidad condicional (PostgreSQL)
        migrations.AddConstraint(
            model_name='olt',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_deleted', False)),
                fields=['abreviatura'],
                name='unique_abreviatura_when_not_deleted'
            ),
        ),
        
        # 5. Agregar ordering
        migrations.AlterModelOptions(
            name='olt',
            options={'ordering': ['abreviatura'], 'verbose_name': 'OLT', 'verbose_name_plural': 'OLTs'},
        ),
    ]

