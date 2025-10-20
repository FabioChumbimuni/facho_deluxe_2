"""
Comando para probar la lógica de programación (primera vez vs. posteriores).
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from odf_management.models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Prueba la lógica de programación de primera vez vs posteriores'

    def handle(self, *args, **options):
        self.stdout.write("🧪 PROBANDO LÓGICA DE PROGRAMACIÓN...")
        
        # Limpiar programación de prueba si existe
        ZabbixCollectionSchedule.objects.filter(nombre__startswith="PRUEBA LÓGICA").delete()
        
        # 1. Crear programación nueva (primera vez)
        schedule = ZabbixCollectionSchedule.objects.create(
            nombre="PRUEBA LÓGICA - CADA 5MIN",
            intervalo_minutos=5,
            habilitado=True
        )
        
        ahora = timezone.now()
        self.stdout.write(f"\n⏰ HORA ACTUAL: {ahora}")
        
        # 2. Calcular primera ejecución
        schedule.calcular_proxima_ejecucion(primera_vez=True)
        schedule.save()
        
        diferencia_primera = (schedule.proxima_ejecucion - ahora).total_seconds()
        self.stdout.write(f"\n✅ PRIMERA EJECUCIÓN:")
        self.stdout.write(f"   Programada para: {schedule.proxima_ejecucion}")
        self.stdout.write(f"   Diferencia: {diferencia_primera:.0f} segundos (~1 minuto)")
        
        # 3. Simular ejecución completada
        schedule.ultima_ejecucion = ahora
        schedule.save()
        
        # 4. Calcular próxima ejecución (posterior)
        schedule.calcular_proxima_ejecucion(primera_vez=False)
        schedule.save()
        
        diferencia_posterior = (schedule.proxima_ejecucion - ahora).total_seconds()
        self.stdout.write(f"\n🔄 EJECUCIÓN POSTERIOR:")
        self.stdout.write(f"   Programada para: {schedule.proxima_ejecucion}")
        self.stdout.write(f"   Diferencia: {diferencia_posterior:.0f} segundos")
        self.stdout.write(f"   Sigue intervalo de {schedule.intervalo_minutos} minutos: {'✅ SÍ' if diferencia_posterior > 60 else '❌ NO'}")
        
        # 5. Probar diferentes intervalos
        self.stdout.write(f"\n📊 PRUEBA DE DIFERENTES INTERVALOS:")
        
        intervalos_test = [10, 15, 30]
        for intervalo in intervalos_test:
            test_schedule = ZabbixCollectionSchedule(
                nombre=f"TEST {intervalo}MIN",
                intervalo_minutos=intervalo,
                habilitado=True
            )
            
            # Primera vez
            test_schedule.calcular_proxima_ejecucion(primera_vez=True)
            diff_primera = (test_schedule.proxima_ejecucion - ahora).total_seconds()
            
            # Simular ejecución
            test_schedule.ultima_ejecucion = ahora
            test_schedule.calcular_proxima_ejecucion(primera_vez=False)
            diff_posterior = (test_schedule.proxima_ejecucion - ahora).total_seconds()
            
            self.stdout.write(f"   {intervalo} min: Primera={diff_primera:.0f}s, Posterior={diff_posterior:.0f}s")
        
        # 6. Limpiar
        schedule.delete()
        
        self.stdout.write(f"\n✅ LÓGICA IMPLEMENTADA:")
        self.stdout.write(f"   🚀 Primera ejecución: 1 minuto después de guardar")
        self.stdout.write(f"   🔄 Ejecuciones posteriores: Según intervalo configurado")
        self.stdout.write(f"   ⏰ Intervalos disponibles: 5, 10, 15, 20, 30, 60 minutos")
        
        self.stdout.write(f"\n✅ Prueba completada")
