# snmp_jobs/management/commands/limpiar_tareas_legacy.py
from django.core.management.base import BaseCommand
from django.db import transaction
from snmp_jobs.models import SnmpJobHost, SnmpJob
from executions.models import Execution
from django.utils import timezone


class Command(BaseCommand):
    help = 'Elimina todas las tareas legacy (SnmpJobHost) y sus SnmpJob asociados si no tienen más referencias'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se eliminaría sin hacer cambios reales',
        )
        parser.add_argument(
            '--keep-executions',
            action='store_true',
            help='Mantiene los registros de Execution (solo elimina SnmpJobHost y SnmpJob)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        keep_executions = options['keep_executions']

        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('LIMPIEZA DE TAREAS LEGACY'))
        self.stdout.write(self.style.WARNING('=' * 60))

        # Contar elementos
        total_job_hosts = SnmpJobHost.objects.count()
        total_jobs = SnmpJob.objects.count()
        total_executions = Execution.objects.filter(snmp_job__isnull=False).count()

        self.stdout.write(f'\n📊 Estado actual:')
        self.stdout.write(f'  - SnmpJobHost (tareas legacy): {total_job_hosts}')
        self.stdout.write(f'  - SnmpJob (plantillas legacy): {total_jobs}')
        self.stdout.write(f'  - Executions asociadas: {total_executions}')

        if total_job_hosts == 0:
            self.stdout.write(self.style.SUCCESS('\n✅ No hay tareas legacy para eliminar.'))
            return

        # Mostrar resumen por OLT
        self.stdout.write(f'\n📋 Resumen por OLT:')
        from django.db.models import Count
        from hosts.models import OLT
        
        olt_summary = (
            SnmpJobHost.objects
            .values('olt__abreviatura', 'olt__id')
            .annotate(count=Count('id'))
            .order_by('olt__abreviatura')
        )
        
        for item in olt_summary:
            self.stdout.write(f'  - {item["olt__abreviatura"]}: {item["count"]} tareas')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n⚠️  MODO DRY-RUN: No se eliminará nada.'))
            self.stdout.write(self.style.WARNING('   Ejecuta sin --dry-run para eliminar realmente.'))
            return

        # Confirmar eliminación
        self.stdout.write(self.style.ERROR('\n⚠️  ADVERTENCIA: Esta acción eliminará:'))
        self.stdout.write(self.style.ERROR(f'  - {total_job_hosts} SnmpJobHost'))
        self.stdout.write(self.style.ERROR(f'  - {total_jobs} SnmpJob'))
        if not keep_executions:
            self.stdout.write(self.style.ERROR(f'  - {total_executions} Executions asociadas'))
        else:
            self.stdout.write(self.style.WARNING(f'  - Se mantendrán {total_executions} Executions (historial)'))

        respuesta = input('\n¿Continuar? (escribe "SI" para confirmar): ')
        if respuesta != 'SI':
            self.stdout.write(self.style.WARNING('Operación cancelada.'))
            return

        # Eliminar en transacción
        with transaction.atomic():
            deleted_hosts = 0
            deleted_jobs = 0
            deleted_executions = 0

            # 1. Eliminar Executions asociadas (si no se mantienen)
            if not keep_executions:
                self.stdout.write('\n🗑️  Eliminando Executions...')
                deleted_executions = Execution.objects.filter(snmp_job__isnull=False).delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  ✅ {deleted_executions} Executions eliminadas'))

            # 2. Eliminar SnmpJobHost
            self.stdout.write('\n🗑️  Eliminando SnmpJobHost...')
            deleted_hosts = SnmpJobHost.objects.all().delete()[0]
            self.stdout.write(self.style.SUCCESS(f'  ✅ {deleted_hosts} SnmpJobHost eliminados'))

            # 3. Eliminar SnmpJob (ya no tienen referencias)
            self.stdout.write('\n🗑️  Eliminando SnmpJob...')
            deleted_jobs = SnmpJob.objects.all().delete()[0]
            self.stdout.write(self.style.SUCCESS(f'  ✅ {deleted_jobs} SnmpJob eliminados'))

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('✅ LIMPIEZA COMPLETADA'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'\n📊 Resumen:')
        self.stdout.write(f'  - SnmpJobHost eliminados: {deleted_hosts}')
        self.stdout.write(f'  - SnmpJob eliminados: {deleted_jobs}')
        if not keep_executions:
            self.stdout.write(f'  - Executions eliminadas: {deleted_executions}')
        self.stdout.write(self.style.SUCCESS('\n✅ Ahora puedes usar solo el sistema de Workflows.'))

