# 🎯 Sistema de Fórmulas SNMP - Implementación Completa

## ✅ Resumen Ejecutivo

Se ha implementado exitosamente un **sistema configurable de fórmulas SNMP** que permite soportar múltiples marcas de OLT (Huawei, ZTE, etc.) sin necesidad de modificar código. Todo es configurable desde Django Admin.

---

## 📦 Componentes Implementados

### **1. Nueva App Django: `snmp_formulas`**

**Ubicación**: `/opt/facho_deluxe_v2/snmp_formulas/`

**Archivos creados**:
- ✅ `models.py` - Modelo `IndexFormula` con todos los parámetros configurables
- ✅ `admin.py` - Admin completo con vista previa de fórmulas y badges
- ✅ `README.md` - Documentación completa del sistema
- ✅ `test_formulas.py` - Script de pruebas interno
- ✅ `migrations/0001_initial.py` - Creación de tabla
- ✅ `migrations/0002_add_huawei_formula.py` - Data migration con fórmula Huawei

### **2. Modificaciones en Apps Existentes**

#### **`hosts` (OLT)**
- ✅ Agregado campo `modelo` para especificar modelos específicos
- ✅ Admin actualizado para mostrar modelo en lista y formulario

#### **`discovery` (OnuIndexMap)**
- ✅ Migrado de lógica hardcoded a sistema configurable
- ✅ Prioriza: marca+modelo específico → marca genérica → fallback legacy
- ✅ Usa `IndexFormula.calculate_components()` automáticamente

#### **`core/settings.py`**
- ✅ Agregada `snmp_formulas` a `INSTALLED_APPS`

### **3. Base de Datos**

**Nueva tabla**: `index_formulas`

```sql
CREATE TABLE index_formulas (
    id SERIAL PRIMARY KEY,
    marca_id INT NOT NULL REFERENCES marcas(id),
    modelo VARCHAR(100) NULL,
    nombre VARCHAR(255) NOT NULL,
    activo BOOLEAN DEFAULT TRUE,
    
    -- Configuración
    calculation_mode VARCHAR(20) DEFAULT 'linear',
    
    -- Modo LINEAR
    base_index BIGINT DEFAULT 0,
    step_slot INT DEFAULT 0,
    step_port INT DEFAULT 0,
    
    -- Modo BITSHIFT
    shift_slot_bits INT DEFAULT 0,
    shift_port_bits INT DEFAULT 0,
    mask_slot VARCHAR(20) NULL,
    mask_port VARCHAR(20) NULL,
    
    -- Adicionales
    onu_offset INT DEFAULT 0,
    has_dot_notation BOOLEAN DEFAULT FALSE,
    dot_is_onu_number BOOLEAN DEFAULT TRUE,
    
    -- Validación
    slot_max INT DEFAULT 64,
    port_max INT DEFAULT 64,
    onu_max INT DEFAULT 128,
    
    -- Formato
    normalized_format VARCHAR(50) DEFAULT '{slot}/{port}',
    
    descripcion TEXT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    UNIQUE(marca_id, modelo)
);
```

**Modificaciones en tablas existentes**:
- ✅ `olt`: Agregado campo `modelo VARCHAR(100) NULL`
- ✅ `db_diagram.md`: Actualizado con nueva tabla y relaciones

### **4. Documentación**

- ✅ **README.md**: Guía completa del sistema
- ✅ **db_diagram.md**: Diagrama de BD actualizado
- ✅ **Este documento**: Resumen de implementación

---

## 🎨 Características del Sistema

### **Parámetros Configurables**

| Categoría | Parámetros | Descripción |
|-----------|------------|-------------|
| **Identificación** | marca, modelo, nombre, activo | Define a qué equipo aplica |
| **Cálculo LINEAR** | base_index, step_slot, step_port | Fórmula: INDEX = BASE + (slot × STEP_SLOT) + (port × STEP_PORT) |
| **Cálculo BITSHIFT** | shift_slot_bits, shift_port_bits, masks | Extrae componentes con operaciones binarias |
| **Adicionales** | onu_offset, has_dot_notation, dot_is_onu_number | Configuraciones especiales |
| **Validación** | slot_max, port_max, onu_max | Límites para validar rangos |
| **Formato** | normalized_format | Template de salida (ej: "{slot}/{port}") |

