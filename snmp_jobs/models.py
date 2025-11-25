# snmp_jobs/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings
from hosts.models import OLT
from datetime import datetime


class SnmpJob(models.Model):
    """
    Plantilla de trabajo SNMP. Puede agrupar varias OLTs y un OID específico.
    `run_options` sirve para parámetros dinámicos (timeout, version, community override, etc.).
    """
    JOB_TYPES = [
        ("descubrimiento", "descubrimiento"),
        ("walk", "walk"),
        ("get", "get"),
        ("table", "table"),
        ("bulk", "bulk"),
    ]

    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    marca = models.ForeignKey("brands.Brand", on_delete=models.PROTECT, db_column="marca_id")

    job_type = models.CharField(max_length=20, choices=JOB_TYPES, default="descubrimiento")

    # intervalo: raw y segundos calculados
    interval_raw = models.CharField(max_length=16, blank=True, help_text="Ej: 30s, 5m, 1h")
    interval_seconds = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        help_text="Intervalo en segundos"
    )

    # soporte para cron expr si se usa cron-based scheduling
    cron_expr = models.CharField(max_length=120, null=True, blank=True)

    enabled = models.BooleanField(default=True)
    max_retries = models.PositiveSmallIntegerField(default=2)
    retry_delay_seconds = models.PositiveIntegerField(default=30)

    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    # Opciones dinámicas: timeout, snmp version, community (mejor cifrar), flags, etc.
    run_options = models.JSONField(default=dict, blank=True)

    # relaciones
    olts = models.ManyToManyField("hosts.OLT", through="SnmpJobHost", related_name="snmp_jobs")
    oid = models.ForeignKey("oids.OID", on_delete=models.PROTECT, db_column="oid_id", related_name="snmp_jobs")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_jobs"
        ordering = ["next_run_at", "id"]
        indexes = [
            models.Index(fields=["next_run_at"]),
        ]
        verbose_name = "Tarea SNMP"
        verbose_name_plural = "Tareas SNMP"

    def __str__(self):
        return f"{self.nombre} ({self.marca})"
    
    def clean(self):
        """
        Validación personalizada: solo intervalo O cron, no ambos
        """
        from django.core.exceptions import ValidationError
        
        super().clean()
        
        # Verificar que solo uno de los dos campos esté lleno
        has_interval = bool(self.interval_raw and self.interval_raw.strip())
        has_cron = bool(self.cron_expr and self.cron_expr.strip())
        
        if has_interval and has_cron:
            raise ValidationError({
                'interval_raw': 'Solo puede especificar intervalo O cron, no ambos.',
                'cron_expr': 'Solo puede especificar intervalo O cron, no ambos.'
            })
        
        if not has_interval and not has_cron:
            raise ValidationError({
                'interval_raw': 'Debe especificar un intervalo O una expresión cron.',
                'cron_expr': 'Debe especificar un intervalo O una expresión cron.'
            })
    
    def save(self, *args, **kwargs):
        """
        Calcula automáticamente interval_seconds basado en interval_raw
        y next_run_at si no está definido
        """
        if self.interval_raw and self.interval_raw.strip():
            self.interval_seconds = self._calculate_interval_seconds()
        
        # Actualizar descripción con información del espacio del OID
        self._update_description_with_oid_space()
        
        # Calcular next_run_at si no está definido y el job está habilitado
        if self.enabled and not self.next_run_at:
            self.next_run_at = self._calculate_next_run()
            
        super().save(*args, **kwargs)
    
    def _update_description_with_oid_space(self):
        """
        Actualiza la descripción de la tarea con información del espacio del OID
        """
        if not self.oid:
            return
            
        espacio_display = self.oid.get_espacio_display()
        espacio_info = f"Espacio: {espacio_display}"
        
        # Limpiar información de espacio anterior si existe
        if self.descripcion and "Espacio:" in self.descripcion:
            # Remover líneas que contengan "Espacio:"
            lines = self.descripcion.split('\n')
            lines = [line for line in lines if not line.strip().startswith('Espacio:')]
            self.descripcion = '\n'.join(lines).strip()
        
        # Agregar información del espacio
        if self.descripcion:
            self.descripcion = f"{self.descripcion}\n{espacio_info}"
        else:
            self.descripcion = espacio_info
    
    def _calculate_next_run(self, from_now=False):
        """
        Calcula el próximo tiempo de ejecución usando la lógica del dispatcher
        
        Args:
            from_now (bool): Si True, calcula desde el momento actual (sin catch-up)
        """
        from django.utils import timezone
        from datetime import timedelta
        from croniter import croniter
        
        now = timezone.now()
        
        # Si from_now=True, siempre usar el momento actual
        base_time = now if from_now else (self.last_run_at if self.last_run_at else now)
        
        # 1. PRIORIDAD: Cron expression
        if self.cron_expr and self.cron_expr.strip():
            try:
                cron = croniter(self.cron_expr, base_time)
                return cron.get_next(datetime)
            except Exception:
                pass
        
        # 2. SEGUNDA PRIORIDAD: interval_seconds
        if self.interval_seconds and self.interval_seconds > 0:
            # CORRECCIÓN: Usar now como base para evitar ejecuciones en cadena
            return now + timedelta(seconds=self.interval_seconds)
        
        # 3. TERCERA PRIORIDAD: interval_raw
        if self.interval_raw and self.interval_raw.strip():
            try:
                seconds = self._calculate_interval_seconds()
                if seconds:
                    # CORRECCIÓN: Usar now como base para evitar ejecuciones en cadena
                    return now + timedelta(seconds=seconds)
            except Exception:
                pass
        
        # 4. FALLBACK: 1 hora
        return now + timedelta(hours=1)
    
    def _calculate_interval_seconds(self):
        """
        Convierte interval_raw a segundos
        """
        if not self.interval_raw:
            return None
            
        interval_str = self.interval_raw.strip().lower()
        
        # Extraer número y unidad
        import re
        match = re.match(r'^(\d+)([smhd])$', interval_str)
        if not match:
            return None
            
        value = int(match.group(1))
        unit = match.group(2)
        
        multipliers = {
            's': 1,           # segundos
            'm': 60,          # minutos
            'h': 3600,        # horas
            'd': 86400,       # días
        }
        
        return value * multipliers.get(unit, 60)  # Default a minutos si no se reconoce
    
    def get_schedule_description(self):
        """
        Retorna una descripción legible del horario programado
        """
        if self.cron_expr and self.cron_expr.strip():
            return self._parse_cron_description()
        elif self.interval_raw and self.interval_raw.strip():
            return self._parse_interval_description()
        else:
            return "Sin programación definida"
    
    def _parse_cron_description(self):
        """
        Convierte expresión cron en descripción legible
        """
        try:
            import croniter
            from datetime import datetime
            from django.utils import timezone
            
            # Crear un croniter para obtener la próxima ejecución
            now = timezone.now()
            cron = croniter.croniter(self.cron_expr, now)
            next_run = cron.get_next(datetime)
            
            # Parsear la expresión cron
            parts = self.cron_expr.split()
            if len(parts) == 5:
                minute, hour, day, month, weekday = parts
                
                # Caso: */30 * * * * (cada 30 minutos)
                if minute == "*/30" and hour == "*" and day == "*" and month == "*" and weekday == "*":
                    return "Cada 30 minutos"
                
                # Caso: */15 * * * * (cada 15 minutos)
                elif minute == "*/15" and hour == "*" and day == "*" and month == "*" and weekday == "*":
                    return "Cada 15 minutos"
                
                # Caso: */10 * * * * (cada 10 minutos)
                elif minute == "*/10" and hour == "*" and day == "*" and month == "*" and weekday == "*":
                    return "Cada 10 minutos"
                
                # Caso: */5 * * * * (cada 5 minutos)
                elif minute == "*/5" and hour == "*" and day == "*" and month == "*" and weekday == "*":
                    return "Cada 5 minutos"
                
                # Caso: * * * * * (cada minuto)
                elif minute == "*" and hour == "*" and day == "*" and month == "*" and weekday == "*":
                    return "Cada minuto"
                
                # Caso: 0 * * * * (cada hora)
                elif minute == "0" and hour == "*" and day == "*" and month == "*" and weekday == "*":
                    return "Cada hora"
                
                # Caso: 0 0 * * * (cada día a medianoche)
                elif minute == "0" and hour == "0" and day == "*" and month == "*" and weekday == "*":
                    return "Cada día a medianoche"
                
                # Caso: 0 8 * * * (todos los días a las 8:00 AM)
                elif minute == "0" and hour != "*" and day == "*" and month == "*" and weekday == "*":
                    hour_int = int(hour)
                    if hour_int == 0:
                        return "Todos los días a medianoche"
                    elif hour_int == 12:
                        return "Todos los días a mediodía"
                    elif hour_int > 12:
                        return f"Todos los días a las {hour_int-12}:00 PM"
                    else:
                        return f"Todos los días a las {hour}:00 AM"
                
                # Caso: 30 8 * * * (todos los días a las 8:30 AM)
                elif minute != "0" and minute != "*" and hour != "*" and day == "*" and month == "*" and weekday == "*":
                    hour_int = int(hour)
                    minute_int = int(minute)
                    if hour_int == 0:
                        return f"Todos los días a las 12:{minute_int:02d} AM"
                    elif hour_int == 12:
                        return f"Todos los días a las 12:{minute_int:02d} PM"
                    elif hour_int > 12:
                        return f"Todos los días a las {hour_int-12}:{minute_int:02d} PM"
                    else:
                        return f"Todos los días a las {hour}:{minute_int:02d} AM"
                
                # Caso: 0 8 * * 1 (lunes a las 8:00 AM)
                elif minute == "0" and hour != "*" and day == "*" and month == "*" and weekday != "*":
                    weekdays = {
                        "0": "domingo", "1": "lunes", "2": "martes", "3": "miércoles",
                        "4": "jueves", "5": "viernes", "6": "sábado", "7": "domingo"
                    }
                    weekday_name = weekdays.get(weekday, weekday)
                    hour_int = int(hour)
                    if hour_int == 0:
                        return f"Cada {weekday_name} a medianoche"
                    elif hour_int == 12:
                        return f"Cada {weekday_name} a mediodía"
                    elif hour_int > 12:
                        return f"Cada {weekday_name} a las {hour_int-12}:00 PM"
                    else:
                        return f"Cada {weekday_name} a las {hour}:00 AM"
                
                else:
                    # Caso genérico
                    return f"Programado con cron: {self.cron_expr} (Próxima: {next_run.strftime('%Y-%m-%d %H:%M')})"
            else:
                return f"Expresión cron: {self.cron_expr}"
                
        except Exception as e:
            return f"Error en cron: {self.cron_expr}"
    
    def _parse_interval_description(self):
        """
        Convierte intervalo en descripción legible
        """
        if not self.interval_raw:
            return "Sin intervalo definido"
        
        try:
            value = int(''.join(filter(str.isdigit, self.interval_raw)))
            unit = ''.join(filter(str.isalpha, self.interval_raw)).lower()
            
            if unit == 's':
                return f"Cada {value} segundo{'s' if value != 1 else ''}"
            elif unit == 'm':
                return f"Cada {value} minuto{'s' if value != 1 else ''}"
            elif unit == 'h':
                return f"Cada {value} hora{'s' if value != 1 else ''}"
            else:
                return f"Intervalo: {self.interval_raw}"
        except:
            return f"Intervalo: {self.interval_raw}"
    
    def calculate_next_run(self, is_new_task=False, from_now=False):
        """
        Calcula el próximo tiempo de ejecución basado en interval_raw o cron_expr
        Usa timezone de Perú (America/Lima)
        
        Args:
            is_new_task (bool): True si es una tarea recién creada
            from_now (bool): Si True, calcula desde el momento actual (sin catch-up)
        """
        from django.utils import timezone
        from datetime import timedelta, datetime
        import logging
        import croniter
        
        logger = logging.getLogger(__name__)
        now = timezone.now()
        
        # REGLA ESPECIAL: Si es una tarea nueva, ejecutar en 1 minuto
        if is_new_task:
            return now + timedelta(minutes=1)
        
        # Si from_now=True, siempre usar el momento actual
        base_time = now if from_now else (self.last_run_at if self.last_run_at else now)
        
        # Si hay expresión cron, usarla para calcular la próxima ejecución
        if self.cron_expr and self.cron_expr.strip():
            try:
                cron = croniter.croniter(self.cron_expr, base_time)
                next_run = cron.get_next(datetime)
                
                # Verificar si next_run ya tiene timezone
                if timezone.is_aware(next_run):
                    return next_run
                else:
                    return timezone.make_aware(next_run, timezone.get_current_timezone())
                    
            except Exception as e:
                logger.warning(f"Error parsing cron expression '{self.cron_expr}': {e}")
                # Fallback a interval_raw
        
        # Usar interval_raw si no hay cron_expr o falló
        if not self.interval_raw or not self.interval_raw.strip():
            return now + timedelta(minutes=5)  # Default 5 minutos
        
        # Parsear interval_raw (ej: "30s", "5m", "1h")
        value = int(''.join(filter(str.isdigit, self.interval_raw)))
        unit = ''.join(filter(str.isalpha, self.interval_raw)).lower()
        
        if unit == 's':
            next_run = base_time + timedelta(seconds=value)
        elif unit == 'm':
            next_run = base_time + timedelta(minutes=value)
        elif unit == 'h':
            next_run = base_time + timedelta(hours=value)
        elif unit == 'd':
            next_run = base_time + timedelta(days=value)
        else:
            next_run = base_time + timedelta(minutes=value)  # Default a minutos
        
        return next_run
    
    def save(self, *args, **kwargs):
        """
        Override save para calcular automáticamente next_run_at
        """
        # Calcular interval_seconds si interval_raw está definido
        if self.interval_raw and self.interval_raw.strip():
            self.interval_seconds = self._calculate_interval_seconds()
        
        # Detectar si es una tarea nueva
        is_new_task = self._state.adding if hasattr(self, '_state') else (self.pk is None)
        
        # Detectar si se está deshabilitando la tarea
        was_enabled = None
        if not is_new_task and self.pk:
            try:
                old_instance = SnmpJob.objects.get(pk=self.pk)
                was_enabled = old_instance.enabled
            except SnmpJob.DoesNotExist:
                was_enabled = None
        
        # Si el job está habilitado y no tiene next_run_at, o si se está habilitando
        if self.enabled:
            if not self.next_run_at:
                # Primera vez: calcular (1 minuto si es nueva, intervalo normal si no)
                self.next_run_at = self.calculate_next_run(is_new_task=is_new_task)
            elif is_new_task:
                # Nuevo job: ejecutar en 1 minuto
                self.next_run_at = self.calculate_next_run(is_new_task=True)
            elif was_enabled is False and self.enabled:
                # Si se está habilitando (estaba deshabilitada), SIN catch-up
                # Calcular next_run_at desde el momento actual (SIN catch-up)
                self.next_run_at = self._calculate_next_run(from_now=True)
        
        super().save(*args, **kwargs)
        
        # DESPUÉS del save: Abortar ejecuciones si se deshabilitó la tarea
        if was_enabled is True and not self.enabled:
            # Usar transaction.on_commit para evitar deadlocks
            from django.db import transaction
            def abort_executions():
                try:
                    self.abort_all_pending_executions("Tarea deshabilitada")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"❌ Error abortando ejecuciones para tarea {self.nombre}: {e}")
            
            transaction.on_commit(abort_executions)
    
    def update_next_run(self):
        """
        Actualiza next_run_at basado en el intervalo
        """
        self.next_run_at = self.calculate_next_run(is_new_task=False)
        self.save(update_fields=['next_run_at'])
    
    def enable_from_now(self):
        """
        Habilita la tarea y calcula next_run_at desde el momento actual
        SIN catch-up: No recupera ejecuciones perdidas
        """
        from django.utils import timezone
        self.enabled = True
        self.last_run_at = None  # Resetear para que calcule desde ahora
        self.next_run_at = self.calculate_next_run(is_new_task=False)
        self.save(update_fields=['enabled', 'last_run_at', 'next_run_at'])
    
    def enable_with_catchup_prevention(self):
        """
        Habilita la tarea SIN catch-up
        Calcula next_run_at desde el momento actual, ignorando ejecuciones perdidas
        """
        import logging
        logger = logging.getLogger(__name__)
        
        self.enabled = True
        self.last_run_at = None  # Resetear para que calcule desde ahora
        
        # Calcular next_run_at desde el momento actual (SIN catch-up)
        self.next_run_at = self._calculate_next_run(from_now=True)
        
        self.save(update_fields=['enabled', 'last_run_at', 'next_run_at'])
        logger.info(f"✅ Tarea '{self.nombre}' habilitada SIN catch-up - Próxima ejecución: {self.next_run_at}")
    
    def get_time_until_next_run(self):
        """
        Retorna el tiempo restante hasta la próxima ejecución en formato legible
        """
        from django.utils import timezone
        import pytz
        
        # Si el job está deshabilitado, no mostrar tiempo
        if not self.enabled:
            return "No disponible"
        
        if not self.next_run_at:
            return "No programado"
        
        now = timezone.now()
        if self.next_run_at <= now:
            return "Listo para ejecutar"
        
        # Calcular diferencia
        diff = self.next_run_at - now
        total_seconds = int(diff.total_seconds())
        
        if total_seconds < 60:
            return f"En {total_seconds} segundos"
        elif total_seconds < 3600:  # Menos de 1 hora
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            if seconds > 0:
                return f"En {minutes}m {seconds}s"
            else:
                return f"En {minutes} minutos"
        elif total_seconds < 86400:  # Menos de 1 día
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if minutes > 0:
                return f"En {hours}h {minutes}m"
            else:
                return f"En {hours} horas"
        else:  # Más de 1 día
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            if hours > 0:
                return f"En {days}d {hours}h"
            else:
                return f"En {days} días"
    
    def get_next_run_display(self):
        """
        Retorna la próxima ejecución en formato legible con zona horaria de Perú
        """
        # Si el job está deshabilitado, no mostrar próxima ejecución
        if not self.enabled:
            return "No disponible"
        
        if not self.next_run_at:
            return "No programado"
        
        import pytz
        lima_tz = pytz.timezone('America/Lima')
        next_run_lima = self.next_run_at.astimezone(lima_tz)
        return next_run_lima.strftime('%d/%m/%Y %H:%M:%S')
    
    def is_ready_to_run(self):
        """
        Retorna True si el job está listo para ejecutarse
        """
        from django.utils import timezone
        if not self.next_run_at:
            return False
        return self.next_run_at <= timezone.now()

    @staticmethod
    def abort_pending_executions_for_olt(olt_id, reason="OLT deshabilitada"):
        """
        Aborta todas las ejecuciones PENDING para una OLT específica
        """
        from executions.models import Execution
        from django.utils import timezone
        from hosts.models import OLT
        
        # Obtener información de la OLT
        try:
            olt = OLT.objects.get(id=olt_id)
            olt_name = olt.abreviatura
        except OLT.DoesNotExist:
            olt_name = f"OLT ID {olt_id}"
        
        # Obtener las ejecuciones que se van a abortar para mostrar detalles
        pending_executions = Execution.objects.filter(
            olt_id=olt_id,
            status='PENDING'
        ).select_related('snmp_job')
        
        aborted_count = pending_executions.update(
            status='INTERRUPTED',
            finished_at=timezone.now(),
            error_message=reason
        )
        
        if aborted_count > 0:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🛑 ABORTO MASIVO: {aborted_count} ejecuciones PENDING abortadas para {olt_name}")
            logger.info(f"   📋 Motivo: {reason}")
            
            # Mostrar detalles de las tareas afectadas
            task_names = list(pending_executions.values_list('snmp_job__nombre', flat=True).distinct())
            if task_names:
                logger.info(f"   📊 Tareas afectadas: {', '.join(task_names)}")
        
        return aborted_count

    def abort_all_pending_executions(self, reason="Tarea deshabilitada"):
        """
        Aborta todas las ejecuciones PENDING para esta tarea
        """
        from executions.models import Execution
        from django.utils import timezone
        
        # Obtener las ejecuciones que se van a abortar para mostrar detalles
        pending_executions = Execution.objects.filter(
            snmp_job=self,
            status='PENDING'
        ).select_related('olt')
        
        aborted_count = pending_executions.update(
            status='INTERRUPTED',
            finished_at=timezone.now(),
            error_message=reason
        )
        
        if aborted_count > 0:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🛑 ABORTO DE TAREA: {aborted_count} ejecuciones PENDING abortadas")
            logger.info(f"   📋 Tarea: '{self.nombre}' (ID: {self.id})")
            logger.info(f"   📋 Motivo: {reason}")
            
            # Mostrar detalles de las OLTs afectadas
            olt_names = list(pending_executions.values_list('olt__abreviatura', flat=True).distinct())
            if olt_names:
                logger.info(f"   📊 OLTs afectadas: {', '.join(olt_names)}")
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"ℹ️ No hay ejecuciones PENDING para abortar en tarea '{self.nombre}'")
        
        return aborted_count


