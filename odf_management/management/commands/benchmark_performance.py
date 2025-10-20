"""
Comando para hacer benchmark de rendimiento de las consultas ODF.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
import time
from odf_management.models import ZabbixPortData, ODFHilos
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Hace benchmark de rendimiento de las consultas ODF'

    def add_arguments(self, parser):
        parser.add_argument(
            '--iterations',
            type=int,
            default=10,
            help='Número de iteraciones para el benchmark (default: 10)'
        )

    def handle(self, *args, **options):
        iterations = options['iterations']
        
        self.stdout.write("🚀 BENCHMARK DE RENDIMIENTO ODF")
        self.stdout.write(f"Iteraciones: {iterations}")
        self.stdout.write("=" * 50)
        
        # 1. Benchmark de consulta básica ZabbixPortData
        self.stdout.write("\n📊 1. Consulta básica ZabbixPortData (primeros 100)")
        start_time = time.time()
        
        for _ in range(iterations):
            list(ZabbixPortData.objects.select_related('olt')[:100])
        
        end_time = time.time()
        avg_time = (end_time - start_time) / iterations
        self.stdout.write(f"   Tiempo promedio: {avg_time:.3f}s")
        
        # 2. Benchmark de consulta con filtros
        self.stdout.write("\n📊 2. Consulta con filtros (slot=1, disponible=True)")
        start_time = time.time()
        
        for _ in range(iterations):
            list(ZabbixPortData.objects.filter(slot=1, disponible=True).select_related('olt')[:50])
        
        end_time = time.time()
        avg_time = (end_time - start_time) / iterations
        self.stdout.write(f"   Tiempo promedio: {avg_time:.3f}s")
        
        # 3. Benchmark de consulta ODFHilos con relaciones
        self.stdout.write("\n📊 3. Consulta ODFHilos con relaciones (primeros 50)")
        start_time = time.time()
        
        for _ in range(iterations):
            list(ODFHilos.objects.select_related(
                'odf', 'odf__olt', 'zabbix_port', 
                'personal_proyectos', 'personal_noc', 'tecnico_habilitador'
            )[:50])
        
        end_time = time.time()
        avg_time = (end_time - start_time) / iterations
        self.stdout.write(f"   Tiempo promedio: {avg_time:.3f}s")
        
        # 4. Benchmark de consulta específica (simula la URL del problema)
        try:
            port_id = ZabbixPortData.objects.first().id
            self.stdout.write(f"\n📊 4. Consulta específica (zabbix_port={port_id})")
            start_time = time.time()
            
            for _ in range(iterations):
                try:
                    port = ZabbixPortData.objects.select_related('olt').get(id=port_id)
                    list(ODFHilos.objects.filter(
                        slot=port.slot, 
                        port=port.port
                    ).select_related('odf', 'odf__olt')[:10])
                except:
                    pass
            
            end_time = time.time()
            avg_time = (end_time - start_time) / iterations
            self.stdout.write(f"   Tiempo promedio: {avg_time:.3f}s")
            
        except:
            self.stdout.write("   ⚠️ No se pudo ejecutar (sin datos)")
        
        # 5. Estadísticas de la base de datos
        self.stdout.write("\n📈 ESTADÍSTICAS DE LA BASE DE DATOS:")
        
        with connection.cursor() as cursor:
            # Contar registros
            cursor.execute("SELECT COUNT(*) FROM zabbix_port_data;")
            zabbix_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM odf_hilos;")
            hilos_count = cursor.fetchone()[0]
            
            self.stdout.write(f"   ZabbixPortData: {zabbix_count:,} registros")
            self.stdout.write(f"   ODFHilos: {hilos_count:,} registros")
            
            # Verificar índices creados
            cursor.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename IN ('zabbix_port_data', 'odf_hilos') 
                AND indexname LIKE '%performance%' OR indexname LIKE '%filter%' OR indexname LIKE '%disponibles%'
                ORDER BY indexname;
            """)
            
            new_indexes = cursor.fetchall()
            self.stdout.write(f"\n🔍 ÍNDICES DE RENDIMIENTO APLICADOS:")
            for idx in new_indexes:
                self.stdout.write(f"   ✅ {idx[0]}")
        
        self.stdout.write("\n💡 RECOMENDACIONES:")
        self.stdout.write("   • Si los tiempos son >1s, considera usar paginación")
        self.stdout.write("   • Usa list_select_related en los admins")
        self.stdout.write("   • Los índices compuestos mejoran consultas con filtros múltiples")
        
        self.stdout.write("\n✅ Benchmark completado")
