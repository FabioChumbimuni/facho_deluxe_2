"""
Comando para debuggear el sistema de programación.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from odf_management.models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from odf_management.tasks import sync_scheduled_olts


class Command(BaseCommand):
    help = 'Debug del sistema de programación ODF'

    def handle(self, *args, **options):
        self.stdout.write("🔍 DEBUGGEANDO SISTEMA DE PROGRAMACIÓN")
        
        # 1. Verificar programaciones
        self.stdout.write("\n📅 PROGRAMACIONES:")
        schedules = ZabbixCollectionSchedule.objects.all()
        
        for schedule in schedules:
            status = "✅ Activa" if schedule.habilitado else "❌ Inactiva"
            self.stdout.write(f"  • {schedule.nombre} ({status})")
            self.stdout.write(f"    Próxima: {schedule.proxima_ejecucion}")
            self.stdout.write(f"    Última: {schedule.ultima_ejecucion}")
            
            # OLTs
            olts = schedule.zabbixcollectionolt_set.all()
            self.stdout.write(f"    OLTs: {olts.count()}")
            for olt_config in olts:
                olt_status = "✅" if olt_config.habilitado else "❌"
                self.stdout.write(f"      {olt_status} {olt_config.olt.abreviatura} - {olt_config.ultimo_estado}")
        
        # 2. Verificar qué programaciones deberían ejecutarse
        now = timezone.now()
        self.stdout.write(f"\n⏰ HORA ACTUAL: {now}")
        
        ready_schedules = ZabbixCollectionSchedule.objects.filter(
            habilitado=True,
            proxima_ejecucion__lte=now
        )
        
        self.stdout.write(f"\n🚀 PROGRAMACIONES LISTAS PARA EJECUTAR: {ready_schedules.count()}")
        for schedule in ready_schedules:
            self.stdout.write(f"  • {schedule.nombre} (próxima: {schedule.proxima_ejecucion})")
        
        # 3. Ejecutar tarea manualmente
        self.stdout.write("\n🔄 EJECUTANDO TAREA MANUALMENTE...")
        try:
            result = sync_scheduled_olts()
            self.stdout.write(f"✅ Resultado: {result}")
        except Exception as e:
            self.stdout.write(f"❌ Error: {e}")
            import traceback
            self.stdout.write(traceback.format_exc())
        
        # 4. Verificar estado después
        self.stdout.write("\n📊 ESTADO DESPUÉS DE EJECUCIÓN:")
        for schedule in ready_schedules:
            schedule.refresh_from_db()
            self.stdout.write(f"  • {schedule.nombre}:")
            self.stdout.write(f"    Nueva próxima: {schedule.proxima_ejecucion}")
            self.stdout.write(f"    Nueva última: {schedule.ultima_ejecucion}")
