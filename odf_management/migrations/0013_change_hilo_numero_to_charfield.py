# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('odf_management', '0012_add_hora_habilitacion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='odfhilos',
            name='hilo_numero',
            field=models.CharField(
                max_length=100,
                help_text="Número o identificador físico del hilo hacia la NAP (puede ser numérico o texto como 'SPLITTER 5')"
            ),
        ),
    ]

