"""
Comando de gestión para sincronizar active y presence en ONUs
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from discovery.models import OnuInventory, OnuStatus


class Command(BaseCommand):
    help = 'Sincroniza el campo active de OnuInventory con presence de OnuStatus'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se corregiría sin aplicar cambios',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Aplica las correcciones automáticamente',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fix = options['fix']
        
        if not dry_run and not fix:
            self.stdout.write(self.style.WARNING(
                'Usa --dry-run para ver inconsistencias o --fix para corregirlas'
            ))
            return
        
        self.stdout.write(self.style.NOTICE('🔍 Buscando inconsistencias active ↔ presence...'))
        
        inconsistencias = 0
        corregidas = 0
        
        # Obtener todas las ONUs con su estado
        onus = OnuInventory.objects.select_related('onu_index__status').all()
        
        for onu in onus:
            if not hasattr(onu.onu_index, 'status'):
                continue
                
            status = onu.onu_index.status
            
            # Verificar inconsistencia
            esperado_presence = 'ENABLED' if onu.active else 'DISABLED'
            
            if status.presence != esperado_presence:
                inconsistencias += 1
                
                self.stdout.write(
                    f'⚠️  ONU {onu.id} ({onu.onu_index.normalized_id}): '
                    f'active={onu.active} pero presence={status.presence} '
                    f'(esperado: {esperado_presence})'
                )
                
                if fix:
                    status.presence = esperado_presence
                    status.save(update_fields=['presence', 'updated_at'])
                    corregidas += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'   ✅ Corregido a presence={esperado_presence}')
                    )
        
        # Resumen
        self.stdout.write('')
        if inconsistencias == 0:
            self.stdout.write(self.style.SUCCESS('✅ No se encontraron inconsistencias'))
        else:
            if fix:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ {corregidas} de {inconsistencias} inconsistencias corregidas')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  Se encontraron {inconsistencias} inconsistencias. '
                        f'Usa --fix para corregirlas'
                    )
                )

