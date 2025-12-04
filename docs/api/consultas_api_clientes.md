# 📡 Consultas API - Clientes Facho Deluxe v2

## 🔐 Información de Autenticación

**URL Base:** `https://10.80.80.229/api`

**Formato de autenticación:**
- **Header:** `Authorization: Token TU_TOKEN_AQUI`
- **Alternativa (API Key):** `x-api-key: TU_API_KEY`

**Ejemplo con Token:**
```bash
Authorization: Token 992f9d275d8b5852d5449988b2419f467f1fe932
```

**Ejemplo con API Key:**
```bash
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**⚠️ Nota sobre Certificado SSL:**
Como estamos usando un certificado autofirmado, necesitas usar la opción `-k` o `--insecure` en los comandos `curl`.

---

## 1. Verificar Estado del Servidor

**GET** `/api/health`

Verifica que el servidor esté funcionando correctamente.

**Nota:** Esta ruta NO requiere autenticación con API Key.

**Request (sin API Key):**

```bash
GET https://10.80.80.229/api/health
```

**Request (con API Key en query parameter - opcional):**

```bash
GET https://10.80.80.229/api/health?api_key=1124323423dfgfdgd
```

**Response (200 OK):**

```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00.123456Z",
  "version": "2.0.0"
}
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/health" -k
```

---

## 2. Obtener IP del Cliente

**GET** `/api/client-ip`

Obtiene información sobre la IP del cliente (útil para debugging).

**Nota:** Este endpoint requiere autenticación.

**Request (con API Key en header):**

```bash
GET https://10.80.80.229/api/client-ip
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Request (con API Key en query parameter):**

```bash
GET https://10.80.80.229/api/client-ip?api_key=444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Request (con Token de autenticación):**

```bash
curl -X GET "https://10.80.80.229/api/client-ip" \
  -H "Authorization: Token TU_TOKEN_AQUI" \
  -k
```

**Request (con API Key en header):**

```bash
curl -X GET "https://10.80.80.229/api/client-ip" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "clientIp": "192.168.26.100",
  "publicIp": "201.218.159.50",
  "headers": {
    "x-forwarded-for": null,
    "x-real-ip": null,
    "x-public-ip": null,
    "remote-address": "::ffff:192.168.26.100"
  }
}
```

**Response (401 Unauthorized - sin API Key):**

```json
{
  "success": false,
  "message": "API Key requerida. Proporcione la API Key en el header (x-api-key o api-key) o como query parameter (api_key o apiKey)",
  "code": "API_KEY_MISSING"
}
```

**Response (403 Forbidden - API Key inválida):**

```json
{
  "success": false,
  "message": "API Key inválida",
  "code": "API_KEY_INVALID"
}
```

---

## 3. Consultar ONUs por SNMP Description (DNI/Nombre)

**GET** `/api/onus/`

Busca ONUs por su descripción SNMP (DNI, nombre o código del cliente).

### 3.1. Búsqueda Exacta (Recomendado)

Para buscar el valor exacto (ej: solo "74150572", sin "74150572_2"):

**Request:**

```bash
GET https://10.80.80.229/api/onus/?snmp_description=74150572
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/?snmp_description=74150572" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Combinar con otros filtros:**

```bash
# Búsqueda exacta por DNI y filtrar por OLT
curl -X GET "https://10.80.80.229/api/onus/?snmp_description=74150572&olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 3.2. Búsqueda Parcial (Contiene)

Para buscar valores que contengan el texto (ej: "74150572" encontrará "74150572", "74150572_2", "74150572_3", etc.):

**Request:**

```bash
GET https://10.80.80.229/api/onus/?search=74150572
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/?search=74150572" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Nota:** 
- **Búsqueda exacta:** Usa `?snmp_description=74150572` - Solo encuentra valores exactos
- **Búsqueda parcial:** Usa `?search=74150572` - Encuentra valores que contengan el texto (busca en `serial_number`, `mac_address`, `subscriber_id`, y `snmp_description`)

