# Generated manually - remover constraint y hacer marca/modelo non-nullable

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('brands', '0001_initial'),
        ('olt_models', '0002_add_sample_models'),
        ('snmp_formulas', '0004_alter_indexformula_marca_and_more'),
    ]

    operations = [
        # Remover constraint si existe (puede no existir en algunas instalaciones)
        migrations.RunSQL(
            sql="ALTER TABLE index_formulas DROP CONSTRAINT IF EXISTS formula_generica_sin_marca_sin_modelo;",
            reverse_sql="",  # No reverse necesario
        ),
        migrations.AlterField(
            model_name='indexformula',
            name='marca',
            field=models.ForeignKey(
                db_column='marca_id',
                help_text='Marca del equipo',
                on_delete=django.db.models.deletion.CASCADE,
                to='brands.brand',
                verbose_name='Marca'
            ),
        ),
        migrations.AlterField(
            model_name='indexformula',
            name='modelo',
            field=models.ForeignKey(
                db_column='modelo_id',
                help_text='Modelo del equipo',
                on_delete=django.db.models.deletion.CASCADE,
                to='olt_models.oltmodel',
                verbose_name='Modelo'
            ),
        ),
    ]

