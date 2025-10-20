# Generated manually for performance optimization

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('odf_management', '0008_zabbixportdata_disponible'),
    ]

    operations = [
        # Índice compuesto para consultas frecuentes en ODFHilos
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS odf_hilos_performance_idx ON odf_hilos (odf_id, slot, port, en_zabbix);",
            reverse_sql="DROP INDEX IF EXISTS odf_hilos_performance_idx;"
        ),
        
        # Índice para consultas de ZabbixPortData con filtros comunes
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS zabbix_port_filter_idx ON zabbix_port_data (olt_id, disponible, slot, port);",
            reverse_sql="DROP INDEX IF EXISTS zabbix_port_filter_idx;"
        ),
        
        # Índice para búsquedas por descripción (usado en el admin)
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS zabbix_port_desc_idx ON zabbix_port_data USING gin (to_tsvector('spanish', descripcion_zabbix));",
            reverse_sql="DROP INDEX IF EXISTS zabbix_port_desc_idx;"
        ),
        
        # Índice parcial para puertos disponibles (más eficiente)
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS zabbix_port_disponibles_idx ON zabbix_port_data (olt_id, slot, port) WHERE disponible = true;",
            reverse_sql="DROP INDEX IF EXISTS zabbix_port_disponibles_idx;"
        ),
        
        # Índice para hilos habilitados en Zabbix (consultas frecuentes)
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS odf_hilos_zabbix_enabled_idx ON odf_hilos (odf_id, en_zabbix, slot, port) WHERE en_zabbix = true;",
            reverse_sql="DROP INDEX IF EXISTS odf_hilos_zabbix_enabled_idx;"
        ),
    ]
