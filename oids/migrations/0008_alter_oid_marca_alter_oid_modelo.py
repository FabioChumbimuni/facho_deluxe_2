# Generated manually - hacer marca y modelo non-nullable

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('brands', '0001_initial'),
        ('olt_models', '0002_add_sample_models'),
        ('oids', '0007_marca_nullable_for_universal'),
    ]

    operations = [
        migrations.AlterField(
            model_name='oid',
            name='marca',
            field=models.ForeignKey(
                db_column='marca_id',
                help_text='Marca del equipo. Usar "🌐 Genérico" para aplicar a todas las marcas',
                on_delete=django.db.models.deletion.CASCADE,
                to='brands.brand',
                verbose_name='Marca'
            ),
        ),
        migrations.AlterField(
            model_name='oid',
            name='modelo',
            field=models.ForeignKey(
                db_column='modelo_id',
                help_text='Modelo del equipo. Usar "🌐 Genérico" para aplicar a todos los modelos',
                on_delete=django.db.models.deletion.CASCADE,
                to='olt_models.oltmodel',
                verbose_name='Modelo'
            ),
        ),
    ]

