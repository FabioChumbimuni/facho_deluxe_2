from django.db import models
from django.conf import settings
from snmp_jobs.models import SnmpJob, SnmpJobHost


class Execution(models.Model):
    """
    Registro de ejecución (por OLT). `raw_output` puede contener resultados para varios OIDs
    (si ejecutas un batch de OIDs sobre la OLT) o un único valor si eliges por OID.
    """
    STATUS_PENDING = "PENDING"
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_INTERRUPTED = "INTERRUPTED"
    STATUS_CHOICES = [
        (STATUS_PENDING, STATUS_PENDING),
        (STATUS_RUNNING, STATUS_RUNNING),
        (STATUS_SUCCESS, STATUS_SUCCESS),
        (STATUS_FAILED, STATUS_FAILED),
        (STATUS_INTERRUPTED, STATUS_INTERRUPTED),
    ]

    snmp_job = models.ForeignKey(SnmpJob, null=True, blank=True, on_delete=models.SET_NULL, db_column="snmp_job_id")
    job_host = models.ForeignKey(SnmpJobHost, null=True, blank=True, on_delete=models.SET_NULL, db_column="job_host_id")
    olt = models.ForeignKey("hosts.OLT", null=True, blank=True, on_delete=models.SET_NULL, db_column="olt_id")

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    celery_task_id = models.CharField(max_length=255, null=True, blank=True)
    worker_name = models.CharField(max_length=255, null=True, blank=True)

    attempt = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    # resultado: summary para listar, raw_output para todo (json)
    result_summary = models.JSONField(null=True, blank=True)
    raw_output = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "snmp_executions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]
        verbose_name = "Ejecución"
        verbose_name_plural = "Ejecuciones"

    def __str__(self):
        olt_repr = self.olt.abreviatura if self.olt else "no-olt"
        return f"Exec {self.id} {olt_repr} [{self.status}]"
