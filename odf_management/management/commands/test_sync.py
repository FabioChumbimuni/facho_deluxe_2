"""
Comando simple para probar la sincronización.
"""

from django.core.management.base import BaseCommand
from odf_management.models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from django.utils import timezone


class Command(BaseCommand):
    help = 'Prueba simple de sincronización'

    def handle(self, *args, **options):
        self.stdout.write("🔄 PROBANDO SINCRONIZACIÓN...")
        
        # 1. Verificar programaciones
        schedules = ZabbixCollectionSchedule.objects.filter(habilitado=True)
        self.stdout.write(f"📅 Programaciones activas: {schedules.count()}")
        
        for schedule in schedules:
            self.stdout.write(f"\n📋 {schedule.nombre}:")
            self.stdout.write(f"   Próxima: {schedule.proxima_ejecucion}")
            self.stdout.write(f"   Ahora: {timezone.now()}")
            
            # Ver OLTs asociadas
            olts = ZabbixCollectionOLT.objects.filter(schedule=schedule, habilitado=True)
            self.stdout.write(f"   OLTs configuradas: {olts.count()}")
            
            for olt_config in olts:
                self.stdout.write(f"     • {olt_config.olt.abreviatura} - {olt_config.ultimo_estado}")
        
        # 2. Ejecutar tarea manualmente
        self.stdout.write("\n🚀 Ejecutando tarea manualmente...")
        try:
            from odf_management.tasks import sync_scheduled_olts
            result = sync_scheduled_olts()
            self.stdout.write(f"✅ Resultado: {result}")
        except Exception as e:
            self.stdout.write(f"❌ Error: {e}")
            import traceback
            self.stdout.write(traceback.format_exc())
        
        self.stdout.write("\n✅ Prueba completada.")
