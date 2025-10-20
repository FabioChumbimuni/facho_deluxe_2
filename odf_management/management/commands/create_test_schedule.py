"""
Comando para crear una programación de prueba con 3 OLTs.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from odf_management.models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Crea una programación de prueba con 3 OLTs'

    def handle(self, *args, **options):
        self.stdout.write("🚀 CREANDO PROGRAMACIÓN DE PRUEBA CON 3 OLTs...")
        
        # 1. Ver OLTs disponibles
        olts_disponibles = OLT.objects.filter(habilitar_olt=True)[:5]
        self.stdout.write(f"\n🖥️ OLTs DISPONIBLES ({olts_disponibles.count()}):")
        for olt in olts_disponibles:
            self.stdout.write(f"  • {olt.abreviatura} - {olt.ip_address}")
        
        if olts_disponibles.count() < 3:
            self.stdout.write(self.style.WARNING("⚠️ Se necesitan al menos 3 OLTs habilitadas"))
            return
        
        # 2. Crear o actualizar programación
        schedule_name = "PRUEBA 3 OLTs - CADA 2MIN"
        schedule, created = ZabbixCollectionSchedule.objects.get_or_create(
            nombre=schedule_name,
            defaults={
                'intervalo_minutos': 5,  # Cada 5 minutos para prueba
                'habilitado': True
            }
        )
        
        if created:
            self.stdout.write(f"✅ Programación creada: {schedule_name}")
        else:
            self.stdout.write(f"ℹ️ Programación actualizada: {schedule_name}")
        
        # 3. Limpiar OLTs existentes
        ZabbixCollectionOLT.objects.filter(schedule=schedule).delete()
        
        # 4. Agregar 3 OLTs
        olts_seleccionadas = olts_disponibles[:3]
        for olt in olts_seleccionadas:
            ZabbixCollectionOLT.objects.create(
                schedule=schedule,
                olt=olt,
                habilitado=True
            )
            self.stdout.write(f"  ➕ Agregada: {olt.abreviatura}")
        
        # 5. Programar para ejecutarse en 1 minuto
        proxima = timezone.now() + timedelta(minutes=1)
        schedule.proxima_ejecucion = proxima
        schedule.save()
        
        self.stdout.write(f"\n⏰ PROGRAMACIÓN CONFIGURADA:")
        self.stdout.write(f"  Nombre: {schedule.nombre}")
        self.stdout.write(f"  Intervalo: {schedule.get_intervalo_minutos_display()}")
        self.stdout.write(f"  OLTs: {len(olts_seleccionadas)}")
        self.stdout.write(f"  Próxima ejecución: {schedule.proxima_ejecucion}")
        self.stdout.write(f"  Hora actual: {timezone.now()}")
        
        self.stdout.write(f"\n📊 VERIFICAR LOGS EN:")
        self.stdout.write(f"  • logs/celerybeat.log (scheduler)")
        self.stdout.write(f"  • logs/celery-discovery_main.log (tareas principales)")
        self.stdout.write(f"  • logs/celery-default.log (tareas por defecto)")
        
        self.stdout.write(f"\n🔍 MONITOREAR CON:")
        self.stdout.write(f"  python manage.py test_sync")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Programación lista para ejecutarse en 1 minuto!"))
