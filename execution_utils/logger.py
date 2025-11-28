"""
Sistema de Logging Dual para el Coordinator

Escribe tanto en:
1. Base de datos (CoordinatorLog model) para consultas
2. Archivo de log rotativo para troubleshooting
"""

import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from django.conf import settings
from django.utils import timezone


class CoordinatorLogger:
    """
    Logger personalizado para el Coordinator
    Escribe en BD y archivo simultáneamente
    """
    
    def __init__(self, name='coordinator'):
        self.name = name
        
        # Logger estándar de Python
        self.file_logger = logging.getLogger(f'coordinator.{name}')
        self.file_logger.setLevel(logging.DEBUG)
        
        # Configurar handler de archivo si no existe
        if not self.file_logger.handlers:
            self._setup_file_handler()
    
    def _setup_file_handler(self):
        """Configura el handler de archivo rotativo"""
        # Directorio de logs
        log_dir = Path(settings.BASE_DIR) / 'logs' / 'coordinator'
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Archivo de log
        log_file = log_dir / f'{self.name}.log'
        
        # Handler rotativo (10 MB por archivo, mantener 5 archivos)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        
        # Formato detallado
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        self.file_logger.addHandler(handler)
    
    def _log_to_db(self, event_type, message, olt=None, level='INFO', details=None):
        """Escribe log en la base de datos"""
        try:
            # Importar desde execution_coordinator.models porque los modelos deben mantenerse en la BD
            from execution_coordinator.models import CoordinatorLog
            CoordinatorLog.log(
                event_type=event_type,
                message=message,
                olt=olt,
                level=level,
                details=details
            )
        except Exception as e:
            # Si falla el log en BD, solo registrar en archivo
            self.file_logger.error(f"Error escribiendo log en BD: {e}")
    
    def debug(self, message, olt=None, event_type='STATE_CHANGE', details=None):
        """Log nivel DEBUG"""
        self.file_logger.debug(message)
        # DEBUG no se guarda en BD por volumen
    
    def info(self, message, olt=None, event_type='STATE_CHANGE', details=None):
        """Log nivel INFO"""
        self.file_logger.info(message)
        self._log_to_db(event_type, message, olt, 'INFO', details)
    
    def warning(self, message, olt=None, event_type='QUOTA_WARNING', details=None):
        """Log nivel WARNING"""
        self.file_logger.warning(message)
        self._log_to_db(event_type, message, olt, 'WARNING', details)
    
    def error(self, message, olt=None, event_type='EXECUTION_FAILED', details=None):
        """Log nivel ERROR"""
        self.file_logger.error(message)
        self._log_to_db(event_type, message, olt, 'ERROR', details)
    
    def critical(self, message, olt=None, event_type='QUOTA_VIOLATION', details=None):
        """Log nivel CRITICAL"""
        self.file_logger.critical(message)
        self._log_to_db(event_type, message, olt, 'CRITICAL', details)
    
    # Métodos de conveniencia para eventos específicos
    
    def log_task_added(self, task_name, olt=None, details=None):
        """Log cuando se agrega una tarea al plan"""
        msg = f"✅ Tarea '{task_name}' agregada al plan"
        self.info(msg, olt=olt, event_type='TASK_ADDED', details=details)
    
    def log_task_removed(self, task_name, olt=None, details=None):
        """Log cuando se remueve una tarea del plan"""
        msg = f"❌ Tarea '{task_name}' removida del plan"
        self.warning(msg, olt=olt, event_type='TASK_REMOVED', details=details)
    
    def log_plan_created(self, olt, total_tasks, details=None):
        """Log cuando se crea un nuevo plan"""
        msg = f"📋 Plan de ejecución creado: {total_tasks} tareas para {olt.abreviatura if olt else 'OLT'}"
        self.info(msg, olt=olt, event_type='PLAN_CREATED', details=details)
    
    def log_plan_adjusted(self, olt, reason, details=None):
        """Log cuando se ajusta un plan existente"""
        msg = f"🔄 Plan ajustado para {olt.abreviatura if olt else 'OLT'}: {reason}"
        self.warning(msg, olt=olt, event_type='PLAN_ADJUSTED', details=details)
    
    def log_execution_started(self, task_name, olt=None, details=None):
        """Log cuando inicia una ejecución"""
        msg = f"▶️ Iniciando ejecución: {task_name}"
        self.info(msg, olt=olt, event_type='EXECUTION_STARTED', details=details)
    
    def log_execution_completed(self, task_name, duration_ms, olt=None, details=None):
        """Log cuando completa una ejecución"""
        msg = f"✅ Ejecución completada: {task_name} ({duration_ms}ms)"
        self.info(msg, olt=olt, event_type='EXECUTION_COMPLETED', details=details)
    
    def log_execution_failed(self, task_name, error, olt=None, details=None):
        """Log cuando falla una ejecución"""
        msg = f"❌ Ejecución fallida: {task_name} - Error: {error}"
        self.error(msg, olt=olt, event_type='EXECUTION_FAILED', details=details)
    
    def log_execution_interrupted(self, task_name, reason, olt=None, details=None):
        """Log cuando una ejecución es interrumpida o perdida"""
        msg = f"⏸️ Ejecución interrumpida: {task_name} - Razón: {reason}"
        self.warning(msg, olt=olt, event_type='EXECUTION_INTERRUPTED', details=details)
    
    def log_execution_aborted(self, task_name, reason, olt=None, details=None):
        """Log cuando se aborta una ejecución"""
        msg = f"🛑 Ejecución abortada: {task_name} - Razón: {reason}"
        self.warning(msg, olt=olt, event_type='EXECUTION_ABORTED', details=details)
    
    def log_quota_warning(self, olt, task_type, completion_pct, details=None):
        """Log cuando una cuota está en riesgo"""
        msg = f"⚠️ Cuota en riesgo: {task_type} - {completion_pct:.1f}% completado"
        self.warning(msg, olt=olt, event_type='QUOTA_WARNING', details=details)
    
    def log_quota_violation(self, olt, task_type, severity, details=None):
        """Log cuando se viola una cuota"""
        msg = f"🚨 Violación de cuota [{severity}]: {task_type}"
        self.critical(msg, olt=olt, event_type='QUOTA_VIOLATION', details=details)
    
    def log_olt_disabled(self, olt, details=None):
        """Log cuando se deshabilita una OLT"""
        msg = f"🛑 OLT deshabilitada: {olt.abreviatura if olt else 'OLT'}"
        self.warning(msg, olt=olt, event_type='OLT_DISABLED', details=details)
    
    def log_olt_enabled(self, olt, details=None):
        """Log cuando se habilita una OLT"""
        msg = f"✅ OLT habilitada: {olt.abreviatura if olt else 'OLT'}"
        self.info(msg, olt=olt, event_type='OLT_ENABLED', details=details)
    
    def log_slow_mode(self, olt, reason, details=None):
        """Log cuando se activa modo lento"""
        msg = f"🐌 Modo lento activado: {reason}"
        self.warning(msg, olt=olt, event_type='SLOW_MODE_ACTIVATED', details=details)
    
    def log_emergency_replan(self, olt, reason, details=None):
        """Log cuando se activa re-planificación de emergencia"""
        msg = f"🚨 Re-planificación de emergencia: {reason}"
        self.error(msg, olt=olt, event_type='EMERGENCY_REPLAN', details=details)
    
    def log_triage_mode(self, olt, tasks_kept, tasks_skipped, details=None):
        """Log cuando se activa modo triage"""
        msg = f"⚠️ Modo triage activado: {tasks_kept} tareas mantenidas, {tasks_skipped} omitidas"
        self.error(msg, olt=olt, event_type='TRIAGE_MODE', details=details)


# Instancia global del logger
coordinator_logger = CoordinatorLogger('main')

