# 📐 Sistema de Fórmulas SNMP - Configuración de Índices por Marca

## 🎯 Descripción General

Este módulo permite **configurar fórmulas de cálculo de índices SNMP** para diferentes marcas y modelos de OLT sin necesidad de modificar código. Cada fabricante (Huawei, ZTE, Alcatel, etc.) codifica los índices SNMP de manera diferente, y este sistema permite manejar todas las variaciones desde la base de datos.

---

## 📊 Conceptos Clave

### **Problema que Resuelve**

Los índices SNMP varían según el fabricante:

- **Huawei**: `4194312448.2` → slot=1, port=1, logical=2
- **ZTE**: `268566784` → slot=2, port=1
- **Otros**: Diferentes fórmulas y formatos

Antes, cada marca requería código específico. Ahora todo es **configurable desde Django Admin**.

### **Tabla `index_formulas`**

Almacena las fórmulas de cálculo con estos componentes:

1. **Marca/Modelo**: A qué equipo aplica
2. **Modo de Cálculo**: Linear (base + pasos) o Bitshift (desplazamiento de bits)
3. **Parámetros**: Base, steps, offsets, máscaras, etc.
4. **Validación**: Límites máximos esperados
5. **Formato de Salida**: Cómo se muestra el ID normalizado

---

## 🔧 Modos de Cálculo

### **1. Modo LINEAR (Base + Pasos)**

Fórmula: `INDEX = BASE + (slot × STEP_SLOT) + (port × STEP_PORT) + onu_id`

**Ejemplo Huawei:**
```
BASE = 4194304000
STEP_SLOT = 8192
STEP_PORT = 256

Índice: 4194312448
→ delta = 4194312448 - 4194304000 = 8448
→ slot = 8448 ÷ 8192 = 1
→ resto = 8448 % 8192 = 256
→ port = 256 ÷ 256 = 1
→ onu_id = 256 % 256 = 0
✅ Resultado: slot=1, port=1, onu_id=0
```

### **2. Modo BITSHIFT (Desplazamiento de Bits)**

Extrae componentes usando operaciones binarias.

**Ejemplo:**
```
slot = (INDEX >> shift_slot_bits) & mask_slot
port = (INDEX >> shift_port_bits) & mask_port
onu_id = INDEX & 0xFF
```

---

## 📝 Parámetros Configurables

### **Identificación**
- `marca`: Marca del equipo (FK a `marcas`)
- `modelo`: Modelo específico (opcional, NULL = genérico)
- `nombre`: Nombre descriptivo
- `activo`: Si está habilitado

### **Cálculo LINEAR**
- `base_index`: Base del índice (ej: 4194304000)
- `step_slot`: Incremento por slot (ej: 8192)
- `step_port`: Incremento por puerto (ej: 256)

### **Cálculo BITSHIFT**
- `shift_slot_bits`: Bits a desplazar para slot
- `shift_port_bits`: Bits a desplazar para puerto
- `mask_slot`: Máscara hexadecimal para slot (ej: "0xFF")
- `mask_port`: Máscara hexadecimal para puerto (ej: "0xFF")

### **Adicionales**
- `onu_offset`: Si la numeración ONU empieza en 0 o 1
- `has_dot_notation`: Si el índice incluye `.ONU` (ej: "4194312448.2")
- `dot_is_onu_number`: Si la parte después del punto es el número ONU lógico

### **Validación**
- `slot_max`: Rango máximo de slots (default: 64)
- `port_max`: Rango máximo de puertos (default: 64)
- `onu_max`: Rango máximo de ONUs (default: 128)

### **Formato**
- `normalized_format`: Template de salida (ej: "{slot}/{port}")
  - Variables disponibles: `{slot}`, `{port}`, `{logical}`

---

## 🚀 Uso en el Sistema

### **1. Configurar Fórmula (Django Admin)**

1. Ir a: **SNMP Formulas → Index Formulas → Agregar**
2. Seleccionar marca (ej: Huawei, ZTE)
3. Opcionalmente especificar modelo (ej: MA5800, C320)
4. Configurar parámetros según el fabricante
5. Guardar

### **2. Asignar Modelo a OLT (Opcional)**

En **Hosts → OLTs**, editar una OLT y especificar el campo `modelo` si necesitas una fórmula específica por modelo.

### **3. Procesamiento Automático**

Cuando el sistema procesa un descubrimiento SNMP:

1. Obtiene el `raw_index_key` (ej: "4194312448.2")
2. Busca la fórmula:
   - Primero: marca + modelo específico
   - Luego: marca genérica (modelo=NULL)
3. Aplica la fórmula y calcula `slot`, `port`, `logical`
4. Guarda en `onu_index_map` con el `normalized_id` formateado

---

## 📋 Ejemplo: Configurar ZTE

Supongamos que ZTE usa esta lógica:
- Índice: `268566784`
- Resultado esperado: slot=2, port=1

**Configuración en Admin:**

```
Marca: ZTE
Modelo: (vacío - genérico)
Nombre: ZTE - Fórmula Estándar
Activo: ✓

Modo de Cálculo: linear
Base Index: 268435456  (ejemplo, ajustar según la fórmula real)
Step Slot: 65536
Step Port: 256

ONU Offset: 0
Has Dot Notation: ✗ (si no usa punto)
Dot is ONU Number: ✓

Slot Max: 64
Port Max: 64
ONU Max: 128

Normalized Format: {slot}/{port}
```

