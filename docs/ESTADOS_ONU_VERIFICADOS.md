# 📊 Estados ONU (Lookup) - Sistema Verificado y Corregido

## ✅ Resumen Ejecutivo

Se ha **corregido y verificado** el sistema de Estados ONU (Lookup) que tenía un conflicto de diseño. Ahora funciona con **lógica de prioridad** similar a las fórmulas SNMP, permitiendo estados específicos por marca y fallback a estados generales.

---

## ❌ Problema Original Identificado

### **Conflicto de Diseño**

**Problema**: El campo `value` tenía `unique=True`, lo que impedía tener el mismo valor numérico para diferentes marcas.

**Ejemplo del conflicto**:
```python
# ❌ NO SE PODÍA HACER:
OnuStateLookup(value=1, marca=Huawei, label="ACTIVO")
OnuStateLookup(value=1, marca=ZTE, label="ONLINE")  # Error: duplicate key
```

**Causa**: Restricción `unique=True` en el campo `value` del modelo.

---

## ✅ Solución Implementada

### **1. Corrección del Modelo** ✅

**Antes** (problemático):
```python
class OnuStateLookup(models.Model):
    value = models.SmallIntegerField(unique=True)  # ❌ Impedía duplicados entre marcas
    marca = models.ForeignKey(Brand, null=True, blank=True)
```

**Ahora** (corregido):
```python
class OnuStateLookup(models.Model):
    value = models.SmallIntegerField()  # ✅ Sin unique=True
    marca = models.ForeignKey(Brand, null=True, blank=True)
    
    class Meta:
        unique_together = [('value', 'marca')]  # ✅ Permite mismo valor para diferentes marcas
        indexes = [
            models.Index(fields=['value', 'marca']),
            models.Index(fields=['marca']),
        ]
```

### **2. Lógica de Prioridad Mejorada** ✅

**Antes** (limitada):
```python
# Solo buscaba por marca específica
state_lookup = OnuStateLookup.objects.get(value=state_value, marca=self.job.marca)
```

**Ahora** (con prioridad):
```python
# PRIORIDAD 1: Estado específico por marca
try:
    state_lookup = OnuStateLookup.objects.get(value=state_value, marca=self.job.marca)
    state_label = state_lookup.label
except OnuStateLookup.DoesNotExist:
    # PRIORIDAD 2: Estado general (sin marca)
    try:
        state_lookup = OnuStateLookup.objects.get(value=state_value, marca__isnull=True)
        state_label = state_lookup.label
    except OnuStateLookup.DoesNotExist:
        state_label = 'UNKNOWN'
```

---

## 🎯 Lógica de Prioridad de Estados

### **Jerarquía de Búsqueda** ✅

```
🥇 PRIORIDAD 1: Estado específico por marca
   Busca: value=X, marca=Y
   Ejemplo: value=1, marca=Huawei → "ACTIVO"
   Ejemplo: value=1, marca=ZTE → "ONLINE"

🥈 PRIORIDAD 2: Estado general (sin marca)
   Busca: value=X, marca=NULL
   Ejemplo: value=3, marca=NULL → "INACTIVO"
   Ejemplo: value=4, marca=NULL → "ERROR"

❌ SIN ESTADO: UNKNOWN
   Si no encuentra en ninguna prioridad
   Ejemplo: value=99 → "UNKNOWN"
```

### **Casos de Uso** ✅

| Marca | Valor | Resultado | Prioridad |
|-------|-------|-----------|-----------|
| **Huawei** | 1 | "ACTIVO" | 🥇 Específico |
| **Huawei** | 2 | "SUSPENDIDO" | 🥇 Específico |
| **Huawei** | 3 | "INACTIVO" | 🥈 General |
| **ZTE** | 1 | "ONLINE" | 🥇 Específico |
| **ZTE** | 2 | "OFFLINE" | 🥇 Específico |
| **ZTE** | 3 | "REGISTERING" | 🥇 Específico |
| **ZTE** | 4 | "ERROR" | 🥈 General |
| **Cualquiera** | 99 | "UNKNOWN" | ❌ Sin estado |

---

## 📊 Estados Configurados

### **Estados Específicos por Marca** ✅

#### **Huawei** (2 estados):
```
• 1 → ACTIVO (ONU activa y funcionando)
• 2 → SUSPENDIDO (ONU suspendida o inactiva)
```

#### **ZTE** (3 estados):
```
• 1 → ONLINE (ONU ZTE online)
• 2 → OFFLINE (ONU ZTE offline)
• 3 → REGISTERING (ONU ZTE registrándose)
```

### **Estados Generales** ✅

#### **Sin Marca** (5 estados):
```
• 1 → ACTIVO (ONU activa y operativa)
• 2 → SUSPENDIDO (ONU suspendida temporalmente)
• 3 → INACTIVO (ONU inactiva)
• 4 → ERROR (ONU con error)
• 5 → MANTENIMIENTO (ONU en mantenimiento)
```

---

## 🧪 Verificación Completa

### **Tests de Prioridad** ✅

