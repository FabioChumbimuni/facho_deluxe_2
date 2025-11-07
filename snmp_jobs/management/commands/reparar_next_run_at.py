"""
Comando para detectar y reparar SnmpJobHost con next_run_at = None
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from snmp_jobs.models import SnmpJobHost


class Command(BaseCommand):
    help = 'Detecta y repara SnmpJobHost con next_run_at = None'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin hacer cambios'
        )
        parser.add_argument(
            '--job-id',
            type=int,
            help='Reparar solo un job específico (opcional)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        job_id = options.get('job_id')
        
        self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 MODO DRY-RUN - Sin hacer cambios reales"))
        else:
            self.stdout.write(self.style.WARNING("🔧 REPARANDO SNMPJOBHOST CON next_run_at = None"))
        self.stdout.write(self.style.WARNING(f"{'='*80}\n"))
        
        # Filtrar SnmpJobHost problemáticos
        query = SnmpJobHost.objects.filter(
            enabled=True,
            snmp_job__enabled=True,
            next_run_at__isnull=True
        ).select_related('snmp_job', 'olt')
        
        if job_id:
            query = query.filter(snmp_job_id=job_id)
        
        job_hosts = query.all()
        
        if not job_hosts:
            self.stdout.write(self.style.SUCCESS("\n✅ No hay SnmpJobHost con next_run_at = None"))
            self.stdout.write(self.style.SUCCESS("   Todos los JobHosts están correctamente inicializados\n"))
            return
        
        self.stdout.write(self.style.WARNING(f"❌ Encontrados {job_hosts.count()} SnmpJobHost problemáticos:\n"))
        
        repaired_count = 0
        
        for jh in job_hosts:
            self.stdout.write(f"\n  Job: {jh.snmp_job.nombre} (ID: {jh.snmp_job.id})")
            self.stdout.write(f"  OLT: {jh.olt.abreviatura} (ID: {jh.olt.id})")
            self.stdout.write(f"  Tipo: {jh.snmp_job.job_type}")
            self.stdout.write(f"  Intervalo: {jh.snmp_job.interval_raw}")
            self.stdout.write(f"  Estado actual:")
            self.stdout.write(f"    - next_run_at: {jh.next_run_at}")
            self.stdout.write(f"    - last_run_at: {jh.last_run_at}")
            
            if not dry_run:
                # Calcular next_run_at
                now = timezone.now()
                
                # Determinar si es primera vez o no
                is_new = not jh.last_run_at
                
                if is_new:
                    # Primera vez: ejecutar en 1 minuto
                    next_time = now + timedelta(minutes=1)
                else:
                    # Ya se ejecutó antes: usar intervalo
                    interval_seconds = jh.snmp_job.interval_seconds or 300
                    next_time = now + timedelta(seconds=interval_seconds)
                
                # Aplicar desfase según tipo
                if jh.snmp_job.job_type == 'descubrimiento':
                    next_time = next_time.replace(second=0, microsecond=0)
                elif jh.snmp_job.job_type == 'get':
                    next_time = next_time.replace(second=10, microsecond=0)
                
                jh.next_run_at = next_time
                jh.save(update_fields=['next_run_at'])
                
                self.stdout.write(self.style.SUCCESS(f"  ✅ REPARADO:"))
                self.stdout.write(self.style.SUCCESS(f"    - next_run_at: {jh.next_run_at}"))
                repaired_count += 1
            else:
                self.stdout.write(self.style.WARNING(f"  [DRY-RUN] Se calcularía next_run_at y se guardaría"))
        
        # Resumen
        self.stdout.write(self.style.WARNING(f"\n{'='*80}"))
        self.stdout.write(self.style.WARNING("📊 RESUMEN:"))
        self.stdout.write(self.style.WARNING(f"{'='*80}"))
        
        if dry_run:
            self.stdout.write(f"✅ Detectados: {job_hosts.count()} SnmpJobHost sin next_run_at")
            self.stdout.write(f"\n⚠️  Esto fue un DRY-RUN. Para aplicar cambios ejecuta:")
            self.stdout.write(f"   python manage.py reparar_next_run_at")
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Reparados: {repaired_count} SnmpJobHost"))
            self.stdout.write(self.style.SUCCESS(f"\n✅ Ahora el coordinador podrá programar estas tareas correctamente"))
        
        self.stdout.write(self.style.WARNING(f"\n{'='*80}\n"))

