from django.core.management.base import BaseCommand
from odf_management.models import ZabbixCollectionSchedule
from django.utils import timezone


class Command(BaseCommand):
    help = 'Inicializa programaciones predefinidas de recolección'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Fuerza la creación aunque ya existan programaciones'
        )

    def handle(self, *args, **options):
        force = options['force']
        
        # Programaciones predefinidas
        schedules_predefinidos = [
            {
                'nombre': 'Recolección Rápida - Cada 5 minutos',
                'intervalo_minutos': 5,
                'habilitado': False  # Deshabilitado por defecto
            },
            {
                'nombre': 'Recolección Frecuente - Cada 10 minutos', 
                'intervalo_minutos': 10,
                'habilitado': False
            },
            {
                'nombre': 'Recolección Estándar - Cada 15 minutos',
                'intervalo_minutos': 15,
                'habilitado': True  # Habilitado por defecto
            },
            {
                'nombre': 'Recolección Moderada - Cada 30 minutos',
                'intervalo_minutos': 30,
                'habilitado': False
            },
            {
                'nombre': 'Recolección Horaria - Cada 60 minutos',
                'intervalo_minutos': 60,
                'habilitado': False
            }
        ]
        
        if not force and ZabbixCollectionSchedule.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    'Ya existen programaciones. Use --force para crear las predefinidas de todas formas.'
                )
            )
            return
        
        self.stdout.write('Creando programaciones predefinidas...')
        
        created_count = 0
        for schedule_data in schedules_predefinidos:
            schedule, created = ZabbixCollectionSchedule.objects.get_or_create(
                nombre=schedule_data['nombre'],
                defaults={
                    'intervalo_minutos': schedule_data['intervalo_minutos'],
                    'habilitado': schedule_data['habilitado']
                }
            )
            
            if created:
                # Calcular próxima ejecución
                schedule.calcular_proxima_ejecucion()
                schedule.save()
                created_count += 1
                
                estado = "✅ ACTIVA" if schedule.habilitado else "⏸️ INACTIVA"
                self.stdout.write(f'  • {schedule.nombre} ({estado})')
            else:
                self.stdout.write(f'  - {schedule.nombre} (ya existía)')
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(f'✅ {created_count} programaciones creadas exitosamente!')
        )
        
        if created_count > 0:
            self.stdout.write('')
            self.stdout.write('📋 PRÓXIMOS PASOS:')
            self.stdout.write('1. Acceder al Django Admin')
            self.stdout.write('2. Ir a "ODF Management" > "Programaciones de Recolección Zabbix"')
            self.stdout.write('3. Seleccionar la programación deseada')
            self.stdout.write('4. Agregar OLTs a la programación usando "OLTs en Programación"')
            self.stdout.write('5. Habilitar las programaciones necesarias')
            self.stdout.write('')
            self.stdout.write('⚠️  IMPORTANTE:')
            self.stdout.write('- Solo la programación "Estándar - 15 min" está habilitada por defecto')
            self.stdout.write('- Debe asociar OLTs manualmente a cada programación')
            self.stdout.write('- El sistema verificará cada minuto las programaciones activas')
            self.stdout.write('')
            self.stdout.write('🔧 CONFIGURACIÓN:')
            self.stdout.write('- Token Zabbix ya configurado en settings.py')
            self.stdout.write('- Item key: port.descover.walk')
            self.stdout.write('- Celery beat debe estar ejecutándose para el cron')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('¡Configuración inicial completada!'))
