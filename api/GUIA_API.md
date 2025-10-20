# 🚀 GUÍA COMPLETA DE LA API REST - Facho Deluxe v2

## 📋 Índice
1. [Autenticación](#autenticación)
2. [Arquitectura de Estados](#arquitectura-de-estados)
3. [Gestión de ONUs](#gestión-de-onus)
4. [Gestión de ODFs e Hilos](#gestión-de-odfs-e-hilos)
5. [Consultas y Búsquedas](#consultas-y-búsquedas)
6. [Cambios de Estado](#cambios-de-estado)
7. [Operaciones Masivas](#operaciones-masivas)
8. [Casos de Uso Comunes](#casos-de-uso-comunes)
9. [Referencia Rápida](#referencia-rápida)

---

## 🏗️ Arquitectura de Estados

### **Campos de Estado de ONUs**

Esta API maneja **3 campos relacionados** que controlan el estado de las ONUs:

| Campo | Ubicación | Valores | Descripción | Sincronización |
|-------|-----------|---------|-------------|----------------|
| **`active`** | `OnuInventory` | `true` / `false` | Indica si la ONU está activa en el inventario | ⚡ Automática con `presence` |
| **`presence`** | `OnuStatus` | `ENABLED` / `DISABLED` | Detectado por SNMP walk (fuente de verdad física) | ⚡ Automática con `active` |
| **`Estado`** | `OnuStatus` (`last_state_label`) | `ACTIVO` / `SUSPENDIDO` | Estado administrativo del servicio | ✋ Independiente |

### **🔗 Sincronización Automática**

**La API sincroniza automáticamente `active` ↔ `presence` en TODAS las operaciones:**

```
active = true  ←→ presence = ENABLED
active = false ←→ presence = DISABLED
```

**✅ Garantizado en:**
- ✓ Creación de ONUs (POST `/onus/`)
- ✓ Actualización de ONUs (PATCH/PUT `/onus/{id}/`)
- ✓ Activar presence (`/onus/{id}/activar-presence/`)
- ✓ Desactivar presence (`/onus/{id}/desactivar-presence/`)
- ✓ Soft delete (`/onus/{id}/desactivar/`)

**📌 IMPORTANTE:** No puede existir `active=true` con `presence=DISABLED`, ni `active=false` con `presence=ENABLED`.

### **Comando de Verificación**

Si sospechas inconsistencias en los datos, ejecuta:

```bash
# Ver inconsistencias
python manage.py sincronizar_presence_active --dry-run

# Corregir automáticamente
python manage.py sincronizar_presence_active --fix
```

---

## 🔐 Autenticación

Todos los comandos requieren un token de autenticación:

```bash
TOKEN="992f9d275d8b5852d5449988b2419f467f1fe932"
API_URL="http://192.168.56.222:8000/api/v1"
```

### Obtener un nuevo token

```bash
curl -X POST "${API_URL}/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{"username": "tu_usuario", "password": "tu_contraseña"}'
```

---

## 📦 Gestión de ONUs

### 1️⃣ Crear una ONU Nueva

**Campos Obligatorios para Crear ONU:**
1. `olt`: ID de la OLT
2. `slot_input`: Número de slot
3. `port_input`: Número de puerto
4. `logical_input`: Número lógico de ONU
5. `snmp_description`: DNI, nombre o código del cliente
6. `estado_input`: `"ACTIVO"` o `"SUSPENDIDO"` - Define el estado administrativo del servicio

**Campos Opcionales:**
- `presence_input`: `"ENABLED"` o `"DISABLED"` (default: `"ENABLED"`)
  - Define si la ONU está físicamente presente/detectada

**⚠️ Sincronización Automática:**
- `presence_input=ENABLED` → `active=true` y `presence=ENABLED`
- `presence_input=DISABLED` → `active=false` y `presence=DISABLED`
- `estado_input` es independiente de `presence`/`active`

**📝 Nota:** El campo `active` (true/false) se calcula automáticamente y siempre refleja `presence`

**Campos Opcionales:**
- `serial_number`: Número de serie
- `mac_address`: Dirección MAC
- `modelo_onu`: Modelo del equipo (ej: HG8310M, F601)
- `plan_onu`: Plan de servicio (ej: 100MB, 50MB)
- `distancia_onu`: Distancia en metros
- `subscriber_id`: ID del suscriptor

**Comportamiento de Creación:**

| `estado_input` | `presence_input` | `active` (calculado) | `presence` (OnuStatus) | `Estado` (OnuStatus) | Descripción |
|----------------|------------------|----------------------|------------------------|----------------------|-------------|
| `ACTIVO` | `ENABLED` | `true` | `ENABLED` | `ACTIVO` | ONU conectada con servicio activo (caso normal) |
| `SUSPENDIDO` | `ENABLED` | `true` | `ENABLED` | `SUSPENDIDO` | ONU conectada pero servicio suspendido |
| `ACTIVO` | `DISABLED` | `false` | `DISABLED` | `ACTIVO` | ONU desconectada pero servicio activo (eventual reconexión) |
| `SUSPENDIDO` | `DISABLED` | `false` | `DISABLED` | `SUSPENDIDO` | ONU desconectada y servicio suspendido |
| `ACTIVO` *(req)* | *(omitido)* | `true` | `ENABLED` | `ACTIVO` | estado_input obligatorio, presence_input opcional (default: ENABLED) |

**📌 IMPORTANTE:** 
- **`active` se calcula automáticamente**: NO lo envíes en el JSON, se deriva de `presence_input`
- **`active` y `presence` siempre van juntos**: `presence=ENABLED` → `active=true`, `presence=DISABLED` → `active=false`
- **`Estado` (ACTIVO/SUSPENDIDO)** es independiente de `presence`/`active`

#### Ejemplo 1: ONU Conectada con Servicio Activo (caso normal)

```bash
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 10,
    "serial_number": "HWTC12345678",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "modelo_onu": "HG8310M",
    "plan_onu": "100MB",
    "distancia_onu": 250,
    "snmp_description": "74150572",
    "subscriber_id": "CLI-2024-00123",
    "estado_input": "ACTIVO",
    "presence_input": "ENABLED"
  }'
```

#### Ejemplo 2: ONU Conectada pero Suspendida Administrativamente

```bash
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 11,
    "snmp_description": "75139456",
    "estado_input": "SUSPENDIDO",
    "presence_input": "ENABLED"
  }'
```

#### Ejemplo 3: ONU Desconectada con Servicio Activo

```bash
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 12,
    "snmp_description": "76123789",
    "estado_input": "ACTIVO",
    "presence_input": "DISABLED"
  }'
```

#### Ejemplo 4: ONU Mínima (campos obligatorios)

```bash
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 13,
    "snmp_description": "77456123",
    "estado_input": "ACTIVO"
  }'
```
**Nota:** Solo `estado_input` es obligatorio. `presence_input` es opcional (default: `ENABLED`)

**Resultado:**
- Se crean automáticamente 3 registros: `OnuIndexMap`, `OnuStatus`, `OnuInventory`
- El `raw_index_key` se calcula automáticamente según la fórmula de la OLT
- El campo `active` se sincroniza automáticamente con `presence`

---

## 📡 Gestión de ODFs e Hilos

### 1️⃣ Crear ODF

**Campos Obligatorios:**
1. `olt`: ID de la OLT
2. `numero_odf`: Número identificador del ODF
3. `nombre_troncal`: Nombre de la troncal

**Campos Opcionales:**
- `descripcion`: Descripción del ODF

```bash
# Crear ODF
curl -X POST "${API_URL}/odfs/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 23,
    "numero_odf": 33,
    "nombre_troncal": "SD-ANILLO ZAPALLAL INTERNEXA 1-12",
    "descripcion": "ODF principal zona norte"
  }' | jq
```

### 2️⃣ Crear Hilo ODF

**Campos Obligatorios:**
1. `odf`: ID del ODF
2. `slot`: Número de slot
3. `port`: Número de puerto
4. `hilo_numero`: Número del hilo (1-12 típicamente)
5. `vlan`: VLAN asignada
6. `operativo_noc`: `true` (operativo) o `false` (no operativo) - **OBLIGATORIO especificar**

**Campos Bloqueados (NO se pueden especificar - gestionados automáticamente):**
- `estado`: Siempre inicia en "disabled", lo actualiza el script de Zabbix
- `origen`: Se establece automáticamente en "manual" al crear por API
- `en_zabbix`: Siempre inicia en false, lo actualiza el script de sincronización
- `created_at`, `updated_at`: Timestamps automáticos

**Campos Opcionales:**
- `descripcion_manual`: Descripción del hilo
- `hora_habilitacion`: Hora de habilitación
- `personal_proyectos`, `personal_noc`, `tecnico_habilitador`: IDs de personal

```bash
# Crear Hilo ODF Operativo
curl -X POST "${API_URL}/odf-hilos/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "odf": 1,
    "slot": 5,
    "port": 10,
    "hilo_numero": 1,
    "vlan": 100,
    "operativo_noc": true,
    "descripcion_manual": "Cliente PRUEBA - Servicio 100MB",
    "fecha_habilitacion": "2025-10-18"
  }' | jq
```

**⚠️ IMPORTANTE:**
- Los campos `estado`, `origen` y `en_zabbix` están **bloqueados (read-only)** en la API
- No se pueden especificar al crear - se establecen automáticamente con valores por defecto
- Solo el script de sincronización con Zabbix puede modificar `estado` y `en_zabbix`
- Especifica `operativo_noc` para indicar si el hilo está listo para uso del NOC

### 3️⃣ Listar Hilos de un ODF

```bash
# Ver todos los hilos de un ODF específico
curl -s "${API_URL}/odf-hilos/?odf=1" \
  -H "Authorization: Token ${TOKEN}" | \
  jq '.results[] | {id, slot, port, hilo_numero, vlan, estado, operativo_noc}'
```

---

## 🔍 Consultas y Búsquedas

### Buscar ONUs por DNI/Descripción

```bash
# Buscar por snmp_description (DNI: 74150572)
curl -X GET "${API_URL}/onus/?search=74150572" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Buscar ONUs de una OLT específica

```bash
# Todas las ONUs de SD-3 (ID=21)
curl -X GET "${API_URL}/onus/?olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Buscar ONUs por slot/port

```bash
# ONUs en slot 5, port 3
curl -X GET "${API_URL}/onus/?olt=21" \
  -H "Authorization: Token ${TOKEN}" | \
  jq '.results[] | select(.slot==5 and .port==3)'
```

### Buscar por DNI + verificar posición

```bash
# Buscar DNI 74150572 en slot 5/3/10
curl -X GET "${API_URL}/onus/?search=74150572&olt=21" \
  -H "Authorization: Token ${TOKEN}" | \
  jq '.results[] | select(.slot==5 and .port==3 and .logical==10)'
```

### Listar solo ONUs ACTIVAS

```bash
curl -X GET "${API_URL}/onus/?active=true&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Listar solo ONUs SUSPENDIDAS

```bash
curl -X GET "${API_URL}/onus/?active=false&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Ver detalles de una ONU específica

```bash
# Reemplaza 59856 con el ID real
curl -X GET "${API_URL}/onus/59856/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Formato tabla legible

```bash
curl -X GET "${API_URL}/onus/?olt=21&page_size=50" \
  -H "Authorization: Token ${TOKEN}" | \
  jq -r '["ID","Slot/Port/Onu","SNMP Desc","Serial","Modelo","Plan","Active","Estado"], 
         ["---","-------------","----------","------","------","----","------","------"], 
         (.results[] | [.id, "\(.slot)/\(.port)/\(.logical)", 
                        (.snmp_description // "N/A"), 
                        (.serial_number // "N/A"), 
                        (.modelo_onu // "N/A"), 
                        (.plan_onu // "N/A"),
                        .active,
                        .estado_display]) | @tsv'
```

---

## 🔄 Cambios de Estado

### 📌 Conceptos Importantes - Terminología

**⚠️ NO CONFUNDIR:**

**1. `active` (OnuInventory) y `presence` (OnuStatus) - SIEMPRE SINCRONIZADOS:**
- `active=true` ↔ `presence=ENABLED` (ONU puede conectarse físicamente)
- `active=false` ↔ `presence=DISABLED` (ONU bloqueada físicamente)
- **Se cambian juntos** con `/activar-presence/` y `/desactivar-presence/`

**2. `Estado` (last_state_label en OnuStatus) - INDEPENDIENTE:**
- Valores: `"ACTIVO"` o `"SUSPENDIDO"`
- Estado administrativo del servicio (NO afecta conexión física)
- **Se cambia independientemente** con `/activar-estado/` y `/suspender-estado/`

**Ejemplo de combinación:**
- `active=true` + `presence=ENABLED` + `Estado=SUSPENDIDO` → Cliente conectado físicamente pero servicio suspendido
- `active=false` + `presence=DISABLED` + `Estado=ACTIVO` → Cliente bloqueado físicamente pero servicio activo administrativamente

---

### 1️⃣ Cambiar ESTADO Administrativo

#### ✅ Activar Estado (→ ACTIVO)

```bash
# Cambiar estado a ACTIVO (NO modifica active/presence)
curl -X POST "${API_URL}/onus/ID_ONU/activar-estado/" \
  -H "Authorization: Token ${TOKEN}"
```

**Ejemplo con búsqueda:**
```bash
# Buscar y activar estado
ONU_ID=$(curl -s "${API_URL}/onus/?search=74150572&olt=21" \
  -H "Authorization: Token ${TOKEN}" | \
  jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/activar-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

#### 🔒 Suspender Estado (→ SUSPENDIDO)

```bash
# Cambiar estado a SUSPENDIDO (NO modifica active/presence)
curl -X POST "${API_URL}/onus/ID_ONU/suspender-estado/" \
  -H "Authorization: Token ${TOKEN}"
```

**Ejemplo con búsqueda:**
```bash
# Buscar y suspender estado
ONU_ID=$(curl -s "${API_URL}/onus/?search=75139456&olt=21" \
  -H "Authorization: Token ${TOKEN}" | \
  jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/suspender-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

---

### 2️⃣ Cambiar PRESENCE (Conexión Física)

#### ✅ Activar Presence (→ ENABLED)

```bash
# Activar presence: active=true + presence=ENABLED (estado NO cambia)
curl -X POST "${API_URL}/onus/ID_ONU/activar-presence/" \
  -H "Authorization: Token ${TOKEN}"
```

**Ejemplo:** Reconectar una ONU suspendida que se detectó físicamente
```bash
ONU_ID=$(curl -s "${API_URL}/onus/?search=cliente123&olt=21" \
  -H "Authorization: Token ${TOKEN}" | \
  jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/activar-presence/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

#### 🔌 Desactivar Presence (→ DISABLED)

```bash
# Desactivar presence: active=false + presence=DISABLED (estado NO cambia)
curl -X POST "${API_URL}/onus/ID_ONU/desactivar-presence/" \
  -H "Authorization: Token ${TOKEN}"
```

---

### 3️⃣ Desactivar Completamente (Soft Delete)

```bash
# Desactiva TODO: presence=DISABLED + estado=SUSPENDIDO + active=false
curl -X POST "${API_URL}/onus/ID_ONU/desactivar/" \
  -H "Authorization: Token ${TOKEN}"
```

**Efecto:**
- La ONU se ignorará en el recolector hasta que se detecte nuevamente
- Los datos se mantienen en las 3 tablas

---

### 4️⃣ Eliminar Permanentemente (Hard Delete)

```bash
# ⚠️ IRREVERSIBLE: Borra de OnuInventory, OnuStatus y OnuIndexMap
curl -X DELETE "${API_URL}/onus/ID_ONU/eliminar-permanente/" \
  -H "Authorization: Token ${TOKEN}"
```

**⚠️ ADVERTENCIA:** Esta acción NO se puede deshacer.

---

## 🔢 Operaciones Masivas

### Suspender Varias ONUs

```bash
#!/bin/bash
# suspender_masivo.sh

TOKEN="TU_TOKEN_AQUI"
API_URL="http://192.168.56.222:8000/api/v1"

# Lista de DNIs a suspender
DNIS=("74150572" "75139456" "70634252" "44273350")

for DNI in "${DNIS[@]}"; do
    echo "🔍 Buscando DNI: ${DNI}..."
    
    ONU_ID=$(curl -s "${API_URL}/onus/?search=${DNI}&olt=21" \
      -H "Authorization: Token ${TOKEN}" | \
      jq -r '.results[0].id // empty')
    
    if [ ! -z "$ONU_ID" ]; then
        echo "   ✅ Encontrado ID: ${ONU_ID}"
        echo "   🔒 Suspendiendo estado..."
        
        curl -s -X POST "${API_URL}/onus/${ONU_ID}/suspender-estado/" \
          -H "Authorization: Token ${TOKEN}" | jq -c '{id, active, estado, presence}'
        
        echo ""
    else
        echo "   ❌ No encontrado"
        echo ""
    fi
done

echo "✅ Proceso completado"
```

### Activar Varias ONUs

```bash
#!/bin/bash
# activar_masivo.sh

TOKEN="TU_TOKEN_AQUI"
API_URL="http://192.168.56.222:8000/api/v1"

# Lista de IDs a activar
IDS=(59865 59866 59867 59868)

for ID in "${IDS[@]}"; do
    echo "✅ Activando ONU ID: ${ID}..."
    
    curl -s -X POST "${API_URL}/onus/${ID}/activar-estado/" \
      -H "Authorization: Token ${TOKEN}" | \
      jq -c '{id, active, estado, presence}'
    
    echo ""
done

echo "✅ Todas las ONUs activadas"
```

### Eliminar ONUs de un Slot Completo

```bash
#!/bin/bash
# eliminar_slot.sh

TOKEN="TU_TOKEN_AQUI"
API_URL="http://192.168.56.222:8000/api/v1"
OLT_ID=21
SLOT=5

echo "⚠️  ELIMINANDO ONUs del Slot ${SLOT} de OLT ${OLT_ID}..."
echo ""

# Obtener todas las ONUs del slot
IDS=$(curl -s "${API_URL}/onus/?olt=${OLT_ID}&page_size=1000" \
  -H "Authorization: Token ${TOKEN}" | \
  jq -r ".results[] | select(.slot==${SLOT}) | .id")

COUNT=0
for ID in $IDS; do
    echo "🗑️  Eliminando ONU ID: ${ID}..."
    
    curl -s -X DELETE "${API_URL}/onus/${ID}/eliminar-permanente/" \
      -H "Authorization: Token ${TOKEN}" | jq -c '.message'
    
    ((COUNT++))
done

echo ""
echo "✅ ${COUNT} ONUs eliminadas del Slot ${SLOT}"
```

### Actualizar Plan de Varias ONUs

```bash
#!/bin/bash
# actualizar_plan_masivo.sh

TOKEN="TU_TOKEN_AQUI"
API_URL="http://192.168.56.222:8000/api/v1"

# Lista de DNIs y su nuevo plan
declare -A CLIENTES=(
    ["74150572"]="200MB"
    ["75139456"]="100MB"
    ["70634252"]="50MB"
)

for DNI in "${!CLIENTES[@]}"; do
    PLAN="${CLIENTES[$DNI]}"
    
    echo "🔍 Buscando DNI: ${DNI}..."
    
    ONU_ID=$(curl -s "${API_URL}/onus/?search=${DNI}&olt=21" \
      -H "Authorization: Token ${TOKEN}" | \
      jq -r '.results[0].id // empty')
    
    if [ ! -z "$ONU_ID" ]; then
        echo "   ✅ Encontrado ID: ${ONU_ID}"
        echo "   📝 Actualizando plan a: ${PLAN}..."
        
        curl -s -X PATCH "${API_URL}/onus/${ONU_ID}/" \
          -H "Authorization: Token ${TOKEN}" \
          -H "Content-Type: application/json" \
          -d "{\"plan_onu\": \"${PLAN}\"}" | \
          jq -c '{id, snmp_description, plan_onu}'
        
        echo ""
    else
        echo "   ❌ No encontrado"
        echo ""
    fi
done

echo "✅ Planes actualizados"
```

---

## 💼 Casos de Uso Comunes

### Caso 1: Cliente Nuevo (Alta de Servicio)

```bash
# 1. Crear ONU ACTIVA
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 15,
    "serial_number": "HWTC99887766",
    "snmp_description": "12345678",
    "plan_onu": "100MB",
    "modelo_onu": "HG8310M",
    "estado_input": "ACTIVO",
    "presence_input": "ENABLED"
  }' | jq
```

### Caso 2: Suspender Cliente por Falta de Pago

```bash
# Buscar por DNI y suspender ESTADO (mantiene presence activo)
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/suspender-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

**Resultado:** Cliente suspendido administrativamente pero la ONU sigue físicamente conectada

### Caso 3: Reconexión de Cliente (Pagó)

```bash
# Buscar por DNI y activar ESTADO
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/activar-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Caso 4: Cliente se Desconectó Físicamente

```bash
# Desactivar PRESENCE (active=false, presence=DISABLED)
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/desactivar-presence/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Caso 5: Cliente Reconectó su Equipo

```bash
# Activar PRESENCE (active=true, presence=ENABLED, estado NO cambia)
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/activar-presence/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Caso 6: Cliente Dio de Baja (Cancelación)

```bash
# Opción A: Soft Delete (mantiene historial)
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X POST "${API_URL}/onus/${ONU_ID}/desactivar/" \
  -H "Authorization: Token ${TOKEN}" | jq

# Opción B: Hard Delete (elimina permanentemente)
curl -X DELETE "${API_URL}/onus/${ONU_ID}/eliminar-permanente/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Caso 7: Cambio de Plan

```bash
# Actualizar solo el plan_onu
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X PATCH "${API_URL}/onus/${ONU_ID}/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"plan_onu": "200MB"}' | jq
```

### Caso 8: Actualizar Datos de Cliente

```bash
# Actualizar varios campos a la vez
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X PATCH "${API_URL}/onus/${ONU_ID}/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "snmp_description": "87654321",
    "serial_number": "HWTC11223344",
    "plan_onu": "100MB",
    "modelo_onu": "F601"
  }' | jq
```

### Caso 9: Migrar Cliente a Otro Puerto

⚠️ **IMPORTANTE:** No se puede cambiar `slot/port/logical` de una ONU existente. Debes:

```bash
# 1. Obtener datos de la ONU actual
OLD_ONU=$(curl -s "${API_URL}/onus/?search=12345678&olt=21" \
  -H "Authorization: Token ${TOKEN}" | jq '.results[0]')

echo "$OLD_ONU" | jq '{serial_number, plan_onu, modelo_onu, snmp_description}'

# 2. Eliminar ONU antigua
OLD_ID=$(echo "$OLD_ONU" | jq -r '.id')
curl -X DELETE "${API_URL}/onus/${OLD_ID}/eliminar-permanente/" \
  -H "Authorization: Token ${TOKEN}"

# 3. Crear ONU en nueva posición
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 6,
    "port_input": 5,
    "logical_input": 20,
    "serial_number": "HWTC99887766",
    "snmp_description": "12345678",
    "plan_onu": "100MB",
    "modelo_onu": "HG8310M",
    "estado_input": "ACTIVO",
    "presence_input": "ENABLED"
  }' | jq
```

### Caso 10: Reporte de ONUs por Presencia (Conectadas/Desconectadas)

```bash
# Contar ONUs por presencia física en una OLT
echo "📊 REPORTE DE ONUs - OLT SD-3 (ID=21)"
echo "======================================"
echo ""

TOTAL=$(curl -s "${API_URL}/onus/?olt=21&page_size=1" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.count')

# active=true filtra ONUs con presence=ENABLED (conectadas)
CONECTADAS=$(curl -s "${API_URL}/onus/?olt=21&active=true&page_size=1" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.count')

# active=false filtra ONUs con presence=DISABLED (desconectadas)
DESCONECTADAS=$(curl -s "${API_URL}/onus/?olt=21&active=false&page_size=1" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.count')

echo "Total ONUs: ${TOTAL}"
echo "  📡 Conectadas (presence=ENABLED): ${CONECTADAS}"
echo "  ⚠️  Desconectadas (presence=DISABLED): ${DESCONECTADAS}"
```

---

## 📚 Referencia Rápida

### Endpoints Principales

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/v1/onus/` | Listar ONUs |
| `POST` | `/api/v1/onus/` | Crear ONU |
| `GET` | `/api/v1/onus/{id}/` | Ver detalles de ONU |
| `PATCH` | `/api/v1/onus/{id}/` | Actualizar ONU parcialmente |
| `PUT` | `/api/v1/onus/{id}/` | Actualizar ONU completa |
| `POST` | `/api/v1/onus/{id}/activar-estado/` | Cambiar estado a ACTIVO |
| `POST` | `/api/v1/onus/{id}/suspender-estado/` | Cambiar estado a SUSPENDIDO |
| `POST` | `/api/v1/onus/{id}/activar-presence/` | Activar presence (ENABLED) |
| `POST` | `/api/v1/onus/{id}/desactivar-presence/` | Desactivar presence (DISABLED) |
| `POST` | `/api/v1/onus/{id}/desactivar/` | Desactivar completamente (soft delete) |
| `DELETE` | `/api/v1/onus/{id}/eliminar-permanente/` | Eliminar permanentemente (hard delete) |

### Parámetros de Búsqueda

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `search` | Buscar en serial, MAC, DNI, subscriber_id | `?search=74150572` |
| `olt` | Filtrar por OLT | `?olt=21` |
| `active` | Filtrar por estado active | `?active=true` |
| `plan_onu` | Filtrar por plan | `?plan_onu=100MB` |
| `modelo_onu` | Filtrar por modelo | `?modelo_onu=HG8310M` |
| `ordering` | Ordenar resultados | `?ordering=-created_at` |
| `page_size` | Resultados por página | `?page_size=100` |

### Estados y sus Significados

| Campo | Tipo | Valores | Obligatorio | Significado |
|-------|------|---------|-------------|-------------|
| `estado_input` | Entrada (write) | `"ACTIVO"` / `"SUSPENDIDO"` | ✅ Sí | Define el estado administrativo al crear/editar |
| `presence_input` | Entrada (write) | `"ENABLED"` / `"DISABLED"` | ❌ No (default: ENABLED) | Define la presencia física al crear/editar |
| `active` | Salida (read) | `true` / `false` | - | Calculado automáticamente desde `presence` |
| `presence` | Salida (read) | `"ENABLED"` / `"DISABLED"` | - | Presencia física en OnuStatus |
| `estado_label` | Salida (read) | `"ACTIVO"` / `"SUSPENDIDO"` | - | Estado administrativo en OnuStatus |
| `estado_display` | Salida (read) | `"ACTIVO"` / `"SUSPENDIDO"` | - | Alias de `estado_label` |

### Relación entre Campos

```
ENTRADA (al crear/editar):
  estado_input:   "ACTIVO" o "SUSPENDIDO"  → Define Estado administrativo
  presence_input: "ENABLED" o "DISABLED"   → Define Presence físico

SINCRONIZACIÓN AUTOMÁTICA:
  presence_input = "ENABLED"  → active = true  + presence = "ENABLED"
  presence_input = "DISABLED" → active = false + presence = "DISABLED"

INDEPENDIENTE:
  estado_input → estado_label (NO afecta active/presence)
```

---

## 🆘 Solución de Problemas

### Error: "Token inválido"

```bash
# Regenerar token
curl -X POST "${API_URL}/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{"username": "tu_usuario", "password": "tu_contraseña"}'
```

### Error: "No se encontró fórmula SNMP activa"

Verifica que la OLT tenga una fórmula configurada:
```bash
curl -X GET "${API_URL}/formulas/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Error: "ONU no encontrada"

Verifica el ID correcto:
```bash
curl -X GET "${API_URL}/onus/?search=TU_BUSQUEDA" \
  -H "Authorization: Token ${TOKEN}" | jq '.results[] | {id, slot, port, logical}'
```

### Ver logs de errores

```bash
tail -f /opt/facho_deluxe_2/logs/gunicorn.log
```

---

## 📖 Documentación Adicional

- **Swagger UI**: http://192.168.56.222:8000/api/schema/swagger-ui/
- **ReDoc**: http://192.168.56.222:8000/api/schema/redoc/
- **OpenAPI Schema**: http://192.168.56.222:8000/api/schema/

---

## 📝 Notas Finales

1. **Backup antes de operaciones masivas**: Siempre haz backup antes de eliminar múltiples ONUs
2. **Tokens de seguridad**: Mantén los tokens seguros y rotar periódicamente
3. **Rate limiting**: La API tiene límites de 100 requests/minuto por usuario
4. **Logs**: Todas las operaciones quedan registradas en los logs del sistema

---

**Versión**: 2.0.0  
**Última actualización**: 18 de Octubre, 2025  
**Contacto**: Soporte Técnico Facho Deluxe

