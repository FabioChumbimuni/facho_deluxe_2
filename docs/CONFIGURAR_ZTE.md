# 🔧 Guía para Configurar ZTE en el Sistema de Fórmulas SNMP

## 📊 Información del Usuario

Mencionaste que en ZTE:
- **Índice**: `268566784` 
- **Resultado esperado**: `2/1` (slot=2, port=1)

## ⚠️ Paso Crítico: Investigar la Fórmula ZTE

Para configurar ZTE correctamente, necesitas **investigar y calcular la fórmula**:

### **Método 1: Ingeniería Inversa (Recomendado)**

Si tienes varios índices ZTE conocidos, puedes deducir la fórmula:

```python
# Ejemplo con datos que tengas:
# Índice → slot/port
268566784 → 2/1
268632320 → 2/2  (si tienes este dato)
268697856 → 2/3  (si tienes este dato)
134479872 → 1/1  (si tienes este dato)

# Calcular diferencias:
# Entre puertos del mismo slot:
268632320 - 268566784 = 65536  ← STEP_PORT candidato

# Entre slots:
268566784 - 134479872 = 134086912  ← STEP_SLOT candidato

# Calcular BASE:
# BASE = Índice - (slot × STEP_SLOT) - (port × STEP_PORT)
BASE = 268566784 - (2 × STEP_SLOT) - (1 × STEP_PORT)
```

### **Método 2: Documentación del Fabricante**

Buscar en la documentación técnica de ZTE:
- MIBs oficiales de ZTE
- Manuales técnicos del modelo específico
- Foros técnicos de ZTE OLT

### **Método 3: Análisis de Bits (Bitshift)**

Si ZTE usa desplazamiento de bits:

```python
# Convertir a binario
268566784 en binario = 0001 0000 0000 0001 0000 0000 0000 0000

# Identificar patrones:
# - Bits para slot
# - Bits para port
# - Bits para ONU
```

---

## 🎯 Una Vez Tengas la Fórmula

### **Opción A: Configurar desde Django Admin**

1. Ir a: `http://127.0.0.1:8000/admin/snmp_formulas/indexformula/add/`

2. Completar el formulario:

```
=== Información Básica ===
Marca: ZTE
Modelo: (dejar vacío para genérico)
Nombre: ZTE - Fórmula Estándar
Activo: ✓
Descripción: Fórmula calculada para equipos ZTE. Índice 268566784 = slot 2, port 1

=== Configuración de Cálculo ===
Calculation Mode: linear

=== Parámetros Lineales (Base + Pasos) ===
Base Index: [TU_VALOR_CALCULADO]
Step Slot: [TU_VALOR_CALCULADO]
Step Port: [TU_VALOR_CALCULADO]

=== Parámetros Adicionales ===
ONU Offset: 0
Has Dot Notation: ✗ (NO, si ZTE no usa punto como Huawei)
Dot is ONU Number: ✓

=== Validación y Límites ===
Slot Max: 64
Port Max: 64
ONU Max: 128

=== Formato de Salida ===
Normalized Format: {slot}/{port}
```

3. **Guardar**

### **Opción B: Crear mediante Django Shell**

```python
from snmp_formulas.models import IndexFormula
from brands.models import Brand

# Obtener marca ZTE
zte = Brand.objects.get(nombre__iexact='zte')

# Crear fórmula
IndexFormula.objects.create(
    marca=zte,
    modelo=None,  # Genérico
    nombre='ZTE - Fórmula Estándar',
    activo=True,
    calculation_mode='linear',
    base_index=0,  # ← REEMPLAZAR con valor calculado
    step_slot=0,   # ← REEMPLAZAR con valor calculado
    step_port=0,   # ← REEMPLAZAR con valor calculado
    onu_offset=0,
    has_dot_notation=False,
    dot_is_onu_number=True,
    slot_max=64,
    port_max=64,
    onu_max=128,
    normalized_format='{slot}/{port}',
    descripcion='Fórmula estándar para ZTE. Índice 268566784 = slot 2, port 1'
)

print("✅ Fórmula ZTE creada")
```

---

## 🧪 Probar la Configuración

### **1. Verificar con Script**

```bash
cd /opt/facho_deluxe_v2
source venv/bin/activate
python verificar_formulas.py
```

