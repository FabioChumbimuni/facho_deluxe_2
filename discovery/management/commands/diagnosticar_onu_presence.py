"""
Comando para diagnosticar por qué una ONU no se marca como DISABLED
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from discovery.models import OnuInventory, OnuStatus, OnuIndexMap
from executions.models import Execution
from snmp_jobs.models import SnmpJob


class Command(BaseCommand):
    help = 'Diagnostica por qué una ONU no se marcó como DISABLED'

    def add_arguments(self, parser):
        parser.add_argument(
            '--onu-id',
            type=int,
            required=True,
            help='ID de OnuInventory a diagnosticar'
        )
        parser.add_argument(
            '--execution-id',
            type=int,
            help='ID de la ejecución a revisar (opcional)'
        )

    def handle(self, *args, **options):
        onu_id = options['onu_id']
        execution_id = options.get('execution_id')
        
        self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
        self.stdout.write(self.style.WARNING(f"🔍 DIAGNÓSTICO DE ONU - ID: {onu_id}"))
        self.stdout.write(self.style.WARNING(f"{'='*80}\n"))
        
        try:
            # 1. Obtener la ONU del inventario
            onu = OnuInventory.objects.select_related('onu_index', 'olt').get(id=onu_id)
            
            self.stdout.write(self.style.SUCCESS("✅ ONU ENCONTRADA EN INVENTARIO:"))
            self.stdout.write(f"   - ID: {onu.id}")
            self.stdout.write(f"   - Normalized ID: {onu.onu_index.normalized_id}")
            self.stdout.write(f"   - OLT: {onu.olt.abreviatura} (ID: {onu.olt.id})")
            self.stdout.write(f"   - Active: {onu.active}")
            self.stdout.write(f"   - Serial Number: {onu.serial_number or 'N/A'}")
            self.stdout.write(f"   - Subscriber ID: {onu.subscriber_id or 'N/A'}")
            self.stdout.write(f"   - Última actualización: {onu.updated_at}")
            
            # 2. Verificar OnuIndexMap
            onu_index = onu.onu_index
            self.stdout.write(self.style.SUCCESS("\n✅ ONU INDEX MAP:"))
            self.stdout.write(f"   - ID: {onu_index.id}")
            self.stdout.write(f"   - Raw Index Key: {onu_index.raw_index_key}")
            self.stdout.write(f"   - Normalized ID: {onu_index.normalized_id}")
            self.stdout.write(f"   - Marca Formula: {onu_index.marca_formula}")
            self.stdout.write(f"   - Slot: {onu_index.slot or 'N/A'}")
            self.stdout.write(f"   - Port: {onu_index.port or 'N/A'}")
            
            # 3. Verificar OnuStatus
            try:
                status = onu_index.status
                self.stdout.write(self.style.SUCCESS("\n✅ ONU STATUS:"))
                self.stdout.write(f"   - Presence: {status.presence}")
                self.stdout.write(f"   - Last State: {status.last_state_label} ({status.last_state_value})")
                self.stdout.write(f"   - Consecutive Misses: {status.consecutive_misses}")
                self.stdout.write(f"   - Last Seen: {status.last_seen_at}")
                self.stdout.write(f"   - Last Change Execution: {status.last_change_execution_id or 'N/A'}")
            except OnuStatus.DoesNotExist:
                self.stdout.write(self.style.ERROR("\n❌ NO TIENE ONUSTATUS ASOCIADO"))
                self.stdout.write("   🔧 Esto podría ser el problema.")
            
            # 4. Verificar ejecuciones recientes para esta OLT
            self.stdout.write(self.style.WARNING("\n🔍 EJECUCIONES RECIENTES DE DISCOVERY:"))
            recent_executions = Execution.objects.filter(
                olt=onu.olt,
                snmp_job__job_type='descubrimiento',
                status='SUCCESS'
            ).select_related('snmp_job', 'snmp_job__marca').order_by('-started_at')[:5]
            
            for exec in recent_executions:
                self.stdout.write(f"\n   Execution ID: {exec.id}")
                self.stdout.write(f"   - Job: {exec.snmp_job.nombre}")
                self.stdout.write(f"   - Marca del Job: {exec.snmp_job.marca.nombre if exec.snmp_job.marca else 'N/A'}")
                self.stdout.write(f"   - Started: {exec.started_at}")
                self.stdout.write(f"   - Status: {exec.status}")
                self.stdout.write(f"   - Duration: {exec.duration_ms or 'N/A'} ms")
            
            # 5. Si se especifica execution_id, analizarla
            if execution_id:
                self.stdout.write(self.style.WARNING(f"\n🔍 ANALIZANDO EJECUCIÓN ESPECÍFICA: {execution_id}"))
                try:
                    execution = Execution.objects.select_related('snmp_job', 'snmp_job__marca').get(id=execution_id)
                    
                    self.stdout.write(f"   - Job: {execution.snmp_job.nombre}")
                    self.stdout.write(f"   - Job Type: {execution.snmp_job.job_type}")
                    self.stdout.write(f"   - Marca del Job: {execution.snmp_job.marca.nombre if execution.snmp_job.marca else 'N/A'}")
                    self.stdout.write(f"   - OLT: {execution.olt.abreviatura}")
                    self.stdout.write(f"   - Status: {execution.status}")
                    self.stdout.write(f"   - Started: {execution.started_at}")
                    self.stdout.write(f"   - Finished: {execution.finished_at}")
                    
                    # Verificar si la marca del job coincide con la marca formula de la ONU
                    expected_marca_formula = f"marca_{execution.snmp_job.marca.nombre}" if execution.snmp_job.marca else None
                    
                    if expected_marca_formula == onu_index.marca_formula:
                        self.stdout.write(self.style.SUCCESS(f"\n   ✅ MARCA COINCIDE: {expected_marca_formula}"))
                        self.stdout.write("   Esta ONU DEBERÍA haber sido evaluada en este walk")
                    else:
                        self.stdout.write(self.style.ERROR(f"\n   ❌ MARCA NO COINCIDE:"))
                        self.stdout.write(f"      - Job tiene: {expected_marca_formula}")
                        self.stdout.write(f"      - ONU tiene: {onu_index.marca_formula}")
                        self.stdout.write(self.style.WARNING("   ⚠️ PROBLEMA IDENTIFICADO: El job de discovery usa una marca diferente"))
                        self.stdout.write("      La ONU NO fue evaluada en _mark_missing_onus() porque el filtro por marca la excluye")
                    
                except Execution.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"   ❌ Ejecución {execution_id} no encontrada"))
            
            # 6. Buscar todas las ONUs con la misma marca_formula en esta OLT
            self.stdout.write(self.style.WARNING(f"\n🔍 ONUs CON LA MISMA MARCA_FORMULA ({onu_index.marca_formula}):"))
            similar_onus = OnuIndexMap.objects.filter(
                olt=onu.olt,
                marca_formula=onu_index.marca_formula
            ).count()
            self.stdout.write(f"   Total: {similar_onus} ONUs")
            
            # 7. Jobs de discovery activos para esta OLT
            self.stdout.write(self.style.WARNING(f"\n🔍 JOBS DE DISCOVERY ACTIVOS PARA {onu.olt.abreviatura}:"))
            active_jobs = SnmpJob.objects.filter(
                job_type='descubrimiento',
                enabled=True,
                job_hosts__olt=onu.olt,
                job_hosts__enabled=True
            ).select_related('marca').distinct()
            
            for job in active_jobs:
                marca_formula = f"marca_{job.marca.nombre}" if job.marca else "N/A"
                matches = "✅ COINCIDE" if marca_formula == onu_index.marca_formula else "❌ NO COINCIDE"
                self.stdout.write(f"\n   Job: {job.nombre} (ID: {job.id})")
                self.stdout.write(f"   - Marca: {job.marca.nombre if job.marca else 'N/A'}")
                self.stdout.write(f"   - Marca Formula: {marca_formula}")
                self.stdout.write(f"   - {matches} con la ONU")
            
            # 8. RECOMENDACIONES
            self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
            self.stdout.write(self.style.WARNING("💡 RECOMENDACIONES:"))
            self.stdout.write(self.style.WARNING(f"{'='*80}"))
            
            try:
                status = onu_index.status
                if status.presence == 'ENABLED':
                    self.stdout.write(self.style.ERROR("\n❌ La ONU sigue marcada como ENABLED pero reportas que ya no aparece en el walk"))
                    self.stdout.write("\n   Posibles causas:")
                    self.stdout.write("   1. El job de discovery que se ejecutó tiene una marca diferente")
                    self.stdout.write("   2. La ONU fue creada con una marca_formula incorrecta")
                    self.stdout.write("   3. La función _mark_missing_onus() no se está ejecutando")
                    self.stdout.write("   4. Hay un error en el filtro de marca")
                    
                    self.stdout.write("\n   🔧 Soluciones:")
                    self.stdout.write(f"   - Esperar al siguiente discovery del job correcto")
                    self.stdout.write(f"   - Corregir manualmente: python manage.py shell")
                    self.stdout.write(f"     >>> from discovery.models import OnuStatus")
                    self.stdout.write(f"     >>> status = OnuStatus.objects.get(onu_index_id={onu_index.id})")
                    self.stdout.write(f"     >>> status.presence = 'DISABLED'")
                    self.stdout.write(f"     >>> status.save()")
                    self.stdout.write(f"     >>> inv = OnuInventory.objects.get(id={onu_id})")
                    self.stdout.write(f"     >>> inv.active = False")
                    self.stdout.write(f"     >>> inv.save()")
                else:
                    self.stdout.write(self.style.SUCCESS("\n✅ La ONU ya está marcada como DISABLED en OnuStatus"))
                    if onu.active:
                        self.stdout.write(self.style.ERROR("❌ PERO el inventario sigue activo (active=True)"))
                        self.stdout.write("\n   🔧 Ejecutar sincronización:")
                        self.stdout.write("   python manage.py sincronizar_presence_active --fix")
                    else:
                        self.stdout.write(self.style.SUCCESS("✅ Y el inventario también está inactivo (active=False)"))
                        self.stdout.write("\n   Todo está correcto. La ONU está correctamente marcada como DISABLED.")
                        
            except OnuStatus.DoesNotExist:
                self.stdout.write(self.style.ERROR("\n❌ PROBLEMA CRÍTICO: La ONU no tiene OnuStatus"))
                self.stdout.write("   Esto significa que nunca se procesó correctamente en un discovery")
                self.stdout.write("\n   🔧 Solución: Crear OnuStatus manualmente o esperar al siguiente discovery")
            
            self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
            self.stdout.write(self.style.SUCCESS("✅ DIAGNÓSTICO COMPLETADO"))
            self.stdout.write(self.style.WARNING(f"{'='*80}\n"))
            
        except OnuInventory.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"\n❌ OnuInventory con ID {onu_id} no encontrada"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())

