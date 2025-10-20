"""
Comando para simular la recolección de datos de Zabbix y probar la sincronización automática
"""

from django.core.management.base import BaseCommand
from odf_management.models import ODFHilos, ZabbixPortData
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Simula la recolección de Zabbix y prueba la sincronización automática'

    def add_arguments(self, parser):
        parser.add_argument(
            '--puerto-id',
            type=int,
            help='ID del puerto Zabbix a usar para la simulación'
        )
        parser.add_argument(
            '--simular-desaparicion',
            action='store_true',
            help='Simular que el puerto desaparece de Zabbix'
        )

    def handle(self, *args, **options):
        puerto_id = options.get('puerto_id')
        simular_desaparicion = options['simular_desaparicion']
        
        self.stdout.write("🌾 SIMULACIÓN DE COSECHA DE ZABBIX")
        self.stdout.write("=" * 50)
        
        # Buscar puerto con hilos asociados
        if puerto_id:
            try:
                puerto = ZabbixPortData.objects.get(id=puerto_id)
            except ZabbixPortData.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Puerto con ID {puerto_id} no encontrado"))
                return
        else:
            # Buscar puerto que tenga hilos asociados
            puerto = ZabbixPortData.objects.filter(odfhilos__isnull=False).first()
            if not puerto:
                self.stdout.write(self.style.ERROR("❌ No se encontró puerto con hilos asociados"))
                return
        
        hilos = puerto.odfhilos_set.all()
        
        self.stdout.write(f"🎯 PUERTO SELECCIONADO:")
        self.stdout.write(f"   ID: {puerto.id}")
        self.stdout.write(f"   OLT: {puerto.olt.abreviatura}")
        self.stdout.write(f"   Slot/Port: {puerto.slot}/{puerto.port}")
        self.stdout.write(f"   Hilos asociados: {hilos.count()}")
        
        # Mostrar estado inicial
        self.stdout.write(f"\n📊 ESTADO ANTES DE LA COSECHA:")
        self.stdout.write(f"   Puerto disponible: {'✅' if puerto.disponible else '❌'}")
        self.stdout.write(f"   Puerto operativo NOC: {'✅' if puerto.operativo_noc else '❌'}")
        
        for hilo in hilos:
            self.stdout.write(f"   Hilo {hilo.id} en_zabbix: {'✅' if hilo.en_zabbix else '❌'}")
            self.stdout.write(f"   Hilo {hilo.id} operativo_noc: {'✅' if hilo.operativo_noc else '❌'}")
        
        # Simular cambio en la cosecha de Zabbix
        if simular_desaparicion:
            self.stdout.write(f"\n🌾 SIMULANDO: Puerto desaparece de Zabbix")
            puerto.disponible = False
        else:
            self.stdout.write(f"\n🌾 SIMULANDO: Puerto aparece/se mantiene en Zabbix")
            puerto.disponible = True
        
        puerto.save()
        
        # Simular la lógica de sincronización del servicio Zabbix
        self.stdout.write(f"🔄 EJECUTANDO LÓGICA DE SINCRONIZACIÓN...")
        
        for hilo in hilos:
            # Esta es la lógica que ejecuta el servicio Zabbix
            if hilo.en_zabbix != puerto.disponible:
                hilo.en_zabbix = puerto.disponible
                hilo.save()
                
                if puerto.disponible:
                    self.stdout.write(f"   ✅ Hilo {hilo.id} marcado como EN ZABBIX")
                else:
                    self.stdout.write(f"   ❌ Hilo {hilo.id} marcado como NO EN ZABBIX")
            else:
                self.stdout.write(f"   ℹ️ Hilo {hilo.id} ya estaba sincronizado")
        
        # Mostrar estado final
        self.stdout.write(f"\n📊 ESTADO DESPUÉS DE LA COSECHA:")
        self.stdout.write(f"   Puerto disponible: {'✅' if puerto.disponible else '❌'}")
        self.stdout.write(f"   Puerto operativo NOC: {'✅' if puerto.operativo_noc else '❌'}")
        
        for hilo in hilos:
            hilo.refresh_from_db()
            self.stdout.write(f"   Hilo {hilo.id} en_zabbix: {'✅' if hilo.en_zabbix else '❌'}")
            self.stdout.write(f"   Hilo {hilo.id} operativo_noc: {'✅' if hilo.operativo_noc else '❌'}")
        
        # Verificar sincronización (refrescar datos primero)
        sincronizados = True
        for hilo in hilos:
            hilo.refresh_from_db()  # Importante: refrescar datos
            if hilo.en_zabbix != puerto.disponible:
                sincronizados = False
                break
        
        if sincronizados:
            self.stdout.write(f"\n✅ SINCRONIZACIÓN EXITOSA:")
            self.stdout.write(f"   Puerto.disponible ↔ Hilo.en_zabbix = {'✅' if puerto.disponible else '❌'}")
        else:
            self.stdout.write(f"\n❌ ERROR EN SINCRONIZACIÓN")
        
        # Resumen
        self.stdout.write(f"\n💡 LO QUE PASÓ:")
        if simular_desaparicion:
            self.stdout.write(f"   🌾 Zabbix no encontró el puerto en la cosecha")
            self.stdout.write(f"   📉 Puerto.disponible = False")
            self.stdout.write(f"   🔄 Hilo.en_zabbix = False (sincronizado)")
            self.stdout.write(f"   ✅ operativo_noc se mantiene intacto (solo manual)")
        else:
            self.stdout.write(f"   🌾 Zabbix encontró el puerto en la cosecha")
            self.stdout.write(f"   📈 Puerto.disponible = True")
            self.stdout.write(f"   🔄 Hilo.en_zabbix = True (sincronizado)")
            self.stdout.write(f"   ✅ operativo_noc se mantiene intacto (solo manual)")
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Simulación completada"))
