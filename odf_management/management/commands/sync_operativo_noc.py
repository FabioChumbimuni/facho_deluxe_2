"""
Comando para sincronizar el campo operativo_noc entre ODFHilos y ZabbixPortData
"""

from django.core.management.base import BaseCommand
from odf_management.models import ODFHilos, ZabbixPortData


class Command(BaseCommand):
    help = 'Sincroniza el campo operativo_noc entre ODFHilos y ZabbixPortData'

    def add_arguments(self, parser):
        parser.add_argument(
            '--direccion',
            choices=['hilo_a_puerto', 'puerto_a_hilo', 'auto'],
            default='auto',
            help='Dirección de sincronización (default: auto)'
        )
        parser.add_argument(
            '--hilo-id',
            type=int,
            help='Sincronizar solo un hilo específico por ID'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar cambios sin aplicarlos'
        )

    def handle(self, *args, **options):
        direccion = options['direccion']
        hilo_id = options.get('hilo_id')
        dry_run = options['dry_run']
        
        self.stdout.write("🔄 SINCRONIZACIÓN DE OPERATIVO NOC")
        self.stdout.write("=" * 50)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("⚠️ MODO DRY-RUN - No se aplicarán cambios"))
        
        # Determinar hilos a procesar
        if hilo_id:
            try:
                hilos = [ODFHilos.objects.get(id=hilo_id)]
                self.stdout.write(f"🎯 Procesando hilo específico ID: {hilo_id}")
            except ODFHilos.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Hilo con ID {hilo_id} no encontrado"))
                return
        else:
            hilos = ODFHilos.objects.all().select_related('zabbix_port', 'odf__olt')
            self.stdout.write(f"🔍 Procesando todos los hilos ({hilos.count()})")
        
        stats = {
            'procesados': 0,
            'sincronizados': 0,
            'auto_asociados': 0,
            'sin_puerto': 0,
            'ya_sincronizados': 0,
            'errores': 0
        }
        
        for hilo in hilos:
            stats['procesados'] += 1
            
            try:
                self.stdout.write(f"\n📋 Procesando Hilo ID {hilo.id}:")
                self.stdout.write(f"   ODF: {hilo.odf}")
                self.stdout.write(f"   Slot/Port: {hilo.slot}/{hilo.port}")
                self.stdout.write(f"   Operativo NOC (hilo): {hilo.operativo_noc}")
                
                if hilo.zabbix_port:
                    self.stdout.write(f"   Puerto Zabbix ID: {hilo.zabbix_port.id}")
                    self.stdout.write(f"   Operativo NOC (puerto): {hilo.zabbix_port.operativo_noc}")
                    
                    if hilo.operativo_noc != hilo.zabbix_port.operativo_noc:
                        if not dry_run:
                            if direccion == 'auto' or direccion == 'hilo_a_puerto':
                                hilo.zabbix_port.operativo_noc = hilo.operativo_noc
                                hilo.zabbix_port.save()
                                self.stdout.write(f"   ✅ Sincronizado: Puerto → {hilo.operativo_noc}")
                            else:  # puerto_a_hilo
                                hilo.operativo_noc = hilo.zabbix_port.operativo_noc
                                hilo.save()
                                self.stdout.write(f"   ✅ Sincronizado: Hilo → {hilo.zabbix_port.operativo_noc}")
                        else:
                            self.stdout.write(f"   🔄 Sería sincronizado: {hilo.operativo_noc} ↔ {hilo.zabbix_port.operativo_noc}")
                        
                        stats['sincronizados'] += 1
                    else:
                        self.stdout.write(f"   ✅ Ya sincronizado")
                        stats['ya_sincronizados'] += 1
                else:
                    # Intentar auto-asociar
                    puertos_candidatos = ZabbixPortData.objects.filter(
                        olt=hilo.odf.olt,
                        slot=hilo.slot,
                        port=hilo.port,
                        disponible=True
                    )
                    
                    if puertos_candidatos.count() == 1:
                        puerto = puertos_candidatos.first()
                        self.stdout.write(f"   🔗 Puerto candidato encontrado: ID {puerto.id}")
                        self.stdout.write(f"   Operativo NOC (puerto): {puerto.operativo_noc}")
                        
                        if not dry_run:
                            hilo.zabbix_port = puerto
                            hilo.save()
                            
                            # Sincronizar después de asociar
                            if hilo.operativo_noc != puerto.operativo_noc:
                                puerto.operativo_noc = hilo.operativo_noc
                                puerto.save()
                                self.stdout.write(f"   ✅ Auto-asociado y sincronizado")
                            else:
                                self.stdout.write(f"   ✅ Auto-asociado (ya sincronizado)")
                        else:
                            self.stdout.write(f"   🔗 Sería auto-asociado con puerto ID {puerto.id}")
                        
                        stats['auto_asociados'] += 1
                    else:
                        self.stdout.write(f"   ⚠️ Sin puerto Zabbix asociado ({puertos_candidatos.count()} candidatos)")
                        stats['sin_puerto'] += 1
                        
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error: {e}"))
                stats['errores'] += 1
        
        # Resumen final
        self.stdout.write(f"\n📊 RESUMEN:")
        self.stdout.write(f"   Procesados: {stats['procesados']}")
        self.stdout.write(f"   Sincronizados: {stats['sincronizados']}")
        self.stdout.write(f"   Auto-asociados: {stats['auto_asociados']}")
        self.stdout.write(f"   Ya sincronizados: {stats['ya_sincronizados']}")
        self.stdout.write(f"   Sin puerto: {stats['sin_puerto']}")
        self.stdout.write(f"   Errores: {stats['errores']}")
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS("\n✅ Dry-run completado. Ejecuta sin --dry-run para aplicar cambios."))
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ Sincronización completada."))
