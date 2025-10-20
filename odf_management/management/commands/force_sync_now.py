"""
Comando para forzar la ejecución inmediata de sincronización.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from odf_management.models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from odf_management.tasks import sync_single_olt_ports


class Command(BaseCommand):
    help = 'Fuerza la ejecución inmediata de sincronización'

    def handle(self, *args, **options):
        self.stdout.write("🚀 FORZANDO EJECUCIÓN INMEDIATA...")
        
        # 1. Obtener programaciones que deberían ejecutarse
        now = timezone.now()
        schedules = ZabbixCollectionSchedule.objects.filter(habilitado=True)
        
        total_executed = 0
        
        for schedule in schedules:
            self.stdout.write(f"\n📋 Procesando: {schedule.nombre}")
            
            # Obtener OLTs habilitadas
            olt_configs = ZabbixCollectionOLT.objects.filter(
                schedule=schedule,
                habilitado=True
            ).select_related('olt')
            
            self.stdout.write(f"   OLTs a sincronizar: {olt_configs.count()}")
            
            for olt_config in olt_configs:
                self.stdout.write(f"   🖥️ Ejecutando para {olt_config.olt.abreviatura}...")
                
                # Actualizar estado a pending
                olt_config.ultimo_estado = 'pending'
                olt_config.save()
                
                # Ejecutar tarea sincrónicamente para debug
                try:
                    result = sync_single_olt_ports(olt_config.olt.id, schedule.id)
                    
                    if result.get('success'):
                        self.stdout.write(f"      ✅ Éxito: {result.get('stats', {})}")
                        olt_config.ultimo_estado = 'success'
                        olt_config.ultimo_error = ''
                    else:
                        self.stdout.write(f"      ❌ Error: {result.get('error', 'Unknown error')}")
                        olt_config.ultimo_estado = 'error'
                        olt_config.ultimo_error = str(result.get('error', 'Unknown error'))[:500]
                    
                    olt_config.ultima_recoleccion = now
                    olt_config.save()
                    total_executed += 1
                    
                except Exception as e:
                    self.stdout.write(f"      ❌ Excepción: {e}")
                    olt_config.ultimo_estado = 'error'
                    olt_config.ultimo_error = str(e)[:500]
                    olt_config.ultima_recoleccion = now
                    olt_config.save()
            
            # Actualizar próxima ejecución
            schedule.ultima_ejecucion = now
            schedule.calcular_proxima_ejecucion()
            schedule.save()
            
            self.stdout.write(f"   📅 Próxima ejecución: {schedule.proxima_ejecucion}")
        
        self.stdout.write(f"\n✅ Ejecución completada!")
        self.stdout.write(f"   Total OLTs procesadas: {total_executed}")
        self.stdout.write(f"   Revisa el admin para ver los estados actualizados")
