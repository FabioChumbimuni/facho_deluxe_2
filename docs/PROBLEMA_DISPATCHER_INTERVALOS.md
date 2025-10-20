# 🚨 PROBLEMA: Dispatcher No Respeta Intervalos de Jobs

## 📋 **Descripción del Problema**

El sistema actual tiene un **dispatcher** que se ejecuta cada 30 segundos y está creando ejecuciones constantemente, **ignorando completamente los intervalos configurados** en los jobs.

### 🔍 **Síntomas Observados**

1. **Dispatcher ejecutándose cada 30 segundos**:
   ```
   [19:30:53] 🔍 Dispatcher: Revisando tareas habilitadas...
   [19:31:23] 🔍 Dispatcher: Revisando tareas habilitadas...
   [19:31:53] 🔍 Dispatcher: Revisando tareas habilitadas...
   ```

2. **Jobs ejecutándose constantemente**:
   - Job configurado para `1d` (1 día) se ejecuta cada 30 segundos
   - Job configurado para `30s` se ejecuta cada 30 segundos
   - **No hay diferencia** entre intervalos

3. **Creación excesiva de ejecuciones**:
   ```
   ✅ Creada ejecución: 32764 para OLT SMP-10
   ✅ Creada ejecución: 32765 para OLT SMP-10
   ✅ Creada ejecución: 32766 para OLT SMP-10
   ```

## 🔧 **Configuración Actual Problemática**

### **1. Dispatcher Fijo**
```python
# core/settings.py
CELERY_BEAT_SCHEDULE = {
    'dispatcher-check-and-enqueue': {
        'task': 'snmp_jobs.tasks.dispatcher_check_and_enqueue',
        'schedule': 30.0,  # ❌ FIJO cada 30 segundos
    },
}
```

### **2. Lógica del Dispatcher**
```python
@shared_task
def dispatcher_check_and_enqueue():
    # ❌ PROBLEMA: Se ejecuta cada 30s sin importar el intervalo del job
    enabled_tasks = SnmpJob.objects.filter(
        enabled=True, 
        job_type='descubrimiento',
        next_run_at__lte=now  # ❌ next_run_at se actualiza mal
    )
```

### **3. Actualización Incorrecta de next_run_at**
```python
# ❌ PROBLEMA: next_run_at se actualiza INMEDIATAMENTE
next_run = calculate_next_run(task.interval_raw)
task.next_run_at = next_run  # ❌ Se actualiza antes de verificar
task.save()
```

## 🎯 **Problemas Específicos**

### **Problema 1: Dispatcher Demasiado Frecuente**
- **Actual**: Cada 30 segundos
- **Ideal**: Debería adaptarse al job más lento
- **Impacto**: Desperdicio de recursos, logs saturados

### **Problema 2: next_run_at Se Actualiza Mal**
- **Actual**: Se actualiza inmediatamente después de crear ejecución
- **Ideal**: Solo se actualiza cuando el job realmente se ejecuta
- **Impacto**: Jobs se ejecutan constantemente

### **Problema 3: No Respeta Intervalos**
- **Actual**: Job de 1 día se ejecuta cada 30 segundos
- **Ideal**: Job de 1 día se ejecuta cada 24 horas
- **Impacto**: Sobrecarga del sistema, datos duplicados

## 📊 **Impacto en el Sistema**

### **Recursos**
- ⚠️ **CPU**: Dispatcher ejecutándose constantemente
- ⚠️ **Memoria**: Ejecuciones acumulándose
- ⚠️ **Redis**: Colas saturadas
- ⚠️ **Logs**: Archivos creciendo exponencialmente

### **Datos**
- ⚠️ **Duplicados**: Múltiples ejecuciones del mismo job
- ⚠️ **Inconsistencia**: next_run_at incorrecto
- ⚠️ **Performance**: Base de datos sobrecargada

### **Operaciones**
- ⚠️ **SNMP**: Consultas excesivas a equipos
- ⚠️ **Locks**: Conflictos de concurrencia
- ⚠️ **Workers**: Saturados con tareas innecesarias

## 🛠️ **Soluciones Propuestas**

### **Opción 1: Celery Beat Dinámico (Recomendado)**
```python
# Cada job tiene su propio schedule
CELERY_BEAT_SCHEDULE = {
    'job-prueba-daily': {
        'task': 'snmp_jobs.tasks.discovery_main_task',
        'schedule': crontab(minute=0, hour=0),  # Diario
        'args': (job_id, olt_id, execution_id)
    }
}
```

### **Opción 2: Dispatcher Inteligente**
```python
# Dispatcher que respeta intervalos
def dispatcher_check_and_enqueue():
    # Solo ejecutar jobs que realmente están listos
    ready_jobs = SnmpJob.objects.filter(
        enabled=True,
        next_run_at__lte=timezone.now()
    )
    # Actualizar next_run_at SOLO después de ejecutar
```

### **Opción 3: APScheduler**
```python
# Programador más flexible
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=discovery_main_task,
    trigger="interval",
    days=1,  # Respeta el intervalo
    id='daily_discovery'
)
```

## 🎯 **Recomendación**

**Implementar Opción 1 (Celery Beat Dinámico)** porque:

1. ✅ **Profesional**: Usa herramientas estándar de Celery
2. ✅ **Eficiente**: Cada job tiene su propio schedule
3. ✅ **Escalable**: Fácil agregar/quitar jobs
4. ✅ **Mantenible**: Código más limpio y comprensible
5. ✅ **Confiable**: Menos puntos de falla

## 📈 **Beneficios Esperados**

- 🚀 **Performance**: 90% menos ejecuciones innecesarias
- 💾 **Recursos**: 80% menos uso de CPU/memoria
- 📝 **Logs**: 95% menos entradas de log
- 🔒 **Estabilidad**: Sin conflictos de locks
- 📊 **Datos**: Sin duplicados ni inconsistencias

---

**Fecha**: 2025-09-08  
**Severidad**: 🔴 CRÍTICA  
**Estado**: 🚧 EN PROGRESO  
**Asignado**: Sistema de Tareas Facho Deluxe v2
