"""
Comando para monitorear los logs de ODF en tiempo real.
"""

from django.core.management.base import BaseCommand
import subprocess
import time
from datetime import datetime


class Command(BaseCommand):
    help = 'Monitorea los logs de ODF en tiempo real'

    def add_arguments(self, parser):
        parser.add_argument(
            '--duration',
            type=int,
            default=60,
            help='Duración del monitoreo en segundos (default: 60)'
        )

    def handle(self, *args, **options):
        duration = options['duration']
        
        self.stdout.write(f"📊 MONITOREANDO LOGS DE ODF POR {duration} SEGUNDOS...")
        self.stdout.write(f"⏰ Inicio: {datetime.now()}")
        self.stdout.write("=" * 70)
        
        # Monitorear logs en tiempo real
        try:
            # Usar tail -f para seguir los logs en tiempo real
            cmd = [
                'timeout', str(duration),
                'tail', '-f',
                'logs/celery-discovery_main.log',
                'logs/celery-odf_sync.log'
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Filtrar solo líneas relevantes de ODF
            for line in iter(process.stdout.readline, ''):
                if any(keyword in line for keyword in [
                    'sync_scheduled_olts',
                    'sync_single_olt_ports',
                    'odf_management',
                    'OLT',
                    'Zabbix',
                    'ERROR',
                    'SUCCESS'
                ]):
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    self.stdout.write(f"[{timestamp}] {line.strip()}")
            
            process.wait()
            
        except KeyboardInterrupt:
            self.stdout.write("\n⏹️ Monitoreo interrumpido por el usuario")
        except Exception as e:
            self.stdout.write(f"\n❌ Error en monitoreo: {e}")
        
        self.stdout.write("=" * 70)
        self.stdout.write(f"⏰ Fin: {datetime.now()}")
        self.stdout.write("✅ Monitoreo completado")
