"""
Comando para verificar que el modo prueba está funcionando correctamente.
Crea ejecuciones y verifica que se simulen sin hacer consultas SNMP reales.
"""
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from hosts.models import OLT
from snmp_jobs.models import SnmpJob, SnmpJobHost
from executions.models import Execution
from configuracion_avanzada.models import ConfiguracionSistema
from snmp_jobs.tasks import execute_discovery
from snmp_get.tasks import execute_get_main


class Command(BaseCommand):
    help = 'Verifica que el modo prueba funcione correctamente simulando ejecuciones'

    def add_arguments(self, parser):
        parser.add_argument(
            '--num-ejecuciones',
            type=int,
            default=3,
            help='Número de ejecuciones a probar (default: 3)'
        )

    def _print_status(self, message, style='SUCCESS'):
        """Imprime mensaje con estilo"""
        if style == 'SUCCESS':
            self.stdout.write(self.style.SUCCESS(message))
        elif style == 'WARNING':
            self.stdout.write(self.style.WARNING(message))
        elif style == 'ERROR':
            self.stdout.write(self.style.ERROR(message))
        else:
            self.stdout.write(message)

    def handle(self, *args, **options):
        num_ejecuciones = options.get('num_ejecuciones', 3)

        self.stdout.write(self.style.SUCCESS("\n" + "="*80))
        self.stdout.write(self.style.SUCCESS("  🧪 VERIFICACIÓN DEL MODO PRUEBA"))
        self.stdout.write(self.style.SUCCESS("="*80 + "\n"))

        # 1. Verificar estado del modo prueba
        is_modo_prueba = ConfiguracionSistema.is_modo_prueba()
        self._print_status(f"📊 Estado del Modo Prueba: {'🧪 ACTIVO' if is_modo_prueba else '✅ INACTIVO'}", 
                          'SUCCESS' if is_modo_prueba else 'WARNING')
        
        if not is_modo_prueba:
            self._print_status("⚠️ El modo prueba NO está activo. Las ejecuciones serán REALES.", 'WARNING')
            respuesta = input("¿Deseas continuar de todas formas? (s/N): ")
            if respuesta.lower() != 's':
                return

        # 2. Obtener OLT y tareas
        olt = OLT.objects.filter(habilitar_olt=True).first()
        if not olt:
            self._print_status("❌ No hay OLTs habilitadas", 'ERROR')
            return

        jobs = SnmpJob.objects.filter(enabled=True, nombre__startswith='[PRUEBA]')[:num_ejecuciones]
        if not jobs.exists():
            self._print_status("❌ No hay tareas de prueba habilitadas", 'ERROR')
            return

        self._print_status(f"📡 OLT seleccionada: {olt.abreviatura} ({olt.ip_address})")
        self._print_status(f"📋 Tareas a probar: {jobs.count()}")

        # 3. Crear y ejecutar ejecuciones
        ejecuciones_procesadas = []

        for idx, job in enumerate(jobs, 1):
            self.stdout.write(self.style.SUCCESS(f"\n{'='*80}"))
            self.stdout.write(self.style.SUCCESS(f"  PRUEBA {idx}/{jobs.count()}: {job.nombre}"))
            self.stdout.write(self.style.SUCCESS(f"{'='*80}\n"))

            try:
                # Obtener o crear job_host
                job_host, created = SnmpJobHost.objects.get_or_create(
                    snmp_job=job,
                    olt=olt,
                    defaults={'enabled': True, 'consecutive_failures': 0}
                )

                # Crear ejecución
                execution = Execution.objects.create(
                    snmp_job=job,
                    job_host=job_host,
                    olt=olt,
                    status='PENDING',
                    attempt=0
                )

                self._print_status(f"✅ Ejecución creada: ID {execution.id}")
                self._print_status(f"   Estado inicial: {execution.status}")
                self._print_status(f"   Tipo: {job.job_type}")

                # Verificar detección de modo prueba
                is_test_job = job.nombre.startswith('[PRUEBA]')
                self._print_status(f"   Es tarea [PRUEBA]: {is_test_job}")
                self._print_status(f"   Modo prueba global: {is_modo_prueba}")
                self._print_status(f"   Se simulará: {is_modo_prueba or is_test_job}")

                # Ejecutar según tipo
                inicio = timezone.now()
                self._print_status("   ⏳ Ejecutando...")

                if job.job_type == 'descubrimiento':
                    execute_discovery(job.id, olt.id, execution.id, queue_name='discovery_main')
                elif job.job_type == 'get':
                    execute_get_main(job.id, olt.id, execution.id, queue_name='get_main')
                else:
                    self._print_status(f"   ⚠️ Tipo {job.job_type} no soportado en esta prueba", 'WARNING')
                    continue

                # Refrescar ejecución
                execution.refresh_from_db()
                fin = timezone.now()
                duracion = (fin - inicio).total_seconds()

                # Verificar resultado
                self._print_status(f"   ✅ Ejecución completada en {duracion:.2f}s")
                self._print_status(f"   Estado final: {execution.status}")
                
                if execution.result_summary:
                    simulated = execution.result_summary.get('simulated', False)
                    if simulated:
                        self._print_status(f"   🧪 SIMULADA: {execution.result_summary}", 'SUCCESS')
                    else:
                        self._print_status(f"   ⚠️ NO SIMULADA: {execution.result_summary}", 'WARNING')
                else:
                    self._print_status(f"   ⚠️ Sin result_summary", 'WARNING')

                if execution.error_message:
                    self._print_status(f"   Mensaje: {execution.error_message}")

                ejecuciones_procesadas.append({
                    'execution_id': execution.id,
                    'job_name': job.nombre,
                    'status': execution.status,
                    'simulated': execution.result_summary.get('simulated', False) if execution.result_summary else False,
                    'duration': duracion
                })

            except Exception as e:
                self._print_status(f"   ❌ Error: {str(e)}", 'ERROR')
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))

        # 4. Resumen
        self.stdout.write(self.style.SUCCESS("\n" + "="*80))
        self.stdout.write(self.style.SUCCESS("  📊 RESUMEN DE PRUEBAS"))
        self.stdout.write(self.style.SUCCESS("="*80 + "\n"))

        simuladas = sum(1 for e in ejecuciones_procesadas if e['simulated'])
        no_simuladas = len(ejecuciones_procesadas) - simuladas

        self._print_status(f"Total ejecuciones: {len(ejecuciones_procesadas)}")
        self._print_status(f"Simuladas correctamente: {simuladas}", 'SUCCESS' if simuladas == len(ejecuciones_procesadas) else 'WARNING')
        if no_simuladas > 0:
            self._print_status(f"NO simuladas: {no_simuladas}", 'ERROR')

        self.stdout.write("\n")
        for ejec in ejecuciones_procesadas:
            status_color = 'SUCCESS' if ejec['simulated'] else 'ERROR'
            self._print_status(
                f"  • Ejecución {ejec['execution_id']}: {ejec['job_name']} - "
                f"{ejec['status']} ({ejec['duration']:.2f}s) - "
                f"{'🧪 SIMULADA' if ejec['simulated'] else '⚠️ NO SIMULADA'}",
                status_color
            )

        if simuladas == len(ejecuciones_procesadas):
            self.stdout.write(self.style.SUCCESS("\n✅ Todas las ejecuciones se simularon correctamente\n"))
        else:
            self.stdout.write(self.style.ERROR("\n❌ Algunas ejecuciones NO se simularon. Revisa la configuración.\n"))