---

## 🔍 Verificación

### **Consulta SQL**
```sql
SELECT * FROM index_formulas WHERE marca_id = (SELECT id FROM marcas WHERE nombre = 'Huawei');
```

### **Django Shell**
```python
from snmp_formulas.models import IndexFormula
from brands.models import Brand

# Ver fórmula de Huawei
huawei = Brand.objects.get(nombre='Huawei')
formula = IndexFormula.objects.get(marca=huawei, modelo__isnull=True)

# Probar cálculo
result = formula.calculate_components('4194312448.2')
print(result)
# {'slot': 1, 'port': 1, 'logical': 2, 'onu_id': 0, 'onu_number': 2, 'snmp_index': 4194312448}

# Ver ID normalizado
normalized = formula.get_normalized_id(result['slot'], result['port'], result['logical'])
print(normalized)  # "1/1"
```

---

## 📚 Casos de Uso

### **Caso 1: Nueva Marca**
1. Investigar fórmula del fabricante
2. Crear registro en `index_formulas`
3. El sistema lo usará automáticamente

### **Caso 2: Modelo Específico**
Si un modelo de Huawei usa fórmula diferente:
1. Crear nueva fórmula con `marca=Huawei, modelo=MA5680T`
2. Asignar `modelo=MA5680T` a las OLTs correspondientes
3. El sistema priorizará la fórmula específica

### **Caso 3: Múltiples Formatos de Salida**
Cambiar `normalized_format`:
- `{slot}/{port}` → "1/1"
- `{slot}/{port}/{logical}` → "1/1/2"
- `S{slot}-P{port}` → "S1-P1"

---

## 🛠️ Desarrollo y Extensión

### **Agregar Nuevo Modo de Cálculo**

Editar `/opt/facho_deluxe_v2/snmp_formulas/models.py`:

```python
CALCULATION_MODE_CHOICES = [
    ('linear', 'Lineal (Base + Pasos)'),
    ('bitshift', 'Desplazamiento de Bits'),
    ('custom', 'Personalizado'),  # ← Nuevo
]

def calculate_components(self, raw_index_key: str) -> dict:
    # ... código existente ...
    
    elif self.calculation_mode == 'custom':
        slot, port, onu_id = self._calculate_custom(snmp_index)
```

### **Testing**

```python
# En Django shell
from snmp_formulas.models import IndexFormula

formula = IndexFormula.objects.get(marca__nombre='Huawei')

# Casos de prueba
test_cases = [
    ('4194312448.2', {'slot': 1, 'port': 1, 'logical': 2}),
    ('4194316032.10', {'slot': 1, 'port': 15, 'logical': 10}),
]

for raw_index, expected in test_cases:
    result = formula.calculate_components(raw_index)
    assert result['slot'] == expected['slot'], f"Fallo: {raw_index}"
    print(f"✅ {raw_index} → slot={result['slot']}, port={result['port']}")
```

---

## 📖 Referencias

- **Modelo**: `/opt/facho_deluxe_v2/snmp_formulas/models.py`
- **Admin**: `/opt/facho_deluxe_v2/snmp_formulas/admin.py`
- **Migraciones**: `/opt/facho_deluxe_v2/snmp_formulas/migrations/`
- **Diagrama BD**: `/opt/facho_deluxe_v2/db_diagram.md`

---

## ✅ Fórmulas Pre-configuradas

### **Huawei (Genérico)**
- **Modo**: Linear
- **Base**: 4194304000
- **Step Slot**: 8192
- **Step Port**: 256
- **Dot Notation**: Sí (`.ONU` es número lógico)
- **Estado**: ✅ Activo

### **ZTE (Pendiente)**
⚠️ Requiere configuración con parámetros correctos del fabricante.

---

## 🔗 Integración con OnuIndexMap

El modelo `OnuIndexMap` usa automáticamente las fórmulas:

```python
def save(self, *args, **kwargs):
    if self.slot is None or self.port is None:
        formula = IndexFormula.objects.filter(
            marca=self.olt.marca,
            modelo=self.olt.modelo,
            activo=True
        ).first()
        
        if formula:
            components = formula.calculate_components(self.raw_index_key)
            self.slot = components['slot']
            self.port = components['port']
            self.logical = components['logical']
            self.normalized_id = formula.get_normalized_id(...)
```

**Prioridad de búsqueda:**
1. Marca + Modelo específico
2. Marca genérica (modelo=NULL)
3. Fallback a código legacy (Huawei hardcoded)

---

## 🎉 Ventajas

✅ **Sin código**: Toda la configuración desde Django Admin  
✅ **Extensible**: Soporta nuevas marcas sin desarrollo  
✅ **Flexible**: Múltiples modos de cálculo  
✅ **Validado**: Límites y rangos configurables  
✅ **Histórico**: Mantiene compatibilidad con lógica antigua  

---

**¿Necesitas ayuda?** Revisa el código en `snmp_formulas/models.py` o consulta el `db_diagram.md`.

