"""
Comando para programar una ejecución inmediata de prueba.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from odf_management.models import ZabbixCollectionSchedule


class Command(BaseCommand):
    help = 'Programa una ejecución de prueba para el próximo minuto'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schedule-name',
            type=str,
            default='PRUEBA CADA 5MIN',
            help='Nombre de la programación a ejecutar'
        )
        parser.add_argument(
            '--minutes',
            type=int,
            default=1,
            help='Minutos para la próxima ejecución (default: 1)'
        )

    def handle(self, *args, **options):
        schedule_name = options['schedule_name']
        minutes = options['minutes']
        
        try:
            schedule = ZabbixCollectionSchedule.objects.get(nombre=schedule_name)
            
            # Programar para X minutos
            proxima = timezone.now() + timedelta(minutes=minutes)
            schedule.proxima_ejecucion = proxima
            schedule.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Programación "{schedule_name}" actualizada')
            )
            self.stdout.write(f'⏰ Próxima ejecución: {proxima}')
            self.stdout.write(f'🕐 Hora actual: {timezone.now()}')
            self.stdout.write(f'⏳ Se ejecutará en {minutes} minuto(s)')
            
            # Verificar OLTs
            olts = schedule.zabbixcollectionolt_set.filter(habilitado=True)
            self.stdout.write(f'🖥️ OLTs que se sincronizarán: {olts.count()}')
            for olt_config in olts:
                self.stdout.write(f'   • {olt_config.olt.abreviatura}')
            
            self.stdout.write(
                self.style.WARNING(f'\n📊 Monitorear con: python manage.py start_odf_scheduler --mode status')
            )
            
        except ZabbixCollectionSchedule.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'❌ Programación "{schedule_name}" no encontrada')
            )
            
            # Mostrar programaciones disponibles
            schedules = ZabbixCollectionSchedule.objects.all()
            if schedules:
                self.stdout.write('📅 Programaciones disponibles:')
                for s in schedules:
                    status = "✅ Activa" if s.habilitado else "❌ Inactiva"
                    self.stdout.write(f'   • {s.nombre} ({status})')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error: {e}')
            )