**Response (200 OK):**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 12345,
      "olt": 21,
      "olt_nombre": "OLT-PRINCIPAL",
      "slot": 5,
      "port": 3,
      "logical": 10,
      "normalized_id": "5/3/10",
      "raw_index_key": "4194312192.2",
      "snmpindexonu": "4194312192.2",
      "serial_number": "HWTC12345678",
      "mac_address": "AA:BB:CC:DD:EE:FF",
      "snmp_description": "74150572",
      "subscriber_id": "CLI-2024-00123",
      "plan_onu": "100MB",
      "modelo_onu": "HG8310M",
      "presence": "ENABLED",
      "estado": "ACTIVO",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**Nota:** El campo `snmpindexonu` es un alias de `raw_index_key` y contiene el índice SNMP de la ONU (ej: "4194312192.2").

**Combinar búsqueda con filtros:**

```bash
# Buscar por DNI y filtrar por OLT
curl -X GET "https://10.80.80.229/api/onus/?search=74150572&olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k

# Buscar por DNI y filtrar por presence ENABLED
curl -X GET "https://10.80.80.229/api/onus/?search=74150572&onu_index__status__presence=ENABLED" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## 4. Consultar ONUs por MAC Address

**GET** `/api/onus/`

Busca ONUs por su dirección MAC.

**Request:**

```bash
GET https://10.80.80.229/api/onus/?search=AA:BB:CC:DD:EE:FF
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/?search=AA:BB:CC:DD:EE:FF" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Alternativa (búsqueda exacta con filtro):**

```bash
# Si conoces el formato exacto de la MAC
curl -X GET "https://10.80.80.229/api/onus/?mac_address=AA:BB:CC:DD:EE:FF" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 12345,
      "olt": 21,
      "olt_nombre": "OLT-PRINCIPAL",
      "slot": 5,
      "port": 3,
      "logical": 10,
      "snmpindexonu": "4194312192.2",
      "mac_address": "AA:BB:CC:DD:EE:FF",
      "snmp_description": "74150572",
      "presence": "ENABLED",
      "estado": "ACTIVO"
    }
  ]
}
```

---

## 5. Consultar ONUs por Port (Puerto PON)

**GET** `/api/onus/`

Filtra ONUs por puerto PON (port).

**Request:**

```bash
GET https://10.80.80.229/api/onus/?onu_index__port=3
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/?onu_index__port=3" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Combinar con otros filtros:**

```bash
# Filtrar por OLT y puerto
curl -X GET "https://10.80.80.229/api/onus/?olt=21&onu_index__port=3" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k

# Filtrar por slot, puerto y ONU lógica
curl -X GET "https://10.80.80.229/api/onus/?olt=21&onu_index__slot=5&onu_index__port=3&onu_index__logical=10" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "count": 15,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 12345,
      "olt": 21,
      "olt_nombre": "OLT-PRINCIPAL",
      "slot": 5,
      "port": 3,
      "logical": 10,
      "snmpindexonu": "4194312192.2",
      "snmp_description": "74150572",
      "presence": "ENABLED",
      "estado": "ACTIVO"
    },
    {
      "id": 12346,
      "olt": 21,
      "olt_nombre": "OLT-PRINCIPAL",
      "slot": 5,
      "port": 3,
      "logical": 11,
      "snmpindexonu": "4194312448.3",
      "snmp_description": "75139456",
      "presence": "ENABLED",
      "estado": "ACTIVO"
    }
  ]
}
```

**Nota:** También puedes filtrar por:
- `onu_index__slot`: Filtra por slot
- `onu_index__logical`: Filtra por ONU lógica (logical)

---

## 6. Consultar ONUs por OLT

**GET** `/api/onus/`

Filtra ONUs por OLT específica.

**Request:**

```bash
GET https://10.80.80.229/api/onus/?olt=21
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/?olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Obtener lista de OLTs disponibles:**

