"""
Comando para estudiar ejecuciones generadas por plantillas
Analiza el orden, prioridades, dependencias y estadísticas
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, Count, Avg, Max, Min
from executions.models import Execution
from snmp_jobs.models import WorkflowNode, WorkflowEdge
from datetime import timedelta
import json


class Command(BaseCommand):
    help = 'Estudia las ejecuciones generadas por plantillas (workflow_node)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=18,
            help='Número de ejecuciones a analizar (default: 18)'
        )
        parser.add_argument(
            '--olt',
            type=int,
            help='ID de OLT específica para filtrar'
        )
        parser.add_argument(
            '--horas',
            type=int,
            default=24,
            help='Horas hacia atrás para buscar ejecuciones (default: 24)'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        olt_id = options.get('olt')
        horas = options['horas']
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('📊 ESTUDIO DE EJECUCIONES GENERADAS POR PLANTILLAS'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))
        
        # 1. Obtener ejecuciones (priorizar con workflow_node, pero también sin él)
        desde = timezone.now() - timedelta(hours=horas)
        
        # Primero intentar con workflow_node
        query = Execution.objects.filter(
            created_at__gte=desde
        ).select_related(
            'workflow_node',
            'workflow_node__template_node',
            'workflow_node__template_node__oid',
            'workflow_node__workflow',
            'workflow_node__workflow__olt',
            'snmp_job',
            'olt'
        ).order_by('-created_at')
        
        if olt_id:
            query = query.filter(olt_id=olt_id)
        
        ejecuciones = list(query[:limit])
        
        if not ejecuciones:
            self.stdout.write(self.style.WARNING(f'⚠️ No se encontraron ejecuciones en las últimas {horas} horas'))
            return
        
        con_workflow = sum(1 for e in ejecuciones if e.workflow_node)
        sin_workflow = len(ejecuciones) - con_workflow
        
        self.stdout.write(self.style.SUCCESS(f'✅ Encontradas {len(ejecuciones)} ejecuciones'))
        if con_workflow > 0:
            self.stdout.write(self.style.SUCCESS(f'   - Con workflow_node: {con_workflow}'))
        if sin_workflow > 0:
            self.stdout.write(self.style.WARNING(f'   - Sin workflow_node: {sin_workflow} (sistema legacy)\n'))
        else:
            self.stdout.write('\n')
        
        # 2. Análisis general
        self.analizar_general(ejecuciones)
        
        # 3. Análisis por orden de ejecución
        self.analizar_orden(ejecuciones)
        
        # 4. Análisis de prioridades
        self.analizar_prioridades(ejecuciones)
        
        # 5. Análisis de dependencias
        self.analizar_dependencias(ejecuciones)
        
        # 6. Análisis temporal
        self.analizar_temporal(ejecuciones)
        
        # 7. Detalle de cada ejecución
        self.mostrar_detalle(ejecuciones)
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*80))
        self.stdout.write(self.style.SUCCESS('✅ ESTUDIO COMPLETADO'))
        self.stdout.write(self.style.SUCCESS('='*80 + '\n'))

    def analizar_general(self, ejecuciones):
        """Análisis general de las ejecuciones"""
        self.stdout.write(self.style.HTTP_INFO('\n📈 ANÁLISIS GENERAL'))
        self.stdout.write('-'*80)
        
        total = len(ejecuciones)
        por_estado = {}
        por_tipo = {}
        por_olt = {}
        
        for exec in ejecuciones:
            # Por estado
            estado = exec.status
            por_estado[estado] = por_estado.get(estado, 0) + 1
            
            # Por tipo (descubrimiento/get)
            if exec.workflow_node and exec.workflow_node.template_node and exec.workflow_node.template_node.oid:
                tipo = 'descubrimiento' if exec.workflow_node.template_node.oid.espacio == 'descubrimiento' else 'get'
            elif exec.snmp_job:
                tipo = exec.snmp_job.job_type or 'desconocido'
            else:
                tipo = 'desconocido'
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
            
            # Por OLT
            olt_name = exec.olt.abreviatura if exec.olt else 'Sin OLT'
            por_olt[olt_name] = por_olt.get(olt_name, 0) + 1
        
        self.stdout.write(f'Total de ejecuciones: {total}')
        self.stdout.write(f'\n📊 Por Estado:')
        for estado, count in sorted(por_estado.items(), key=lambda x: -x[1]):
            porcentaje = (count / total) * 100
            emoji = '✅' if estado == 'SUCCESS' else '❌' if estado == 'FAILED' else '⏳' if estado == 'PENDING' else '🔄'
            self.stdout.write(f'  {emoji} {estado}: {count} ({porcentaje:.1f}%)')
        
        self.stdout.write(f'\n📊 Por Tipo:')
        for tipo, count in sorted(por_tipo.items(), key=lambda x: -x[1]):
            porcentaje = (count / total) * 100
            emoji = '🔍' if tipo == 'descubrimiento' else '📋' if tipo == 'get' else '❓'
            self.stdout.write(f'  {emoji} {tipo}: {count} ({porcentaje:.1f}%)')
        
        self.stdout.write(f'\n📊 Por OLT:')
        for olt_name, count in sorted(por_olt.items(), key=lambda x: -x[1]):
            self.stdout.write(f'  🏢 {olt_name}: {count} ejecuciones')

    def analizar_orden(self, ejecuciones):
        """Analiza el orden de ejecución (descubrimiento antes de descripción)"""
        self.stdout.write(self.style.HTTP_INFO('\n🔀 ANÁLISIS DE ORDEN DE EJECUCIÓN'))
        self.stdout.write('-'*80)
        
        # Agrupar por OLT y ordenar por tiempo
        ejecuciones_por_olt = {}
        for exec in ejecuciones:
            olt_id = exec.olt_id if exec.olt else None
            if olt_id not in ejecuciones_por_olt:
                ejecuciones_por_olt[olt_id] = []
            ejecuciones_por_olt[olt_id].append(exec)
        
        # Ordenar cada grupo por created_at
        for olt_id, execs in ejecuciones_por_olt.items():
            execs.sort(key=lambda x: x.created_at)
        
        problemas_orden = []
        correctos = 0
        
        for olt_id, execs in ejecuciones_por_olt.items():
            olt_name = execs[0].olt.abreviatura if execs[0].olt else 'Sin OLT'
            
            # Verificar que descubrimiento vaya antes de get
            descubrimiento_encontrado = False
            get_antes_de_discovery = []
            
            for i, exec in enumerate(execs):
                tipo = self.obtener_tipo(exec)
                
                if tipo == 'descubrimiento':
                    descubrimiento_encontrado = True
                elif tipo == 'get' and not descubrimiento_encontrado:
                    # GET ejecutado antes de descubrimiento
                    get_antes_de_discovery.append((i, exec))
            
            if get_antes_de_discovery:
                problemas_orden.append({
                    'olt': olt_name,
                    'problemas': get_antes_de_discovery
                })
            else:
                correctos += 1
        
        if problemas_orden:
            self.stdout.write(self.style.ERROR(f'\n❌ PROBLEMAS DE ORDEN DETECTADOS:'))
            for problema in problemas_orden:
                self.stdout.write(self.style.ERROR(f'\n  OLT: {problema["olt"]}'))
                for idx, exec in problema['problemas']:
                    self.stdout.write(self.style.ERROR(
                        f'    ⚠️ Ejecución #{idx+1} (ID: {exec.id}): GET ejecutado ANTES de descubrimiento'
                    ))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ ORDEN CORRECTO: Todas las ejecuciones respetan el orden (descubrimiento → get)'))
        
        self.stdout.write(f'\n📊 Resumen:')
        self.stdout.write(f'  ✅ OLTs con orden correcto: {correctos}')
        self.stdout.write(f'  ❌ OLTs con problemas: {len(problemas_orden)}')

    def analizar_prioridades(self, ejecuciones):
        """Analiza las prioridades asignadas"""
        self.stdout.write(self.style.HTTP_INFO('\n🎯 ANÁLISIS DE PRIORIDADES'))
        self.stdout.write('-'*80)
        
        prioridades_esperadas = {
            'descubrimiento': 90,
            'get': 40
        }
        
        problemas_prioridad = []
        correctos = 0
        
        for exec in ejecuciones:
            tipo = self.obtener_tipo(exec)
            prioridad_esperada = prioridades_esperadas.get(tipo, None)
            
            if prioridad_esperada:
                # La prioridad se asigna en el coordinador, no se guarda en Execution
                # Pero podemos verificar el tipo vs el orden de ejecución
                pass
        
        # Verificar que descubrimiento tenga mayor prioridad que get
        descubrimientos = [e for e in ejecuciones if self.obtener_tipo(e) == 'descubrimiento']
        gets = [e for e in ejecuciones if self.obtener_tipo(e) == 'get']
        
        self.stdout.write(f'\n📊 Distribución de Prioridades:')
        self.stdout.write(f'  🔍 Descubrimiento (P90): {len(descubrimientos)} ejecuciones')
        self.stdout.write(f'  📋 GET (P40): {len(gets)} ejecuciones')
        
        if len(descubrimientos) > 0 and len(gets) > 0:
            # Verificar que descubrimiento se ejecute primero en promedio
            avg_time_discovery = sum((e.created_at.timestamp() for e in descubrimientos)) / len(descubrimientos)
            avg_time_get = sum((e.created_at.timestamp() for e in gets)) / len(gets)
            
            if avg_time_discovery < avg_time_get:
                self.stdout.write(self.style.SUCCESS(f'\n✅ PRIORIDAD RESPETADA: Descubrimiento se ejecuta antes en promedio'))
            else:
                self.stdout.write(self.style.ERROR(f'\n❌ PROBLEMA DE PRIORIDAD: GET se ejecuta antes que descubrimiento en promedio'))

    def analizar_dependencias(self, ejecuciones):
        """Analiza las dependencias entre nodos"""
        self.stdout.write(self.style.HTTP_INFO('\n🔗 ANÁLISIS DE DEPENDENCIAS'))
        self.stdout.write('-'*80)
        
        # Agrupar por workflow
        ejecuciones_por_workflow = {}
        for exec in ejecuciones:
            if exec.workflow_node:
                workflow_id = exec.workflow_node.workflow_id
                if workflow_id not in ejecuciones_por_workflow:
                    ejecuciones_por_workflow[workflow_id] = []
                ejecuciones_por_workflow[workflow_id].append(exec)
        
        problemas_dependencias = []
        correctos = 0
        
        for workflow_id, execs in ejecuciones_por_workflow.items():
            # Obtener dependencias del workflow
            edges = WorkflowEdge.objects.filter(workflow_id=workflow_id).select_related('upstream_node', 'downstream_node')
            
            if not edges.exists():
                continue
            
            # Verificar que las dependencias se respeten
            for edge in edges:
                upstream = edge.upstream_node
                downstream = edge.downstream_node
                
                # Buscar ejecuciones de upstream y downstream
                exec_upstream = [e for e in execs if e.workflow_node_id == upstream.id]
                exec_downstream = [e for e in execs if e.workflow_node_id == downstream.id]
                
                if exec_upstream and exec_downstream:
                    # Verificar que upstream se ejecute antes
                    for exec_up in exec_upstream:
                        for exec_down in exec_downstream:
                            if exec_down.created_at < exec_up.created_at:
                                problemas_dependencias.append({
                                    'upstream': upstream.name,
                                    'downstream': downstream.name,
                                    'upstream_time': exec_up.created_at,
                                    'downstream_time': exec_down.created_at
                                })
                                break
        
        if problemas_dependencias:
            self.stdout.write(self.style.ERROR(f'\n❌ PROBLEMAS DE DEPENDENCIAS DETECTADOS:'))
            for problema in problemas_dependencias:
                self.stdout.write(self.style.ERROR(
                    f'  ⚠️ {problema["downstream"]} ejecutado ANTES de {problema["upstream"]}'
                ))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ DEPENDENCIAS RESPETADAS: Todas las dependencias se cumplen correctamente'))
        
        self.stdout.write(f'\n📊 Resumen:')
        self.stdout.write(f'  ✅ Dependencias correctas: {len(ejecuciones_por_workflow) - len(problemas_dependencias)} workflows')
        self.stdout.write(f'  ❌ Problemas detectados: {len(problemas_dependencias)}')

    def analizar_temporal(self, ejecuciones):
        """Análisis temporal de las ejecuciones"""
        self.stdout.write(self.style.HTTP_INFO('\n⏰ ANÁLISIS TEMPORAL'))
        self.stdout.write('-'*80)
        
        if not ejecuciones:
            return
        
        # Ordenar por tiempo
        ejecuciones_ordenadas = sorted(ejecuciones, key=lambda x: x.created_at)
        
        primera = ejecuciones_ordenadas[0]
        ultima = ejecuciones_ordenadas[-1]
        
        duracion_total = (ultima.created_at - primera.created_at).total_seconds()
        
        self.stdout.write(f'\n📅 Rango Temporal:')
        self.stdout.write(f'  Primera ejecución: {primera.created_at.strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'  Última ejecución: {ultima.created_at.strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'  Duración total: {duracion_total:.1f} segundos ({duracion_total/60:.1f} minutos)')
        
        # Calcular intervalos entre ejecuciones
        intervalos = []
        for i in range(1, len(ejecuciones_ordenadas)):
            intervalo = (ejecuciones_ordenadas[i].created_at - ejecuciones_ordenadas[i-1].created_at).total_seconds()
            intervalos.append(intervalo)
        
        if intervalos:
            self.stdout.write(f'\n⏱️ Intervalos entre ejecuciones:')
            self.stdout.write(f'  Promedio: {sum(intervalos)/len(intervalos):.1f} segundos')
            self.stdout.write(f'  Mínimo: {min(intervalos):.1f} segundos')
            self.stdout.write(f'  Máximo: {max(intervalos):.1f} segundos')
        
        # Duración de ejecuciones
        duraciones = [e.duration_ms for e in ejecuciones if e.duration_ms]
        if duraciones:
            self.stdout.write(f'\n⏱️ Duración de ejecuciones:')
            self.stdout.write(f'  Promedio: {sum(duraciones)/len(duraciones):.1f} ms')
            self.stdout.write(f'  Mínimo: {min(duraciones)} ms')
            self.stdout.write(f'  Máximo: {max(duraciones)} ms')

    def mostrar_detalle(self, ejecuciones):
        """Muestra el detalle de cada ejecución"""
        self.stdout.write(self.style.HTTP_INFO('\n📋 DETALLE DE EJECUCIONES'))
        self.stdout.write('-'*80)
        
        # Ordenar por tiempo
        ejecuciones_ordenadas = sorted(ejecuciones, key=lambda x: x.created_at)
        
        for i, exec in enumerate(ejecuciones_ordenadas, 1):
            tipo = self.obtener_tipo(exec)
            emoji_tipo = '🔍' if tipo == 'descubrimiento' else '📋' if tipo == 'get' else '❓'
            emoji_estado = '✅' if exec.status == 'SUCCESS' else '❌' if exec.status == 'FAILED' else '⏳' if exec.status == 'PENDING' else '🔄'
            
            self.stdout.write(f'\n{i}. {emoji_tipo} {emoji_estado} Ejecución #{exec.id}')
            self.stdout.write(f'   Nodo: {exec.workflow_node.name if exec.workflow_node else "N/A"}')
            self.stdout.write(f'   Tipo: {tipo}')
            self.stdout.write(f'   OLT: {exec.olt.abreviatura if exec.olt else "N/A"}')
            self.stdout.write(f'   Estado: {exec.status}')
            self.stdout.write(f'   Creada: {exec.created_at.strftime("%Y-%m-%d %H:%M:%S")}')
            if exec.started_at:
                self.stdout.write(f'   Iniciada: {exec.started_at.strftime("%Y-%m-%d %H:%M:%S")}')
            if exec.finished_at:
                self.stdout.write(f'   Finalizada: {exec.finished_at.strftime("%Y-%m-%d %H:%M:%S")}')
            if exec.duration_ms:
                self.stdout.write(f'   Duración: {exec.duration_ms} ms')
            if exec.error_message:
                self.stdout.write(self.style.ERROR(f'   Error: {exec.error_message[:100]}'))

    def obtener_tipo(self, exec):
        """Obtiene el tipo de ejecución (descubrimiento/get)"""
        if exec.workflow_node and exec.workflow_node.template_node and exec.workflow_node.template_node.oid:
            oid = exec.workflow_node.template_node.oid
            return 'descubrimiento' if oid.espacio == 'descubrimiento' else 'get'
        elif exec.snmp_job:
            return exec.snmp_job.job_type or 'desconocido'
        return 'desconocido'

