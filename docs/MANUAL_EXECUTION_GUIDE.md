# 🚀 Guía de Ejecución Manual de Tareas SNMP

## 📋 Descripción

La nueva funcionalidad de **Ejecución Manual** permite ejecutar tareas SNMP seleccionadas desde el Django Admin sin esperar a que se ejecuten automáticamente según su programación.

## 🎯 Características

- ✅ **Ejecución inmediata** de tareas seleccionadas
- ✅ **Validación automática** de tareas y OLTs habilitadas
- ✅ **Retroalimentación visual** con mensajes informativos
- ✅ **Respeto de configuraciones** (solo procesa OLTs habilitadas)
- ✅ **Registro de usuario** que ejecutó la tarea manualmente
- ✅ **Actualización automática** del campo `last_run_at`

## 🔧 Cómo Usar

### 1. Acceder al Admin de Tareas SNMP

1. Ingresar al Django Admin
2. Ir a **SNMP Jobs** → **Snmp jobs**
3. Verás la lista de todas las tareas SNMP

### 2. Seleccionar Tareas

1. **Marcar las casillas** de las tareas que deseas ejecutar
2. Las tareas pueden estar habilitadas o deshabilitadas (solo se ejecutarán las habilitadas)

### 3. Ejecutar la Acción

1. En el dropdown de **Acciones**, seleccionar **🚀 Ejecutar tareas seleccionadas**
2. Hacer clic en **Ir**

### 4. Verificar Resultados

La acción mostrará mensajes informativos:

- **🚀 Éxito**: `Ejecutadas X tareas: Y ejecuciones creadas y encoladas`
- **📊 Info**: `Las ejecuciones aparecerán en "Ejecuciones" y se procesarán en la cola discovery_main`
- **⚠️ Advertencia**: Si no hay tareas habilitadas o sin OLTs asociadas

## 📊 Qué Sucede Internamente

### 1. Validación
- Filtra solo **tareas habilitadas** (`enabled=True`)
- Verifica que tengan **job_hosts habilitados**
- Confirma que las **OLTs estén habilitadas** (`habilitar_olt=True`)

### 2. Creación de Ejecuciones
Para cada tarea válida:
- Crea registros en la tabla **Executions** con estado `PENDING`
- Registra el **usuario** que ejecutó la acción
- Encola la tarea en la cola **discovery_main** con 20 hilos

### 3. Actualización de Metadatos
- Actualiza `last_run_at` de la tarea con la fecha/hora actual
- Asigna el `celery_task_id` a cada ejecución

## 🔍 Verificar Ejecuciones

### Ver Ejecuciones Creadas
1. Ir a **EXECUTIONS** → **Executions**
2. Filtrar por fecha reciente o usuario
3. Ver el progreso de las ejecuciones:
   - `PENDING`: Esperando procesamiento
   - `RUNNING`: En ejecución
   - `SUCCESS`: Completada exitosamente
   - `FAILED`: Falló durante la ejecución

### Monitorear con Gestionar Sistema
```bash
# Ver estado general
python gestionar_sistema.py status

# Ver ejecuciones recientes
python gestionar_sistema.py recent

# Ver tareas activas en Celery
python gestionar_sistema.py tasks
```

## 🎯 Casos de Uso

### 1. Pruebas de Desarrollo
- Ejecutar tareas específicas para probar configuraciones
- Verificar conectividad con OLTs particulares

### 2. Ejecución Bajo Demanda
- Ejecutar tareas fuera de su horario programado
- Obtener datos SNMP inmediatamente cuando se necesite

### 3. Resolución de Problemas
- Re-ejecutar tareas que fallaron
- Probar tareas después de cambios de configuración

### 4. Mantenimiento
- Ejecutar tareas después de mantenimiento de red
- Verificar estado de OLTs después de cambios

## ⚠️ Consideraciones Importantes

### Limitaciones
- Solo se ejecutan **tareas habilitadas**
- Solo procesa **OLTs habilitadas**
- Requiere que la tarea tenga **job_hosts configurados**

### Rendimiento
- Las ejecuciones se procesan en la cola **discovery_main** (20 hilos)
- Múltiples ejecuciones simultáneas son posibles
- El sistema respeta los **locks de Redis** para evitar conflictos

### Seguridad
- Solo usuarios con permisos de **staff** pueden ejecutar
- Se registra qué usuario ejecutó cada tarea
- Respeta todas las validaciones de seguridad existentes

## 🔧 Troubleshooting

### "No se crearon ejecuciones"
**Posibles causas:**
- Tareas seleccionadas están deshabilitadas
- No tienen OLTs asociadas
- Las OLTs asociadas están deshabilitadas
- No hay job_hosts habilitados

**Solución:**
1. Verificar que las tareas estén habilitadas
2. Confirmar que tengan OLTs asociadas y habilitadas
3. Revisar la configuración de job_hosts

### "Las ejecuciones no aparecen"
**Posibles causas:**
- Error en la cola de Celery
- Workers no están ejecutándose

**Solución:**
```bash
# Verificar workers
python gestionar_sistema.py workers

# Reiniciar si es necesario
python gestionar_sistema.py restart
```

### Ejecuciones se quedan en PENDING
**Posibles causas:**
- Workers de discovery_main no están activos
- Problemas de conectividad con Redis
- Locks de Redis bloqueando ejecuciones

**Solución:**
```bash
# Verificar estado completo
python gestionar_sistema.py status

# Limpiar locks si es necesario
redis-cli keys "lock:snmp:olt:*" | xargs redis-cli del
```

## 📈 Ejemplos de Uso

### Ejemplo 1: Ejecutar Tarea Específica
1. Buscar la tarea por nombre en el admin
2. Seleccionar solo esa tarea
3. Ejecutar acción
4. Verificar en Executions el resultado

### Ejemplo 2: Ejecutar Múltiples Tareas de una Marca
1. Filtrar por marca en el admin
2. Seleccionar todas las tareas deseadas
3. Ejecutar acción
4. Monitorear progreso con `gestionar_sistema.py tasks`

### Ejemplo 3: Re-ejecutar Tareas Fallidas
1. Identificar tareas que fallaron recientemente
2. Ejecutarlas manualmente para retry
3. Verificar que se resuelvan los problemas

---

## 🎉 ¡Funcionalidad Lista para Usar!

La ejecución manual de tareas está completamente implementada y probada. Permite un control granular sobre cuándo y qué tareas SNMP se ejecutan, manteniendo todas las validaciones y medidas de seguridad del sistema.