```bash
curl -X GET "https://10.80.80.229/api/olts/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK) - Lista de ONUs:**

```json
{
  "count": 150,
  "next": "https://10.80.80.229/api/onus/?olt=21&page=2",
  "previous": null,
  "results": [
    {
      "id": 12345,
      "olt": 21,
      "olt_nombre": "OLT-PRINCIPAL",
      "slot": 5,
      "port": 3,
      "logical": 10,
      "snmp_description": "74150572",
      "presence": "ENABLED",
      "estado": "ACTIVO"
    }
  ]
}
```

**Combinar con otros filtros:**

```bash
# Filtrar por OLT y presence ENABLED
curl -X GET "https://10.80.80.229/api/onus/?olt=21&onu_index__status__presence=ENABLED" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k

# Filtrar por OLT y estado ACTIVO
curl -X GET "https://10.80.80.229/api/onus/?olt=21&active=true" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## 7. Agregar Cliente con Presence Activa (ENABLED)

**POST** `/api/onus/`

Crea una nueva ONU con presencia física activa (ENABLED).

**Campos Obligatorios:**
1. `olt`: ID de la OLT
2. `slot_input`: Número de slot
3. `port_input`: Número de puerto
4. `logical_input`: Número lógico de ONU
5. `snmp_description`: DNI, nombre o código del cliente
6. `estado_input`: `"ACTIVO"` o `"SUSPENDIDO"` - Define el estado administrativo del servicio

**Campos Opcionales:**
- `presence_input`: `"ENABLED"` o `"DISABLED"` (default: `"ENABLED"`)
- `serial_number`: Número de serie
- `mac_address`: Dirección MAC
- `modelo_onu`: Modelo del equipo (ej: HG8310M, F601)
- `plan_onu`: Plan de servicio (ej: 100MB, 50MB)
- `distancia_onu`: Distancia en metros
- `subscriber_id`: ID del suscriptor

**Request:**

```bash
POST https://10.80.80.229/api/onus/
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
Content-Type: application/json
```

**Body (Ejemplo 1: Cliente Activo con Presence ENABLED):**

```json
{
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
}
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
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
  }' \
  -k
```

**Ejemplo 2: Cliente Mínimo (solo campos obligatorios):**

```bash
curl -X POST "https://10.80.80.229/api/onus/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 10,
    "snmp_description": "74150572",
    "estado_input": "ACTIVO"
  }' \
  -k
```

**Nota:** Si no especificas `presence_input`, por defecto se establece como `"ENABLED"`.

**Response (201 Created):**

```json
{
      "id": 12345,
      "olt": 21,
      "olt_nombre": "OLT-PRINCIPAL",
      "slot": 5,
      "port": 3,
      "logical": 10,
      "normalized_id": "5/3/10",
      "raw_index_key": "4194312192.2",
      "snmpindexonu": "4194312192.2",
      "serial_number": "HWTC12345678",
      "mac_address": "AA:BB:CC:DD:EE:FF",
      "snmp_description": "74150572",
      "subscriber_id": "CLI-2024-00123",
      "plan_onu": "100MB",
      "modelo_onu": "HG8310M",
      "presence": "ENABLED",
      "estado": "ACTIVO",
      "created_at": "2024-01-15T10:30:00Z"
}
```

**Comportamiento:**
- `presence_input=ENABLED` → `active=true` (interno) y `presence=ENABLED` (salida)
- `estado_input=ACTIVO` → `estado=ACTIVO` (salida)
- Se crean automáticamente 3 registros: `OnuIndexMap`, `OnuStatus`, `OnuInventory`

---

## 8. Agregar Cliente con Presence Desactiva (DISABLED)

**POST** `/api/onus/`

Crea una nueva ONU con presencia física desactiva (DISABLED). Útil para clientes que aún no tienen el equipo conectado pero ya están registrados en el sistema.

**Request:**

```bash
POST https://10.80.80.229/api/onus/
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
Content-Type: application/json
```

**Body (Ejemplo 1: Cliente Activo pero Desconectado):**

