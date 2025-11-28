"""
Comando para asignar ejecuciones activas a pollers
Útil cuando hay ejecuciones RUNNING sin poller asociado
"""
from django.core.management.base import BaseCommand
from executions.models import Execution
from zabbix_pollers.tasks import get_poller_manager
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Asigna ejecuciones activas a pollers libres'

    def handle(self, *args, **options):
        pm = get_poller_manager()
        
        self.stdout.write('=== ASIGNANDO EJECUCIONES ACTIVAS A POLLERS ===\n')
        
        # Buscar todas las ejecuciones activas
        active = Execution.objects.filter(
            status__in=['PENDING', 'RUNNING'],
            workflow_node__isnull=False
        ).select_related('workflow_node', 'olt').order_by('-created_at')
        
        self.stdout.write(f'Total ejecuciones activas: {active.count()}\n')
        
        assigned_count = 0
        for e in active:
            # Verificar si algún poller ya la tiene
            has_poller = False
            for i, p in enumerate(pm.pollers):
                stats = p.get_stats()
                if stats.get("current_execution_id") == e.id:
                    has_poller = True
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ Execution {e.id}: Ya asignada a Poller {i}'
                    ))
                    break
            
            if not has_poller:
                # Buscar poller libre
                free_poller = None
                for i, p in enumerate(pm.pollers):
                    stats = p.get_stats()
                    if stats["status"] == "FREE":
                        free_poller = (i, p)
                        break
                
                if free_poller:
                    poller_idx, poller = free_poller
                    # Asignar execution al poller
                    with poller.lock:
                        poller.current_execution_id = e.id
                        poller.status = 'BUSY'
                    
                    # Guardar poller_id en execution
                    if not e.result_summary:
                        e.result_summary = {}
                    if isinstance(e.result_summary, dict):
                        e.result_summary['poller_id'] = poller_idx
                        e.save(update_fields=['result_summary'])
                    
                    node_type = 'MASTER' if not e.workflow_node.is_chain_node else 'CADENA'
                    self.stdout.write(self.style.SUCCESS(
                        f'✅ Execution {e.id}: Asignada a Poller {poller_idx} '
                        f'({e.workflow_node.name} - {node_type} - {e.olt.abreviatura})'
                    ))
                    assigned_count += 1
                else:
                    node_type = 'MASTER' if not e.workflow_node.is_chain_node else 'CADENA'
                    self.stdout.write(self.style.WARNING(
                        f'⚠️ Execution {e.id}: No hay pollers libres '
                        f'({e.workflow_node.name} - {node_type} - {e.olt.abreviatura})'
                    ))
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Asignadas: {assigned_count} de {active.count()}'))
        
        # Mostrar estado final
        self.stdout.write('\n=== ESTADO DE POLLERS ===\n')
        busy_count = 0
        for i, p in enumerate(pm.pollers):
            stats = p.get_stats()
            if stats["status"] == "BUSY":
                busy_count += 1
                self.stdout.write(
                    f'Poller {i}: BUSY - Execution {stats.get("current_execution_id")} - '
                    f'{stats.get("current_node_name")}'
                )
        
        self.stdout.write(f'\nTotal pollers ocupados: {busy_count} de {len(pm.pollers)}')

