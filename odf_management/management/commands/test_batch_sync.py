"""
Comando para probar la sincronización masiva batch entre odf_hilos y zabbix_port_data
"""

from django.core.management.base import BaseCommand
from django.db import connection
from odf_management.models import ODFHilos, ZabbixPortData, ODF
from hosts.models import OLT
from odf_management.tasks import sync_all_odf_hilos, sync_odf_hilos_for_olt


class Command(BaseCommand):
    help = 'Prueba la sincronización masiva batch basada en NUEVO METODO.md'

    def add_arguments(self, parser):
        parser.add_argument(
            '--olt-id',
            type=int,
            help='ID específico de OLT para probar sincronización'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Ejecutar como tarea Celery asíncrona'
        )
        parser.add_argument(
            '--all-olts',
            action='store_true',
            help='Sincronizar todas las OLTs'
        )

    def handle(self, *args, **options):
        olt_id = options.get('olt_id')
        async_mode = options['async']
        all_olts = options['all_olts']
        
        self.stdout.write("🔄 PRUEBA DE SINCRONIZACIÓN MASIVA BATCH")
        self.stdout.write("=" * 60)
        
        if all_olts:
            self._test_all_olts_sync(async_mode)
        elif olt_id:
            self._test_single_olt_sync(olt_id, async_mode)
        else:
            self._show_sync_status()

    def _test_single_olt_sync(self, olt_id, async_mode):
        """Probar sincronización para una OLT específica"""
        try:
            olt = OLT.objects.get(id=olt_id)
            self.stdout.write(f"🎯 PROBANDO SINCRONIZACIÓN PARA OLT: {olt.abreviatura}")
            
            # Mostrar estado antes
            self._show_olt_stats_before(olt)
            
            if async_mode:
                self.stdout.write("⚡ Ejecutando como tarea Celery asíncrona...")
                result = sync_odf_hilos_for_olt.delay(olt_id)
                self.stdout.write(f"✅ Tarea encolada con ID: {result.id}")
                self.stdout.write("💡 Usa 'python manage.py monitor_odf_logs' para ver progreso")
            else:
                self.stdout.write("🔄 Ejecutando sincronización directa...")
                result = sync_odf_hilos_for_olt(olt_id)
                self.stdout.write(f"📊 RESULTADO: {result}")
                
                # Mostrar estado después
                self._show_olt_stats_after(olt)
                
        except OLT.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ OLT con ID {olt_id} no encontrada"))

    def _test_all_olts_sync(self, async_mode):
        """Probar sincronización masiva para todas las OLTs"""
        olts_habilitadas = OLT.objects.filter(habilitar_olt=True)
        
        self.stdout.write(f"🌐 PROBANDO SINCRONIZACIÓN MASIVA")
        self.stdout.write(f"📊 OLTs habilitadas: {olts_habilitadas.count()}")
        
        if async_mode:
            self.stdout.write("⚡ Ejecutando como tarea Celery asíncrona...")
            result = sync_all_odf_hilos.delay()
            self.stdout.write(f"✅ Tarea maestra encolada con ID: {result.id}")
            self.stdout.write("💡 Usa 'python manage.py monitor_odf_logs' para ver progreso")
        else:
            self.stdout.write("🔄 Ejecutando sincronización directa...")
            result = sync_all_odf_hilos()
            self.stdout.write(f"📊 RESULTADO: {result}")

    def _show_sync_status(self):
        """Mostrar estado actual de sincronización"""
        self.stdout.write("📊 ESTADO ACTUAL DE SINCRONIZACIÓN")
        self.stdout.write("-" * 50)
        
        # Estadísticas generales
        total_hilos = ODFHilos.objects.count()
        hilos_en_zabbix = ODFHilos.objects.filter(en_zabbix=True).count()
        hilos_con_puerto = ODFHilos.objects.filter(zabbix_port__isnull=False).count()
        
        self.stdout.write(f"📋 Total hilos ODF: {total_hilos}")
        self.stdout.write(f"✅ Hilos en Zabbix: {hilos_en_zabbix}")
        self.stdout.write(f"🔗 Hilos con puerto asociado: {hilos_con_puerto}")
        
        # Estadísticas por OLT
        self.stdout.write(f"\n📊 POR OLT:")
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    o.abreviatura,
                    COUNT(h.id) as total_hilos,
                    COUNT(CASE WHEN h.en_zabbix THEN 1 END) as en_zabbix,
                    COUNT(CASE WHEN h.zabbix_port_id IS NOT NULL THEN 1 END) as con_puerto
                FROM olt o
                LEFT JOIN odf odf ON odf.olt_id = o.id
                LEFT JOIN odf_hilos h ON h.odf_id = odf.id
                WHERE o.habilitar_olt = true
                GROUP BY o.id, o.abreviatura
                ORDER BY total_hilos DESC;
            """)
            
            for row in cursor.fetchall():
                abrev, total, en_zabbix, con_puerto = row
                if total > 0:
                    self.stdout.write(f"  {abrev}: {total} hilos ({en_zabbix} en Zabbix, {con_puerto} con puerto)")

    def _show_olt_stats_before(self, olt):
        """Mostrar estadísticas antes de la sincronización"""
        hilos = ODFHilos.objects.filter(odf__olt=olt)
        total = hilos.count()
        en_zabbix = hilos.filter(en_zabbix=True).count()
        con_puerto = hilos.filter(zabbix_port__isnull=False).count()
        
        self.stdout.write(f"\n📊 ANTES - {olt.abreviatura}:")
        self.stdout.write(f"  Total hilos: {total}")
        self.stdout.write(f"  En Zabbix: {en_zabbix}")
        self.stdout.write(f"  Con puerto: {con_puerto}")

    def _show_olt_stats_after(self, olt):
        """Mostrar estadísticas después de la sincronización"""
        hilos = ODFHilos.objects.filter(odf__olt=olt)
        total = hilos.count()
        en_zabbix = hilos.filter(en_zabbix=True).count()
        con_puerto = hilos.filter(zabbix_port__isnull=False).count()
        
        self.stdout.write(f"\n📊 DESPUÉS - {olt.abreviatura}:")
        self.stdout.write(f"  Total hilos: {total}")
        self.stdout.write(f"  En Zabbix: {en_zabbix}")
        self.stdout.write(f"  Con puerto: {con_puerto}")
        
        # Mostrar cambios
        self.stdout.write(f"\n✅ SINCRONIZACIÓN COMPLETADA")
