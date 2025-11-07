"""
Comando para reparar ONUs que no tienen OnuStatus pero deberían marcarse como DISABLED
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from discovery.models import OnuInventory, OnuStatus, OnuIndexMap


class Command(BaseCommand):
    help = 'Repara ONUs sin OnuStatus marcándolas como DISABLED'

    def add_arguments(self, parser):
        parser.add_argument(
            '--onu-id',
            type=int,
            help='ID específico de OnuInventory a reparar (opcional, si no se especifica repara todas)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin hacer cambios'
        )
        parser.add_argument(
            '--fix-inventory',
            action='store_true',
            help='También marcar el inventario como inactive (active=False)'
        )

    def handle(self, *args, **options):
        onu_id = options.get('onu_id')
        dry_run = options['dry_run']
        fix_inventory = options['fix_inventory']
        
        self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 MODO DRY-RUN - Sin hacer cambios reales"))
        else:
            self.stdout.write(self.style.WARNING("🔧 REPARANDO ONUs SIN ONUSTATUS"))
        self.stdout.write(self.style.WARNING(f"{'='*80}\n"))
        
        # Filtrar ONUs
        if onu_id:
            try:
                onus_query = OnuInventory.objects.filter(id=onu_id).select_related('onu_index')
            except OnuInventory.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ OnuInventory {onu_id} no encontrada"))
                return
        else:
            # Todas las ONUs que no tienen OnuStatus
            onus_query = OnuInventory.objects.select_related('onu_index').all()
        
        repaired_count = 0
        skipped_count = 0
        error_count = 0
        
        for onu in onus_query:
            try:
                # Verificar si tiene OnuStatus
                try:
                    status = onu.onu_index.status
                    self.stdout.write(f"⏭️  ONU {onu.onu_index.normalized_id} - Ya tiene OnuStatus (presence={status.presence})")
                    skipped_count += 1
                    continue
                    
                except OnuStatus.DoesNotExist:
                    # Esta ONU NO tiene OnuStatus
                    self.stdout.write(self.style.WARNING(f"\n❌ ONU {onu.onu_index.normalized_id} (ID: {onu.id}) - SIN ONUSTATUS"))
                    
                    if dry_run:
                        self.stdout.write(f"   [DRY-RUN] Se crearía OnuStatus con presence=DISABLED")
                        if fix_inventory and onu.active:
                            self.stdout.write(f"   [DRY-RUN] Se marcaría inventario como active=False")
                    else:
                        # Crear OnuStatus con presence=DISABLED
                        new_status = OnuStatus.objects.create(
                            onu_index=onu.onu_index,
                            olt=onu.olt,
                            presence='DISABLED',
                            last_state_value=0,
                            last_state_label='UNKNOWN',
                            consecutive_misses=1,
                            last_seen_at=None,
                            last_change_execution=None
                        )
                        self.stdout.write(self.style.SUCCESS(f"   ✅ OnuStatus creado (ID: {new_status.id}, presence=DISABLED)"))
                        
                        # Opcionalmente marcar inventario como inactivo
                        if fix_inventory and onu.active:
                            onu.active = False
                            onu.updated_at = timezone.now()
                            onu.save(update_fields=['active', 'updated_at'])
                            self.stdout.write(self.style.SUCCESS(f"   ✅ Inventario marcado como active=False"))
                    
                    repaired_count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Error procesando ONU {onu.id}: {str(e)}"))
                error_count += 1
        
        # Resumen
        self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
        self.stdout.write(self.style.WARNING("📊 RESUMEN:"))
        self.stdout.write(self.style.WARNING(f"{'='*80}"))
        self.stdout.write(f"✅ ONUs reparadas: {repaired_count}")
        self.stdout.write(f"⏭️  ONUs omitidas (ya tienen status): {skipped_count}")
        self.stdout.write(f"❌ Errores: {error_count}")
        
        if dry_run and repaired_count > 0:
            self.stdout.write(self.style.WARNING(f"\n⚠️  Esto fue un DRY-RUN. Para aplicar cambios ejecuta sin --dry-run"))
            if onu_id:
                self.stdout.write(f"   python manage.py reparar_onu_sin_status --onu-id {onu_id} --fix-inventory")
            else:
                self.stdout.write(f"   python manage.py reparar_onu_sin_status --fix-inventory")
        
        self.stdout.write(self.style.WARNING(f"\n{'='*80}\n"))

