"""
Comando para simular el flujo completo de ejecución sin realizar consultas SNMP reales.

Muestra:
- Loop del coordinador cada 5 segundos
- Detección de tareas listas
- Creación de ejecuciones (simuladas)
- Cambios de estado (PENDING → RUNNING → SUCCESS/FAILED)
- Mensajes del coordinador
- Colores según estado
- Historial de eventos
"""
import time
import json
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from hosts.models import OLT
from snmp_jobs.models import SnmpJobHost
from executions.models import Execution
# ✅ DESHABILITADO: ExecutionCoordinator y DynamicScheduler ya no se usan
# from execution_coordinator.coordinator import ExecutionCoordinator
# from execution_coordinator.dynamic_scheduler import DynamicScheduler
from execution_utils.logger import coordinator_logger  # Se mantiene porque se usa en callbacks
from execution_coordinator.models import CoordinatorLog, CoordinatorEvent


class Command(BaseCommand):
    help = 'Simula el flujo completo de ejecución sin realizar consultas SNMP reales'

    def add_arguments(self, parser):
        parser.add_argument(
            '--olt-id',
            type=int,
            help='ID de la OLT a simular (opcional, si no se especifica usa la primera activa)'
        )
        parser.add_argument(
            '--iteraciones',
            type=int,
            default=10,
            help='Número de iteraciones del loop (default: 10)'
        )
        parser.add_argument(
            '--intervalo',
            type=int,
            default=5,
            help='Intervalo entre iteraciones en segundos (default: 5)'
        )
        parser.add_argument(
            '--crear-ejecuciones',
            action='store_true',
            help='Crear ejecuciones reales en BD (solo simula, no ejecuta SNMP)'
        )

    def _get_color(self, status):
        """Retorna código de color ANSI según estado"""
        colors = {
            'PENDING': '\033[94m',      # Azul
            'RUNNING': '\033[93m',      # Amarillo
            'SUCCESS': '\033[92m',      # Verde
            'FAILED': '\033[91m',       # Rojo
            'INTERRUPTED': '\033[91m',  # Rojo
            'INFO': '\033[96m',         # Cyan
            'WARNING': '\033[93m',      # Amarillo
            'ERROR': '\033[91m',        # Rojo
        }
        return colors.get(status, '\033[0m')

    def _reset_color(self):
        """Resetea color ANSI"""
        return '\033[0m'

    def _print_status(self, message, status='INFO', indent=0):
        """Imprime mensaje con color según estado"""
        color = self._get_color(status)
        reset = self._reset_color()
        indent_str = '  ' * indent
        timestamp = timezone.now().strftime('%H:%M:%S')
        self.stdout.write(f"{color}{timestamp} [{status:10}] {indent_str}{message}{reset}")

    def _print_header(self, title):
        """Imprime encabezado"""
        self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
        self.stdout.write(self.style.SUCCESS(f"  {title}"))
        self.stdout.write(self.style.SUCCESS(f"{'='*80}\n"))

    def _print_separator(self):
        """Imprime separador"""
        self.stdout.write(self.style.WARNING(f"{'-'*80}"))

    def handle(self, *args, **options):
        olt_id = options.get('olt_id')
        iteraciones = options.get('iteraciones', 10)
        intervalo = options.get('intervalo', 5)
        crear_ejecuciones = options.get('crear_ejecuciones', False)

        self._print_header("🚀 SIMULADOR DE EJECUCIÓN - COORDINADOR")

        # Obtener OLT
        if olt_id:
            try:
                olt = OLT.objects.get(id=olt_id, habilitar_olt=True)
            except OLT.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ OLT {olt_id} no existe o no está habilitada"))
                return
        else:
            olt = OLT.objects.filter(habilitar_olt=True).first()
            if not olt:
                self.stdout.write(self.style.ERROR("❌ No hay OLTs habilitadas"))
                return

        olt_id = olt.id
        self._print_status(f"📡 OLT seleccionada: {olt.abreviatura} ({olt.ip_address})", 'INFO')
        self._print_status(f"🔄 Iteraciones: {iteraciones}", 'INFO')
        self._print_status(f"⏱️  Intervalo: {intervalo}s", 'INFO')
        self._print_status(f"💾 Crear ejecuciones: {'SÍ' if crear_ejecuciones else 'NO (solo simulación)'}", 'INFO')
        self._print_separator()

        # Inicializar coordinador y scheduler
        # ✅ DESHABILITADO: ExecutionCoordinator y DynamicScheduler ya no se usan
        # coordinator = ExecutionCoordinator(olt_id)
        # scheduler = DynamicScheduler(olt_id)
        self.stdout.write(self.style.WARNING(
            "⚠️ Este comando está deshabilitado. El sistema de pollers Zabbix reemplaza "
            "completamente el coordinador antiguo. Usa el sistema de pollers Zabbix en su lugar."
        ))
        return

        # Historial de eventos
        historial = []

        # Loop de simulación
        for iteracion in range(1, iteraciones + 1):
            self._print_header(f"ITERACIÓN {iteracion}/{iteraciones}")

            # 1. Leer estado actual
            self._print_status("📊 Leyendo estado del sistema...", 'INFO')
            current_state = coordinator.get_system_state()
            
            if not current_state:
                self._print_status("⚠️ No se pudo leer el estado del sistema", 'WARNING')
                time.sleep(intervalo)
                continue

            # Mostrar estado de la OLT
            olt_state = current_state.get('olt', {})
            self._print_status(f"OLT: {olt_state.get('abreviatura', 'N/A')} - Habilitada: {olt_state.get('enabled', False)}", 'INFO', 1)

            # Mostrar tareas
            tasks_state = current_state.get('tasks', [])
            self._print_status(f"Tareas habilitadas: {len(tasks_state)}", 'INFO', 1)
            for task in tasks_state[:5]:  # Mostrar solo las primeras 5
                next_run = task.get('next_run_at', 'N/A')
                if next_run:
                    try:
                        next_run_dt = timezone.datetime.fromisoformat(next_run.replace('Z', '+00:00'))
                        now = timezone.now()
                        if next_run_dt <= now:
                            status_color = 'WARNING'
                            status_text = 'LISTA'
                        else:
                            status_color = 'INFO'
                            status_text = 'PROGRAMADA'
                    except:
                        status_color = 'INFO'
                        status_text = next_run
                else:
                    status_color = 'WARNING'
                    status_text = 'SIN PROGRAMAR'
                
                self._print_status(
                    f"  • {task.get('job_name', 'N/A')} ({task.get('job_type', 'N/A')}) - {status_text}",
                    status_color,
                    2
                )

            # 2. Obtener estado anterior
            previous_state = coordinator.get_previous_state()
            
            # 3. Calcular hashes para detección de cambios
            current_hash = coordinator.calculate_state_hash(current_state)
            previous_hash = coordinator.calculate_state_hash(previous_state) if previous_state else None
            
            if current_hash != previous_hash:
                self._print_status("🔄 Cambio detectado en el estado del sistema", 'WARNING', 1)
                historial.append({
                    'iteracion': iteracion,
                    'timestamp': timezone.now(),
                    'evento': 'STATE_CHANGE',
                    'mensaje': 'Cambio detectado en el estado del sistema'
                })
            else:
                self._print_status("✓ Sin cambios en el estado", 'INFO', 1)

            # 4. Procesar tareas listas
            self._print_status("🔍 Buscando tareas listas para ejecutar...", 'INFO')
            ready_tasks = scheduler.get_ready_tasks()
            
            if ready_tasks:
                self._print_status(f"✅ Encontradas {len(ready_tasks)} tarea(s) lista(s)", 'SUCCESS', 1)
                
                for task in ready_tasks:
                    job_name = task.get('job_name', 'N/A')
                    job_type = task.get('job_type', 'N/A')
                    priority = task.get('priority', 0)
                    
                    self._print_status(
                        f"  • {job_name} ({job_type}) - Prioridad: {priority}",
                        'INFO',
                        2
                    )
                    
                    # Simular ejecución
                    if crear_ejecuciones:
                        # Crear ejecución real (pero no ejecutar SNMP)
                        try:
                            with transaction.atomic():
                                from snmp_jobs.models import SnmpJob, SnmpJobHost
                                
                                job = SnmpJob.objects.get(id=task['job_id'])
                                job_host = SnmpJobHost.objects.get(id=task['job_host_id'])
                                
                                # Verificar si OLT está ocupada
                                from redis import Redis
                                from django.conf import settings
                                redis_client = Redis.from_url(settings.CELERY_BROKER_URL)
                                olt_lock_key = f"lock:execution:olt:{olt_id}"
                                olt_is_busy = redis_client.exists(olt_lock_key)
                                
                                if olt_is_busy:
                                    self._print_status(
                                        f"⏸️  OLT ocupada, encolando {job_name}",
                                        'WARNING',
                                        3
                                    )
                                    historial.append({
                                        'iteracion': iteracion,
                                        'timestamp': timezone.now(),
                                        'evento': 'TASK_ENQUEUED',
                                        'mensaje': f'{job_name} encolada (OLT ocupada)',
                                        'job_name': job_name,
                                        'job_type': job_type
                                    })
                                    continue
                                
                                # Crear ejecución
                                execution = Execution.objects.create(
                                    snmp_job=job,
                                    job_host=job_host,
                                    olt_id=olt_id,
                                    status='PENDING',
                                    attempt=0
                                )
                                
                                self._print_status(
                                    f"📝 Ejecución creada: ID {execution.id} - {job_name}",
                                    'PENDING',
                                    3
                                )
                                
                                historial.append({
                                    'iteracion': iteracion,
                                    'timestamp': timezone.now(),
                                    'evento': 'EXECUTION_CREATED',
                                    'mensaje': f'Ejecución {execution.id} creada para {job_name}',
                                    'execution_id': execution.id,
                                    'job_name': job_name,
                                    'job_type': job_type,
                                    'status': 'PENDING'
                                })
                                
                                # Simular cambio a RUNNING después de 1 segundo
                                time.sleep(1)
                                execution.status = 'RUNNING'
                                execution.started_at = timezone.now()
                                execution.save()
                                
                                self._print_status(
                                    f"▶️  Ejecución {execution.id} iniciada - {job_name}",
                                    'RUNNING',
                                    3
                                )
                                
                                historial.append({
                                    'iteracion': iteracion,
                                    'timestamp': timezone.now(),
                                    'evento': 'EXECUTION_STARTED',
                                    'mensaje': f'Ejecución {execution.id} iniciada',
                                    'execution_id': execution.id,
                                    'job_name': job_name,
                                    'status': 'RUNNING'
                                })
                                
                                # Simular finalización (SUCCESS o FAILED aleatorio para demo)
                                import random
                                time.sleep(2)  # Simular tiempo de ejecución
                                
                                if random.random() > 0.2:  # 80% éxito
                                    execution.status = 'SUCCESS'
                                    execution.finished_at = timezone.now()
                                    if execution.started_at:
                                        duration = (execution.finished_at - execution.started_at).total_seconds()
                                        execution.duration_ms = int(duration * 1000)
                                    execution.save()
                                    
                                    self._print_status(
                                        f"✅ Ejecución {execution.id} completada exitosamente - {job_name}",
                                        'SUCCESS',
                                        3
                                    )
                                    
                                    historial.append({
                                        'iteracion': iteracion,
                                        'timestamp': timezone.now(),
                                        'evento': 'EXECUTION_SUCCESS',
                                        'mensaje': f'Ejecución {execution.id} completada exitosamente',
                                        'execution_id': execution.id,
                                        'job_name': job_name,
                                        'status': 'SUCCESS'
                                    })
                                else:
                                    execution.status = 'FAILED'
                                    execution.error_message = 'Simulación: Error simulado'
                                    execution.finished_at = timezone.now()
                                    if execution.started_at:
                                        duration = (execution.finished_at - execution.started_at).total_seconds()
                                        execution.duration_ms = int(duration * 1000)
                                    execution.save()
                                    
                                    self._print_status(
                                        f"❌ Ejecución {execution.id} falló - {job_name}",
                                        'FAILED',
                                        3
                                    )
                                    
                                    historial.append({
                                        'iteracion': iteracion,
                                        'timestamp': timezone.now(),
                                        'evento': 'EXECUTION_FAILED',
                                        'mensaje': f'Ejecución {execution.id} falló',
                                        'execution_id': execution.id,
                                        'job_name': job_name,
                                        'status': 'FAILED'
                                    })
                        except Exception as e:
                            self._print_status(
                                f"❌ Error creando ejecución: {str(e)}",
                                'ERROR',
                                3
                            )
                    else:
                        # Solo simular sin crear en BD
                        self._print_status(
                            f"📝 [SIMULADO] Ejecución para {job_name}",
                            'PENDING',
                            3
                        )
                        
                        historial.append({
                            'iteracion': iteracion,
                            'timestamp': timezone.now(),
                            'evento': 'EXECUTION_SIMULATED',
                            'mensaje': f'Ejecución simulada para {job_name}',
                            'job_name': job_name,
                            'job_type': job_type
                        })
            else:
                self._print_status("ℹ️  No hay tareas listas para ejecutar", 'INFO', 1)

            # 5. Mostrar ejecuciones activas
            active_executions = Execution.objects.filter(
                olt_id=olt_id,
                status__in=['PENDING', 'RUNNING']
            ).select_related('snmp_job')[:5]
            
            if active_executions:
                self._print_status(f"🔄 Ejecuciones activas: {active_executions.count()}", 'INFO')
                for exec in active_executions:
                    status = exec.status
                    self._print_status(
                        f"  • Ejecución {exec.id}: {exec.snmp_job.nombre} - {status}",
                        status,
                        2
                    )

            # 6. Mostrar últimos logs del coordinador
            recent_logs = CoordinatorLog.objects.filter(
                olt_id=olt_id
            ).order_by('-timestamp')[:5]
            
            if recent_logs:
                self._print_status("📋 Últimos logs del coordinador:", 'INFO')
                for log in recent_logs:
                    self._print_status(
                        f"  • [{log.level}] {log.message}",
                        log.level,
                        2
                    )

            # Guardar estado actual como anterior
            coordinator.save_state(current_state)

            # Esperar antes de la siguiente iteración
            if iteracion < iteraciones:
                self._print_status(f"⏳ Esperando {intervalo}s antes de la siguiente iteración...", 'INFO')
                time.sleep(intervalo)

        # Mostrar resumen del historial
        self._print_header("📊 RESUMEN DEL HISTORIAL")
        
        eventos_por_tipo = {}
        for evento in historial:
            tipo = evento.get('evento', 'UNKNOWN')
            eventos_por_tipo[tipo] = eventos_por_tipo.get(tipo, 0) + 1
        
        self._print_status("Eventos por tipo:", 'INFO')
        for tipo, count in sorted(eventos_por_tipo.items()):
            self._print_status(f"  • {tipo}: {count}", 'INFO', 1)
        
        self._print_separator()
        self._print_status("Últimos 10 eventos:", 'INFO')
        for evento in historial[-10:]:
            timestamp = evento['timestamp'].strftime('%H:%M:%S')
            self._print_status(
                f"  [{timestamp}] {evento.get('evento', 'UNKNOWN')}: {evento.get('mensaje', '')}",
                evento.get('status', 'INFO'),
                1
            )
        
        self._print_separator()
        self.stdout.write(self.style.SUCCESS("\n✅ Simulación completada\n"))

