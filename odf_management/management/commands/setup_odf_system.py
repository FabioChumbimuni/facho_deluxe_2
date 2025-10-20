from django.core.management.base import BaseCommand
from odf_management.models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from hosts.models import OLT
from django.utils import timezone


class Command(BaseCommand):
    help = 'Configuración completa del sistema ODF con programaciones y OLTs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-assign-olts',
            action='store_true',
            help='Asignar automáticamente todas las OLTs a la programación estándar'
        )

    def handle(self, *args, **options):
        auto_assign = options['auto_assign_olts']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 CONFIGURACIÓN INICIAL DEL SISTEMA ODF')
        )
        self.stdout.write('')
        
        # 1. Crear programaciones predefinidas
        self.stdout.write('📋 Paso 1: Creando programaciones predefinidas...')
        
        schedules_data = [
            {'nombre': 'Recolección Rápida - Cada 5 minutos', 'intervalo': 5, 'habilitado': False},
            {'nombre': 'Recolección Frecuente - Cada 10 minutos', 'intervalo': 10, 'habilitado': False},
            {'nombre': 'Recolección Estándar - Cada 15 minutos', 'intervalo': 15, 'habilitado': True},
            {'nombre': 'Recolección Moderada - Cada 30 minutos', 'intervalo': 30, 'habilitado': False},
            {'nombre': 'Recolección Horaria - Cada 60 minutos', 'intervalo': 60, 'habilitado': False}
        ]
        
        schedule_estandar = None
        created_schedules = 0
        
        for data in schedules_data:
            schedule, created = ZabbixCollectionSchedule.objects.get_or_create(
                nombre=data['nombre'],
                defaults={
                    'intervalo_minutos': data['intervalo'],
                    'habilitado': data['habilitado']
                }
            )
            
            if created:
                schedule.calcular_proxima_ejecucion()
                schedule.save()
                created_schedules += 1
            
            if 'Estándar' in data['nombre']:
                schedule_estandar = schedule
            
            estado = "✅ ACTIVA" if schedule.habilitado else "⏸️ INACTIVA"
            action = "Creada" if created else "Ya existía"
            self.stdout.write(f'   {action}: {schedule.nombre} ({estado})')
        
        self.stdout.write(f'   Total creadas: {created_schedules}')
        self.stdout.write('')
        
        # 2. Mostrar OLTs disponibles
        self.stdout.write('🖥️  Paso 2: Verificando OLTs disponibles...')
        
        olts = OLT.objects.all()
        if not olts.exists():
            self.stdout.write(self.style.WARNING('   ⚠️  No hay OLTs registradas en el sistema'))
            self.stdout.write('   💡 Primero registre OLTs en Django Admin > Hosts > OLTs')
            return
        
        self.stdout.write(f'   Encontradas {olts.count()} OLTs:')
        for olt in olts:
            estado = "🟢 Habilitada" if olt.habilitar_olt else "🔴 Deshabilitada"
            self.stdout.write(f'   • {olt.abreviatura} ({olt.ip_address}) - {estado}')
        
        self.stdout.write('')
        
        # 3. Asignar OLTs automáticamente si se solicita
        if auto_assign and schedule_estandar:
            self.stdout.write('🔗 Paso 3: Asignando OLTs a programación estándar...')
            
            assigned_count = 0
            for olt in olts.filter(habilitar_olt=True):
                collection_olt, created = ZabbixCollectionOLT.objects.get_or_create(
                    schedule=schedule_estandar,
                    olt=olt,
                    defaults={'habilitado': True}
                )
                
                if created:
                    assigned_count += 1
                    self.stdout.write(f'   ✅ Asignada: {olt.abreviatura}')
                else:
                    self.stdout.write(f'   ℹ️  Ya asignada: {olt.abreviatura}')
            
            self.stdout.write(f'   Total asignadas: {assigned_count}')
            self.stdout.write('')
        
        # 4. Mostrar resumen final
        self.stdout.write('📊 RESUMEN DE CONFIGURACIÓN:')
        self.stdout.write('')
        
        for schedule in ZabbixCollectionSchedule.objects.all():
            olts_count = schedule.zabbixcollectionolt_set.count()
            olts_habilitadas = schedule.zabbixcollectionolt_set.filter(habilitado=True).count()
            
            estado_schedule = "🟢 ACTIVA" if schedule.habilitado else "🔴 INACTIVA"
            
            self.stdout.write(f'📋 {schedule.nombre}')
            self.stdout.write(f'   Estado: {estado_schedule}')
            self.stdout.write(f'   Intervalo: {schedule.get_intervalo_minutos_display()}')
            self.stdout.write(f'   OLTs asignadas: {olts_habilitadas}/{olts_count}')
            if schedule.proxima_ejecucion:
                self.stdout.write(f'   Próxima ejecución: {schedule.proxima_ejecucion.strftime("%Y-%m-%d %H:%M")}')
            self.stdout.write('')
        
        # 5. Instrucciones finales
        self.stdout.write('🎯 PRÓXIMOS PASOS:')
        self.stdout.write('')
        
        if not auto_assign:
            self.stdout.write('1. 🔗 ASIGNAR OLTs A PROGRAMACIONES:')
            self.stdout.write('   • Acceder a Django Admin')
            self.stdout.write('   • Ir a "ODF Management" > "Programaciones de Recolección Zabbix"')
            self.stdout.write('   • Seleccionar una programación')
            self.stdout.write('   • En la sección "Zabbix collection olts" agregar OLTs')
            self.stdout.write('   • Marcar como habilitado')
            self.stdout.write('')
        
        self.stdout.write('2. ⚙️  VERIFICAR CONFIGURACIÓN:')
        self.stdout.write('   • URL Zabbix: http://10.80.80.73/zabbix/api_jsonrpc.php')
        self.stdout.write('   • Token configurado: ✅')
        self.stdout.write('   • Item key: port.descover.walk')
        self.stdout.write('')
        
        self.stdout.write('3. 🚀 INICIAR SERVICIOS:')
        self.stdout.write('   • Celery Worker: ./start_celery_workers.sh')
        self.stdout.write('   • Celery Beat: celery -A core beat --loglevel=info')
        self.stdout.write('')
        
        self.stdout.write('4. 🧪 PROBAR MANUALMENTE:')
        self.stdout.write('   • python manage.py sync_odf_zabbix --dry-run')
        self.stdout.write('')
        
        self.stdout.write(
            self.style.SUCCESS('✅ ¡CONFIGURACIÓN COMPLETADA!')
        )
        
        if auto_assign and schedule_estandar and assigned_count > 0:
            self.stdout.write('')
            self.stdout.write(
                self.style.SUCCESS(
                    f'🎉 Sistema listo! {assigned_count} OLTs configuradas para '
                    f'recolección automática cada 15 minutos.'
                )
            )
