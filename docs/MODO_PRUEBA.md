# 🧪 Modo Prueba - Sistema de Simulación de Ejecuciones SNMP

## 📋 ¿Qué es el Modo Prueba?

El **Modo Prueba** es un sistema de simulación que permite ejecutar todas las tareas SNMP **sin realizar consultas reales** a las OLTs. Todas las ejecuciones se simulan con tiempos aleatorios y resultados simulados.

### Características:

- ✅ **Todas las ejecuciones se simulan** (no se hacen consultas SNMP reales)
- ⏱️ **Tiempos aleatorios**: desde milisegundos hasta 3 minutos máximo
- 📊 **Resultados simulados**: 80% éxito, 15% fallo, 5% interrumpido
- 🔄 **Flujo completo**: El coordinador funciona normalmente, solo se simulan las consultas SNMP
- 🛡️ **Seguro**: No hay riesgo de sobrecargar las OLTs durante pruebas

---

## 🎯 ¿Cuándo usar el Modo Prueba?

- ✅ Desarrollo y pruebas locales
- ✅ Demostraciones sin afectar producción
- ✅ Pruebas de rendimiento del coordinador
- ✅ Validación de workflows sin consultas reales
- ✅ Capacitación sin riesgo

---

## ⚙️ Cómo Activar/Desactivar el Modo Prueba

### Desde el Admin de Django:

1. **Ir a**: `Configuración Avanzada` → `Configuraciones del Sistema`
2. **Buscar o crear** una configuración activa
3. **Marcar/Desmarcar** el campo **"Modo Prueba"**
4. **Guardar**

### Verificación Visual:

- 🧪 **Badge Rojo "MODO PRUEBA ACTIVO"**: Modo prueba está activo
- ✅ **Badge Verde "PRODUCCIÓN"**: Modo producción (consultas reales)

---

## 🔧 Cómo Funciona

### 1. Activación Global

El modo prueba se activa/desactiva desde **una sola configuración** en el admin:

```
Configuración del Sistema → Modo Prueba = True/False
```

### 2. Detección en Tareas SNMP

Cuando una tarea SNMP se ejecuta:

```python
# Verifica si el modo prueba está activo globalmente
is_modo_prueba = ConfiguracionSistema.is_modo_prueba()

# También detecta tareas con nombre [PRUEBA]
is_test_job = job.nombre.startswith('[PRUEBA]')

# Si cualquiera es True, simula la ejecución
if is_modo_prueba or is_test_job:
    # Simular ejecución sin SNMP real
```

### 3. Simulación de Ejecución

**Tiempo de simulación:**
- Mínimo: 0.001 segundos (1 milisegundo)
- Máximo: 180 segundos (3 minutos)
- Aleatorio: `random.uniform(0.001, 180)`

**Resultados simulados:**
- 80% → `SUCCESS` (éxito)
- 15% → `FAILED` (fallo)
- 5% → `INTERRUPTED` (interrumpido)

**Datos simulados:**
- Discovery: `total_found`, `enabled_count`, `disabled_count`
- GET: `success_count`, `error_count`, `total_onus`

---

## 🚨 Cómo SALIR del Modo Prueba

### Método 1: Desde el Admin (Recomendado)

1. Ir a: **Admin Django** → **Configuración Avanzada** → **Configuraciones del Sistema**
2. Buscar cualquier configuración con **"Modo Prueba"** activo
3. **Desmarcar** el checkbox **"Modo Prueba"**
4. **Guardar**

### Método 2: Desde la Shell de Django

```python
from configuracion_avanzada.models import ConfiguracionSistema

# Desactivar modo prueba en todas las configuraciones
ConfiguracionSistema.objects.filter(modo_prueba=True).update(modo_prueba=False)

# Verificar que está desactivado
print(f"Modo prueba activo: {ConfiguracionSistema.is_modo_prueba()}")
# Debe mostrar: Modo prueba activo: False
```

### Método 3: Eliminar Configuraciones de Prueba

```python
from configuracion_avanzada.models import ConfiguracionSistema

# Eliminar todas las configuraciones con modo_prueba activo
ConfiguracionSistema.objects.filter(modo_prueba=True).delete()
```

---

## 📊 Verificación del Estado

### Verificar si el Modo Prueba está Activo:

```python
from configuracion_avanzada.models import ConfiguracionSistema

if ConfiguracionSistema.is_modo_prueba():
    print("⚠️ MODO PRUEBA ACTIVO - No se ejecutan consultas SNMP reales")
else:
    print("✅ MODO PRODUCCIÓN - Se ejecutan consultas SNMP reales")
```

### Ver Configuraciones con Modo Prueba:

```python
from configuracion_avanzada.models import ConfiguracionSistema

configs = ConfiguracionSistema.objects.filter(modo_prueba=True, activo=True)
for config in configs:
    print(f"Configuración: {config.nombre} - Modo Prueba: {config.modo_prueba}")
```

---

## ⚠️ Advertencias Importantes

1. **No usar en Producción**: El modo prueba está diseñado solo para desarrollo y pruebas
2. **Verificar antes de desplegar**: Siempre verificar que el modo prueba esté desactivado antes de desplegar a producción
3. **Logs indican simulación**: Los logs mostrarán `🧪 MODO SIMULACIÓN` cuando se simule una ejecución
4. **Tareas [PRUEBA]**: Las tareas con nombre que empieza con `[PRUEBA]` siempre se simulan, incluso si el modo prueba global está desactivado

---

## 🔍 Logs y Monitoreo

Cuando el modo prueba está activo, verás en los logs:

```
🧪 MODO SIMULACIÓN: [Nombre Tarea] - Simulando ejecución sin consultas SNMP reales
🧪 Simulación completada: SUCCESS en 1234ms
```

Esto indica que la ejecución fue simulada, no real.

---

## 📝 Resumen

| Aspecto | Modo Prueba | Modo Producción |
|---------|-------------|-----------------|
| **Consultas SNMP** | ❌ No se ejecutan | ✅ Se ejecutan |
| **Tiempo ejecución** | Aleatorio (1ms - 3min) | Real (depende de OLT) |
| **Resultados** | Simulados (80% éxito) | Reales |
| **Riesgo OLTs** | ✅ Sin riesgo | ⚠️ Riesgo normal |
| **Uso** | Desarrollo/Pruebas | Producción |

---

**Última actualización**: 2024  
**Versión**: 1.0

