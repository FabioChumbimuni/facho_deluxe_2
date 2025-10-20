from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from odf_management.services.zabbix_service import ZabbixService
import os


class Command(BaseCommand):
    help = 'Sincroniza datos básicos de puertos desde Zabbix usando el item master'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zabbix-url',
            type=str,
            help='URL del servidor Zabbix (ej: http://zabbix.example.com/api_jsonrpc.php)',
            default=os.getenv('ZABBIX_URL', 'http://10.80.80.73/zabbix/api_jsonrpc.php')
        )
        parser.add_argument(
            '--token',
            type=str,
            help='Token de autenticación de Zabbix',
            default=os.getenv('ZABBIX_TOKEN', '1c5a2f49f420e8fd82e0a66064c764765ff5dc4dbd59af0c8313f7d1f57f8b24')
        )
        parser.add_argument(
            '--item-key',
            type=str,
            help='Clave del item master en Zabbix',
            default='port.descover.walk'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecuta en modo de prueba sin hacer cambios'
        )

    def handle(self, *args, **options):
        zabbix_url = options['zabbix_url']
        token = options['token']
        item_key = options['item_key']
        dry_run = options['dry_run']

        # Validar parámetros requeridos
        if not zabbix_url:
            raise CommandError(
                'URL de Zabbix es requerida. '
                'Usar --zabbix-url o definir ZABBIX_URL en variables de entorno.'
            )
        
        if not token:
            raise CommandError(
                'Token de Zabbix es requerido. '
                'Usar --token o definir ZABBIX_TOKEN en variables de entorno.'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Iniciando sincronización de puertos desde Zabbix...'
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO PRUEBA: No se realizarán cambios en la base de datos')
            )

        try:
            # Crear servicio de Zabbix
            zabbix_service = ZabbixService(zabbix_url, token)
            
            if dry_run:
                # En modo prueba, solo obtener y mostrar datos
                self.stdout.write('Obteniendo datos desde Zabbix...')
                items = zabbix_service.get_item_master_data(item_key)
                
                if not items:
                    self.stdout.write(
                        self.style.ERROR(f'No se encontraron items con clave: {item_key}')
                    )
                    return
                
                self.stdout.write(
                    self.style.SUCCESS(f'Encontrados {len(items)} items en Zabbix:')
                )
                
                for item in items:
                    host_info = item.get('hosts', [{}])[0]
                    host_name = host_info.get('name', 'N/A')
                    
                    self.stdout.write(f'  - Item ID: {item["itemid"]}')
                    self.stdout.write(f'    Host: {host_name}')
                    self.stdout.write(f'    Nombre: {item["name"]}')
                    self.stdout.write(f'    Clave: {item["key_"]}')
                    
                    if item.get('lastvalue'):
                        ports_data = zabbix_service.parse_odf_data(item['lastvalue'], olt=None)
                        self.stdout.write(f'    Puertos parseados: {len(ports_data) if ports_data else 0}')
                    
                    self.stdout.write('')
                    
            else:
                # Ejecutar sincronización real
                stats = zabbix_service.sync_zabbix_ports(item_key)
                
                # Mostrar estadísticas
                self.stdout.write(
                    self.style.SUCCESS('Sincronización completada!')
                )
                self.stdout.write(f'Puertos creados: {stats["ports_created"]}')
                self.stdout.write(f'Puertos actualizados: {stats["ports_updated"]}')
                
                if stats["errors"] > 0:
                    self.stdout.write(
                        self.style.ERROR(f'Errores encontrados: {stats["errors"]}')
                    )
                
        except Exception as e:
            raise CommandError(f'Error durante la sincronización: {e}')

        self.stdout.write(
            self.style.SUCCESS('Proceso completado exitosamente!')
        )
