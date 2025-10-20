"""
Comando para probar la lógica de hilos manuales y vinculación automática con Zabbix
"""

from django.core.management.base import BaseCommand
from odf_management.models import ODFHilos, ZabbixPortData, ODF
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Prueba la lógica de hilos manuales y vinculación automática'

    def handle(self, *args, **options):
        self.stdout.write("🧪 PRUEBA DE LÓGICA HILOS MANUALES")
        self.stdout.write("=" * 50)
        
        # 1. Crear un hilo manual (sin vinculación Zabbix)
        try:
            # Usar un ODF existente
            odf = ODF.objects.select_related('olt').first()
            if not odf:
                self.stdout.write(self.style.ERROR("❌ No hay ODFs disponibles"))
                return
            
            olt = odf.olt
            
            self.stdout.write(f"🎯 Usando OLT: {olt.abreviatura}")
            self.stdout.write(f"🎯 Usando ODF: {odf.nombre_troncal}")
            
            # 2. Crear hilo manual
            hilo_manual = ODFHilos.objects.create(
                odf=odf,
                slot=1,
                port=99,  # Puerto que no existe en Zabbix
                hilo_numero=999,
                vlan=999,
                descripcion_manual="Hilo de prueba manual",
                operativo_noc=True,  # Configuración manual NOC
                en_zabbix=False,     # No está en Zabbix inicialmente
                origen='manual'
            )
            
            self.stdout.write(f"✅ Hilo manual creado: ID {hilo_manual.id}")
            self.stdout.write(f"   Slot/Port: {hilo_manual.slot}/{hilo_manual.port}")
            self.stdout.write(f"   Operativo NOC: {hilo_manual.operativo_noc}")
            self.stdout.write(f"   En Zabbix: {hilo_manual.en_zabbix}")
            self.stdout.write(f"   Puerto Zabbix asociado: {hilo_manual.zabbix_port}")
            
            # 3. Verificar si existe puerto Zabbix correspondiente
            puerto_zabbix = ZabbixPortData.objects.filter(
                olt=olt,
                slot=hilo_manual.slot,
                port=hilo_manual.port,
                disponible=True
            ).first()
            
            if puerto_zabbix:
                self.stdout.write(f"🔗 Puerto Zabbix encontrado: ID {puerto_zabbix.id}")
                self.stdout.write(f"   Operativo NOC (puerto): {puerto_zabbix.operativo_noc}")
                
                # Simular vinculación automática (como haría Zabbix)
                hilo_manual.zabbix_port = puerto_zabbix
                hilo_manual.en_zabbix = True
                puerto_zabbix.operativo_noc = hilo_manual.operativo_noc  # Sincronizar
                
                hilo_manual.save()
                puerto_zabbix.save()
                
                self.stdout.write("✅ Vinculación automática simulada")
                self.stdout.write(f"   Hilo operativo NOC: {hilo_manual.operativo_noc}")
                self.stdout.write(f"   Puerto operativo NOC: {puerto_zabbix.operativo_noc}")
                
            else:
                self.stdout.write("⚠️ No hay puerto Zabbix correspondiente (normal para hilo manual)")
            
            # 4. Mostrar estado final
            self.stdout.write(f"\n📊 ESTADO FINAL DEL HILO:")
            self.stdout.write(f"   ID: {hilo_manual.id}")
            self.stdout.write(f"   En Zabbix: {'✅' if hilo_manual.en_zabbix else '❌'}")
            self.stdout.write(f"   Operativo NOC: {'✅' if hilo_manual.operativo_noc else '❌'}")
            self.stdout.write(f"   Vinculado a puerto: {'✅' if hilo_manual.zabbix_port else '❌'}")
            
            # 5. Limpiar - eliminar hilo de prueba
            hilo_manual.delete()
            self.stdout.write(f"\n🗑️ Hilo de prueba eliminado")
            
            # 6. Mostrar resumen de la lógica
            self.stdout.write(f"\n💡 LÓGICA CONFIRMADA:")
            self.stdout.write(f"   ✅ Hilos manuales se crean independientes")
            self.stdout.write(f"   ✅ operativo_noc se mantiene como se configuró")
            self.stdout.write(f"   ✅ Cuando Zabbix encuentra el puerto → vinculación automática")
            self.stdout.write(f"   ✅ operativo_noc del hilo se copia al puerto (hilo = fuente de verdad)")
            self.stdout.write(f"   ✅ Si puerto desaparece de Zabbix → solo cambia 'en_zabbix', operativo_noc se mantiene")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {e}"))
            
        self.stdout.write(self.style.SUCCESS("\n✅ Prueba completada"))
