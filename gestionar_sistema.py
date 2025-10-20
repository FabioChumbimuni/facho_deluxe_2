#!/usr/bin/env python
"""
Sistema de Gestión Completa - Facho Deluxe v2
Script único para gestionar workers, colas, tareas y estado del sistema
"""
import os
import sys
import django
import subprocess
import time
import json
from datetime import datetime

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from executions.models import Execution
from snmp_jobs.models import SnmpJob, SnmpJobHost
from hosts.models import OLT

class GestorSistema:
    """Gestor completo del sistema Facho Deluxe v2"""
    
    def __init__(self):
        self.workers = {
            'discovery_main': {'concurrency': 20, 'queue': 'discovery_main'},
            'discovery_retry': {'concurrency': 5, 'queue': 'discovery_retry'},  # Nueva cola para reintentos
            'discovery_manual': {'concurrency': 10, 'queue': 'discovery_manual'},  # Máxima prioridad
            'cleanup': {'concurrency': 2, 'queue': 'cleanup'},
            'background_deletes': {'concurrency': 3, 'queue': 'background_deletes'},
            'odf_sync': {'concurrency': 4, 'queue': 'odf_sync'}  # Nueva cola para ODF
        }
        self.log_dir = 'logs'
        self.pids_dir = 'pids'
        self.ensure_directories()
    
    def ensure_directories(self):
        """Asegura que existen los directorios necesarios"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        if not os.path.exists(self.pids_dir):
            os.makedirs(self.pids_dir)
    
    def print_header(self, title):
        """Imprime un encabezado formateado"""
        print("\n" + "=" * 70)
        print(f"🚀 {title}")
        print("=" * 70)
    
    def start_worker(self, worker_name):
        """Inicia un worker específico"""
        if worker_name not in self.workers:
            print(f"❌ Worker '{worker_name}' no existe")
            return False
        
        config = self.workers[worker_name]
        
        try:
            cmd = [
                'celery', '-A', 'core', 'worker',
                '--loglevel=info',
                f'--concurrency={config["concurrency"]}',
                f'--queues={config["queue"]}',
                f'--hostname=celery@{config["queue"]}',
                '--detach',
                f'--pidfile={self.pids_dir}/celery-{config["queue"]}.pid',
                f'--logfile={self.log_dir}/celery-{config["queue"]}.log'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✅ Worker {worker_name} iniciado exitosamente")
                return True
            else:
                print(f"❌ Error iniciando worker {worker_name}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error iniciando worker {worker_name}: {e}")
            return False
    
    def stop_worker(self, worker_name):
        """Detiene un worker específico"""
        if worker_name not in self.workers:
            print(f"❌ Worker '{worker_name}' no existe")
            return False
        
        config = self.workers[worker_name]
        
        try:
            pid_file = f"{self.pids_dir}/celery-{config['queue']}.pid"
            
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                os.kill(pid, 15)  # SIGTERM
                time.sleep(2)
                
                # Verificar si el proceso aún existe
                try:
                    os.kill(pid, 0)
                    # Si llegamos aquí, el proceso aún existe, usar SIGKILL
                    os.kill(pid, 9)
                    time.sleep(1)
                except OSError:
                    # El proceso ya no existe
                    pass
                
                # Eliminar archivo PID
                if os.path.exists(pid_file):
                    os.remove(pid_file)
                
                print(f"✅ Worker {worker_name} detenido exitosamente")
                return True
            else:
                print(f"⚠️ Worker {worker_name} no está ejecutándose (no hay archivo PID)")
                return True
                
        except Exception as e:
            print(f"❌ Error deteniendo worker {worker_name}: {e}")
            return False
    
    def start_beat(self):
        """Inicia Celery Beat"""
        try:
            cmd = [
                'celery', '-A', 'core', 'beat',
                '--loglevel=info',
                '--detach',
                f'--pidfile={self.pids_dir}/celerybeat.pid',
                f'--logfile={self.log_dir}/celerybeat.log'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Celery Beat iniciado exitosamente")
                return True
            else:
                print(f"❌ Error iniciando Celery Beat: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error iniciando Celery Beat: {e}")
            return False
    
    def stop_beat(self):
        """Detiene Celery Beat"""
        try:
            pid_file = f"{self.pids_dir}/celerybeat.pid"
            
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                os.kill(pid, 15)  # SIGTERM
                time.sleep(2)
                
                # Verificar si el proceso aún existe
                try:
                    os.kill(pid, 0)
                    # Si llegamos aquí, el proceso aún existe, usar SIGKILL
                    os.kill(pid, 9)
                    time.sleep(1)
                except OSError:
                    # El proceso ya no existe
                    pass
                
                # Eliminar archivo PID
                if os.path.exists(pid_file):
                    os.remove(pid_file)
                
                print("✅ Celery Beat detenido exitosamente")
                return True
            else:
                print("⚠️ Celery Beat no está ejecutándose (no hay archivo PID)")
                return True
                
        except Exception as e:
            print(f"❌ Error deteniendo Celery Beat: {e}")
            return False
    
    def get_status(self):
        """Obtiene el estado actual del sistema"""
        self.print_header("ESTADO DEL SISTEMA")
        
        # Verificar workers
        print("\n📊 WORKERS:")
        for worker_name, config in self.workers.items():
            pid_file = f"{self.pids_dir}/celery-{config['queue']}.pid"
            
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    
                    # Verificar si el proceso está ejecutándose
                    try:
                        os.kill(pid, 0)
                        print(f"  ✅ {worker_name}: Ejecutándose (PID: {pid})")
                    except OSError:
                        print(f"  ❌ {worker_name}: PID file existe pero proceso no está ejecutándose")
                        # Limpiar archivo PID huérfano
                        os.remove(pid_file)
                except Exception as e:
                    print(f"  ❌ {worker_name}: Error leyendo PID file: {e}")
            else:
                print(f"  ⚪ {worker_name}: No ejecutándose")
        
        # Verificar Celery Beat
        print("\n⏰ CELERY BEAT:")
        beat_pid_file = f"{self.pids_dir}/celerybeat.pid"
        
        if os.path.exists(beat_pid_file):
            try:
                with open(beat_pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                try:
                    os.kill(pid, 0)
                    print(f"  ✅ Beat: Ejecutándose (PID: {pid})")
                except OSError:
                    print("  ❌ Beat: PID file existe pero proceso no está ejecutándose")
                    os.remove(beat_pid_file)
            except Exception as e:
                print(f"  ❌ Beat: Error leyendo PID file: {e}")
        else:
            print("  ⚪ Beat: No ejecutándose")
        
        # Estadísticas de la base de datos
        print("\n📈 ESTADÍSTICAS DE BASE DE DATOS:")
        try:
            total_jobs = SnmpJob.objects.count()
            enabled_jobs = SnmpJob.objects.filter(enabled=True).count()
            total_executions = Execution.objects.count()
            recent_executions = Execution.objects.filter(
                created_at__gte=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ).count()
            
            print(f"  📋 Total de jobs: {total_jobs}")
            print(f"  ✅ Jobs habilitados: {enabled_jobs}")
            print(f"  📊 Total de ejecuciones: {total_executions}")
            print(f"  📅 Ejecuciones hoy: {recent_executions}")
            
        except Exception as e:
            print(f"  ❌ Error obteniendo estadísticas: {e}")
    
    def start_all(self):
        """Inicia todos los workers y Beat"""
        self.print_header("INICIANDO WORKERS DE CELERY")
        
        success_count = 0
        total_count = len(self.workers) + 1  # +1 para Beat
        
        # Iniciar workers
        for worker_name in self.workers.keys():
            if self.start_worker(worker_name):
                success_count += 1
        
        # Iniciar Beat
        if self.start_beat():
            success_count += 1
        
        print(f"\n📊 RESUMEN: {success_count}/{total_count} servicios iniciados exitosamente")
    
    def stop_all(self):
        """Detiene todos los workers y Beat"""
        self.print_header("DETENIENDO WORKERS DE CELERY")
        
        success_count = 0
        total_count = len(self.workers) + 1  # +1 para Beat
        
        # Detener Beat primero
        if self.stop_beat():
            success_count += 1
        
        # Detener workers
        for worker_name in self.workers.keys():
            if self.stop_worker(worker_name):
                success_count += 1
        
        print(f"\n📊 RESUMEN: {success_count}/{total_count} servicios detenidos exitosamente")


def main():
    """Función principal"""
    if len(sys.argv) < 2:
        print("Uso: python gestionar_sistema.py <comando> [worker]")
        print("\nComandos disponibles:")
        print("  start [worker]  - Inicia worker específico o todos")
        print("  stop [worker]   - Detiene worker específico o todos")
        print("  status          - Muestra estado del sistema")
        print("  restart [worker]- Reinicia worker específico o todos")
        print("\nWorkers disponibles:")
        print("  discovery_main, discovery_retry, discovery_manual, cleanup, background_deletes, odf_sync, beat, all")
        return
    
    gestor = GestorSistema()
    comando = sys.argv[1].lower()
    
    if comando == 'status':
        gestor.get_status()
    
    elif comando == 'start':
        if len(sys.argv) > 2:
            worker = sys.argv[2].lower()
            if worker == 'all':
                gestor.start_all()
            elif worker == 'beat':
                gestor.start_beat()
            elif worker in gestor.workers:
                gestor.start_worker(worker)
            else:
                print(f"❌ Worker '{worker}' no existe")
        else:
            gestor.start_all()
    
    elif comando == 'stop':
        if len(sys.argv) > 2:
            worker = sys.argv[2].lower()
            if worker == 'all':
                gestor.stop_all()
            elif worker == 'beat':
                gestor.stop_beat()
            elif worker in gestor.workers:
                gestor.stop_worker(worker)
            else:
                print(f"❌ Worker '{worker}' no existe")
        else:
            gestor.stop_all()
    
    elif comando == 'restart':
        if len(sys.argv) > 2:
            worker = sys.argv[2].lower()
            if worker == 'all':
                gestor.stop_all()
                time.sleep(2)
                gestor.start_all()
            elif worker == 'beat':
                gestor.stop_beat()
                time.sleep(2)
                gestor.start_beat()
            elif worker in gestor.workers:
                gestor.stop_worker(worker)
                time.sleep(2)
                gestor.start_worker(worker)
            else:
                print(f"❌ Worker '{worker}' no existe")
        else:
            gestor.stop_all()
            time.sleep(2)
            gestor.start_all()
    
    else:
        print(f"❌ Comando '{comando}' no reconocido")


if __name__ == "__main__":
    main()
