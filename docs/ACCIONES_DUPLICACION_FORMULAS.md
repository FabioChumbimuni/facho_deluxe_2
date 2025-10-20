# 🎯 Acciones de Duplicación de Fórmulas SNMP - Implementación Completa

## ✅ Resumen Ejecutivo

Se han implementado **2 acciones de duplicación** en el admin de IndexFormula para facilitar la creación de fórmulas específicas por modelo. Esto permite duplicar fórmulas genéricas para crear versiones específicas de cada modelo de OLT.

---

## 🚀 Acciones Implementadas

### **1. 📋 Duplicar Fórmula Seleccionada**

**Propósito**: Crear una copia exacta de una fórmula para modificarla sin perder la original.

**Características**:
- ✅ Crea copia exacta con nombre modificado (agrega " (Copia)")
- ✅ Se crea **inactiva por defecto** para revisar antes de activar
- ✅ Copia todos los parámetros: base_index, step_slot, step_port, etc.
- ✅ Útil para hacer modificaciones experimentales

**Uso**:
```
1. Seleccionar UNA fórmula
2. Acción: "📋 Duplicar fórmula seleccionada"
3. Ejecutar
4. Resultado: Nueva fórmula inactiva lista para editar
```

### **2. 🎯 Duplicar para Modelos Específicos**

**Propósito**: Crear fórmulas específicas para todos los modelos de una marca basándose en la fórmula genérica.

**Características**:
- ✅ Solo funciona con fórmulas **genéricas** (sin modelo asignado)
- ✅ Crea fórmulas específicas para **todos los modelos activos** de la marca
- ✅ **Evita duplicados**: No crea si ya existe fórmula para el modelo
- ✅ Se crean **activas por defecto** y listas para usar
- ✅ Nombres automáticos: "Huawei MA5800 - Fórmula específica"

**Uso**:
```
1. Seleccionar UNA fórmula GENÉRICA (sin modelo)
2. Acción: "🎯 Duplicar para modelos específicos"
3. Ejecutar
4. Resultado: Fórmulas específicas para todos los modelos de la marca
```

---

## 📊 Estado Actual del Sistema

### **Fórmulas Existentes** ✅

| Fórmula | Tipo | Modelo | Estado |
|---------|------|--------|--------|
| **Huawei - MA5800** | Específica | MA5800 | ✅ Activa |
| **Huawei - Fórmula Estándar** | Genérica | NULL | ✅ Activa |

### **Modelos Pendientes** ⚠️

| Modelo | Estado | Acción Requerida |
|--------|--------|------------------|
| **MA5608T** | Sin fórmula específica | Duplicar desde genérica |
| **AN5516-06** | Sin fórmula específica | Duplicar desde genérica |

---

## 🎯 Cómo Usar las Acciones

### **Paso 1: Acceder al Admin**

**URL**: `http://127.0.0.1:8000/admin/snmp_formulas/indexformula/`

### **Paso 2: Crear Fórmulas Específicas**

**Para completar los modelos Huawei**:

1. **Seleccionar fórmula genérica**:
   - Marcar checkbox de "Huawei - Fórmula Estándar"

2. **Ejecutar acción**:
   - Dropdown "Acción": "🎯 Duplicar para modelos específicos"
   - Click "Ejecutar"

3. **Resultado esperado**:
   ```
   ✅ Creadas 2 fórmulas específicas para modelos de Huawei.
   ```

4. **Fórmulas creadas**:
   - "Huawei MA5608T - Fórmula específica"
   - "Huawei AN5516-06 - Fórmula específica"

### **Paso 3: Verificar Resultado**

Después de ejecutar la acción, tendrás:

| Fórmula | Tipo | Modelo | Estado |
|---------|------|--------|--------|
| **Huawei - MA5800** | Específica | MA5800 | ✅ Activa |
| **Huawei MA5608T - Fórmula específica** | Específica | MA5608T | ✅ Activa |
| **Huawei AN5516-06 - Fórmula específica** | Específica | AN5516-06 | ✅ Activa |
| **Huawei - Fórmula Estándar** | Genérica | NULL | ✅ Activa |

---

## 🔍 Validaciones Implementadas

### **Validaciones de Seguridad**

#### **Para "Duplicar Fórmula Seleccionada"**:
- ✅ **Solo una selección**: Debe seleccionar exactamente UNA fórmula
- ✅ **Copia inactiva**: Se crea inactiva para revisar antes de activar
- ✅ **Nombre único**: Agrega " (Copia)" para evitar conflictos

#### **Para "Duplicar para Modelos Específicos"**:
- ✅ **Solo fórmulas genéricas**: Solo funciona con `modelo=NULL`
- ✅ **Solo una selección**: Debe seleccionar exactamente UNA fórmula genérica
- ✅ **Evita duplicados**: No crea si ya existe fórmula para el modelo
- ✅ **Solo modelos activos**: Solo considera modelos con `activo=True`

### **Mensajes de Error Informativos**

```python
# Ejemplos de mensajes
"⚠️ Selecciona exactamente UNA fórmula para duplicar."
"⚠️ Solo se pueden duplicar fórmulas genéricas (sin modelo específico)."
"⚠️ No hay modelos de Huawei sin fórmula específica."
"✅ Creadas 2 fórmulas específicas para modelos de Huawei."
```