Deberías ver:
```
✅ ACTIVA ZTE (ZTE - Fórmula Estándar)
   Marca: ZTE
   Modo: Lineal (Base + Pasos)
   Base: [tu_valor]
   Step Slot: [tu_valor]
   Step Port: [tu_valor]
```

### **2. Probar Cálculo Manual**

```python
from snmp_formulas.models import IndexFormula
from brands.models import Brand

zte = Brand.objects.get(nombre='ZTE')
formula = IndexFormula.objects.get(marca=zte, modelo__isnull=True)

# Probar con el índice conocido
result = formula.calculate_components('268566784')

print(f"Slot: {result['slot']}")    # Esperado: 2
print(f"Port: {result['port']}")    # Esperado: 1
print(f"Logical: {result['logical']}")

normalized = formula.get_normalized_id(result['slot'], result['port'], result['logical'])
print(f"Normalizado: {normalized}")  # Esperado: "2/1"
```

### **3. Verificar con Datos Reales**

1. Ejecutar una tarea de descubrimiento en una OLT ZTE
2. Ver los registros en `onu_index_map`
3. Verificar que `slot`, `port`, y `normalized_id` sean correctos

---

## 📝 Ejemplo Hipotético (AJUSTAR con datos reales)

**Supongamos que investigaste y encontraste**:

```
BASE = 134217728  (ejemplo hipotético)
STEP_SLOT = 67108864
STEP_PORT = 65536
```

**Verificación**:
```python
# Índice conocido: 268566784 → slot=2, port=1

delta = 268566784 - 134217728 = 134349056
slot = 134349056 // 67108864 = 2 ✅
resto = 134349056 % 67108864 = 131328
port = 131328 // 65536 = 2 ❌ (esperábamos 1)

# Si no coincide, ajustar valores
```

---

## 🔍 Recursos para Investigar

### **Fuentes de Información ZTE**

1. **MIBs Oficiales**:
   - Buscar en sitio oficial de ZTE
   - Solicitar al proveedor del equipo
   - Revisar archivos MIB del equipo

2. **Documentación Técnica**:
   - Manuales de administración ZTE OLT
   - Guías de integración SNMP
   - Notas técnicas del fabricante

3. **Comunidad**:
   - Foros de operadores de fibra
   - Grupos técnicos de ZTE
   - Stack Overflow / Reddit

4. **Análisis Práctico**:
   - Consultar múltiples ONUs de la misma OLT ZTE
   - Anotar pares índice → slot/port
   - Buscar patrones matemáticos

### **Script para Recolectar Datos**

Si tienes acceso SNMP a una OLT ZTE:

```python
from easysnmp import Session

# Conectar a OLT ZTE
session = Session(
    hostname='IP_OLT_ZTE',
    community='public',
    version=2
)

# OID de descubrimiento ZTE (ajustar según el modelo)
oid_base = '1.3.6.1.4.1.3902.1082.500.10.2.1.1'  # Ejemplo

# Walk para obtener índices
items = session.walk(oid_base)

# Imprimir índices encontrados
for item in items:
    print(f"Índice: {item.oid_index} → Valor: {item.value}")
    
# Comparar con datos conocidos de slot/port
# para deducir la fórmula
```

---

## ✅ Checklist Final

Antes de configurar ZTE, asegúrate de tener:

- [ ] Múltiples índices SNMP de ZTE conocidos
- [ ] Relación índice → slot/port verificada
- [ ] Fórmula calculada y validada
- [ ] Valores de BASE, STEP_SLOT, STEP_PORT determinados
- [ ] Marca "ZTE" creada en tabla `marcas`

**Cuando tengas estos datos**, configura la fórmula en el Admin y el sistema funcionará automáticamente para todas las OLTs ZTE.

---

## 🆘 Si Necesitas Ayuda

1. **Consultar README**: `/opt/facho_deluxe_v2/snmp_formulas/README.md`
2. **Ver ejemplos**: Revisar la fórmula Huawei en el Admin
3. **Testing**: Usar `verificar_formulas.py` para probar

---

## 📞 Siguiente Paso

**¡Investigar la fórmula de ZTE!** Una vez la tengas, configurarla tomará solo 2 minutos en el Admin. 🚀

