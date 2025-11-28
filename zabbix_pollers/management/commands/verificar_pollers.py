"""
Comando para verificar el uso de pollers y el orden master -> cadena por OLT
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from executions.models import Execution
from zabbix_pollers.tasks import get_poller_manager
from snmp_jobs.models import WorkflowNode
from collections import defaultdict


class Command(BaseCommand):
    help = 'Verifica el uso de pollers y el orden master -> cadena por OLT'

    def add_arguments(self, parser):
        parser.add_argument(
            '--olt',
            type=str,
            help='Filtrar por OLT específica',
        )
        parser.add_argument(
            '--minutos',
            type=int,
            default=30,
            help='Minutos hacia atrás para verificar (default: 30)',
        )

    def handle(self, *args, **options):
        pm = get_poller_manager()
        olt_filter = options.get('olt')
        minutos = options.get('minutos', 30)
        
        now = timezone.now()
        desde = now - timedelta(minutes=minutos)
        
        self.stdout.write(self.style.SUCCESS(f'\n=== VERIFICACIÓN DE POLLERS (últimos {minutos} minutos) ===\n'))
        
        # 1. Estado actual de pollers
        self.stdout.write(self.style.WARNING('=== ESTADO ACTUAL DE POLLERS ===\n'))
        
        pollers_con_ejecuciones = []
        for i, p in enumerate(pm.pollers):
            stats = p.get_stats()
            
            # Verificar si tiene execution_id directo
            exec_directa = None
            if p.current_execution_id:
                try:
                    exec_directa = Execution.objects.select_related('workflow_node', 'olt').get(id=p.current_execution_id)
                except Execution.DoesNotExist:
                    pass
            
            # Verificar si get_stats() encontró alguna execution
            exec_stats = None
            if stats.get("current_node_id"):
                try:
                    execs = Execution.objects.filter(
                        workflow_node_id=stats["current_node_id"],
                        status__in=['PENDING', 'RUNNING']
                    ).order_by('-created_at').first()
                    if execs:
                        exec_stats = execs
                except Exception:
                    pass
            
            execution = exec_directa or exec_stats
            
            if execution or stats["status"] == "BUSY":
                pollers_con_ejecuciones.append((i, p, stats, execution))
                status_icon = '✅' if execution else '⚠️'
                self.stdout.write(f'{status_icon} Poller {i}:')
                self.stdout.write(f'   Status: {stats["status"]} | Busy: {stats["busy_percentage"]:.1f}%')
                if execution:
                    node_type = 'MASTER' if not execution.workflow_node.is_chain_node else 'CADENA'
                    self.stdout.write(f'   Execution {execution.id}: {execution.workflow_node.name} ({node_type})')
                    self.stdout.write(f'   OLT: {execution.olt.abreviatura} | Status: {execution.status}')
                self.stdout.write('')
        
        if not pollers_con_ejecuciones:
            self.stdout.write(self.style.WARNING('   ❌ Ningún poller tiene ejecuciones activas\n'))
        
        # 2. Ejecuciones activas
        self.stdout.write(self.style.WARNING('=== EJECUCIONES ACTIVAS (PENDING/RUNNING) ===\n'))
        
        active_executions = Execution.objects.filter(
            status__in=['PENDING', 'RUNNING'],
            workflow_node__isnull=False,
            created_at__gte=desde
        )
        
        if olt_filter:
            active_executions = active_executions.filter(olt__abreviatura=olt_filter)
        
        active_executions = active_executions.select_related('workflow_node', 'olt', 'workflow_node__workflow').order_by('-created_at')
        
        self.stdout.write(f'Total: {active_executions.count()}\n')
        
        executions_by_olt = defaultdict(list)
        for e in active_executions:
            executions_by_olt[e.olt.abreviatura].append(e)
            
            # Buscar poller asociado
            poller_found = None
            for i, p in enumerate(pm.pollers):
                if p.current_execution_id == e.id:
                    poller_found = i
                    break
            
            if poller_found is None:
                # Verificar en get_stats()
                for i, p in enumerate(pm.pollers):
                    stats = p.get_stats()
                    if stats.get("current_node_id") == e.workflow_node_id:
                        poller_found = i
                        break
            
            status_icon = '✅' if poller_found is not None else '❌'
            node_type = 'MASTER' if not e.workflow_node.is_chain_node else 'CADENA'
            master_ref = f" (master: {e.workflow_node.master_node.name})" if e.workflow_node.master_node else ""
            
            self.stdout.write(f'{status_icon} Execution {e.id}:')
            self.stdout.write(f'   OLT: {e.olt.abreviatura} | Node: {e.workflow_node.name} ({node_type}{master_ref})')
            self.stdout.write(f'   Status: {e.status} | Created: {e.created_at.strftime("%H:%M:%S")}')
            if poller_found is not None:
                self.stdout.write(f'   ✅ Poller: {poller_found}')
            else:
                self.stdout.write(f'   ❌ Poller: NINGUNO')
            self.stdout.write('')
        
        # 3. Verificación por OLT: orden master -> cadena
        self.stdout.write(self.style.WARNING('=== VERIFICACIÓN POR OLT: ORDEN MASTER -> CADENA ===\n'))
        
        # Buscar ejecuciones completadas recientes
        completed_executions = Execution.objects.filter(
            created_at__gte=desde,
            workflow_node__isnull=False,
            status__in=['SUCCESS', 'FAILED']
        )
        
        if olt_filter:
            completed_executions = completed_executions.filter(olt__abreviatura=olt_filter)
        
        completed_executions = completed_executions.select_related('workflow_node', 'olt').order_by('olt__abreviatura', 'created_at')
        
        completed_by_olt = defaultdict(list)
        for e in completed_executions:
            completed_by_olt[e.olt.abreviatura].append(e)
        
        problemas_encontrados = []
        
        for olt_name in sorted(completed_by_olt.keys()):
            execs = completed_by_olt[olt_name]
            
            # Separar master y cadena
            master_execs = [e for e in execs if not e.workflow_node.is_chain_node]
            chain_execs = [e for e in execs if e.workflow_node.is_chain_node]
            
            if not master_execs or not chain_execs:
                continue  # Solo verificar OLTs que tengan ambos tipos
            
            self.stdout.write(f'OLT: {olt_name}')
            self.stdout.write(f'  Master: {len(master_execs)} | Cadena: {len(chain_execs)}')
            
            # Verificar orden: cada cadena debe tener su master ejecutado antes
            for chain_exec in chain_execs:
                if not chain_exec.workflow_node.master_node:
                    continue
                
                # Buscar el master correspondiente
                master_exec = None
                for m in master_execs:
                    if m.workflow_node_id == chain_exec.workflow_node.master_node.id:
                        master_exec = m
                        break
                
                if master_exec:
                    if chain_exec.created_at < master_exec.created_at:
                        problemas_encontrados.append({
                            'olt': olt_name,
                            'problema': f'Cadena {chain_exec.workflow_node.name} ({chain_exec.created_at.strftime("%H:%M:%S")}) antes que Master {master_exec.workflow_node.name} ({master_exec.created_at.strftime("%H:%M:%S")})'
                        })
                        self.stdout.write(self.style.ERROR(
                            f'  ❌ PROBLEMA: Cadena ejecutada antes que Master'
                        ))
                        self.stdout.write(f'    Master: {master_exec.workflow_node.name} ({master_exec.created_at.strftime("%H:%M:%S")})')
                        self.stdout.write(f'    Cadena: {chain_exec.workflow_node.name} ({chain_exec.created_at.strftime("%H:%M:%S")})')
                    else:
                        self.stdout.write(self.style.SUCCESS(
                            f'  ✅ Orden correcto: Master ({master_exec.created_at.strftime("%H:%M:%S")}) -> Cadena ({chain_exec.created_at.strftime("%H:%M:%S")})'
                        ))
            
            # Mostrar orden de ejecución
            all_execs = sorted(execs, key=lambda x: x.created_at)
            self.stdout.write(f'  Orden de ejecución:')
            for e in all_execs[:10]:  # Primeras 10
                node_type = 'MASTER' if not e.workflow_node.is_chain_node else 'CADENA'
                status_icon = '✅' if e.status == 'SUCCESS' else '❌'
                self.stdout.write(f'    {e.created_at.strftime("%H:%M:%S")} - {status_icon} {e.workflow_node.name} ({node_type}) - {e.status}')
            self.stdout.write('')
        
        # Resumen
        self.stdout.write(self.style.SUCCESS('\n=== RESUMEN ===\n'))
        self.stdout.write(f'Pollers con ejecuciones activas: {len(pollers_con_ejecuciones)}')
        self.stdout.write(f'Ejecuciones activas: {active_executions.count()}')
        self.stdout.write(f'Problemas encontrados: {len(problemas_encontrados)}')
        
        if problemas_encontrados:
            self.stdout.write(self.style.ERROR('\n⚠️ PROBLEMAS ENCONTRADOS:'))
            for p in problemas_encontrados:
                self.stdout.write(self.style.ERROR(f"  - {p['olt']}: {p['problema']}"))
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ No se encontraron problemas en el orden master -> cadena'))

