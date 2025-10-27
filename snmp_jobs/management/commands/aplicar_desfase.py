"""
Comando para aplicar desfase intencional a todas las tareas existentes

Uso:
    python manage.py aplicar_desfase
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from snmp_jobs.models import SnmpJobHost


class Command(BaseCommand):
    help = 'Aplica desfase intencional a todas las tareas para evitar colisiones'

    def handle(self, *args, **kwargs):
        self.stdout.write("\n🔧 Aplicando desfase intencional a todas las tareas...\n")
        
        # Obtener solo tareas de OLTs HABILITADAS
        job_hosts = SnmpJobHost.objects.filter(
            enabled=True,
            snmp_job__enabled=True,
            next_run_at__isnull=False,
            olt__habilitar_olt=True  # Solo OLTs habilitadas
        ).select_related('snmp_job', 'olt')
        
        if not job_hosts.exists():
            self.stdout.write(self.style.WARNING("  ⚠️ No hay tareas habilitadas"))
            return
        
        discovery_count = 0
        get_count = 0
        
        for jh in job_hosts:
            # Mantener la fecha/hora pero ajustar el segundo
            next_time = jh.next_run_at
            
            if jh.snmp_job.job_type == 'descubrimiento':
                # Discovery: segundo 0
                next_time = next_time.replace(second=0, microsecond=0)
                discovery_count += 1
            elif jh.snmp_job.job_type == 'get':
                # GET: segundo 10
                next_time = next_time.replace(second=10, microsecond=0)
                get_count += 1
            
            # Actualizar
            jh.next_run_at = next_time
            jh.save(update_fields=['next_run_at'])
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Desfase aplicado:"))
        self.stdout.write(f"   • Discovery: {discovery_count} tareas → segundo 00")
        self.stdout.write(f"   • GET:       {get_count} tareas → segundo 10")
        self.stdout.write(f"\n🚀 Total actualizado: {job_hosts.count()} tareas\n")