### **Modos de Cálculo Soportados**

1. **LINEAR (Base + Pasos)** ← Usado por Huawei
   ```
   INDEX = BASE + (slot × STEP_SLOT) + (port × STEP_PORT) + onu_id
   ```

2. **BITSHIFT (Desplazamiento de Bits)**
   ```
   slot = (INDEX >> shift_slot_bits) & mask_slot
   port = (INDEX >> shift_port_bits) & mask_port
   ```

---

## 🚀 Fórmula Huawei Pre-configurada

**Estado**: ✅ Activa y funcionando

**Configuración**:
```
Marca: Huawei
Modelo: (vacío - genérica)
Nombre: Huawei - Fórmula Estándar

Modo: linear
Base Index: 4,194,304,000
Step Slot: 8,192
Step Port: 256

Has Dot Notation: ✓
Dot is ONU Number: ✓

Normalized Format: {slot}/{port}
```

**Tests**: ✅ **TODOS PASARON**
```
✅ 4194312448.2   → slot=1, port=1,  logical=2  → "1/1"
✅ 4194316032.10  → slot=1, port=15, logical=10 → "1/15"
✅ 4194338304.1   → slot=4, port=6,  logical=1  → "4/6"
✅ 4194338304.2   → slot=4, port=6,  logical=2  → "4/6"
✅ 4194338304.3   → slot=4, port=6,  logical=3  → "4/6"
```

---

## 📖 Cómo Usar el Sistema

### **1. Acceder al Admin**

**URL**: `http://127.0.0.1:8000/admin/snmp_formulas/indexformula/`

### **2. Ver Fórmulas Existentes**

Lista todas las fórmulas configuradas con:
- Badge de modo (Linear/Bitshift)
- Resumen de parámetros
- Estado activo/inactivo

### **3. Agregar Nueva Fórmula (Ejemplo: ZTE)**

**Pasos**:
1. Click en **"Agregar Index Formula"**
2. Configurar:
   ```
   Marca: ZTE
   Modelo: (vacío)
   Nombre: ZTE - Fórmula Estándar
   Activo: ✓
   
   Calculation Mode: linear
   Base Index: [INVESTIGAR]
   Step Slot: [INVESTIGAR]
   Step Port: [INVESTIGAR]
   
   ONU Offset: 0
   Has Dot Notation: ✗
   
   Normalized Format: {slot}/{port}
   ```
3. Guardar

4. **El sistema lo usará automáticamente** para todas las OLTs marca ZTE

### **4. Especificar Modelo en OLT (Opcional)**

Si una OLT específica necesita fórmula diferente:

1. Ir a **Hosts → OLTs**
2. Editar la OLT
3. Especificar `modelo` (ej: "MA5800", "C320")
4. Crear fórmula con `marca=X, modelo=MA5800`
5. El sistema priorizará la fórmula específica

---

## 🔍 Verificación y Testing

### **Script de Verificación**

**Ubicación**: `/opt/facho_deluxe_v2/verificar_formulas.py`

**Ejecutar**:
```bash
cd /opt/facho_deluxe_v2
source venv/bin/activate
python verificar_formulas.py
```

**Output esperado**:
```
✅ Fórmula Huawei encontrada
✅ Todos los tests pasaron
📋 Lista de fórmulas configuradas
📝 Ejemplo de configuración ZTE
```

### **Testing Manual en Django Shell**

```python
from snmp_formulas.models import IndexFormula
from brands.models import Brand

# Obtener fórmula
huawei = Brand.objects.get(nombre='Huawei')
formula = IndexFormula.objects.get(marca=huawei, modelo__isnull=True)

# Probar cálculo
result = formula.calculate_components('4194312448.2')
print(result)
# {'slot': 1, 'port': 1, 'logical': 2, 'onu_id': 0, ...}

# Ver ID normalizado
normalized = formula.get_normalized_id(result['slot'], result['port'], result['logical'])
print(normalized)  # "1/1"
```

---

