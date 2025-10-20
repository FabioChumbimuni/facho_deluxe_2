from django.core.management.base import BaseCommand
from odf_management.models import ZabbixPortData
from hosts.models import OLT
from django.utils import timezone


class Command(BaseCommand):
    help = 'Simula datos de puertos para probar el sistema mientras se configura Zabbix'

    def add_arguments(self, parser):
        parser.add_argument(
            '--olt',
            type=str,
            help='Abreviatura de la OLT (ej: CHO-14)',
            default='CHO-14'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Limpiar datos simulados existentes'
        )

    def handle(self, *args, **options):
        olt_abreviatura = options['olt']
        clear_data = options['clear']
        
        if clear_data:
            count = ZabbixPortData.objects.all().delete()[0]
            self.stdout.write(
                self.style.SUCCESS(f'🗑️ Eliminados {count} datos simulados')
            )
            return
        
        self.stdout.write('🧪 SIMULANDO DATOS DE PUERTOS PARA PRUEBAS')
        self.stdout.write('')
        
        # Buscar OLT
        try:
            olt = OLT.objects.get(abreviatura=olt_abreviatura)
            self.stdout.write(f'📡 OLT encontrada: {olt.abreviatura} ({olt.ip_address})')
        except OLT.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ OLT "{olt_abreviatura}" no encontrada')
            )
            return
        
        # Generar datos simulados basados en el formato real de Huawei
        ports_data = []
        
        # Simular slots 1-4, cada uno con 16 puertos (0-15)
        for slot in range(1, 5):
            for port in range(16):
                # Calcular SNMP index usando fórmula Huawei
                # BASE = 4194304000, slot*4096 + port*256
                snmp_index = 4194304000 + (slot * 4096) + (port * 256)
                
                interface_name = f"GPON 0/{slot}/{port}"
                
                # Generar descripciones variadas para simular datos reales
                descriptions = [
                    f":CHO-SANTAEULALIA{port+1}-24-O:{slot}-H:{port+1}",
                    f":CHO-RICARDOPALMA{port}-12-O:{slot}-H:{port+2}", 
                    f":CHOSICA-AA{port+1}-24-ODF:{slot}-HILO:{port+3}",
                    f":CHO-VILLARICA{port}-12-ODF:{slot}-HILO:{port+1}",
                    ""  # Algunos puertos sin descripción
                ]
                
                # Alternar descripciones (algunos con datos, otros vacíos)
                if (slot + port) % 3 == 0:
                    descripcion = ""  # Puerto sin usar
                else:
                    desc_index = (slot + port) % len(descriptions)
                    descripcion = descriptions[desc_index]
                
                ports_data.append({
                    'snmp_index': str(snmp_index),
                    'slot': slot,
                    'port': port,
                    'interface_name': interface_name,
                    'descripcion_zabbix': descripcion
                })
        
        self.stdout.write(f'📊 Generando {len(ports_data)} puertos simulados...')
        self.stdout.write('')
        
        # Crear registros en la base de datos
        created_count = 0
        updated_count = 0
        
        for port_data in ports_data:
            port, created = ZabbixPortData.objects.get_or_create(
                olt=olt,
                snmp_index=port_data['snmp_index'],
                defaults={
                    'slot': port_data['slot'],
                    'port': port_data['port'],
                    'interface_name': port_data['interface_name'],
                    'descripcion_zabbix': port_data['descripcion_zabbix'],
                    'last_sync': timezone.now()
                }
            )
            
            if created:
                created_count += 1
            else:
                # Actualizar datos existentes
                port.slot = port_data['slot']
                port.port = port_data['port']
                port.interface_name = port_data['interface_name']
                port.descripcion_zabbix = port_data['descripcion_zabbix']
                port.last_sync = timezone.now()
                port.save()
                updated_count += 1
        
        self.stdout.write('📈 RESUMEN DE SIMULACIÓN:')
        self.stdout.write(f'   ✅ Puertos creados: {created_count}')
        self.stdout.write(f'   🔄 Puertos actualizados: {updated_count}')
        self.stdout.write(f'   📡 OLT: {olt.abreviatura}')
        self.stdout.write('')
        
        # Mostrar estadísticas por slot
        self.stdout.write('📊 DISTRIBUCIÓN POR SLOTS:')
        for slot in range(1, 5):
            slot_ports = ZabbixPortData.objects.filter(olt=olt, slot=slot)
            con_descripcion = slot_ports.exclude(descripcion_zabbix='').count()
            sin_descripcion = slot_ports.filter(descripcion_zabbix='').count()
            
            self.stdout.write(f'   🔌 Slot {slot}: {con_descripcion} con datos, {sin_descripcion} vacíos')
        
        self.stdout.write('')
        self.stdout.write('🎯 PRÓXIMOS PASOS:')
        self.stdout.write('1. Acceder al Django Admin')
        self.stdout.write('2. Ir a "ODF Management" > "Datos de Puerto Zabbix"')
        self.stdout.write('3. Usar los filtros y acciones para agrupar puertos')
        self.stdout.write('4. Crear ODFs y asociar hilos usando los botones "➕ Crear Hilo"')
        self.stdout.write('')
        self.stdout.write('🧹 Para limpiar datos simulados: --clear')
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS('✅ ¡Datos simulados creados! El sistema está listo para pruebas.')
        )
