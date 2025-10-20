# 🎯 EJEMPLO COMPLETO: CREAR Y BORRAR CLIENTE VIA API

## 📋 Configuración Inicial

```bash
TOKEN="992f9d275d8b5852d5449988b2419f467f1fe932"
API_URL="http://192.168.56.222:8000/api/v1"
```

---

## 1️⃣ CREAR CLIENTE NUEVO

### Campos Obligatorios:
- `olt`: ID de la OLT
- `slot_input`, `port_input`, `logical_input`: Posición física
- `snmp_description`: DNI o código del cliente
- `estado_input`: **"ACTIVO"** o **"SUSPENDIDO"** (OBLIGATORIO)

### Campos Opcionales:
- `presence_input`: "ENABLED" o "DISABLED" (default: ENABLED)
- `serial_number`, `mac_address`, `modelo_onu`, `plan_onu`, `distancia_onu`

### Comando:

```bash
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 10,
    "logical_input": 25,
    "snmp_description": "12345678",
    "serial_number": "HWTC99887766",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "modelo_onu": "HG8310M",
    "plan_onu": "100MB",
    "distancia_onu": 250,
    "estado_input": "ACTIVO"
  }' | jq
```

### Respuesta Esperada:

```json
{
  "id": 59900,
  "olt_nombre": "SD-3",
  "slot": 5,
  "port": 10,
  "logical": 25,
  "normalized_id": "5/10",
  "raw_index_key": "4194315530.25",
  "snmp_description": "12345678",
  "serial_number": "HWTC99887766",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "modelo_onu": "HG8310M",
  "plan_onu": "100MB",
  "distancia_onu": "250",
  "presence": "ENABLED",
  "estado_label": "ACTIVO",
  "estado_display": "ACTIVO",
  "created_at": "2025-10-18 15:30:00"
}
```

**✅ Notas:**
- Se crearon automáticamente 3 registros: `OnuIndexMap`, `OnuStatus`, `OnuInventory`
- `presence` = "ENABLED" (por defecto, no fue especificado)
- `estado_label` = "ACTIVO" (según `estado_input`)
- `raw_index_key` se calculó automáticamente según la fórmula de la OLT

---

## 2️⃣ BUSCAR CLIENTE POR DNI

```bash
curl -X GET "${API_URL}/onus/?search=12345678" \
  -H "Authorization: Token ${TOKEN}" | \
  jq '.results[] | {id, olt_nombre, slot, port, logical, snmp_description, presence, estado_display}'
```

### Respuesta:

```json
{
  "id": 59900,
  "olt_nombre": "SD-3",
  "slot": 5,
  "port": 10,
  "logical": 25,
  "snmp_description": "12345678",
  "presence": "ENABLED",
  "estado_display": "ACTIVO"
}
```

---

## 3️⃣ SUSPENDER CLIENTE (Estado Administrativo)

**Caso de Uso:** Cliente no pagó, suspender servicio pero mantener ONU conectada

```bash
# Buscar ID
ONU_ID=$(curl -s "${API_URL}/onus/?search=12345678" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

# Suspender estado
curl -X POST "${API_URL}/onus/${ONU_ID}/suspender-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Respuesta:

```json
{
  "message": "Estado cambiado a SUSPENDIDO exitosamente",
  "id": 59900,
  "presence": "ENABLED",
  "estado": "SUSPENDIDO"
}
```

**✅ Resultado:**
- `presence` = "ENABLED" (ONU sigue conectada físicamente)
- `estado` = "SUSPENDIDO" (servicio suspendido administrativamente)

---

## 4️⃣ REACTIVAR CLIENTE

**Caso de Uso:** Cliente pagó, reactivar servicio

```bash
curl -X POST "${API_URL}/onus/${ONU_ID}/activar-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

### Respuesta:

```json
{
  "message": "Estado cambiado a ACTIVO exitosamente",
  "id": 59900,
  "presence": "ENABLED",
  "estado": "ACTIVO"
}
```

---

## 5️⃣ ACTUALIZAR DATOS DEL CLIENTE

```bash
curl -X PATCH "${API_URL}/onus/${ONU_ID}/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_onu": "200MB",
    "snmp_description": "87654321"
  }' | jq
```

---

## 6️⃣ BORRAR CLIENTE

### Opción A: BORRADO SUAVE (Soft Delete) ✅ Recomendado

**Mantiene historial, solo desactiva el cliente**

```bash
curl -X POST "${API_URL}/onus/${ONU_ID}/desactivar/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

**Resultado:**
- `presence` = "DISABLED"
- `estado` = "SUSPENDIDO"
- Los datos se mantienen en la BD
- El cliente no aparece en listados activos

---

### Opción B: BORRADO PERMANENTE (Hard Delete) ⚠️ CUIDADO

**⚠️ ELIMINA PERMANENTEMENTE - NO SE PUEDE DESHACER**

```bash
curl -X DELETE "${API_URL}/onus/${ONU_ID}/eliminar-permanente/" \
  -H "Authorization: Token ${TOKEN}" | jq
```

**Resultado:**
```json
{
  "message": "ONU y sus registros eliminados exitosamente",
  "id": 59900,
  "deleted_from": [
    "OnuInventory",
    "OnuStatus",
    "OnuIndexMap"
  ]
}
```

---

## 📊 RESUMEN DE OPERACIONES

| Operación | Endpoint | Método | Resultado |
|-----------|----------|--------|-----------|
| **Crear** | `/onus/` | POST | Crea ONU con `estado_input` obligatorio |
| **Buscar** | `/onus/?search=DNI` | GET | Lista ONUs por DNI |
| **Suspender** | `/onus/{id}/suspender-estado/` | POST | `estado` → SUSPENDIDO |
| **Activar** | `/onus/{id}/activar-estado/` | POST | `estado` → ACTIVO |
| **Actualizar** | `/onus/{id}/` | PATCH | Modifica campos específicos |
| **Soft Delete** | `/onus/{id}/desactivar/` | POST | `presence` → DISABLED |
| **Hard Delete** | `/onus/{id}/eliminar-permanente/` | DELETE | Elimina de BD |

---

## 🔑 CAMPOS CLAVE

### Al CREAR (POST):
- **`estado_input`**: "ACTIVO" o "SUSPENDIDO" (OBLIGATORIO)
- **`presence_input`**: "ENABLED" o "DISABLED" (opcional, default: ENABLED)

### En la RESPUESTA (GET):
- **`presence`**: "ENABLED" o "DISABLED" (presencia física)
- **`estado_label`**: "ACTIVO" o "SUSPENDIDO" (estado administrativo)
- **`estado_display`**: "ACTIVO" o "SUSPENDIDO" (alias legible)

**⚠️ IMPORTANTE:** El campo `active` NO se usa en la API. Solo se usa internamente para sincronización.

---

## 🎯 EJEMPLOS RÁPIDOS

### Crear cliente mínimo:
```bash
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 10,
    "logical_input": 30,
    "snmp_description": "99887766",
    "estado_input": "ACTIVO"
  }'
```

### Buscar y eliminar:
```bash
ONU_ID=$(curl -s "${API_URL}/onus/?search=99887766" \
  -H "Authorization: Token ${TOKEN}" | jq -r '.results[0].id')

curl -X DELETE "${API_URL}/onus/${ONU_ID}/eliminar-permanente/" \
  -H "Authorization: Token ${TOKEN}"
```

---

**📝 Ejecuta el script interactivo:**
```bash
bash /opt/facho_deluxe_2/EJEMPLO_COMPLETO_API.sh
```

