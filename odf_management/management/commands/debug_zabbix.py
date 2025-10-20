from django.core.management.base import BaseCommand
from odf_management.services.zabbix_service import ZabbixService
import json
import os


class Command(BaseCommand):
    help = 'Debug detallado de la conexión con Zabbix'

    def handle(self, *args, **options):
        self.stdout.write('🔍 DEBUG DETALLADO DE ZABBIX')
        self.stdout.write('')
        
        # Configuración
        zabbix_url = os.getenv('ZABBIX_URL', 'http://10.80.80.73/zabbix/api_jsonrpc.php')
        token = os.getenv('ZABBIX_TOKEN', '1c5a2f49f420e8fd82e0a66064c764765ff5dc4dbd59af0c8313f7d1f57f8b24')
        item_key = 'port.descover.walk'
        
        self.stdout.write(f'📡 URL: {zabbix_url}')
        self.stdout.write(f'🔑 Token: {token[:20]}...')
        self.stdout.write(f'🗝️  Item Key: {item_key}')
        self.stdout.write('')
        
        # Crear servicio
        service = ZabbixService(zabbix_url, token)
        
        # Obtener items
        self.stdout.write('1️⃣ OBTENIENDO ITEMS...')
        items = service.get_item_master_data(item_key)
        
        if not items:
            self.stdout.write(self.style.ERROR('❌ No se encontraron items'))
            return
        
        self.stdout.write(f'✅ Encontrados {len(items)} items')
        self.stdout.write('')
        
        # Analizar cada item
        for i, item in enumerate(items, 1):
            self.stdout.write(f'📋 ITEM {i}:')
            self.stdout.write(f'   ID: {item.get("itemid")}')
            self.stdout.write(f'   Nombre: {item.get("name")}')
            self.stdout.write(f'   Clave: {item.get("key_")}')
            
            # Información del host
            hosts = item.get('hosts', [])
            if hosts:
                host = hosts[0]
                self.stdout.write(f'   Host: {host.get("name")} ({host.get("host")})')
            
            # Valor actual
            last_value = item.get('lastvalue')
            last_clock = item.get('lastclock')
            
            if last_value:
                self.stdout.write(f'   ✅ Tiene datos (timestamp: {last_clock})')
                self.stdout.write(f'   📊 Tamaño de datos: {len(last_value)} caracteres')
                
                # Mostrar primeras líneas
                lines = last_value.split('\n')[:5]
                self.stdout.write(f'   🔍 Primeras líneas:')
                for line in lines:
                    if line.strip():
                        self.stdout.write(f'      {line[:80]}...')
                
                # Intentar parsear (sin OLT específica en este debug)
                self.stdout.write('   🧮 Intentando parsear (sin fórmula - solo para debug)...')
                parsed_data = service.parse_odf_data(last_value, olt=None)
                self.stdout.write(f'   📈 Puertos parseados: {len(parsed_data) if parsed_data else 0}')
                
                if parsed_data:
                    # Mostrar algunos ejemplos
                    for j, port in enumerate(parsed_data[:3]):
                        self.stdout.write(f'      Puerto {j+1}: Slot {port["slot"]}, Port {port["port"]}, SNMP: {port["snmp_index"]}')
                
            else:
                self.stdout.write(f'   ⚠️  Sin datos (lastvalue está vacío)')
            
            self.stdout.write('')
        
        # Verificar OLTs en Django
        self.stdout.write('2️⃣ VERIFICANDO OLTs EN DJANGO...')
        from hosts.models import OLT
        
        olts = OLT.objects.filter(habilitar_olt=True)
        self.stdout.write(f'✅ OLTs habilitadas: {olts.count()}')
        
        for olt in olts:
            self.stdout.write(f'   • {olt.abreviatura} ({olt.ip_address})')
            
            # Buscar coincidencias con Zabbix
            coincidencias = []
            for item in items:
                hosts = item.get('hosts', [])
                for host in hosts:
                    if host.get('host') == olt.abreviatura or host.get('name') == olt.abreviatura:
                        coincidencias.append(f"Item {item.get('itemid')}")
            
            if coincidencias:
                self.stdout.write(f'     ✅ Coincide con: {", ".join(coincidencias)}')
            else:
                self.stdout.write(f'     ❌ No coincide con ningún host de Zabbix')
        
        self.stdout.write('')
        self.stdout.write('3️⃣ HOSTS DE ZABBIX DISPONIBLES:')
        hosts_zabbix = set()
        for item in items:
            for host in item.get('hosts', []):
                hosts_zabbix.add(f"{host.get('host')} ({host.get('name')})")
        
        for host in sorted(hosts_zabbix):
            self.stdout.write(f'   • {host}')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🔍 Debug completado!'))