```json
{
  "olt": 21,
  "slot_input": 5,
  "port_input": 3,
  "logical_input": 11,
  "snmp_description": "75139456",
  "estado_input": "ACTIVO",
  "presence_input": "DISABLED"
}
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 11,
    "snmp_description": "75139456",
    "estado_input": "ACTIVO",
    "presence_input": "DISABLED"
  }' \
  -k
```

**⚠️ Nota Importante:** Los campos `plan_onu`, `distancia_onu`, `modelo_onu`, `serial_number`, `mac_address` y `subscriber_id` se resetean automáticamente cuando `presence` vuelve a `ENABLED` (cuando el cliente reconecta). Solo `snmp_description` se mantiene, por lo que es el único campo opcional recomendado al crear una ONU con `presence_input=DISABLED`.

**Ejemplo 2: Cliente Suspendido y Desconectado:**

```bash
curl -X POST "https://10.80.80.229/api/onus/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 12,
    "snmp_description": "76123789",
    "estado_input": "SUSPENDIDO",
    "presence_input": "DISABLED"
  }' \
  -k
```

**Response (201 Created):**

```json
{
      "id": 12346,
      "olt": 21,
      "olt_nombre": "OLT-PRINCIPAL",
      "slot": 5,
      "port": 3,
      "logical": 11,
      "normalized_id": "5/3/11",
      "raw_index_key": "4194312448.3",
      "snmpindexonu": "4194312448.3",
      "snmp_description": "75139456",
      "presence": "DISABLED",
      "estado": "ACTIVO",
      "created_at": "2024-01-15T10:30:00Z"
}
```

**Comportamiento:**
- `presence_input=DISABLED` → `active=false` (interno) y `presence=DISABLED` (salida)
- `estado_input` es independiente de `presence`/`active`
- La ONU se crea pero no será detectada por el recolector SNMP hasta que se active el presence

---

## 9. Desactivar Cliente (Baja)

**POST** `/api/onus/{id}/desactivar/`

Desactiva completamente una ONU (soft delete). Cambia el presence a DISABLED, el estado a SUSPENDIDO y active a False.

**Request:**

```bash
POST https://10.80.80.229/api/onus/12345/desactivar/
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/12345/desactivar/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "message": "ONU desactivada exitosamente",
  "id": 12345,
  "presence": "DISABLED",
  "estado": "SUSPENDIDO"
}
```

**Efecto:**
- `active = False` en OnuInventory
- `presence = DISABLED` en OnuStatus
- `last_state_label = SUSPENDIDO` en OnuStatus
- La ONU se ignorará en el recolector hasta que se detecte nuevamente
- Los datos se mantienen en las 3 tablas (soft delete)

**Alternativa: Buscar ONU por DNI (búsqueda exacta) y desactivarla:**

```bash
# 1. Buscar la ONU por DNI (búsqueda EXACTA para evitar múltiples resultados)
ONU_ID=$(curl -s "https://10.80.80.229/api/onus/?snmp_description=74150572&olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k | \
  jq -r '.results[0].id')

# 2. Desactivar la ONU
curl -X POST "https://10.80.80.229/api/onus/${ONU_ID}/desactivar/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**⚠️ Importante:** Usa `snmp_description=74150572` (búsqueda exacta) en lugar de `search=74150572` (búsqueda parcial) para evitar que se seleccione incorrectamente una ONU con descripción como "74150572_2" o "74150572_3".

**⚠️ Eliminación Permanente (Hard Delete):**

Si necesitas eliminar permanentemente la ONU (irreversible):

```bash
curl -X DELETE "https://10.80.80.229/api/onus/12345/eliminar-permanente/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**⚠️ ADVERTENCIA:** Esta acción NO se puede deshacer. Elimina los registros de `OnuInventory`, `OnuStatus` y `OnuIndexMap`.

---

## 10. Suspender Cliente (Cambiar Estado a SUSPENDIDO)

**POST** `/api/onus/{id}/suspender-estado/`

Cambia el estado administrativo de la ONU a SUSPENDIDO (suspende el servicio administrativamente).

