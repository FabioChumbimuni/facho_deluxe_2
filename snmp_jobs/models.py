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
    """
    snmp_job = models.ForeignKey(SnmpJob, on_delete=models.CASCADE, db_column="snmp_job_id", related_name="job_hosts")
    olt = models.ForeignKey("hosts.OLT", on_delete=models.CASCADE, db_column="olt_id", related_name="job_host_links")

    enabled = models.BooleanField(default=True)
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
        ]
        verbose_name = "OLT en Tarea"
        verbose_name_plural = "OLTs en Tarea"

    def __str__(self):
        return f"{self.snmp_job.nombre} -> {self.olt.abreviatura or self.olt.ip_address}"