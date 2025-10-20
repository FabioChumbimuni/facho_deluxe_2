# Sistema de Fórmulas SNMP

## 📚 Descripción General

El sistema de fórmulas SNMP permite calcular automáticamente el `raw_index_key` (índice SNMP) desde la posición física de una ONU (`slot`, `port`, `logical`) según la marca y modelo de la OLT.

Este sistema es **bidireccional**:
- **Directo**: `raw_index_key` → `slot/port/logical` (usado en el descubrimiento automático)
- **Inverso**: `slot/port/logical` → `raw_index_key` (usado en la creación manual via API)

---

## 🔄 ¿Por qué es necesario?

Cada fabricante de OLTs usa una fórmula diferente para calcular el índice SNMP:

### Ejemplo: Huawei MA5800
```
slot=5, port=3, logical=10

raw_index_key = BASE + (slot × STEP_SLOT) + (port × STEP_PORT) + logical
raw_index_key = 4194304000 + (5 × 8192) + (3 × 256) + 10
raw_index_key = 4194304000 + 40960 + 768 + 10
raw_index_key = 4194345738

Si usa notación con punto: 4194345738.10
```

### Ejemplo: ZTE C300 (bitshift)
```
slot=5, port=3, logical=10

raw_index_key = (slot << 24) | (port << 16) | logical
raw_index_key = (5 << 24) | (3 << 16) | 10
raw_index_key = 83886080 | 196608 | 10
raw_index_key = 84082698
```

---

## 🎯 Componentes del Sistema

### 1. Modelo `IndexFormula`
**Ubicación**: `/opt/facho_deluxe_2/snmp_formulas/models.py`

Almacena las fórmulas de cada marca/modelo:

```python
class IndexFormula(models.Model):
    marca = ForeignKey(Brand)           # Huawei, ZTE, Nokia, etc.
    modelo = ForeignKey(OLTModel)       # MA5800, C300, etc. (opcional)
    nombre = CharField()                # Nombre descriptivo
    activo = BooleanField()             # Si está activa
    
    # Modo de cálculo
    calculation_mode = CharField()      # 'linear' o 'bitshift'
    
    # Parámetros lineales (Huawei, Nokia)
    base_index = BigIntegerField()      # Base del índice
    step_slot = IntegerField()          # Incremento por slot
    step_port = IntegerField()          # Incremento por puerto
    
    # Parámetros bitshift (ZTE)
    shift_slot_bits = IntegerField()    # Bits de desplazamiento para slot
    shift_port_bits = IntegerField()    # Bits de desplazamiento para puerto
    mask_slot = CharField()             # Máscara hexadecimal
    mask_port = CharField()             # Máscara hexadecimal
    
    # Configuración adicional
    onu_offset = IntegerField()         # Si la ONU empieza en 0 o 1
    has_dot_notation = BooleanField()   # Si usa notación 4194345738.10
    dot_is_onu_number = BooleanField()  # Si el punto es el número lógico
    
    # Límites de validación
    slot_max = IntegerField()           # Máximo de slots
    port_max = IntegerField()           # Máximo de puertos
    onu_max = IntegerField()            # Máximo de ONUs por puerto
    
    # Formato de salida
    normalized_format = CharField()     # "{slot}/{port}" o "{slot}/{port}/{logical}"
```

### 2. Métodos Principales

#### `calculate_components(raw_index_key)` - DIRECTO
Calcula `slot/port/logical` desde el `raw_index_key`:

```python
formula = IndexFormula.objects.get(marca=olt.marca, activo=True)
componentes = formula.calculate_components("4194345738.10")

# Resultado:
# {
#   'slot': 5,
#   'port': 3,
#   'logical': 10,
#   'snmp_index': 4194345738,
#   'onu_number': 10
# }
```

#### `generate_raw_index_key(slot, port, logical)` - INVERSO
Genera el `raw_index_key` desde `slot/port/logical`:

```python
formula = IndexFormula.objects.get(marca=olt.marca, activo=True)
raw_index_key = formula.generate_raw_index_key(slot=5, port=3, logical=10)

# Resultado: "4194345738.10"
```

---

## 🔧 Uso en la API REST

### Creación de ONU - Automático

Cuando creas una ONU via API, **NO necesitas proporcionar el `raw_index_key`**. El sistema lo calcula automáticamente:

```bash
curl -X POST "http://192.168.56.222:8000/api/v1/onus/" \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot": 5,
    "port": 3,
    "logical": 10,
    "serial_number": "HWTC12345678",
    "modelo_onu": "HG8310M",
    "plan_onu": "100MB",
    "snmp_description": "74150572",
    "active": true
  }'
```

**¿Qué hace el sistema internamente?**

1. Obtiene la OLT con ID=21
2. Busca la fórmula activa de la marca de esa OLT (Huawei)
3. Calcula el `raw_index_key` usando `generate_raw_index_key(5, 3, 10)`
4. Crea `OnuIndexMap` con el `raw_index_key` calculado
5. Crea `OnuStatus` con `presence=ENABLED` (porque `active=true`)
6. Crea `OnuInventory` con todos los datos

### Flujo Completo

