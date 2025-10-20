"""
Comando para probar el widget de selección múltiple.
"""

from django.core.management.base import BaseCommand
from odf_management.models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Prueba el widget de selección múltiple'

    def handle(self, *args, **options):
        self.stdout.write("🧪 PROBANDO WIDGET DE SELECCIÓN MÚLTIPLE...")
        
        # 1. Verificar OLTs disponibles
        olts = OLT.objects.filter(habilitar_olt=True)[:3]
        self.stdout.write(f"\n🖥️ OLTs disponibles para prueba:")
        for olt in olts:
            self.stdout.write(f"  • ID: {olt.id} - {olt.abreviatura}")
        
        # 2. Crear programación de prueba
        schedule_name = "PRUEBA WIDGET - TEMPORAL"
        
        # Limpiar si existe
        ZabbixCollectionSchedule.objects.filter(nombre=schedule_name).delete()
        
        # Crear nueva
        schedule = ZabbixCollectionSchedule.objects.create(
            nombre=schedule_name,
            intervalo_minutos=5,
            habilitado=True
        )
        
        self.stdout.write(f"\n✅ Programación creada: {schedule.nombre}")
        
        # 3. Agregar OLTs manualmente (simulando el widget)
        for olt in olts:
            ZabbixCollectionOLT.objects.create(
                schedule=schedule,
                olt=olt,
                habilitado=True
            )
            self.stdout.write(f"  ➕ OLT agregada: {olt.abreviatura}")
        
        # 4. Verificar que se guardaron
        olts_guardadas = schedule.zabbixcollectionolt_set.all()
        self.stdout.write(f"\n📊 RESULTADO:")
        self.stdout.write(f"  OLTs guardadas: {olts_guardadas.count()}")
        
        for olt_config in olts_guardadas:
            self.stdout.write(f"    • {olt_config.olt.abreviatura} - {'✅ Habilitada' if olt_config.habilitado else '❌ Deshabilitada'}")
        
        # 5. Limpiar
        schedule.delete()
        self.stdout.write(f"\n🗑️ Programación de prueba eliminada")
        
        self.stdout.write(f"\n💡 INSTRUCCIONES PARA EL ADMIN:")
        self.stdout.write(f"  1. Ve a: http://localhost:8000/admin/odf_management/zabbixcollectionschedule/add/")
        self.stdout.write(f"  2. Llena 'Nombre' e 'Intervalo'")
        self.stdout.write(f"  3. En 'Selección de OLTs', mueve OLTs de izquierda a derecha")
        self.stdout.write(f"  4. Haz clic en 'Guardar'")
        self.stdout.write(f"  5. Verifica que aparezcan en la lista de programaciones")
        
        self.stdout.write(f"\n✅ Prueba completada")
