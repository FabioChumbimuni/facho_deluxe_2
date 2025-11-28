"""
Comando para corregir la secuencia de IDs de WorkflowTemplate
Útil cuando la secuencia de PostgreSQL está desincronizada
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Max
from snmp_jobs.models import WorkflowTemplate


class Command(BaseCommand):
    help = 'Corrige la secuencia de IDs de WorkflowTemplate si está desincronizada'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin hacer cambios'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 MODO DRY-RUN - Sin hacer cambios reales"))
        else:
            self.stdout.write(self.style.WARNING("🔧 CORRIGIENDO SECUENCIA DE WORKFLOWTEMPLATE"))
        self.stdout.write(self.style.WARNING(f"{'='*80}\n"))
        
        # Obtener el ID máximo actual
        max_id = WorkflowTemplate.objects.aggregate(max_id=Max('id'))['max_id'] or 0
        self.stdout.write(f"📋 ID máximo en la tabla: {max_id}")
        
        if max_id == 0:
            self.stdout.write(self.style.SUCCESS("\n✅ La tabla está vacía, secuencia en 1"))
            return
        
        # Obtener el siguiente valor de la secuencia
        with connection.cursor() as cursor:
            # Obtener el valor actual sin incrementarlo
            cursor.execute("SELECT last_value, is_called FROM snmp_workflow_templates_id_seq;")
            result = cursor.fetchone()
            last_value = result[0]
            is_called = result[1]
            
            # Calcular el siguiente valor
            if is_called:
                next_value = last_value + 1
            else:
                next_value = last_value
            
            self.stdout.write(f"📋 Último valor de la secuencia: {last_value}")
            self.stdout.write(f"📋 Siguiente valor que usará: {next_value}")
            
            # Verificar si necesita corrección
            if next_value <= max_id:
                new_seq_value = max_id + 1
                self.stdout.write(self.style.WARNING(f"\n⚠️ PROBLEMA DETECTADO:"))
                self.stdout.write(f"   - La secuencia intentará usar el ID {next_value}")
                self.stdout.write(f"   - Pero ya existe un registro con ID {max_id}")
                self.stdout.write(f"   - Necesita reajustar la secuencia a {new_seq_value}")
                
                if not dry_run:
                    # Reajustar la secuencia
                    cursor.execute(
                        "SELECT setval('snmp_workflow_templates_id_seq', %s, true);",
                        [new_seq_value]
                    )
                    self.stdout.write(self.style.SUCCESS(f"\n✅ Secuencia reajustada a {new_seq_value}"))
                    
                    # Verificar que se aplicó correctamente
                    cursor.execute("SELECT last_value FROM snmp_workflow_templates_id_seq;")
                    new_last_value = cursor.fetchone()[0]
                    self.stdout.write(f"📋 Nuevo último valor: {new_last_value}")
                else:
                    self.stdout.write(self.style.WARNING(f"\n🔍 DRY-RUN: Se ajustaría la secuencia a {new_seq_value}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"\n✅ La secuencia está correcta (siguiente valor: {next_value} > {max_id})"))

