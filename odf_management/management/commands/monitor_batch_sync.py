"""
Comando para monitorear la sincronización masiva batch en tiempo real
"""

import time
import os
from django.core.management.base import BaseCommand
from django.db import connection
from datetime import datetime, timedelta
from django.utils import timezone


class Command(BaseCommand):
    help = 'Monitorea la sincronización masiva batch en tiempo real'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tail-logs',
            action='store_true',
            help='Mostrar logs de Celery en tiempo real'
        )
        parser.add_argument(
            '--stats-only',
            action='store_true',
            help='Solo mostrar estadísticas de sincronización'
        )
        parser.add_argument(
            '--refresh-interval',
            type=int,
            default=5,
            help='Intervalo de actualización en segundos (default: 5)'
        )

    def handle(self, *args, **options):
        tail_logs = options['tail_logs']
        stats_only = options['stats_only']
        refresh_interval = options['refresh_interval']
        
        if tail_logs:
            self._tail_celery_logs()
        elif stats_only:
            self._monitor_stats_only(refresh_interval)
        else:
            self._monitor_full(refresh_interval)

    def _monitor_full(self, refresh_interval):
        """Monitoreo completo con estadísticas y logs"""
        self.stdout.write("🔄 MONITOR DE SINCRONIZACIÓN MASIVA BATCH")
        self.stdout.write("=" * 60)
        self.stdout.write("Presiona Ctrl+C para salir\n")
        
        try:
            while True:
                # Limpiar pantalla
                os.system('clear')
                
                self.stdout.write(f"🔄 MONITOR BATCH - {timezone.now().strftime('%H:%M:%S')}")
                self.stdout.write("=" * 60)
                
                # Estadísticas de sincronización
                self._show_sync_stats()
                
                # Tareas Celery recientes
                self._show_recent_tasks()
                
                # Estados por OLT
                self._show_olt_status()
                
                self.stdout.write(f"\n🔄 Actualizando cada {refresh_interval}s... (Ctrl+C para salir)")
                time.sleep(refresh_interval)
                
        except KeyboardInterrupt:
            self.stdout.write("\n✅ Monitor detenido")

    def _monitor_stats_only(self, refresh_interval):
        """Solo mostrar estadísticas"""
        try:
            while True:
                os.system('clear')
                self.stdout.write(f"📊 ESTADÍSTICAS BATCH - {timezone.now().strftime('%H:%M:%S')}")
                self.stdout.write("=" * 50)
                
                self._show_sync_stats()
                self._show_olt_status()
                
                time.sleep(refresh_interval)
                
        except KeyboardInterrupt:
            self.stdout.write("\n✅ Monitor detenido")

    def _show_sync_stats(self):
        """Mostrar estadísticas de sincronización"""
        with connection.cursor() as cursor:
            # Estadísticas generales
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_hilos,
                    COUNT(CASE WHEN en_zabbix THEN 1 END) as en_zabbix,
                    COUNT(CASE WHEN zabbix_port_id IS NOT NULL THEN 1 END) as con_puerto,
                    COUNT(CASE WHEN operativo_noc THEN 1 END) as operativo_noc
                FROM odf_hilos;
            """)
            
            stats = cursor.fetchone()
            total, en_zabbix, con_puerto, operativo_noc = stats
            
            # Estadísticas de puertos Zabbix
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_puertos,
                    COUNT(CASE WHEN disponible THEN 1 END) as disponibles,
                    COUNT(CASE WHEN estado_administrativo = 1 THEN 1 END) as activos,
                    COUNT(CASE WHEN estado_administrativo = 2 THEN 1 END) as inactivos,
                    COUNT(CASE WHEN operativo_noc THEN 1 END) as operativo_noc_puertos
                FROM zabbix_port_data;
            """)
            
            port_stats = cursor.fetchone()
            total_puertos, disponibles, activos, inactivos, operativo_noc_puertos = port_stats
            
        self.stdout.write("📊 ESTADÍSTICAS GENERALES:")
        self.stdout.write(f"  🔗 Hilos ODF: {total} total, {en_zabbix} en Zabbix, {con_puerto} con puerto")
        self.stdout.write(f"  ⚙️ Operativo NOC (hilos): {operativo_noc}")
        self.stdout.write(f"  📡 Puertos Zabbix: {total_puertos} total, {disponibles} disponibles")
        self.stdout.write(f"  🟢 Estados admin: {activos} activos, {inactivos} inactivos")
        self.stdout.write(f"  ⚙️ Operativo NOC (puertos): {operativo_noc_puertos}")
        
        # Sincronización
        if total > 0:
            sync_rate = (en_zabbix / total) * 100
            self.stdout.write(f"  🔄 Tasa sincronización: {sync_rate:.1f}%")

    def _show_recent_tasks(self):
        """Mostrar tareas Celery recientes"""
        # Simular información de tareas (en producción podrías usar Flower o Redis)
        self.stdout.write("\n📋 TAREAS BATCH RECIENTES:")
        self.stdout.write("  🕐 Última ejecución programada: Cada 5 minutos")
        self.stdout.write("  ⚡ Cola: odf_sync (workers dedicados)")
        self.stdout.write("  📝 Para logs detallados: tail -f logs/odf_sync.log")

    def _show_olt_status(self):
        """Mostrar estado por OLT"""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    o.abreviatura,
                    COUNT(h.id) as total_hilos,
                    COUNT(CASE WHEN h.en_zabbix THEN 1 END) as en_zabbix,
                    COUNT(CASE WHEN h.zabbix_port_id IS NOT NULL THEN 1 END) as con_puerto,
                    COUNT(CASE WHEN h.operativo_noc THEN 1 END) as operativo_noc,
                    COUNT(CASE WHEN z.disponible THEN 1 END) as puertos_disponibles,
                    COUNT(CASE WHEN z.estado_administrativo = 1 THEN 1 END) as puertos_activos
                FROM olt o
                LEFT JOIN odf odf ON odf.olt_id = o.id
                LEFT JOIN odf_hilos h ON h.odf_id = odf.id
                LEFT JOIN zabbix_port_data z ON z.olt_id = o.id
                WHERE o.habilitar_olt = true
                GROUP BY o.id, o.abreviatura
                HAVING COUNT(h.id) > 0 OR COUNT(z.id) > 0
                ORDER BY total_hilos DESC;
            """)
            
            self.stdout.write("\n🏢 ESTADO POR OLT:")
            self.stdout.write("  OLT | Hilos | Zabbix | Puerto | OpNOC | PuerDisp | PuerAct")
            self.stdout.write("  " + "-" * 65)
            
            for row in cursor.fetchall():
                abrev, total_hilos, en_zabbix, con_puerto, operativo_noc, puertos_disp, puertos_act = row
                
                # Formatear datos
                abrev = abrev[:8].ljust(8)
                hilos_str = f"{total_hilos}".rjust(5)
                zabbix_str = f"{en_zabbix}".rjust(6)
                puerto_str = f"{con_puerto}".rjust(6)
                opnoc_str = f"{operativo_noc}".rjust(5)
                pdisp_str = f"{puertos_disp}".rjust(8)
                pact_str = f"{puertos_act}".rjust(7)
                
                self.stdout.write(f"  {abrev}|{hilos_str}|{zabbix_str}|{puerto_str}|{opnoc_str}|{pdisp_str}|{pact_str}")

    def _tail_celery_logs(self):
        """Mostrar logs de Celery en tiempo real"""
        log_files = [
            'logs/odf_sync.log',
            'logs/celery.log',
            'logs/beat.log'
        ]
        
        existing_logs = [f for f in log_files if os.path.exists(f)]
        
        if not existing_logs:
            self.stdout.write("❌ No se encontraron archivos de log")
            self.stdout.write("💡 Logs esperados: logs/odf_sync.log, logs/celery.log, logs/beat.log")
            return
            
        self.stdout.write(f"📝 Siguiendo logs: {', '.join(existing_logs)}")
        self.stdout.write("Presiona Ctrl+C para salir\n")
        
        # Usar tail -f para seguir logs
        log_cmd = f"tail -f {' '.join(existing_logs)}"
        os.system(log_cmd)