**Request:**

```bash
POST https://10.80.80.229/api/onus/12345/suspender-estado/
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/12345/suspender-estado/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "message": "Estado cambiado a SUSPENDIDO exitosamente",
  "id": 12345,
  "presence": "ENABLED",
  "estado": "SUSPENDIDO"
}
```

**Efecto:**
- `last_state_label = SUSPENDIDO` en OnuStatus
- `last_state_value = 2` en OnuStatus
- `active` y `presence` NO cambian (son independientes del estado administrativo)

**Alternativa: Buscar ONU por DNI (búsqueda exacta) y suspenderla:**

```bash
# 1. Buscar la ONU por DNI (búsqueda EXACTA)
ONU_ID=$(curl -s "https://10.80.80.229/api/onus/?snmp_description=74150572&olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k | \
  jq -r '.results[0].id')

# 2. Suspender la ONU
curl -X POST "https://10.80.80.229/api/onus/${ONU_ID}/suspender-estado/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## 11. Desactivar Presence (Cambiar a DISABLED)

**POST** `/api/onus/{id}/desactivar-presence/`

Desactiva el presence de la ONU a DISABLED (indica que la ONU está físicamente desconectada).

**Request:**

```bash
POST https://10.80.80.229/api/onus/12345/desactivar-presence/
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/12345/desactivar-presence/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "message": "Presence desactivado exitosamente",
  "id": 12345,
  "presence": "DISABLED",
  "estado": "ACTIVO"
}
```

**Efecto:**
- `active = False` en OnuInventory
- `presence = DISABLED` en OnuStatus
- `estado` (last_state_label) NO cambia (es independiente del presence)

**Alternativa: Buscar ONU por DNI (búsqueda exacta) y desactivar presence:**

```bash
# 1. Buscar la ONU por DNI (búsqueda EXACTA)
ONU_ID=$(curl -s "https://10.80.80.229/api/onus/?snmp_description=74150572&olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k | \
  jq -r '.results[0].id')

# 2. Desactivar presence de la ONU
curl -X POST "https://10.80.80.229/api/onus/${ONU_ID}/desactivar-presence/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## 📚 Referencia Rápida de Filtros

### Parámetros de Búsqueda

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `snmp_description` | **Búsqueda exacta** por descripción SNMP (DNI) | `?snmp_description=74150572` |
| `search` | **Búsqueda parcial** en serial, MAC, DNI, subscriber_id | `?search=74150572` |
| `serial_number` | Búsqueda exacta o parcial por número de serie | `?serial_number=HWTC12345678` |
| `mac_address` | Búsqueda exacta o parcial por dirección MAC | `?mac_address=AA:BB:CC:DD:EE:FF` |
| `subscriber_id` | Búsqueda exacta o parcial por ID de suscriptor | `?subscriber_id=CLI-2024-00123` |
| `olt` | Filtrar por OLT | `?olt=21` |
| `onu_index__slot` | Filtrar por slot | `?onu_index__slot=5` |
| `onu_index__port` | Filtrar por puerto PON | `?onu_index__port=3` |
| `onu_index__logical` | Filtrar por ONU lógica | `?onu_index__logical=10` |
| `onu_index__status__presence` | Filtrar por presence | `?onu_index__status__presence=ENABLED` |
| `active` | Filtrar por estado active | `?active=true` |
| `plan_onu` | Filtrar por plan | `?plan_onu=100MB` |
| `modelo_onu` | Filtrar por modelo | `?modelo_onu=HG8310M` |
| `ordering` | Ordenar resultados | `?ordering=-created_at` |
| `page_size` | Resultados por página | `?page_size=100` |

### Combinar Múltiples Filtros

```bash
# Buscar por DNI, filtrar por OLT y presence ENABLED
curl -X GET "https://10.80.80.229/api/onus/?search=74150572&olt=21&onu_index__status__presence=ENABLED" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k

# Filtrar por OLT, slot, puerto y ONU lógica
curl -X GET "https://10.80.80.229/api/onus/?olt=21&onu_index__slot=5&onu_index__port=3&onu_index__logical=10" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## 🔄 Estados y Presence

### Campos de Entrada (al crear/editar)

| Campo | Tipo | Valores | Obligatorio | Significado |
|-------|------|---------|-------------|-------------|
| `estado_input` | Entrada (write) | `"ACTIVO"` / `"SUSPENDIDO"` | ✅ Sí | Define el estado administrativo del servicio |
| `presence_input` | Entrada (write) | `"ENABLED"` / `"DISABLED"` | ❌ No (default: ENABLED) | Define la presencia física de la ONU |

### Campos de Salida (al consultar)

| Campo | Tipo | Valores | Significado |
|-------|------|---------|-------------|
| `presence` | Salida (read) | `"ENABLED"` / `"DISABLED"` | Presencia física detectada por SNMP |
| `estado` | Salida (read) | `"ACTIVO"` / `"SUSPENDIDO"` | Estado administrativo del servicio |
| `active` | Salida (read) | `true` / `false` | Calculado automáticamente desde `presence` (interno, no aparece en API) |

### Sincronización Automática

- `presence_input=ENABLED` → `active=true` (interno) y `presence=ENABLED` (salida)
- `presence_input=DISABLED` → `active=false` (interno) y `presence=DISABLED` (salida)
- `estado_input` es independiente de `presence`/`active`

---

## 📝 Notas Importantes

1. **Autenticación:** Todos los endpoints (excepto `/api/health/`) requieren autenticación con Token o API Key.

2. **Paginación:** Los resultados están paginados por defecto (50 resultados por página). Usa `?page_size=100` para cambiar el tamaño de página.

3. **Búsqueda:** El parámetro `search` busca en múltiples campos: `serial_number`, `mac_address`, `subscriber_id`, y `snmp_description`.

4. **Campos Internos:** El campo `active` es interno y NO aparece en la API REST. Se sincroniza automáticamente con `presence`.

5. **Creación de ONU:** Al crear una ONU, se crean automáticamente 3 registros en las tablas: `OnuIndexMap`, `OnuStatus`, y `OnuInventory`.

6. **Soft Delete vs Hard Delete:**
   - **Soft Delete** (`/desactivar/`): Mantiene los datos, solo cambia estados
   - **Hard Delete** (`/eliminar-permanente/`): Elimina permanentemente los registros (irreversible)

---

## 🔗 Endpoints Adicionales

### Obtener Detalles de una ONU Específica

```bash
GET https://10.80.80.229/api/onus/12345/
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/12345/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### Actualizar ONU Parcialmente

```bash
PATCH https://10.80.80.229/api/onus/12345/
```

**Ejemplo con curl:**

```bash
curl -X PATCH "https://10.80.80.229/api/onus/12345/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -H "Content-Type: application/json" \
  -d '{"plan_onu": "200MB"}' \
  -k
```

### Activar Estado a ACTIVO

```bash
POST https://10.80.80.229/api/onus/12345/activar-estado/
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/12345/activar-estado/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### Suspender Estado a SUSPENDIDO

```bash
POST https://10.80.80.229/api/onus/12345/suspender-estado/
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/12345/suspender-estado/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### Activar Presence (ENABLED)

```bash
POST https://10.80.80.229/api/onus/12345/activar-presence/
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/12345/activar-presence/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### Desactivar Presence (DISABLED)

```bash
POST https://10.80.80.229/api/onus/12345/desactivar-presence/
```

**Ejemplo con curl:**

```bash
curl -X POST "https://10.80.80.229/api/onus/12345/desactivar-presence/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## 📖 Documentación Completa

Para ver todos los endpoints disponibles y probarlos interactivamente:
- **Swagger UI:** `https://10.80.80.229/api/docs/`
- **ReDoc:** `https://10.80.80.229/api/redoc/`

**⚠️ Nota:** Si usas un navegador, necesitarás aceptar la excepción de seguridad del certificado autofirmado.

