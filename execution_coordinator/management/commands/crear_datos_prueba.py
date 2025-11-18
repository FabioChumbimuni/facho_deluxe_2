"""
Comando para crear datos de prueba: tareas SNMP, plantillas y ejecuciones simuladas.
"""
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from hosts.models import OLT
from snmp_jobs.models import (
    SnmpJob, SnmpJobHost, WorkflowTemplate, WorkflowTemplateNode,
    OLTWorkflow, WorkflowNode, TaskTemplate, TaskFunction
)
from executions.models import Execution
from oids.models import OID
from brands.models import Brand


class Command(BaseCommand):
    help = 'Crea tareas SNMP, plantillas y ejecuciones simuladas para pruebas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--olt-id',
            type=int,
            help='ID de la OLT (opcional, si no se especifica usa la primera activa)'
        )
        parser.add_argument(
            '--num-tareas',
            type=int,
            default=5,
            help='Número de tareas SNMP a crear (default: 5)'
        )
        parser.add_argument(
            '--num-plantillas',
            type=int,
            default=2,
            help='Número de plantillas a crear (default: 2)'
        )
        parser.add_argument(
            '--num-ejecuciones',
            type=int,
            default=10,
            help='Número de ejecuciones simuladas a crear (default: 10)'
        )
        parser.add_argument(
            '--limpiar',
            action='store_true',
            help='Eliminar datos de prueba existentes antes de crear nuevos'
        )

    def _print_status(self, message, style='SUCCESS'):
        """Imprime mensaje con estilo"""
        if style == 'SUCCESS':
            self.stdout.write(self.style.SUCCESS(message))
        elif style == 'WARNING':
            self.stdout.write(self.style.WARNING(message))
        else:
            self.stdout.write(message)

    def handle(self, *args, **options):
        olt_id = options.get('olt_id')
        num_tareas = options.get('num_tareas', 5)
        num_plantillas = options.get('num_plantillas', 2)
        num_ejecuciones = options.get('num_ejecuciones', 10)
        limpiar = options.get('limpiar', False)

        self.stdout.write(self.style.SUCCESS("\n" + "="*80))
        self.stdout.write(self.style.SUCCESS("  🚀 CREANDO DATOS DE PRUEBA"))
        self.stdout.write(self.style.SUCCESS("="*80 + "\n"))

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

        self._print_status(f"📡 OLT seleccionada: {olt.abreviatura} ({olt.ip_address})")

        # Limpiar datos anteriores si se solicita
        if limpiar:
            self._print_status("🧹 Limpiando datos de prueba anteriores...")
            with transaction.atomic():
                # Eliminar ejecuciones de prueba
                Execution.objects.filter(olt=olt, snmp_job__nombre__startswith='[PRUEBA]').delete()
                # Eliminar job hosts de prueba
                SnmpJobHost.objects.filter(olt=olt, snmp_job__nombre__startswith='[PRUEBA]').delete()
                # Eliminar jobs de prueba
                SnmpJob.objects.filter(nombre__startswith='[PRUEBA]').delete()
                # Eliminar workflows de prueba
                OLTWorkflow.objects.filter(olt=olt, name__startswith='[PRUEBA]').delete()
                # Eliminar plantillas de prueba
                WorkflowTemplate.objects.filter(name__startswith='[PRUEBA]').delete()
            self._print_status("✅ Datos anteriores eliminados")

        # Obtener datos necesarios
        brands = list(Brand.objects.all())
        if not brands:
            self.stdout.write(self.style.ERROR("❌ No hay marcas disponibles. Crea al menos una marca primero."))
            return

        oids = list(OID.objects.all())
        if not oids:
            self.stdout.write(self.style.ERROR("❌ No hay OIDs disponibles. Crea al menos un OID primero."))
            return

        self._print_status(f"📦 Marcas disponibles: {len(brands)}")
        self._print_status(f"📦 OIDs disponibles: {len(oids)}")

        # Crear tareas SNMP
        self.stdout.write(self.style.SUCCESS("\n" + "-"*80))
        self.stdout.write(self.style.SUCCESS("  📋 CREANDO TAREAS SNMP"))
        self.stdout.write(self.style.SUCCESS("-"*80 + "\n"))

        job_types = ['descubrimiento', 'get', 'walk']
        intervalos = ['30s', '1m', '5m', '10m', '15m', '30m', '1h']
        tareas_creadas = []

        with transaction.atomic():
            for i in range(num_tareas):
                oid = random.choice(oids)
                brand = random.choice(brands)
                job_type = random.choice(job_types)
                intervalo = random.choice(intervalos)

                nombre = f"[PRUEBA] {job_type.capitalize()} {oid.nombre} {intervalo}"
                
                # Verificar si ya existe
                if SnmpJob.objects.filter(nombre=nombre).exists():
                    continue

                job = SnmpJob.objects.create(
                    nombre=nombre,
                    descripcion=f"Tarea de prueba para {oid.nombre} - Tipo: {job_type} (SIMULADA - No ejecuta SNMP real)",
                    marca=brand,
                    job_type=job_type,
                    interval_raw=intervalo,
                    enabled=True,  # Habilitada para que el coordinador la detecte
                    max_retries=2,
                    retry_delay_seconds=30,
                    oid=oid,
                    run_options={
                        'timeout': random.choice([3, 5, 10]),
                        'retries': random.choice([1, 2]),
                        'version': '2',
                        'simulated': True  # Flag para identificar como simulación
                    }
                )

                # Crear SnmpJobHost para la OLT
                job_host = SnmpJobHost.objects.create(
                    snmp_job=job,
                    olt=olt,
                    enabled=True,
                    consecutive_failures=0
                )
                job_host.initialize_next_run(is_new=True)
                job_host.save()

                tareas_creadas.append(job)
                self._print_status(f"  ✅ Tarea creada: {nombre} (ID: {job.id})")

        self._print_status(f"\n✅ {len(tareas_creadas)} tarea(s) SNMP creada(s)")

        # Crear plantillas de workflow
        self.stdout.write(self.style.SUCCESS("\n" + "-"*80))
        self.stdout.write(self.style.SUCCESS("  📋 CREANDO PLANTILLAS DE WORKFLOW"))
        self.stdout.write(self.style.SUCCESS("-"*80 + "\n"))

        plantillas_creadas = []

        with transaction.atomic():
            for i in range(num_plantillas):
                nombre_plantilla = f"[PRUEBA] Plantilla Workflow {i+1}"
                
                # Verificar si ya existe
                if WorkflowTemplate.objects.filter(name=nombre_plantilla).exists():
                    continue

                template = WorkflowTemplate.objects.create(
                    name=nombre_plantilla,
                    description=f"Plantilla de prueba {i+1} con múltiples nodos",
                    is_active=True
                )

                # Crear nodos para la plantilla
                num_nodos = random.randint(2, 5)
                nodos_creados = []

                for j in range(num_nodos):
                    oid = random.choice(oids)
                    key = f"node_{i+1}_{j+1}"
                    nombre_nodo = f"Nodo {j+1} - {oid.nombre}"
                    intervalos_nodo = [60, 300, 600, 900, 1800, 3600]
                    intervalo_nodo = random.choice(intervalos_nodo)

                    node = WorkflowTemplateNode.objects.create(
                        template=template,
                        oid=oid,
                        key=key,
                        name=nombre_nodo,
                        interval_seconds=intervalo_nodo,
                        priority=random.choice([1, 2, 3, 4, 5]),
                        enabled=True,
                        position_x=random.randint(0, 1000),
                        position_y=random.randint(0, 1000)
                    )
                    nodos_creados.append(node)

                plantillas_creadas.append((template, nodos_creados))
                self._print_status(f"  ✅ Plantilla creada: {nombre_plantilla} con {len(nodos_creados)} nodos")

        self._print_status(f"\n✅ {len(plantillas_creadas)} plantilla(s) creada(s)")

        # Crear workflow para la OLT
        self.stdout.write(self.style.SUCCESS("\n" + "-"*80))
        self.stdout.write(self.style.SUCCESS("  📋 CREANDO WORKFLOW PARA OLT"))
        self.stdout.write(self.style.SUCCESS("-"*80 + "\n"))

        with transaction.atomic():
            # Verificar si ya existe workflow
            workflow, created = OLTWorkflow.objects.get_or_create(
                olt=olt,
                defaults={
                    'name': f"[PRUEBA] Workflow {olt.abreviatura}",
                    'description': f"Workflow de prueba para {olt.abreviatura}",
                    'is_active': True
                }
            )

            if created:
                self._print_status(f"  ✅ Workflow creado: {workflow.name}")
            else:
                workflow.name = f"[PRUEBA] Workflow {olt.abreviatura}"
                workflow.description = f"Workflow de prueba para {olt.abreviatura}"
                workflow.is_active = True
                workflow.save()
                self._print_status(f"  ✅ Workflow actualizado: {workflow.name}")

            # Obtener o crear TaskFunction por defecto
            task_function, _ = TaskFunction.objects.get_or_create(
                code='default-snmp-task',
                defaults={
                    'name': 'Tarea SNMP por Defecto',
                    'description': 'Función por defecto para tareas SNMP',
                    'module_path': 'snmp_jobs.tasks',
                    'callable_name': 'execute_discovery',
                    'function_type': 'get',
                    'is_active': True
                }
            )

            # Crear nodos del workflow basados en las tareas
            for job in tareas_creadas[:3]:  # Solo las primeras 3 tareas
                # Verificar si ya existe nodo para este job
                if WorkflowNode.objects.filter(workflow=workflow, key=f"job_{job.id}").exists():
                    continue

                # Obtener TaskTemplate o crear uno por defecto
                slug_template = f"template-{job.id}"
                task_template, _ = TaskTemplate.objects.get_or_create(
                    slug=slug_template,
                    defaults={
                        'name': f"Template para {job.nombre}",
                        'description': f"Template generado para {job.nombre}",
                        'function': task_function,
                        'is_active': True
                    }
                )

                node = WorkflowNode.objects.create(
                    workflow=workflow,
                    template=task_template,
                    key=f"job_{job.id}",
                    name=job.nombre,
                    oid=job.oid,
                    interval_seconds=job.interval_seconds or 300,
                    priority=3,
                    enabled=True,
                    position_x=random.randint(0, 1000),
                    position_y=random.randint(0, 1000)
                )
                self._print_status(f"  ✅ Nodo creado: {node.name}")

        # Crear ejecuciones simuladas
        self.stdout.write(self.style.SUCCESS("\n" + "-"*80))
        self.stdout.write(self.style.SUCCESS("  📋 CREANDO EJECUCIONES SIMULADAS"))
        self.stdout.write(self.style.SUCCESS("-"*80 + "\n"))

        ejecuciones_creadas = []
        estados = ['SUCCESS', 'FAILED', 'INTERRUPTED']
        ahora = timezone.now()

        with transaction.atomic():
            for i in range(num_ejecuciones):
                # Seleccionar tarea aleatoria
                job = random.choice(tareas_creadas) if tareas_creadas else None
                if not job:
                    break

                # Obtener o crear job_host
                job_host, _ = SnmpJobHost.objects.get_or_create(
                    snmp_job=job,
                    olt=olt,
                    defaults={'enabled': True, 'consecutive_failures': 0}
                )

                # Calcular tiempos simulados (últimas 2 horas)
                horas_atras = random.uniform(0, 2)
                started_at = ahora - timedelta(hours=horas_atras)
                duracion_ms = random.randint(500, 5000)
                finished_at = started_at + timedelta(milliseconds=duracion_ms)

                # Estado aleatorio (80% éxito, 15% fallo, 5% interrumpido)
                rand = random.random()
                if rand < 0.80:
                    status = 'SUCCESS'
                    error_message = None
                elif rand < 0.95:
                    status = 'FAILED'
                    error_message = f"Error simulado: Timeout en consulta SNMP"
                else:
                    status = 'INTERRUPTED'
                    error_message = f"Ejecución interrumpida: OLT desconectada"

                execution = Execution.objects.create(
                    snmp_job=job,
                    job_host=job_host,
                    olt=olt,
                    status=status,
                    attempt=0,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duracion_ms,
                    error_message=error_message,
                    worker_name='simulador_prueba'
                )

                ejecuciones_creadas.append(execution)
                
                status_color = 'SUCCESS' if status == 'SUCCESS' else 'WARNING'
                self._print_status(
                    f"  ✅ Ejecución {execution.id}: {job.nombre} - {status} ({duracion_ms}ms)",
                    status_color
                )

        self._print_status(f"\n✅ {len(ejecuciones_creadas)} ejecución(es) simulada(s) creada(s)")

        # Resumen final
        self.stdout.write(self.style.SUCCESS("\n" + "="*80))
        self.stdout.write(self.style.SUCCESS("  📊 RESUMEN"))
        self.stdout.write(self.style.SUCCESS("="*80 + "\n"))
        self._print_status(f"📡 OLT: {olt.abreviatura} ({olt.ip_address})")
        self._print_status(f"📋 Tareas SNMP: {len(tareas_creadas)}")
        self._print_status(f"📋 Plantillas: {len(plantillas_creadas)}")
        self._print_status(f"📋 Ejecuciones simuladas: {len(ejecuciones_creadas)}")
        self.stdout.write(self.style.SUCCESS("\n✅ Datos de prueba creados exitosamente\n"))
