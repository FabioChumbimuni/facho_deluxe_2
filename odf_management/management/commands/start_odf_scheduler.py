"""
Comando para iniciar el programador automático de recolección ODF.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
import subprocess
import sys
import os


class Command(BaseCommand):
    help = 'Inicia el sistema de programación automática de recolección ODF con Celery'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['worker', 'beat', 'both', 'status'],
            default='both',
            help='Modo de ejecución: worker (solo worker), beat (solo scheduler), both (ambos), status (verificar estado)'
        )
        parser.add_argument(
            '--detach',
            action='store_true',
            help='Ejecutar en segundo plano (detached)'
        )

    def handle(self, *args, **options):
        mode = options['mode']
        detach = options['detach']
        
        self.stdout.write(
            self.style.SUCCESS(f"🚀 Iniciando sistema de programación ODF (modo: {mode})")
        )
        
        if mode == 'status':
            self.check_status()
        elif mode == 'worker':
            self.start_worker(detach)
        elif mode == 'beat':
            self.start_beat(detach)
        elif mode == 'both':
            self.start_both(detach)

    def check_status(self):
        """Verifica el estado de los servicios Celery"""
        self.stdout.write("📊 Verificando estado de servicios...")
        
        try:
            # Verificar worker
            result = subprocess.run(['celery', '-A', 'core', 'inspect', 'active'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS("✅ Celery Worker: ACTIVO"))
            else:
                self.stdout.write(self.style.ERROR("❌ Celery Worker: INACTIVO"))
                
        except subprocess.TimeoutExpired:
            self.stdout.write(self.style.WARNING("⏰ Celery Worker: TIMEOUT (posiblemente inactivo)"))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("❌ Celery no encontrado. Instalar con: pip install celery[redis]"))
            
        try:
            # Verificar programaciones activas
            from odf_management.models import ZabbixCollectionSchedule
            active_schedules = ZabbixCollectionSchedule.objects.filter(habilitado=True).count()
            total_schedules = ZabbixCollectionSchedule.objects.count()
            
            self.stdout.write(f"📅 Programaciones: {active_schedules} activas de {total_schedules} totales")
            
            # Verificar próximas ejecuciones
            next_schedules = ZabbixCollectionSchedule.objects.filter(
                habilitado=True,
                proxima_ejecucion__isnull=False
            ).order_by('proxima_ejecucion')[:3]
            
            if next_schedules:
                self.stdout.write("⏰ Próximas ejecuciones:")
                for schedule in next_schedules:
                    self.stdout.write(f"  • {schedule.nombre}: {schedule.proxima_ejecucion}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error verificando programaciones: {e}"))

    def start_worker(self, detach=False):
        """Inicia el worker de Celery"""
        self.stdout.write("🔧 Iniciando Celery Worker...")
        
        cmd = [
            'celery', '-A', 'core', 'worker',
            '--loglevel=info',
            '--concurrency=4',
            '--queues=odf_sync,discovery_main,cleanup'
        ]
        
        if detach:
            cmd.extend(['--detach', '--pidfile=celery_worker.pid', '--logfile=celery_worker.log'])
            
        try:
            if detach:
                subprocess.Popen(cmd)
                self.stdout.write(self.style.SUCCESS("✅ Celery Worker iniciado en segundo plano"))
                self.stdout.write("📄 Logs: celery_worker.log")
                self.stdout.write("🆔 PID file: celery_worker.pid")
            else:
                self.stdout.write("🔄 Iniciando worker (Ctrl+C para detener)...")
                subprocess.run(cmd)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n⏹️ Worker detenido por el usuario"))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("❌ Celery no encontrado. Instalar con: pip install celery[redis]"))

    def start_beat(self, detach=False):
        """Inicia el scheduler de Celery Beat"""
        self.stdout.write("📅 Iniciando Celery Beat (Scheduler)...")
        
        cmd = [
            'celery', '-A', 'core', 'beat',
            '--loglevel=info',
            '--scheduler=django_celery_beat.schedulers:DatabaseScheduler'
        ]
        
        if detach:
            cmd.extend(['--detach', '--pidfile=celery_beat.pid', '--logfile=celery_beat.log'])
            
        try:
            if detach:
                subprocess.Popen(cmd)
                self.stdout.write(self.style.SUCCESS("✅ Celery Beat iniciado en segundo plano"))
                self.stdout.write("📄 Logs: celery_beat.log")
                self.stdout.write("🆔 PID file: celery_beat.pid")
            else:
                self.stdout.write("🔄 Iniciando scheduler (Ctrl+C para detener)...")
                subprocess.run(cmd)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n⏹️ Scheduler detenido por el usuario"))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("❌ Celery no encontrado. Instalar con: pip install celery[redis]"))

    def start_both(self, detach=False):
        """Inicia worker y beat juntos"""
        if detach:
            self.stdout.write("🚀 Iniciando Worker y Beat en segundo plano...")
            self.start_worker(detach=True)
            self.start_beat(detach=True)
            
            self.stdout.write(self.style.SUCCESS("\n✅ Sistema de programación ODF iniciado completamente!"))
            self.stdout.write("📊 Verificar estado con: python manage.py start_odf_scheduler --mode status")
            self.stdout.write("⏹️ Detener con: pkill -f celery")
            
        else:
            self.stdout.write(self.style.WARNING("⚠️ Modo interactivo no soportado para 'both'"))
            self.stdout.write("💡 Usar --detach para ejecutar en segundo plano")
            self.stdout.write("💡 O ejecutar worker y beat en terminales separadas:")
            self.stdout.write("   Terminal 1: python manage.py start_odf_scheduler --mode worker")
            self.stdout.write("   Terminal 2: python manage.py start_odf_scheduler --mode beat")