class SnmpJobHost(models.Model):
    """
    Through-model job <-> olt. Guarda estado y parámetros por OLT (por ejemplo cola, enabled).
    
    IMPORTANTE: Ahora gestiona next_run_at POR OLT de forma independiente.
    Esto permite que cada OLT tenga su propio horario de ejecución sin afectar a otras OLTs.
    """
    snmp_job = models.ForeignKey(SnmpJob, on_delete=models.CASCADE, db_column="snmp_job_id", related_name="job_hosts")
    olt = models.ForeignKey("hosts.OLT", on_delete=models.CASCADE, db_column="olt_id", related_name="job_host_links")

    enabled = models.BooleanField(default=True)
    
    # NUEVO: Gestión de horarios POR OLT (independiente de otras OLTs)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True, 
                                       help_text='Próxima ejecución para ESTA OLT específica')
    last_run_at = models.DateTimeField(null=True, blank=True,
                                       help_text='Última ejecución para ESTA OLT')
    
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)

    # nombre de cola preferente para esta OLT (ej: snmp_high / snmp_default)
    queue_name = models.CharField(max_length=64, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "snmp_job_hosts"
        unique_together = (("snmp_job", "olt"),)
        indexes = [
            models.Index(fields=["olt", "snmp_job"]),
            models.Index(fields=["snmp_job"]),
            models.Index(fields=["next_run_at"]),
        ]
        verbose_name = "OLT en Tarea"
        verbose_name_plural = "OLTs en Tarea"

    def __str__(self):
        return f"{self.snmp_job.nombre} -> {self.olt.abreviatura or self.olt.ip_address}"
    
    def initialize_next_run(self, is_new=False):
        """
        Inicializa next_run_at cuando se crea o habilita el job_host
        
        Reglas:
        - Job NUEVO desde plantilla: next_run = now + intervalo completo configurado
        - Job EXISTENTE (ya tiene ejecuciones previas): next_run = now + intervalo completo
        - Después de ejecutar: next_run = now + intervalo + DESFASE
        
        DESFASE INTENCIONAL (evita colisiones):
        - Discovery: segundo 0 (XX:XX:00)
        - GET:       segundo 10 (XX:XX:10)
        """
        from django.utils import timezone
        from datetime import timedelta
        from executions.models import Execution
        
        now = timezone.now()
        
        # VERIFICAR: ¿El Job tiene ejecuciones previas?
        # Si tiene ejecuciones, NO es nuevo aunque se esté recreando el JobHost
        has_previous_executions = Execution.objects.filter(
            snmp_job=self.snmp_job,
            olt=self.olt
        ).exists()
        
        # Determinar el intervalo a usar
        interval_seconds = self.snmp_job.interval_seconds or 300
        
        # SIEMPRE usar el intervalo completo configurado, sin importar si es nuevo o no
        # Esto asegura que las plantillas respeten el intervalo configurado
        next_time = now + timedelta(seconds=interval_seconds)
        
        # DESFASE INTENCIONAL según tipo de tarea
        # IMPORTANTE: El desfase solo alinea al segundo, NO reduce el intervalo
        # CRÍTICO: Asegurar que el intervalo mínimo se respete (no usar desfase si reduce el tiempo)
        if self.snmp_job.job_type == 'descubrimiento':
            aligned_time = next_time.replace(second=0, microsecond=0)
            # Solo usar el desfase si NO reduce el intervalo
            if aligned_time > next_time:
                next_time = aligned_time
            elif aligned_time < next_time:
                # El alineamiento redujo el tiempo, NO usar el desfase, mantener el tiempo original
                pass  # next_time ya tiene el valor correcto
        elif self.snmp_job.job_type == 'get':
            aligned_time = next_time.replace(second=10, microsecond=0)
            # Solo usar el desfase si NO reduce el intervalo
            if aligned_time > next_time:
                next_time = aligned_time
            elif aligned_time < next_time:
                # El alineamiento redujo el tiempo, NO usar el desfase, mantener el tiempo original
                pass  # next_time ya tiene el valor correcto
        
        self.next_run_at = next_time


class TaskFunction(models.Model):
    """
    Catálogo de funciones ejecutables por el coordinador (similar a operadores en Airflow).
    Define dónde vive la función Python que implementa la tarea SNMP.
    """

    FUNCTION_TYPES = [
        ("descubrimiento", "Descubrimiento"),
        ("get", "SNMP GET"),
        ("auxiliar", "Auxiliar"),
    ]

    code = models.SlugField(
        max_length=80,
        unique=True,
        help_text="Identificador interno (ej. discovery_onu_huawei)",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    module_path = models.CharField(
        max_length=255,
        help_text="Ruta del módulo Python (ej. snmp_jobs.workers.discovery)",
    )
    callable_name = models.CharField(
        max_length=120,
        help_text="Nombre de la función dentro del módulo (ej. run_discovery)",
    )
    function_type = models.CharField(
        max_length=20,
        choices=FUNCTION_TYPES,
        default="get",
        db_index=True,
    )
    default_parameters = models.JSONField(blank=True, default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_task_functions"
        ordering = ["code"]
        verbose_name = "Función SNMP"
        verbose_name_plural = "Funciones SNMP"

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def dotted_path(self):
        """Retorna module_path + callable_name."""
        return f"{self.module_path}.{self.callable_name}"


class TaskTemplate(models.Model):
    """
    Plantilla configurable que combina una TaskFunction con parámetros,
    prioridad y estilos para la interfaz tipo Airflow.
    """

    PRIORITY_CHOICES = [
        (1, "Muy Alta"),
        (2, "Alta"),
        (3, "Media"),
        (4, "Baja"),
        (5, "Muy Baja"),
    ]

    slug = models.SlugField(
        max_length=80,
        unique=True,
        help_text="Identificador único (ej. discovery-huawei-onu)",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    function = models.ForeignKey(
        TaskFunction,
        on_delete=models.PROTECT,
        related_name="templates",
    )
    default_interval_seconds = models.PositiveIntegerField(default=300)
    default_priority = models.PositiveSmallIntegerField(
        choices=PRIORITY_CHOICES,
        default=3,
    )
    default_retry_policy = models.JSONField(blank=True, default=dict)
    default_run_options = models.JSONField(blank=True, default=dict)
    default_color = models.CharField(
        max_length=16,
        default="#1f77b4",
        help_text="Color hexadecimal para la UI (tema claro/oscuro).",
    )
    default_icon = models.CharField(
        max_length=8,
        blank=True,
        help_text="Emoji o icono corto para representar la tarea.",
    )
    metadata = models.JSONField(blank=True, default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_task_templates"
        ordering = ["name"]
        verbose_name = "Plantilla de Tarea SNMP"
        verbose_name_plural = "Plantillas de Tareas SNMP"

    def __str__(self):
        return self.name


class WorkflowTemplate(models.Model):
    """
    Plantilla maestra de workflow que puede aplicarse a múltiples OLTs.
    Similar a Templates en Zabbix.
    
    IMPORTANTE: Una plantilla solo puede ejecutarse si está vinculada a al menos una OLT.
    Las plantillas sin OLTs asignadas no generan ejecuciones.
    """
    name = models.CharField(max_length=150, unique=True, help_text="Nombre único de la plantilla")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_workflow_templates"
        verbose_name = "Plantilla de Workflow"
        verbose_name_plural = "Plantillas de Workflow"
        ordering = ["name"]

    def __str__(self):
        return self.name
    
    @property
    def has_olts_assigned(self):
        """
        Verifica si la plantilla tiene al menos un workflow vinculado a una OLT.
        """
        return self.workflow_links.filter(
            workflow__olt__habilitar_olt=True
        ).exists()
    
    @property
    def olts_count(self):
        """
        Retorna el número de OLTs a las que está vinculada esta plantilla.
        """
        return self.workflow_links.filter(
            workflow__olt__habilitar_olt=True
        ).count()
    
    def save(self, *args, **kwargs):
        """
        Valida que la plantilla tenga OLTs asignadas antes de activarla.
        Si está activa pero no tiene OLTs, se desactiva automáticamente.
        """
        # Si se está activando pero no tiene OLTs asignadas, desactivar
        if self.is_active and not self.has_olts_assigned:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"⚠️ Plantilla '{self.name}' activada sin OLTs asignadas. "
                f"Se desactivará automáticamente. "
                f"Para ejecutarse, debe aplicarse a al menos una OLT."
            )
            # No desactivar automáticamente, solo advertir
            # El usuario puede querer activarla antes de asignar OLTs
        
        super().save(*args, **kwargs)


class WorkflowTemplateNode(models.Model):
    """
    Nodo dentro de una plantilla de workflow.
    Cada nodo tiene una 'key' única dentro de la plantilla (como items en Zabbix).
    La key identifica de forma única el nodo y permite vinculación automática.
    """
    PRIORITY_CHOICES = TaskTemplate.PRIORITY_CHOICES

    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="template_nodes",
    )
    
    # OID directamente - contiene marca, modelo y espacio
    oid = models.ForeignKey(
        "oids.OID",
        on_delete=models.PROTECT,
        db_column="oid_id",
        related_name="workflow_template_nodes",
        null=True,
        blank=True,
        help_text="OID SNMP que define marca, modelo y tipo de operación (descubrimiento o GET)."
    )
    
    # KEY ÚNICA (como en Zabbix) - identifica el nodo de forma única
    key = models.CharField(
        max_length=150,
        help_text="Identificador único del nodo (ej: discover.60min, get.description.10min). "
                  "Se usa para vincular automáticamente con nodos existentes en workflows."
    )
    name = models.CharField(
        max_length=150,
        help_text="Nombre descriptivo del nodo"
    )
    
    interval_seconds = models.PositiveIntegerField(default=300)
    priority = models.PositiveSmallIntegerField(
        choices=PRIORITY_CHOICES,
        default=3,
    )
    parameters = models.JSONField(default=dict, blank=True)
    retry_policy = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    position_x = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    position_y = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    color_override = models.CharField(max_length=16, blank=True)
    icon_override = models.CharField(max_length=8, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Campos para ejecución en cadena de nodos
    is_chain_node = models.BooleanField(
        default=False,
        help_text="Si True, este nodo está en una cadena y se ejecuta después del nodo master"
    )
    master_node = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chain_nodes',
        help_text="Nodo master de la cadena. Solo los nodos en cadena tienen este campo asignado."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_workflow_template_nodes"
        unique_together = [("template", "key")]  # Key única dentro de cada plantilla
        verbose_name = "Nodo de Plantilla"
        verbose_name_plural = "Nodos de Plantilla"
        ordering = ["template", "priority", "name"]
        indexes = [
            models.Index(fields=["template", "key"]),
        ]

    def __str__(self):
        return f"{self.template.name} → {self.name} ({self.key})"


class WorkflowTemplateLink(models.Model):
    """
    Relación ManyToMany entre WorkflowTemplate y OLTWorkflow.
    Define si un workflow está vinculado a una plantilla y si se sincroniza automáticamente.
    """
    template = models.ForeignKey(
        WorkflowTemplate,
        on_delete=models.CASCADE,
        related_name="workflow_links",
    )
    workflow = models.ForeignKey(
        'OLTWorkflow',
        on_delete=models.CASCADE,
        related_name="template_links",
    )
    auto_sync = models.BooleanField(
        default=True,
        help_text="Si True, los cambios en la plantilla se propagan automáticamente"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_workflow_template_links"
        unique_together = [("template", "workflow")]
        verbose_name = "Vinculación Plantilla-Workflow"
        verbose_name_plural = "Vinculaciones Plantilla-Workflow"

    def __str__(self):
        return f"{self.template.name} → {self.workflow.olt.abreviatura}"


class OLTWorkflow(models.Model):
    """
    Define el workflow (DAG) de tareas para una OLT específica.
    """

    THEME_CHOICES = [
        ("auto", "Automático"),
        ("light", "Claro"),
        ("dark", "Oscuro"),
    ]

    olt = models.OneToOneField(
        OLT,
        on_delete=models.CASCADE,
        related_name="workflow",
    )
    name = models.CharField(max_length=150, default="Workflow SNMP")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    theme = models.CharField(
        max_length=16,
        choices=THEME_CHOICES,
        default="auto",
        help_text="Preferencia de tema para la UI Airflow-like.",
    )
    layout = models.JSONField(
        blank=True,
        default=dict,
        help_text="Metadata de layout (zoom, pan, configuraciones del canvas).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_olt_workflows"
        verbose_name = "Workflow SNMP por OLT"
        verbose_name_plural = "Workflows SNMP por OLT"

    def __str__(self):
        return f"{self.name} - {self.olt.abreviatura if self.olt else self.olt_id}"


class WorkflowNode(models.Model):
    """
    Nodo dentro del workflow de una OLT (equivalente a un operador en Airflow).
    """

    PRIORITY_CHOICES = TaskTemplate.PRIORITY_CHOICES

    workflow = models.ForeignKey(
        OLTWorkflow,
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    template = models.ForeignKey(
        TaskTemplate,
        on_delete=models.PROTECT,
        related_name="nodes",
    )
    # NUEVO: Referencia al nodo de plantilla (si viene de una plantilla)
    template_node = models.ForeignKey(
        'WorkflowTemplateNode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_nodes",
        help_text="Nodo de plantilla del cual proviene este nodo (si aplica)"
    )
    # ✅ OID directo (obligatorio para ejecución, puede venir de template_node o asignarse directamente)
    oid = models.ForeignKey(
        "oids.OID",
        on_delete=models.PROTECT,
        db_column="oid_id",
        related_name="workflow_nodes",
        null=True,
        blank=True,
        help_text="OID SNMP para ejecutar este nodo (obligatorio para ejecución)"
    )
    # KEY ÚNICA (como en Zabbix) - identifica el nodo de forma única dentro del workflow
    key = models.CharField(
        max_length=150,
        null=True,  # Temporalmente nullable para migración
        blank=True,  # Temporalmente blank para migración
        help_text="Identificador único del nodo (ej: discover.60min, get.description.10min). "
                  "Si coincide con una key de plantilla vinculada, se vincula automáticamente."
    )
    name = models.CharField(
        max_length=150,
        help_text="Nombre visible en la UI (editable por OLT).",
    )
    interval_seconds = models.PositiveIntegerField(
        help_text="Intervalo específico para este nodo.",
    )
    priority = models.PositiveSmallIntegerField(
        choices=PRIORITY_CHOICES,
        default=3,
        db_index=True,
    )
    enabled = models.BooleanField(default=True)
    
    # Campos de override (indican si el usuario sobrescribió valores de la plantilla)
    override_interval = models.BooleanField(
        default=False,
        help_text="Si True, el intervalo fue sobrescrito manualmente y no se actualiza desde la plantilla"
    )
    override_priority = models.BooleanField(
        default=False,
        help_text="Si True, la prioridad fue sobrescrita manualmente"
    )
    override_enabled = models.BooleanField(
        default=False,
        help_text="Si True, el estado enabled fue sobrescrito manualmente"
    )
    override_parameters = models.BooleanField(
        default=False,
        help_text="Si True, los parámetros fueron sobrescritos manualmente"
    )
    
    # Campos para ejecución en cadena de nodos
    is_chain_node = models.BooleanField(
        default=False,
        help_text="Si True, este nodo está en una cadena y se ejecuta después del nodo master"
    )
    master_node = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chain_nodes',
        help_text="Nodo master de la cadena. Solo los nodos en cadena tienen este campo asignado."
    )
    
    position_x = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text="Posición X en el canvas Airflow-like.",
    )
    position_y = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text="Posición Y en el canvas Airflow-like.",
    )
    color_override = models.CharField(
        max_length=16,
        blank=True,
        help_text="Color específico para el nodo (opcional).",
    )
    icon_override = models.CharField(
        max_length=8,
        blank=True,
        help_text="Icono específico para el nodo (opcional).",
    )
    parameters = models.JSONField(blank=True, default=dict)
    retry_policy = models.JSONField(blank=True, default=dict)
    metadata = models.JSONField(blank=True, default=dict)
    
    # Campos de ejecución independiente (sin depender de SnmpJob legacy)
    next_run_at = models.DateTimeField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text="Próxima ejecución para este nodo específico del workflow"
    )
    last_run_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Última ejecución de este nodo"
    )
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "snmp_workflow_nodes"
        ordering = ["workflow", "priority", "id"]
        verbose_name = "Nodo de Workflow SNMP"
        verbose_name_plural = "Nodos de Workflow SNMP"
        # NUEVO: Key única dentro de cada workflow
        unique_together = [("workflow", "key")]
        indexes = [
            models.Index(fields=["workflow", "key"]),
            models.Index(fields=["template_node"]),
            models.Index(fields=["next_run_at"]),  # Para búsquedas rápidas de nodos listos
            models.Index(fields=["workflow", "enabled", "next_run_at"]),  # Para coordinador
        ]

    def __str__(self):
        return f"{self.name} ({self.workflow.olt.abreviatura}) - {self.key}"
    
    def link_to_template_node(self, template_node):
        """
        Vincula este nodo a un nodo de plantilla.
        Actualiza los campos desde la plantilla si no tienen override.
        
        ✅ CRÍTICO: Asegura que nodos encadenados siempre tengan interval_seconds=0
        """
        self.template_node = template_node
        
        # ✅ CRÍTICO: Nodos encadenados SIEMPRE tienen interval_seconds=0
        if not self.override_interval:
            if template_node.is_chain_node:
                # Forzar intervalo 0 para nodos encadenados
                target_interval = 0
            else:
                # Nodos master: usar intervalo de la plantilla
                target_interval = template_node.interval_seconds or 0
            self.interval_seconds = target_interval
        
        # Si es nodo encadenado, asegurar que next_run_at sea None
        if template_node.is_chain_node:
            self.is_chain_node = True
            self.next_run_at = None
        
        if not self.override_priority:
            self.priority = template_node.priority
        if not self.override_enabled:
            self.enabled = template_node.enabled
        if not self.override_parameters:
            self.parameters = template_node.parameters.copy()
        metadata = self.metadata or {}
        if metadata.get('origin_template_id') != template_node.template_id:
            metadata['origin_template_id'] = template_node.template_id
        self.metadata = metadata
        self.save()
    
    def is_executable(self):
        """
        Verifica si este nodo puede ejecutarse según la lógica de activación en cascada.
        
        Para que un nodo se ejecute, TODOS estos deben estar activos:
        1. OLT debe estar habilitada (habilitar_olt=True)
        2. Plantilla debe estar activa (is_active=True) - si el nodo viene de plantilla
        3. Workflow debe estar activo (is_active=True)
        4. Nodo debe estar habilitado (enabled=True)
        
        Returns:
            bool: True si el nodo puede ejecutarse, False en caso contrario
        """
        # 1. Verificar que la OLT esté habilitada
        if not self.workflow.olt.habilitar_olt:
            return False
        
        # 2. Verificar que el workflow esté activo
        if not self.workflow.is_active:
            return False
        
        # 3. Si el nodo viene de una plantilla, verificar que la plantilla esté activa
        if self.template_node and self.template_node.template:
            if not self.template_node.template.is_active:
                return False
        
        # 4. Verificar que el nodo esté habilitado
        if not self.enabled:
            return False
        
        return True
    
    def initialize_next_run(self):
        """
        Inicializa next_run_at para este nodo del workflow.
        Usa el intervalo configurado del nodo (interval_seconds).
        
        ✅ CRÍTICO - REGLAS DE INTERVALOS:
        - SOLO nodos MASTER tienen intervalo propio y next_run_at
        - Los nodos ENCADENADOS (is_chain_node=True) NO tienen intervalo (interval_seconds=0)
        - Los nodos ENCADENADOS NO tienen next_run_at (se ejecutan después del master)
        - Los nodos ENCADENADOS dependen del master_node para ejecutarse
        
        IMPORTANTE: 
        - SOLO configura next_run_at si el nodo tiene template_node y OID (requerido para ejecución SNMP)
        - Respeta el intervalo configurado tal cual, sin delays adicionales
        """
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        
        # ✅ CRÍTICO: Nodos encadenados NUNCA tienen intervalo ni next_run_at
        if self.is_chain_node:
            # Los nodos encadenados NO tienen intervalo propio
            # Se ejecutan DESPUÉS del master cuando este termine exitosamente
            # Forzar que interval_seconds sea 0 y next_run_at sea None
            self.interval_seconds = 0
            self.next_run_at = None
            return None
        
        # ✅ CRÍTICO: Solo configurar next_run_at si tiene OID (directo o desde template_node)
        # Los nodos sin OID no pueden ejecutarse (no tienen consulta SNMP)
        oid_to_check = self.oid or (self.template_node.oid if self.template_node else None)
        if not oid_to_check:
            # Nodo sin OID: no configurar next_run_at (no se ejecutará automáticamente)
            self.next_run_at = None
            return None
        
        # Usar el intervalo configurado del nodo (solo para nodos master o independientes con OID)
        interval_seconds = self.interval_seconds or 300
        
        # ✅ CRÍTICO: Calcular próxima ejecución desde el momento de activación
        # SIEMPRE calcular desde 'now' (momento actual) para asegurar que next_run_at esté en el futuro
        # El coordinador puede alinear la hora, pero NO ejecutará inmediatamente al activar
        next_time = now + timedelta(seconds=interval_seconds)
        
        # ✅ GARANTIZAR: next_run_at SIEMPRE debe estar en el futuro
        # Si por alguna razón está en el pasado, recalcular desde ahora
        if next_time <= now:
            next_time = now + timedelta(seconds=interval_seconds)
        
        self.next_run_at = next_time
        return next_time
    
    def can_execute_now(self, now=None):
        """
        Verifica si este nodo puede ejecutarse ahora según:
        1. Dependencias (upstream nodes deben haber terminado)
        2. next_run_at debe estar en el pasado (o None si es nodo en cadena)
        3. Debe estar habilitado (is_executable)
        4. Si es nodo en cadena, el master debe haber terminado exitosamente
        5. Debe tener template_node y OID asociado (para nodos que requieren ejecución SNMP)
        
        Args:
            now: Tiempo actual (opcional, por defecto timezone.now())
        
        Returns:
            tuple: (can_execute: bool, reason: str)
        """
        from django.utils import timezone
        from .models import WorkflowEdge
        
        if now is None:
            now = timezone.now()
        
        # 1. Verificar que esté habilitado
        if not self.is_executable():
            return False, "Nodo no está habilitado o workflow/OLT inactivo"
        
        # 1.5. Verificar que tenga OID (requerido para ejecución SNMP)
        # El OID puede venir directamente del nodo o desde template_node
        oid_to_check = self.oid or (self.template_node.oid if self.template_node else None)
        if not oid_to_check:
            return False, "Nodo no tiene OID asociado (requerido para ejecución SNMP)"
        
        # 2. Si es un nodo en cadena, verificar que el master haya terminado
        if self.is_chain_node:
            if not self.master_node:
                return False, "Nodo en cadena sin master asignado"
            
            if not self.master_node.is_executable():
                return False, f"Master '{self.master_node.name}' no está habilitado"
            
            # El master debe haber terminado (SUCCESS o FAILED) - no solo SUCCESS
            # Verificar last_success_at O last_failure_at O last_run_at (cualquiera indica que terminó)
            if not self.master_node.last_success_at and not self.master_node.last_failure_at and not self.master_node.last_run_at:
                return False, f"Master '{self.master_node.name}' no ha ejecutado (ni exitosamente ni con fallo)"
            
            # Si el master tiene next_run_at en el futuro, aún no ha terminado su ciclo
            # (pero puede estar ejecutando ahora, así que permitimos si last_success_at existe)
            # Los nodos en cadena no tienen next_run_at, se ejecutan inmediatamente después del master
        
        # 3. Verificar que next_run_at esté en el pasado (solo para nodos no en cadena)
        if not self.is_chain_node:
            if not self.next_run_at:
                return False, "next_run_at no inicializado"
            
            if self.next_run_at > now:
                return False, f"next_run_at en el futuro: {self.next_run_at}"
        
        # 4. Verificar dependencias (upstream nodes)
        # Un nodo solo puede ejecutarse si todos sus upstream nodes han terminado exitosamente
        # NOTA: Importar aquí para evitar importación circular
        from snmp_jobs.models import WorkflowEdge
        upstream_edges = WorkflowEdge.objects.filter(
            workflow=self.workflow,
            downstream_node=self
        )
        
        for edge in upstream_edges:
            upstream = edge.upstream_node
            # Si el upstream está habilitado, debe haber terminado exitosamente
            if upstream.enabled and upstream.is_executable():
                # Verificar que el upstream haya ejecutado al menos una vez
                if not upstream.last_success_at:
                    return False, f"Dependencia '{upstream.name}' no ha ejecutado exitosamente"
                
                # Si el upstream tiene next_run_at en el futuro, esperar
                if upstream.next_run_at and upstream.next_run_at > now:
                    return False, f"Dependencia '{upstream.name}' aún no está lista"
        
        return True, "Listo para ejecutar"
    
    def save(self, *args, **kwargs):
        """
        Override save para detectar cuando se habilita un nodo y recalcular next_run_at.
        Cuando se habilita un nodo master, debe ejecutarse desde el momento de activación + intervalo.
        """
        # Detectar si se está habilitando (estaba deshabilitado y ahora se habilita)
        was_enabled = None
        if self.pk:
            try:
                old_instance = WorkflowNode.objects.get(pk=self.pk)
                was_enabled = old_instance.enabled
            except WorkflowNode.DoesNotExist:
                was_enabled = None
        
        # ✅ DETECTAR CAMBIO EN INTERVALO: El cambio de intervalo NO afecta la próxima ejecución programada
        # El nuevo intervalo se aplicará DESPUÉS de la próxima ejecución (en la siguiente)
        # Esto es "Fixed Interval Scheduling": el intervalo actual se respeta hasta que se ejecute
        old_interval = None
        if self.pk:
            try:
                old_instance = WorkflowNode.objects.get(pk=self.pk)
                old_interval = old_instance.interval_seconds
            except WorkflowNode.DoesNotExist:
                old_interval = None
        
        # Si cambió el intervalo, solo loguear (NO recalcular next_run_at)
        # El nuevo intervalo se aplicará en la siguiente ejecución después de que se ejecute la actual
        if old_interval is not None and old_interval != self.interval_seconds and self.enabled and not self.is_chain_node:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"🔄 Intervalo de nodo '{self.name}' cambiado de {old_interval}s a {self.interval_seconds}s. "
                f"El nuevo intervalo se aplicará en la siguiente ejecución (después de {self.next_run_at})."
            )
        
        # Si se está habilitando (estaba deshabilitado y ahora se habilita)
        # Y NO es un nodo en cadena (los nodos en cadena no tienen next_run_at)
        if was_enabled is False and self.enabled and not self.is_chain_node:
            # ✅ VALIDACIÓN: Solo inicializar next_run_at si tiene OID (directo o desde template_node)
            oid_check = self.oid or (self.template_node.oid if self.template_node else None)
            if oid_check:
                # Recalcular next_run_at desde ahora + intervalo completo
                self.initialize_next_run()
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"✅ Nodo '{self.name}' habilitado, next_run_at recalculado: {self.next_run_at}"
                )
            else:
                # Nodo sin OID: no configurar next_run_at
                self.next_run_at = None
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"⚠️ Nodo '{self.name}' habilitado pero sin OID, "
                    f"next_run_at no configurado (no se ejecutará automáticamente)"
                )
        
        # Si se está deshabilitando, abortar ejecuciones pendientes
        if was_enabled is True and not self.enabled:
            from django.db import transaction
            from executions.models import Execution
            import logging
            logger = logging.getLogger(__name__)
            
            def abort_executions():
                try:
                    # Abortar ejecuciones PENDING o RUNNING de este nodo
                    executions = Execution.objects.filter(
                        workflow_node=self,
                        status__in=['PENDING', 'RUNNING']
                    )
                    count = executions.count()
                    if count > 0:
                        executions.update(
                            status='INTERRUPTED',
                            error_message='Nodo deshabilitado'
                        )
                        logger.info(f"🛑 {count} ejecución(es) abortada(s) para nodo '{self.name}'")
                except Exception as e:
                    logger.error(f"❌ Error abortando ejecuciones para nodo {self.name}: {e}")
            
            transaction.on_commit(abort_executions)
        
        super().save(*args, **kwargs)
    
    def get_chain_nodes(self):
        """
        Retorna todos los nodos que están en la misma cadena que este nodo.
        
        Si este nodo es un master, retorna todos los nodos en su cadena.
        Si este nodo está en cadena, retorna todos los nodos de la misma cadena (incluyéndose a sí mismo).
        
        Returns:
            QuerySet: Nodos en la misma cadena, ordenados por prioridad
        """
        if self.is_chain_node and self.master_node:
            # Si es nodo en cadena, retornar todos los nodos de su master
            return WorkflowNode.objects.filter(
                workflow=self.workflow,
                master_node=self.master_node,
                is_chain_node=True
            ).order_by('priority', 'id')
        elif not self.is_chain_node:
            # Si es master, retornar todos sus nodos en cadena
            return WorkflowNode.objects.filter(
                workflow=self.workflow,
                master_node=self,
                is_chain_node=True
            ).order_by('priority', 'id')
        else:
            # Nodo sin master asignado (no debería ocurrir)
            return WorkflowNode.objects.none()
    
    def sync_from_template(self, template_node):
        """
        Sincroniza este nodo desde su nodo de plantilla.
        Si el nodo está vinculado a una plantilla, se sincroniza automáticamente.
        Los campos override solo indican que fueron editados manualmente, pero la sincronización
        siempre actualiza desde la plantilla para mantener consistencia.
        
        Si el nodo no está vinculado al template_node pero tiene la misma key,
        lo vincula primero antes de sincronizar.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Si no está vinculado pero tiene la misma key, vincularlo
        if not self.template_node and self.key == template_node.key:
            logger.info(f"🔗 Vinculando nodo '{self.key}' a template_node antes de sincronizar")
            self.link_to_template_node(template_node)
            return
        
        # Si está vinculado a otro template_node diferente, no sincronizar
        if self.template_node and self.template_node != template_node:
            logger.warning(
                f"⚠️ Nodo '{self.key}' está vinculado a otra plantilla. No se sincroniza."
            )
            return
        
        # Si no está vinculado y no tiene la misma key, no sincronizar
        if not self.template_node:
            logger.warning(
                f"⚠️ Nodo '{self.key}' no está vinculado a template_node '{template_node.key}'. No se sincroniza."
            )
            return
        
        updated = False
        changes = []
        next_run_updated = False
        metadata_updated = False
        
        metadata = self.metadata or {}
        origin_template_id = template_node.template_id
        if metadata.get('origin_template_id') != origin_template_id:
            metadata['origin_template_id'] = origin_template_id
            self.metadata = metadata
            updated = True
            metadata_updated = True
            changes.append("metadata origen plantilla actualizada")
        
        # ✅ CRÍTICO: Sincronizar intervalo - Nodos encadenados SIEMPRE tienen interval_seconds=0
        if template_node.is_chain_node:
            # ✅ FORZAR: Nodos encadenados SIEMPRE tienen intervalo 0 y next_run_at=None
            target_interval = 0
            self.is_chain_node = True
            if self.interval_seconds != 0:
                old_value = self.interval_seconds
                self.interval_seconds = 0
                updated = True
                changes.append(f"intervalo: {old_value}s → 0s (nodo encadenado)")
            # Nodos encadenados NO tienen next_run_at
            if self.next_run_at is not None:
                old_next_run = self.next_run_at
                self.next_run_at = None
                next_run_updated = True
                changes.append(f"next_run_at → None (nodo encadenado): {old_next_run.strftime('%H:%M:%S') if old_next_run else 'N/A'}")
        else:
            # ✅ Nodos master: usar intervalo de la plantilla
            target_interval = template_node.interval_seconds or 0
            
        if self.interval_seconds != target_interval:
            old_value = self.interval_seconds
            self.interval_seconds = target_interval
            # Si tenía override, resetearlo porque ahora viene de la plantilla
            if self.override_interval:
                self.override_interval = False
                changes.append("override_interval reseteado")
            updated = True
            changes.append(f"intervalo: {old_value}s → {target_interval}s")
            
            # CRÍTICO: Si cambió el intervalo, recalcular next_run_at para respetar el nuevo intervalo
            # Esto asegura que el sistema use el nuevo intervalo inmediatamente
            from django.utils import timezone
            from datetime import timedelta
            
            now = timezone.now()
            # Calcular nuevo next_run_at basado en el intervalo actualizado
            if target_interval > 0:
                if not self.next_run_at or self.next_run_at <= now:
                    # No tiene next_run_at o ya pasó, usar nuevo intervalo desde ahora
                    next_time = now + timedelta(seconds=target_interval)
                else:
                    # Está en el futuro, recalcular manteniendo el tiempo relativo
                    time_until_next = (self.next_run_at - now).total_seconds()
                    if time_until_next > target_interval:
                        next_time = now + timedelta(seconds=target_interval)
                    else:
                        next_time = self.next_run_at
            else:
                next_time = None
            
            # ✅ SIN DESFASE: El intervalo se respeta exactamente, sin alineación a segundos específicos
            old_next_run = self.next_run_at
            self.next_run_at = next_time
            if old_next_run != next_time:
                next_run_updated = True
                changes.append(f"next_run_at recalculado: {old_next_run.strftime('%H:%M:%S') if old_next_run else 'N/A'} → {next_time.strftime('%H:%M:%S') if next_time else 'N/A'}")
        
        # Sincronizar prioridad - SIEMPRE desde la plantilla
        if self.priority != template_node.priority:
            old_value = self.priority
            self.priority = template_node.priority
            if self.override_priority:
                self.override_priority = False
                changes.append("override_priority reseteado")
            updated = True
            changes.append(f"prioridad: {old_value} → {template_node.priority}")
        
        # Sincronizar enabled - SIEMPRE desde la plantilla
        if self.enabled != template_node.enabled:
            old_value = self.enabled
            self.enabled = template_node.enabled
            if self.override_enabled:
                self.override_enabled = False
                changes.append("override_enabled reseteado")
            updated = True
            changes.append(f"enabled: {old_value} → {template_node.enabled}")
        
        # Sincronizar parámetros - SIEMPRE desde la plantilla
        if self.parameters != template_node.parameters:
            self.parameters = template_node.parameters.copy()
            if self.override_parameters:
                self.override_parameters = False
                changes.append("override_parameters reseteado")
            updated = True
            changes.append("parámetros actualizados")
        
        # Sincronizar estado de cadena
        template_is_chain = bool(template_node.is_chain_node)
        if self.is_chain_node != template_is_chain:
            old_state = "cadena" if self.is_chain_node else "regular"
            new_state = "cadena" if template_is_chain else "regular"
            self.is_chain_node = template_is_chain
            updated = True
            changes.append(f"estado cadena: {old_state} → {new_state}")
            if not template_is_chain and self.master_node:
                self.master_node = None
                changes.append("master_node eliminado (ya no está en cadena)")
                updated = True
        
        if template_is_chain:
            desired_master = None
            if template_node.master_node:
                desired_master = WorkflowNode.objects.filter(
                    workflow=self.workflow,
                    template_node=template_node.master_node
                ).first()
            if self.master_node != desired_master:
                old_master = self.master_node.name if self.master_node else "N/A"
                self.master_node = desired_master
                new_master = desired_master.name if desired_master else "N/A"
                changes.append(f"master: {old_master} → {new_master}")
                updated = True
        else:
            if self.master_node:
                self.master_node = None
                changes.append("master removido (nodo master)")
                updated = True
        
        # También sincronizar el nombre desde la plantilla
        if self.name != template_node.name:
            old_name = self.name
            self.name = template_node.name
            updated = True
            changes.append(f"nombre: '{old_name}' → '{template_node.name}'")
        
        if updated:
            # Guardar todos los campos actualizados, incluyendo next_run_at si cambió
            update_fields = []
            if self.interval_seconds != template_node.interval_seconds or 'intervalo' in str(changes):
                update_fields.extend(['interval_seconds'])
            if self.priority != template_node.priority or 'prioridad' in str(changes):
                update_fields.extend(['priority'])
            if self.enabled != template_node.enabled or 'enabled' in str(changes):
                update_fields.extend(['enabled'])
            if self.parameters != template_node.parameters or 'parámetros' in str(changes):
                update_fields.extend(['parameters'])
            if self.name != template_node.name or 'nombre' in str(changes):
                update_fields.extend(['name'])
            if next_run_updated:
                update_fields.append('next_run_at')
            if metadata_updated:
                update_fields.append('metadata')
            if any('override' in c for c in changes):
                if 'override_interval' in str(changes):
                    update_fields.append('override_interval')
                if 'override_priority' in str(changes):
                    update_fields.append('override_priority')
                if 'override_enabled' in str(changes):
                    update_fields.append('override_enabled')
                if 'override_parameters' in str(changes):
                    update_fields.append('override_parameters')
            
            # Si no hay campos específicos, guardar todos
            if not update_fields:
                self.save()
            else:
                self.save(update_fields=update_fields)
            logger.info(
                f"✅ Nodo '{self.key}' sincronizado desde plantilla. Cambios: {', '.join(changes)}"
            )
        else:
            logger.debug(f"ℹ️ Nodo '{self.key}' ya está sincronizado con plantilla.")


class WorkflowEdge(models.Model):
    """
    Relación entre nodos (dependencias) dentro de un workflow.
    """

    EDGE_TYPES = [
        ("secuencial", "Secuencial"),
        ("condicional", "Condicional"),
    ]

    workflow = models.ForeignKey(
        OLTWorkflow,
        on_delete=models.CASCADE,
        related_name="edges",
    )
    upstream_node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.CASCADE,
        related_name="downstream_edges",
    )
    downstream_node = models.ForeignKey(
        WorkflowNode,
        on_delete=models.CASCADE,
        related_name="upstream_edges",
    )
    edge_type = models.CharField(
        max_length=20,
        choices=EDGE_TYPES,
        default="secuencial",
    )
    condition = models.JSONField(
        blank=True,
        default=dict,
        help_text="Condiciones adicionales para ejecución (solo para condicional).",
    )
    metadata = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "snmp_workflow_edges"
        unique_together = (("workflow", "upstream_node", "downstream_node"),)
        verbose_name = "Dependencia de Workflow SNMP"
        verbose_name_plural = "Dependencias de Workflow SNMP"

    def __str__(self):
        return f"{self.upstream_node} ➜ {self.downstream_node}"