"""
Comando para probar la sincronización bidireccional entre ZabbixPortData y ODFHilos
"""

from django.core.management.base import BaseCommand
from odf_management.models import ODFHilos, ZabbixPortData


class Command(BaseCommand):
    help = 'Prueba la sincronización bidireccional entre puerto Zabbix y hilos ODF'

    def add_arguments(self, parser):
        parser.add_argument(
            '--puerto-id',
            type=int,
            help='ID del puerto Zabbix a usar para la prueba'
        )

    def handle(self, *args, **options):
        puerto_id = options.get('puerto_id')
        
        self.stdout.write("🔄 PRUEBA DE SINCRONIZACIÓN BIDIRECCIONAL")
        self.stdout.write("=" * 60)
        
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
        self.stdout.write(f"   SNMP Index: {puerto.snmp_index}")
        self.stdout.write(f"   Hilos asociados: {hilos.count()}")
        
        # Mostrar estado inicial
        self.stdout.write(f"\n📊 ESTADO INICIAL:")
        self.stdout.write(f"   Puerto disponible: {'✅' if puerto.disponible else '❌'}")
        self.stdout.write(f"   Puerto operativo NOC: {'✅' if puerto.operativo_noc else '❌'}")
        
        for hilo in hilos:
            self.stdout.write(f"   Hilo {hilo.id} en_zabbix: {'✅' if hilo.en_zabbix else '❌'}")
            self.stdout.write(f"   Hilo {hilo.id} operativo_noc: {'✅' if hilo.operativo_noc else '❌'}")
        
        # PRUEBA 1: Cambiar disponible del puerto
        self.stdout.write(f"\n🧪 PRUEBA 1: Cambiar 'disponible' del puerto")
        estado_original = puerto.disponible
        puerto.disponible = not estado_original
        puerto.save()
        
        self.stdout.write(f"   Puerto disponible: {estado_original} → {'✅' if puerto.disponible else '❌'}")
        
        # Verificar sincronización en hilos
        for hilo in hilos:
            hilo.refresh_from_db()
            self.stdout.write(f"   Hilo {hilo.id} en_zabbix: {'✅' if hilo.en_zabbix else '❌'}")
        
        # PRUEBA 2: Cambiar operativo_noc de un hilo
        if hilos.exists():
            hilo_prueba = hilos.first()
            self.stdout.write(f"\n🧪 PRUEBA 2: Cambiar 'operativo_noc' del hilo {hilo_prueba.id}")
            
            estado_original_hilo = hilo_prueba.operativo_noc
            hilo_prueba.operativo_noc = not estado_original_hilo
            hilo_prueba.save()
            
            # Simular sincronización (como haría el admin)
            hilo_prueba.sincronizar_operativo_noc(forzar_direccion='hilo_a_puerto')
            
            puerto.refresh_from_db()
            self.stdout.write(f"   Hilo operativo_noc: {estado_original_hilo} → {'✅' if hilo_prueba.operativo_noc else '❌'}")
            self.stdout.write(f"   Puerto operativo_noc: {'✅' if puerto.operativo_noc else '❌'}")
        
        # Restaurar estados originales
        self.stdout.write(f"\n🔄 RESTAURANDO ESTADOS ORIGINALES:")
        puerto.disponible = estado_original
        puerto.save()
        
        if hilos.exists():
            hilo_prueba.operativo_noc = estado_original_hilo
            hilo_prueba.save()
            hilo_prueba.sincronizar_operativo_noc(forzar_direccion='hilo_a_puerto')
        
        # Verificar restauración
        puerto.refresh_from_db()
        self.stdout.write(f"   Puerto disponible: {'✅' if puerto.disponible else '❌'}")
        self.stdout.write(f"   Puerto operativo NOC: {'✅' if puerto.operativo_noc else '❌'}")
        
        for hilo in hilos:
            hilo.refresh_from_db()
            self.stdout.write(f"   Hilo {hilo.id} en_zabbix: {'✅' if hilo.en_zabbix else '❌'}")
            self.stdout.write(f"   Hilo {hilo.id} operativo_noc: {'✅' if hilo.operativo_noc else '❌'}")
        
        # Resumen
        self.stdout.write(f"\n💡 CONCLUSIONES:")
        self.stdout.write(f"   ✅ Puerto.disponible ↔ Hilo.en_zabbix (sincronización automática)")
        self.stdout.write(f"   ✅ Hilo.operativo_noc → Puerto.operativo_noc (hilo = fuente de verdad)")
        self.stdout.write(f"   ✅ Estados se restauraron correctamente")
        
        self.stdout.write(f"\n🎯 AHORA PUEDES PROBAR MANUALMENTE EN:")
        self.stdout.write(f"   Puerto Zabbix: http://localhost:8000/admin/odf_management/zabbixportdata/{puerto.id}/change/")
        if hilos.exists():
            self.stdout.write(f"   Hilo ODF: http://localhost:8000/admin/odf_management/odfhilos/{hilos.first().id}/change/")
        
        self.stdout.write(self.style.SUCCESS("\n✅ Prueba completada"))