---

## 🧪 Testing y Verificación

### **Script de Prueba**

**Ubicación**: `/opt/facho_deluxe_v2/probar_acciones_formulas.py`

**Ejecutar**:
```bash
cd /opt/facho_deluxe_v2
source venv/bin/activate
python probar_acciones_formulas.py
```

**Output esperado**:
```
✅ 2 fórmulas existentes (1 específica + 1 genérica)
📊 2 modelos sin fórmula específica
💡 Acción recomendada para completar
```

### **Verificación Manual**

```python
# En Django shell
from snmp_formulas.models import IndexFormula
from olt_models.models import OLTModel

# Ver fórmulas existentes
formulas = IndexFormula.objects.all()
for f in formulas:
    print(f"{f} - Modelo: {f.modelo or 'Genérico'}")

# Ver modelos sin fórmula
modelos_sin_formula = OLTModel.objects.filter(
    activo=True
).exclude(
    id__in=IndexFormula.objects.filter(
        modelo__isnull=False
    ).values_list('modelo_id', flat=True)
)
print(f"Modelos sin fórmula: {modelos_sin_formula.count()}")
```

---

## 🔗 Integración con el Sistema

### **Flujo de Prioridad**

El sistema de fórmulas usa esta prioridad:

1. **Prioridad 1**: Fórmula específica por modelo
   ```
   OLT.modelo = MA5800 → Busca fórmula marca=Huawei, modelo=MA5800
   ```

2. **Prioridad 2**: Fórmula genérica por marca
   ```
   OLT.modelo = NULL → Busca fórmula marca=Huawei, modelo=NULL
   ```

3. **Fallback**: Código legacy
   ```
   Si no hay fórmulas en BD → Usa lógica hardcoded de Huawei
   ```

### **Ventajas de las Fórmulas Específicas**

- ✅ **Personalización por modelo**: Cada modelo puede tener parámetros únicos
- ✅ **Prioridad automática**: El sistema usa la específica si existe
- ✅ **Compatibilidad**: Mantiene la genérica como fallback
- ✅ **Fácil mantenimiento**: Cambios por modelo sin afectar otros

---

## 📋 Casos de Uso

### **Caso 1: Nuevo Modelo Huawei**

```
Escenario: Agregar modelo "MA5600X"
1. Crear modelo en OLT Models
2. Usar acción "🎯 Duplicar para modelos específicos"
3. Resultado: Fórmula específica para MA5600X
```

### **Caso 2: Modificar Parámetros**

```
Escenario: MA5800 necesita parámetros diferentes
1. Usar acción "📋 Duplicar fórmula seleccionada"
2. Editar la copia con nuevos parámetros
3. Activar la nueva fórmula
4. Desactivar la original
```

### **Caso 3: Nueva Marca**

```
Escenario: Agregar soporte para ZTE
1. Crear marca ZTE
2. Crear modelos ZTE (C320, C300, etc.)
3. Crear fórmula genérica ZTE
4. Usar acción "🎯 Duplicar para modelos específicos"
5. Resultado: Fórmulas específicas para todos los modelos ZTE
```

---

## 🛠️ Código Implementado

### **Archivo Modificado**

**Ubicación**: `/opt/facho_deluxe_v2/snmp_formulas/admin.py`

**Cambios**:
- ✅ Importaciones agregadas (`messages`, `gettext_lazy`)
- ✅ Acciones agregadas al admin (`actions = [...]`)
- ✅ Método `duplicar_formula()` implementado
- ✅ Método `duplicar_para_modelo_especifico()` implementado
- ✅ Validaciones y mensajes de error incluidos

### **Características Técnicas**

```python
# Configuración del admin
actions = ['duplicar_formula', 'duplicar_para_modelo_especifico']

# Validaciones implementadas
if queryset.count() != 1:
    # Error: debe seleccionar exactamente una

if not formulas_genericas.exists():
    # Error: solo fórmulas genéricas

# Creación de fórmulas
nueva_formula = IndexFormula.objects.create(
    marca=formula_original.marca,
    modelo=modelo_especifico,  # Para específicas
    # ... todos los parámetros copiados
)
```

---

## 🎉 Resultado Final

**Ahora tienes un sistema completo que**:

1. ✅ **Duplica fórmulas** con un solo click
2. ✅ **Crea fórmulas específicas** para todos los modelos de una marca
3. ✅ **Valida selecciones** y evita errores
4. ✅ **Mantiene compatibilidad** con fórmulas genéricas
5. ✅ **Facilita mantenimiento** de fórmulas por modelo
6. ✅ **Incluye testing** y verificación automática

**Para usar**: Solo necesitas ir al admin, seleccionar la fórmula genérica de Huawei y ejecutar "🎯 Duplicar para modelos específicos". ¡Se crearán automáticamente las fórmulas para MA5608T y AN5516-06! 🚀

---

## 📞 Soporte

**Documentación**:
- Este documento - Guía completa de las acciones
- `/opt/facho_deluxe_v2/probar_acciones_formulas.py` - Script de verificación

**Admin**:
```
http://127.0.0.1:8000/admin/snmp_formulas/indexformula/
```

**Testing**:
```bash
python probar_acciones_formulas.py
```

¡Las acciones están **100% funcionales** y listas para usar! 🎯