```
USUARIO PROPORCIONA:
  olt=21, slot=5, port=3, logical=10

         ↓

API busca fórmula de Huawei MA5800:
  base_index = 4194304000
  step_slot = 8192
  step_port = 256
  has_dot_notation = True

         ↓

Calcula raw_index_key:
  4194304000 + (5 × 8192) + (3 × 256) + 10 = 4194345738
  Con punto: "4194345738.10"

         ↓

CREA 3 REGISTROS:

1. OnuIndexMap:
   - olt = 21
   - raw_index_key = "4194345738.10"
   - slot = 5
   - port = 3
   - logical = 10
   - normalized_id = "5/3"

2. OnuStatus:
   - onu_index → OnuIndexMap
   - olt = 21
   - presence = "ENABLED"

3. OnuInventory:
   - onu_index → OnuIndexMap
   - olt = 21
   - serial_number = "HWTC12345678"
   - modelo_onu = "HG8310M"
   - plan_onu = "100MB"
   - snmp_description = "74150572"
   - active = True
```

---

## 📊 Fórmulas Configuradas

### Huawei (MA5800, MA5600, MA5680T)
- **Modo**: Linear
- **Base**: 4194304000
- **Step Slot**: 8192
- **Step Port**: 256
- **Notación con punto**: Sí
- **Formato**: `{slot}/{port}`

### ZTE (C300, C320)
- **Modo**: Bitshift
- **Shift Slot**: 24 bits
- **Shift Port**: 16 bits
- **Notación con punto**: No
- **Formato**: `{slot}/{port}`

### Nokia (ISAM 7302, 7330)
- **Modo**: Linear
- **Base**: Variable según modelo
- **Step Slot**: Variable
- **Step Port**: Variable
- **Notación con punto**: No
- **Formato**: `{slot}/{port}/{logical}`

---

## ⚠️ Consideraciones Importantes

### 1. Fórmula Activa Requerida
Para crear una ONU, **DEBE existir una fórmula activa** para la marca de la OLT:

```python
# ✅ CORRECTO: Existe fórmula para Huawei
olt = OLT.objects.get(id=21)  # SD-3, marca=Huawei
formula = IndexFormula.objects.filter(marca=olt.marca, activo=True).first()
# formula existe → Puede crear ONU

# ❌ ERROR: No existe fórmula para esa marca
olt = OLT.objects.get(id=99)  # Marca sin fórmula configurada
formula = IndexFormula.objects.filter(marca=olt.marca, activo=True).first()
# formula = None → Error al crear ONU
```

### 2. Unicidad del raw_index_key
El `raw_index_key` es único por OLT. **No puede haber dos ONUs con el mismo índice en la misma OLT**:

```python
# ✅ CORRECTO: Diferentes posiciones
ONU1: olt=21, slot=5, port=3, logical=10 → raw_index_key=4194345738.10
ONU2: olt=21, slot=5, port=3, logical=11 → raw_index_key=4194345738.11

# ❌ ERROR: Misma posición
ONU1: olt=21, slot=5, port=3, logical=10 → raw_index_key=4194345738.10
ONU2: olt=21, slot=5, port=3, logical=10 → raw_index_key=4194345738.10 (duplicado!)
```

### 3. Validación de Rangos
Las fórmulas tienen límites configurados:

```python
formula.slot_max = 64    # Slots válidos: 0-64
formula.port_max = 64    # Puertos válidos: 0-64
formula.onu_max = 128    # ONUs válidas: 0-128
```

Si intentas crear una ONU fuera de estos rangos, el sistema lo permitirá pero registrará un warning.

### 4. Offset de ONU
Algunas OLTs empiezan la numeración de ONUs en 0, otras en 1:

```python
# Huawei: ONUs empiezan en 0
formula.onu_offset = 0
logical=10 → onu_id interno=10

# ZTE: ONUs empiezan en 1
formula.onu_offset = 1
logical=10 → onu_id interno=9
```

---

## 🧪 Testing

### Probar el Cálculo Directo
```python
from snmp_formulas.models import IndexFormula

formula = IndexFormula.objects.get(marca__nombre='Huawei', activo=True)

# Directo: raw_index_key → slot/port/logical
result = formula.calculate_components("4194345738.10")
print(result)
# {'slot': 5, 'port': 3, 'logical': 10, 'snmp_index': 4194345738, 'onu_number': 10}
```

### Probar el Cálculo Inverso
```python
# Inverso: slot/port/logical → raw_index_key
raw_key = formula.generate_raw_index_key(slot=5, port=3, logical=10)
print(raw_key)
# "4194345738.10"
```

### Verificar Bidireccionalidad
```python
# Debe ser consistente en ambas direcciones
original = "4194345738.10"
componentes = formula.calculate_components(original)
regenerado = formula.generate_raw_index_key(
    componentes['slot'], 
    componentes['port'], 
    componentes['logical']
)

assert original == regenerado  # ✅ Debe ser True
```

---

## 📝 Conclusión

El sistema de fórmulas SNMP es el **núcleo del cálculo de índices** en Facho Deluxe v2. Permite:

✅ **Descubrimiento automático**: Convertir índices SNMP crudos en posiciones legibles
✅ **Creación manual via API**: Generar índices SNMP desde posiciones físicas
✅ **Soporte multi-marca**: Configurar diferentes fórmulas sin cambiar código
✅ **Validación**: Verificar que las posiciones sean válidas
✅ **Consistencia**: Garantizar que los cálculos sean bidireccionales

Para agregar una nueva marca de OLT, solo necesitas crear una nueva fórmula en el admin de Django.