## 🔗 Integración Automática

### **Flujo de Procesamiento**

1. **Tarea de descubrimiento** ejecuta SNMP Walk
2. Obtiene índice crudo (ej: "4194312448.2")
3. **`OnuIndexMap.save()`** detecta que faltan componentes
4. Busca fórmula en BD:
   - **Prioridad 1**: `marca=X, modelo=Y` (específica)
   - **Prioridad 2**: `marca=X, modelo=NULL` (genérica)
   - **Fallback**: Código legacy de Huawei
5. Calcula `slot`, `port`, `logical` usando la fórmula
6. Genera `normalized_id` usando el formato configurado
7. Guarda en BD

### **Ejemplo con ZTE (Futuro)**

Cuando se configure ZTE:

```
Índice ZTE: 268566784
→ Busca fórmula marca=ZTE, modelo=NULL
→ Aplica cálculo: slot=2, port=1
→ Normalized ID: "2/1"
→ Guarda en onu_index_map
```

---

## 📋 Próximos Pasos

### **Para ZTE** ⚠️ PENDIENTE

1. **Investigar la fórmula de ZTE**:
   - ¿Cuál es la base del índice?
   - ¿Cuál es el paso por slot?
   - ¿Cuál es el paso por puerto?
   - ¿Usa notación con punto?

2. **Crear configuración en Admin**:
   - Marca: ZTE
   - Completar parámetros investigados
   - Activar

3. **Probar con datos reales**:
   - Ejecutar descubrimiento en OLT ZTE
   - Verificar que los índices se calculen correctamente

### **Para Otros Fabricantes**

Repetir el mismo proceso:
- Alcatel
- Fiberhome
- TP-Link
- Etc.

---

## 🛠️ Archivos Modificados/Creados

### **Nuevos**
```
snmp_formulas/
├── __init__.py
├── apps.py
├── models.py                    ← Modelo IndexFormula
├── admin.py                     ← Admin completo
├── README.md                    ← Documentación
├── test_formulas.py            ← Tests internos
└── migrations/
    ├── 0001_initial.py         ← Crear tabla
    └── 0002_add_huawei_formula.py  ← Data migration Huawei

verificar_formulas.py            ← Script de verificación
SISTEMA_FORMULAS_SNMP.md        ← Este documento
```

### **Modificados**
```
core/settings.py                 ← Agregada app snmp_formulas
hosts/models.py                  ← Campo modelo en OLT
hosts/admin.py                   ← Admin con campo modelo
discovery/models.py              ← Migrado a sistema configurable
db_diagram.md                    ← Tabla index_formulas y relaciones
```

---

## 💡 Ventajas del Sistema

✅ **Sin Código**: Todo configurable desde Django Admin  
✅ **Extensible**: Nuevas marcas sin desarrollo  
✅ **Flexible**: Múltiples modos de cálculo  
✅ **Validado**: Límites y rangos configurables  
✅ **Retrocompatible**: Fallback a lógica legacy  
✅ **Probado**: Tests automáticos para Huawei  
✅ **Documentado**: README completo + ejemplos  

---

## 🎉 Resultado Final

**Ahora tienes un sistema completamente configurable que**:

1. ✅ Soporta Huawei (ya funcionando y probado)
2. ✅ Permite agregar ZTE solo configurando parámetros
3. ✅ Permite agregar cualquier otra marca sin tocar código
4. ✅ Prioriza fórmulas específicas por modelo
5. ✅ Tiene validación y formato personalizable
6. ✅ Incluye admin visual con badges y previews
7. ✅ Está completamente documentado

**Para agregar ZTE**: Solo necesitas investigar su fórmula y configurarla en el Admin. ¡El código ya está listo! 🚀

---

## 📞 Soporte

**Documentación**:
- `/opt/facho_deluxe_v2/snmp_formulas/README.md` - Guía completa
- `/opt/facho_deluxe_v2/db_diagram.md` - Diagrama de BD
- Este documento - Resumen de implementación

**Testing**:
```bash
python verificar_formulas.py
```

**Admin**:
```
http://127.0.0.1:8000/admin/snmp_formulas/indexformula/
```

