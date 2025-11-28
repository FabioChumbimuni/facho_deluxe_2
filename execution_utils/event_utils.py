from typing import Optional, Dict, Any

from django.db import transaction

# Importar desde execution_coordinator.models porque los modelos deben mantenerse en la BD
from execution_coordinator.models import CoordinatorEvent


def create_execution_event(
    *,
    event_type: str,
    execution=None,
    snmp_job=None,
    job_host=None,
    olt=None,
    decision: str = "",
    source: str = "SYSTEM",
    reason: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Optional[CoordinatorEvent]:
    """
    Crea un registro en `CoordinatorEvent` de forma defensiva.

    Args:
        event_type: Código del evento (EXECUTION_STARTED, EXECUTION_COMPLETED, etc.)
        execution: Instancia de `executions.Execution`
        snmp_job: Instancia de `snmp_jobs.SnmpJob`
        job_host: Instancia de `snmp_jobs.SnmpJobHost`
        olt: Instancia de `hosts.OLT`
        decision: Código de decisión (ENQUEUE, COMPLETE, WAIT, ABORT, etc.)
        source: Origen del evento (SCHEDULER, SYSTEM, DELIVERY_CHECKER, etc.)
        reason: Texto descriptivo corto
        details: Diccionario serializable con información adicional
    """
    try:
        with transaction.atomic():
            event = CoordinatorEvent.objects.create(
                execution=execution,
                snmp_job=snmp_job or (execution.snmp_job if execution else None),
                job_host=job_host or (execution.job_host if execution else None),
                olt=olt or (execution.olt if execution else None),
                event_type=event_type,
                decision=decision,
                source=source,
                reason=reason,
                details=details or {},
            )
        return event
    except Exception:
        # Evitar que fallos en logging de eventos interrumpan el flujo principal
        return None


