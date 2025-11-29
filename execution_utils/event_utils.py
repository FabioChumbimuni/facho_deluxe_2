from typing import Optional, Dict, Any

# CoordinatorEvent eliminado - ya no se usan eventos en BD
# Esta función ahora solo retorna None silenciosamente


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
) -> None:
    """
    Función desactivada - CoordinatorEvent ya no existe.
    Los eventos ahora solo se registran en logs de archivo.
    
    Args: (mantenidos para compatibilidad, pero no se usan)
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
    # Ya no se crean eventos en BD - retornar None silenciosamente
    return None


