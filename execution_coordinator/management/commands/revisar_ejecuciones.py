"""
Comando para revisar las ejecuciones actuales y verificar que se cumplan los intervalos programados
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from executions.models import Execution
from snmp_jobs.models import SnmpJobHost
from hosts.models import OLT


class Command(BaseCommand):
    help = 'Revisa las ejecuciones recientes y verifica que se cumplan los intervalos programados'

    def add_arguments(self, parser):
        parser.add_argument(
            '--horas',
            type=int,
            default=2,
            help='Número de horas hacia atrás para revisar (default: 2)'
        )
        parser.add_argument(
            '--olt',
            type=int,
            help='ID de OLT específica para revisar (opcional)'
        )
        parser.add_argument(
            '--detallado',
            action='store_true',
            help='Mostrar detalles de cada ejecución'
        )

    def handle(self, *args, **options):
        horas = options['horas']
        olt_id = options.get('olt')
        detallado = options['detallado']
        
        self.stdout.write(self.style.SUCCESS(f'\n🔍 REVISIÓN DE EJECUCIONES (últimas {horas} horas)\n'))
        self.stdout.write('=' * 100)
        
        # Calcular tiempo de inicio
        ahora = timezone.now()
        desde = ahora - timedelta(hours=horas)
        
        # Obtener ejecuciones
        ejecuciones = Execution.objects.filter(
            created_at__gte=desde
        ).select_related('snmp_job', 'olt', 'job_host').order_by('olt_id', 'snmp_job_id', 'created_at')
        
        if olt_id:
            ejecuciones = ejecuciones.filter(olt_id=olt_id)
        
        if not ejecuciones.exists():
            self.stdout.write(self.style.WARNING(f'⚠️ No se encontraron ejecuciones en las últimas {horas} horas'))
            return
        
        # Agrupar por OLT y Job
        ejecuciones_por_olt_job = {}
        for exec in ejecuciones:
            if not exec.olt or not exec.snmp_job or not exec.job_host:
                continue
            
            key = (exec.olt.id, exec.snmp_job.id)
            if key not in ejecuciones_por_olt_job:
                ejecuciones_por_olt_job[key] = {
                    'olt': exec.olt,
                    'job': exec.snmp_job,
                    'job_host': exec.job_host,
                    'ejecuciones': []
                }
            ejecuciones_por_olt_job[key]['ejecuciones'].append(exec)
        
        # Analizar cada grupo
        problemas_encontrados = []
        total_analizadas = 0
        total_correctas = 0
        total_problemas = 0
        
        for (olt_id, job_id), datos in ejecuciones_por_olt_job.items():
            olt = datos['olt']
            job = datos['job']
            job_host = datos['job_host']
            ejecs = sorted(datos['ejecuciones'], key=lambda x: x.created_at)
            
            intervalo_configurado = job.interval_seconds or 300  # Default 5 min
            intervalo_minimo = intervalo_configurado * 0.8  # 80% del intervalo (tolerancia)
            
            self.stdout.write(f"\n📡 OLT: {olt.abreviatura} ({olt.ip_address})")
            self.stdout.write(f"   Tarea: {job.nombre} ({job.job_type})")
            self.stdout.write(f"   Intervalo configurado: {intervalo_configurado}s ({intervalo_configurado/60:.1f} min)")
            self.stdout.write(f"   Ejecuciones encontradas: {len(ejecs)}")
            
            if job_host.next_run_at:
                tiempo_restante = (job_host.next_run_at - ahora).total_seconds()
                if tiempo_restante > 0:
                    self.stdout.write(f"   ⏰ Próxima ejecución programada: {job_host.next_run_at.strftime('%Y-%m-%d %H:%M:%S')} (en {tiempo_restante/60:.1f} min)")
                else:
                    self.stdout.write(self.style.WARNING(f"   ⚠️ Próxima ejecución programada: {job_host.next_run_at.strftime('%Y-%m-%d %H:%M:%S')} (PASADA - debería ejecutarse ya)"))
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ next_run_at NO CONFIGURADO"))
            
            if job_host.last_run_at:
                tiempo_desde_ultima = (ahora - job_host.last_run_at).total_seconds()
                self.stdout.write(f"   📅 Última ejecución: {job_host.last_run_at.strftime('%Y-%m-%d %H:%M:%S')} (hace {tiempo_desde_ultima/60:.1f} min)")
            
            # Analizar intervalos entre ejecuciones consecutivas
            if len(ejecs) > 1:
                self.stdout.write(f"\n   📊 Análisis de intervalos:")
                for i in range(1, len(ejecs)):
                    exec_anterior = ejecs[i-1]
                    exec_actual = ejecs[i]
                    
                    tiempo_entre = (exec_actual.created_at - exec_anterior.created_at).total_seconds()
                    tiempo_entre_min = tiempo_entre / 60
                    
                    total_analizadas += 1
                    
                    # Verificar si se respetó el intervalo
                    if tiempo_entre < intervalo_minimo:
                        problema = {
                            'olt': olt.abreviatura,
                            'job': job.nombre,
                            'ejec_anterior': exec_anterior.id,
                            'ejec_actual': exec_actual.id,
                            'tiempo_entre': tiempo_entre,
                            'intervalo_esperado': intervalo_configurado,
                            'diferencia': intervalo_configurado - tiempo_entre,
                            'fecha_anterior': exec_anterior.created_at,
                            'fecha_actual': exec_actual.created_at
                        }
                        problemas_encontrados.append(problema)
                        total_problemas += 1
                        
                        self.stdout.write(self.style.ERROR(
                            f"      ❌ Ejecución {exec_anterior.id} → {exec_actual.id}: "
                            f"{tiempo_entre_min:.2f} min (esperado: {intervalo_configurado/60:.1f} min, "
                            f"diferencia: {(intervalo_configurado - tiempo_entre)/60:.2f} min)"
                        ))
                    else:
                        total_correctas += 1
                        if detallado:
                            self.stdout.write(self.style.SUCCESS(
                                f"      ✅ Ejecución {exec_anterior.id} → {exec_actual.id}: "
                                f"{tiempo_entre_min:.2f} min"
                            ))
            
            # Verificar si hay ejecuciones muy recientes que no deberían estar
            ejecuciones_recientes = [e for e in ejecs if (ahora - e.created_at).total_seconds() < 60]
            if len(ejecuciones_recientes) > 1:
                self.stdout.write(self.style.WARNING(
                    f"   ⚠️ {len(ejecuciones_recientes)} ejecuciones en el último minuto (posible ejecución apresurada)"
                ))
        
        # Resumen
        self.stdout.write("\n" + "=" * 100)
        self.stdout.write(self.style.SUCCESS(f"\n📊 RESUMEN:"))
        self.stdout.write(f"   Total de grupos (OLT+Job) analizados: {len(ejecuciones_por_olt_job)}")
        self.stdout.write(f"   Total de intervalos analizados: {total_analizadas}")
        self.stdout.write(self.style.SUCCESS(f"   ✅ Intervalos correctos: {total_correctas}"))
        self.stdout.write(self.style.ERROR(f"   ❌ Intervalos con problemas: {total_problemas}"))
        
        if problemas_encontrados:
            self.stdout.write(self.style.ERROR(f"\n⚠️ PROBLEMAS ENCONTRADOS ({len(problemas_encontrados)}):"))
            for i, problema in enumerate(problemas_encontrados[:10], 1):  # Mostrar máximo 10
                self.stdout.write(f"\n   {i}. OLT: {problema['olt']}")
                self.stdout.write(f"      Tarea: {problema['job']}")
                self.stdout.write(f"      Ejecuciones: {problema['ejec_anterior']} → {problema['ejec_actual']}")
                self.stdout.write(f"      Tiempo entre ejecuciones: {problema['tiempo_entre']/60:.2f} min")
                self.stdout.write(f"      Intervalo esperado: {problema['intervalo_esperado']/60:.1f} min")
                self.stdout.write(f"      Diferencia: {problema['diferencia']/60:.2f} min (se ejecutó {problema['diferencia']/60:.2f} min antes de lo esperado)")
                self.stdout.write(f"      Fechas: {problema['fecha_anterior'].strftime('%H:%M:%S')} → {problema['fecha_actual'].strftime('%H:%M:%S')}")
            
            if len(problemas_encontrados) > 10:
                self.stdout.write(f"\n   ... y {len(problemas_encontrados) - 10} problemas más")
        else:
            self.stdout.write(self.style.SUCCESS(f"\n✅ No se encontraron problemas. Todas las ejecuciones respetan los intervalos programados."))
        
        self.stdout.write("\n")

