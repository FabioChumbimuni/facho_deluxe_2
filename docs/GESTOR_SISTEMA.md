# 🚀 Gestor de Sistema - Facho Deluxe v2

## 📋 Descripción

Script único y completo para gestionar todo el sistema Celery, workers, colas, tareas y estado del sistema Facho Deluxe v2.

## 🎯 Propósito

- **Gestionar Workers**: Iniciar, detener y reiniciar workers de Celery
- **Monitorear Estado**: Verificar workers, Redis, base de datos y tareas
- **Gestionar Tareas**: Habilitar/deshabilitar jobs y limpiar ejecuciones
- **Utilidades**: Limpiar Redis y mostrar información del sistema

## 📊 Workers Configurados

| Worker | Cola | Concurrency | Propósito |
|--------|------|-------------|-----------|
| `default` | `default` | 2 | Tareas generales |
| `discovery_main` | `discovery_main` | 20 | Descubrimiento principal |
| `discovery_priority` | `discovery_priority` | 5 | Descubrimiento prioritario |
| `cleanup` | `cleanup` | 2 | Limpieza de datos |
| `background_deletes` | `background_deletes` | 3 | **Borrado masivo eficiente** |

## 🚀 Comandos Disponibles

### 🚀 Gestión de Workers

```bash
# Iniciar todo el sistema
python gestionar_sistema.py start

# Detener todo el sistema
python gestionar_sistema.py stop

# Reiniciar todo el sistema
python gestionar_sistema.py restart
```

### 📊 Estado del Sistema

```bash
# Estado completo del sistema
python gestionar_sistema.py status

# Solo estado de workers
python gestionar_sistema.py workers

# Solo estado de Redis y colas
python gestionar_sistema.py redis

# Solo estado de la base de datos
python gestionar_sistema.py database

# Solo tareas de Celery activas
python gestionar_sistema.py tasks
```

### ⚙️ Gestión de Tareas

```bash
# Habilitar todos los SNMP Jobs
python gestionar_sistema.py enable-jobs

# Deshabilitar todos los SNMP Jobs
python gestionar_sistema.py disable-jobs

# Limpiar ejecuciones PENDING
python gestionar_sistema.py clear-pending

# Mostrar ejecuciones recientes
python gestionar_sistema.py recent
```

### 🧹 Utilidades

```bash
# Limpiar Redis completamente
python gestionar_sistema.py flush-redis

# Mostrar ayuda
python gestionar_sistema.py help
```

## 🔧 Funcionalidades Específicas

### 🗑️ Borrado Masivo Eficiente

El sistema incluye una cola especial `background_deletes` que:

- **Lotes de 500 registros** por vez
- **Pausas de 0.5 segundos** entre lotes
- **3 workers paralelos** para máxima eficiencia
- **Basado en el código original de GitHub**

### 📊 Monitoreo Completo

El comando `status` muestra:

- ✅ Estado de todos los workers
- 📊 Colas de Redis y tareas pendientes
- 📋 Estadísticas de la base de datos
- 🔄 Tareas de Celery activas
- ⏰ Fecha y hora de verificación

### 🎯 Gestión de Jobs

- **enable-jobs**: Habilita todos los SNMP Jobs para que corran automáticamente
- **disable-jobs**: Deshabilita todos los SNMP Jobs
- **clear-pending**: Limpia ejecuciones PENDING usando la cola eficiente

## 📝 Ejemplos de Uso

### 🔄 Reiniciar y Habilitar Todo

```bash
# 1. Reiniciar el sistema completo
python gestionar_sistema.py restart

# 2. Verificar que todo esté funcionando
python gestionar_sistema.py status

# 3. Habilitar todos los jobs para que corran
python gestionar_sistema.py enable-jobs

# 4. Verificar que los jobs estén habilitados
python gestionar_sistema.py database
```

### 🧹 Limpiar Sistema

```bash
# 1. Limpiar ejecuciones PENDING
python gestionar_sistema.py clear-pending

# 2. Limpiar Redis si es necesario
python gestionar_sistema.py flush-redis

# 3. Verificar estado
python gestionar_sistema.py status
```

### 📊 Monitoreo Continuo

```bash
# Verificar estado completo
python gestionar_sistema.py status

# Solo ver workers
python gestionar_sistema.py workers

# Solo ver colas de Redis
python gestionar_sistema.py redis

# Ver ejecuciones recientes
python gestionar_sistema.py recent
```

## 🔗 Integración con Django Admin

### 🗑️ Acción "Borrar Masivo"

En el Django Admin (`/admin/executions/execution/`):

1. **Seleccionar registros** a eliminar
2. **Usar acción "Borrar masivo"**
3. **Sistema automático**:
   - Usa cola `background_deletes`
   - Lotes de 500 registros
   - Pausas de 0.5s
   - Muestra Task ID
   - No bloquea la interfaz

### 📊 Información Mostrada

- ✅ Task ID de la tarea de borrado
- 📊 Cola utilizada (`background_deletes`)
- ⚙️ Configuración del sistema
- 🎯 Estado de ejecución

## 🚨 Troubleshooting

### ❌ Workers No Inician

```bash
# Verificar logs
tail -f logs/celery-*.log

# Reiniciar completamente
python gestionar_sistema.py stop
python gestionar_sistema.py start
```

### 🔄 Tareas No Se Ejecutan

```bash
# Verificar Redis
python gestionar_sistema.py redis

# Verificar workers
python gestionar_sistema.py workers

# Limpiar Redis si es necesario
python gestionar_sistema.py flush-redis
```

### 📊 Muchas Ejecuciones PENDING

```bash
# Limpiar ejecuciones PENDING
python gestionar_sistema.py clear-pending

# Verificar estado
python gestionar_sistema.py status
```

## 📈 Ventajas del Sistema

1. **🎯 Script Único**: Un solo script para todo
2. **📊 Monitoreo Completo**: Estado detallado del sistema
3. **🗑️ Borrado Eficiente**: Basado en metodología probada
4. **🔄 Gestión Simple**: Comandos claros y directos
5. **📋 Documentación**: Ayuda integrada y ejemplos
6. **🔗 Integración**: Funciona con Django Admin

## 🎯 Próximos Pasos

1. **Ejecutar**: `python gestionar_sistema.py start`
2. **Verificar**: `python gestionar_sistema.py status`
3. **Habilitar Jobs**: `python gestionar_sistema.py enable-jobs`
4. **Probar Admin**: Usar acción "Borrar masivo" en Django Admin