```
✅ Huawei valor 1: 🥇 Específico → "ACTIVO"
✅ Huawei valor 2: 🥇 Específico → "SUSPENDIDO"
✅ Huawei valor 3: 🥈 General → "INACTIVO"
✅ ZTE valor 1: 🥇 Específico → "ONLINE"
✅ ZTE valor 2: 🥇 Específico → "OFFLINE"
✅ ZTE valor 3: 🥇 Específico → "REGISTERING"
✅ ZTE valor 4: 🥈 General → "ERROR"
✅ Valor 99: ❌ Sin estado → "UNKNOWN"
```

### **Verificación de Conflictos** ✅

```
✅ No hay conflictos - unique_together funcionando correctamente
✅ Cobertura: Huawei (2), ZTE (3), General (5)
✅ Lógica de prioridad funcionando
```

---

## 🔧 Integración con Tareas SNMP

### **Flujo de Procesamiento** ✅

1. **Tarea SNMP se ejecuta**:
   ```
   http://127.0.0.1:8000/admin/snmp_jobs/snmpjob/
   ```

2. **Obtiene estado de ONU**:
   - SNMP Walk devuelve valor numérico (ej: 1, 2, 3)
   - Usa la marca del job (no de la OLT)

3. **Búsqueda de estado**:
   - **Prioridad 1**: Busca estado específico por marca del job
   - **Prioridad 2**: Si no encuentra, busca estado general
   - **Sin estado**: Usa "UNKNOWN"

4. **Guardado**:
   - Actualiza `onu_status.last_state_value`
   - Actualiza `onu_status.last_state_label`
   - Crea/actualiza registro en `onu_status`

### **Ejemplo Práctico** ✅

```
Tarea SNMP: Marca=Huawei, OID=descubrimiento
SNMP Walk devuelve: 4194312448.2 = 1

Búsqueda de estado:
1. Busca: value=1, marca=Huawei → ✅ Encontrado "ACTIVO"
2. Guarda: last_state_value=1, last_state_label="ACTIVO"
```

---

## 💡 Ventajas del Sistema Corregido

### **Flexibilidad Total** ✅

| Característica | Beneficio |
|----------------|-----------|
| **Estados específicos** | Personalización por marca |
| **Estados generales** | Fallback para compatibilidad |
| **Sin conflictos** | unique_together permite duplicados entre marcas |
| **Prioridad inteligente** | Busca específico → general automáticamente |

### **Casos de Uso Resueltos** ✅

- ✅ **Huawei con estados específicos**: Usa "ACTIVO", "SUSPENDIDO"
- ✅ **ZTE con estados específicos**: Usa "ONLINE", "OFFLINE", "REGISTERING"
- ✅ **Estados no específicos**: Usa generales "INACTIVO", "ERROR", "MANTENIMIENTO"
- ✅ **Valores inexistentes**: Usa "UNKNOWN"

---

## 🎨 Admin Visual

### **URL del Admin** ✅

```
http://127.0.0.1:8000/admin/discovery/onustatelookup/
```

### **Características del Admin** ✅

- ✅ **Lista por marca**: Filtra estados por marca
- ✅ **Búsqueda**: Por valor, label, descripción
- ✅ **Campos**: value, label, marca, descripción
- ✅ **Validación**: unique_together automática

---

## 📋 Próximos Pasos

### **Para Otras Marcas** ✅

1. **Crear estados específicos**:
   ```
   Admin → Estados ONU → Agregar
   - Value: 1
   - Label: "ACTIVO" (o el específico de la marca)
   - Marca: (seleccionar marca)
   ```

2. **El sistema automáticamente**:
   - Usará estados específicos si existen
   - Fallback a generales si no existen
   - Prioridad transparente para el usuario

### **Para Nuevos Valores** ✅

1. **Agregar estados generales**:
   ```
   Admin → Estados ONU → Agregar
   - Value: 6
   - Label: "NUEVO_ESTADO"
   - Marca: (vacío - general)
   ```

2. **Todas las marcas** podrán usar el nuevo estado automáticamente

---

## 🎉 Resultado Final

**El sistema de Estados ONU está completamente corregido y funcionando**:

1. ✅ **Conflicto resuelto**: unique_together en lugar de unique=True
2. ✅ **Lógica de prioridad**: Específico → general → UNKNOWN
3. ✅ **Estados configurados**: Huawei (2), ZTE (3), General (5)
4. ✅ **Tests pasados**: Todos los casos de prueba funcionando
5. ✅ **Sin conflictos**: unique_together funcionando correctamente
6. ✅ **Integración**: Funciona automáticamente con tareas SNMP

**Para usar**: El sistema funciona automáticamente. Cuando ejecutes tareas SNMP, buscará y aplicará el estado correcto según la prioridad implementada. ¡Todo funciona perfectamente! 🚀

---

## 📞 Soporte

**Documentación**:
- Este documento - Verificación completa de estados
- `/opt/facho_deluxe_v2/verificar_estados_onu.py` - Script de verificación

**Admin**:
```
http://127.0.0.1:8000/admin/discovery/onustatelookup/
```

**Testing**:
```bash
python verificar_estados_onu.py
```

¡El sistema de Estados ONU está **100% corregido** y funcionando! 🎯
