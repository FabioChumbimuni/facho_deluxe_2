"""
Comando para relacionar automáticamente todos los hilos ODF con las ONUs existentes.
Busca ONUs por slot/port en la misma OLT y las relaciona con el hilo correspondiente.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from odf_management.models import ODFHilos
from discovery.models import OnuIndexMap
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Relaciona automáticamente todos los hilos ODF con las ONUs existentes basándose en slot/port'

    def add_arguments(self, parser):
        parser.add_argument(
            '--olt-id',
            type=int,
            help='ID específico de OLT para procesar (si no se especifica, procesa todas)'
        )
        parser.add_argument(
            '--hilo-id',
            type=int,
            help='ID específico de hilo para procesar (si no se especifica, procesa todos)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué relaciones se harían sin aplicarlas realmente'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar reasignación incluso si la ONU ya tiene un hilo asignado'
        )

    def handle(self, *args, **options):
        olt_id = options.get('olt_id')
        hilo_id = options.get('hilo_id')
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS('🔗 RELACIONANDO HILOS ODF CON ONUs'))
        self.stdout.write('=' * 70)
        
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠️  MODO DRY-RUN - No se aplicarán cambios'))
        
        if force:
            self.stdout.write(self.style.WARNING('⚠️  MODO FORCE - Se reasignarán hilos incluso si ya tienen uno'))
        
        self.stdout.write('')
        
        # Determinar qué hilos procesar
        if hilo_id:
            try:
                hilos = [ODFHilos.objects.select_related('odf', 'odf__olt').get(id=hilo_id)]
                self.stdout.write(f'🎯 Procesando hilo específico ID: {hilo_id}')
            except ODFHilos.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ Hilo con ID {hilo_id} no encontrado'))
                return
        elif olt_id:
            try:
                olt = OLT.objects.get(id=olt_id)
                hilos = ODFHilos.objects.filter(
                    odf__olt=olt
                ).select_related('odf', 'odf__olt')
                self.stdout.write(f'🎯 Procesando OLT específica: {olt.abreviatura} (ID: {olt_id})')
                self.stdout.write(f'   Total hilos: {hilos.count()}')
            except OLT.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ OLT con ID {olt_id} no encontrada'))
                return
        else:
            hilos = ODFHilos.objects.all().select_related('odf', 'odf__olt')
            self.stdout.write(f'🌐 Procesando TODOS los hilos del sistema')
            self.stdout.write(f'   Total hilos: {hilos.count()}')
        
        self.stdout.write('')
        
        # Estadísticas
        stats = {
            'hilos_procesados': 0,
            'onus_relacionadas': 0,
            'onus_ya_relacionadas': 0,
            'hilos_sin_onus_disponibles': 0,  # Hilos sin ONUs sin hilo para relacionar
            'hilos_sin_onus_reales': 0,  # Hilos que realmente no tienen ONUs con ese slot/port
            'errores': 0
        }
        
        # Procesar cada hilo
        for hilo in hilos:
            try:
                resultado = self._relacionar_hilo_con_onus(hilo, dry_run, force)
                
                stats['hilos_procesados'] += 1
                stats['onus_relacionadas'] += resultado['relacionadas']
                stats['onus_ya_relacionadas'] += resultado['ya_relacionadas']
                
                if resultado.get('sin_onus', False):
                    if resultado.get('tiene_onus_pero_con_hilo', False):
                        stats['hilos_sin_onus_disponibles'] += 1
                    else:
                        stats['hilos_sin_onus_reales'] += 1
                
                # Mostrar progreso cada 100 hilos
                if stats['hilos_procesados'] % 100 == 0:
                    self.stdout.write(f'   ⏳ Procesados {stats["hilos_procesados"]} hilos...')
                    
            except Exception as e:
                stats['errores'] += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Error procesando hilo {hilo.id}: {str(e)}'
                    )
                )
        
        # Mostrar resumen final
        self.stdout.write('')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('📊 RESUMEN'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'   Hilos procesados: {stats["hilos_procesados"]}')
        self.stdout.write(f'   ✅ ONUs relacionadas (nuevas): {stats["onus_relacionadas"]}')
        self.stdout.write(f'   ℹ️  ONUs ya relacionadas con el hilo correcto: {stats["onus_ya_relacionadas"]}')
        
        # Mostrar información más clara sobre hilos sin ONUs
        if stats["hilos_sin_onus_reales"] > 0:
            self.stdout.write(
                f'   ⚠️  Hilos sin ONUs (no hay ONUs con ese slot/port): {stats["hilos_sin_onus_reales"]}'
            )
        
        if stats["hilos_sin_onus_disponibles"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'   ℹ️  Hilos sin ONUs disponibles (todas sus ONUs ya tienen hilo): '
                    f'{stats["hilos_sin_onus_disponibles"]}'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    '      (Esto es normal si las ONUs ya están relacionadas correctamente)'
                )
            )
        
        # Resumen general
        if stats["onus_relacionadas"] == 0 and stats["hilos_sin_onus_disponibles"] > 0:
            self.stdout.write('')
            self.stdout.write(
                self.style.SUCCESS(
                    '   ✅ CONCLUSIÓN: No hay ONUs sin hilo para relacionar.'
                )
            )
            self.stdout.write(
                '      Esto significa que las ONUs ya están relacionadas o no tienen hilos correspondientes.'
            )
        
        if stats['errores'] > 0:
            self.stdout.write(
                self.style.ERROR(f'   ❌ Errores: {stats["errores"]}')
            )
        
        if dry_run:
            self.stdout.write('')
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  MODO DRY-RUN - Ejecuta sin --dry-run para aplicar los cambios'
                )
            )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Proceso completado'))
    
    def _relacionar_hilo_con_onus(self, hilo, dry_run=False, force=False):
        """
        Relaciona un hilo específico con todas las ONUs que coincidan.
        
        Returns:
            dict: {'relacionadas': int, 'ya_relacionadas': int, 'sin_onus': bool}
        """
        resultado = {
            'relacionadas': 0,
            'ya_relacionadas': 0,
            'sin_onus': False
        }
        
        # Buscar TODAS las ONUs con el mismo slot/port en la misma OLT (sin importar si tienen hilo)
        onus_todas = OnuIndexMap.objects.filter(
            olt=hilo.odf.olt,
            slot=hilo.slot,
            port=hilo.port
        )
        
        total_onus_matching = onus_todas.count()
        
        if total_onus_matching == 0:
            # Realmente no hay ONUs con este slot/port en esta OLT
            resultado['sin_onus'] = True
            resultado['tiene_onus_pero_con_hilo'] = False
            return resultado
        
        # Separar ONUs según su estado de relación
        onus_ya_con_este_hilo = [onu for onu in onus_todas if onu.odf_hilo_id == hilo.id]
        onus_sin_hilo = [onu for onu in onus_todas if onu.odf_hilo_id is None]
        onus_con_otro_hilo = [onu for onu in onus_todas if onu.odf_hilo_id is not None and onu.odf_hilo_id != hilo.id]
        
        resultado['ya_relacionadas'] = len(onus_ya_con_este_hilo)
        
        # ONUs que necesitan ser relacionadas con este hilo
        if force:
            # Si es force, relacionar todas las que no tienen este hilo específico
            onus_a_relacionar = onus_sin_hilo + onus_con_otro_hilo
        else:
            # Sin force, solo las que no tienen hilo asignado
            onus_a_relacionar = onus_sin_hilo
        
        if not onus_a_relacionar:
            # Hay ONUs pero todas ya tienen hilo (este u otro)
            resultado['sin_onus'] = True
            resultado['tiene_onus_pero_con_hilo'] = True
            return resultado
        
        # Hay ONUs para relacionar
        resultado['sin_onus'] = False
        
        if dry_run:
            # Solo mostrar qué se haría
            for onu in onus_a_relacionar:
                estado_actual = f'hilo {onu.odf_hilo_id}' if onu.odf_hilo_id else 'sin hilo'
                self.stdout.write(
                    f'   🔗 [DRY-RUN] ONU {onu.normalized_id} ({onu.slot}/{onu.port}) '
                    f'de {estado_actual} → hilo {hilo.id}'
                )
        else:
            # Relacionar en la base de datos usando bulk_update para mejor rendimiento
            with transaction.atomic():
                # Actualizar todas las ONUs de una vez usando bulk_update
                if len(onus_a_relacionar) > 0:
                    for onu in onus_a_relacionar:
                        onu.odf_hilo = hilo
                    
                    # Usar bulk_update para actualizar todas de una vez (más eficiente)
                    OnuIndexMap.objects.bulk_update(onus_a_relacionar, ['odf_hilo'])
        
        resultado['relacionadas'] = len(onus_a_relacionar)
        
        return resultado

