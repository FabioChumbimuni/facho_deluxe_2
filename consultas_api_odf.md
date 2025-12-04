# 📡 Consultas API - ODF y Troncales Facho Deluxe v2

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

## 1. Información Avanzada de ODF por onudesc

**GET** `/api/odf/info-avanzada/`

Obtiene información del cliente por onudesc, incluyendo:
- Información del cliente
- Troncal (nombre_troncal, numero_odf)
- Hilo (port_troncal, hilo_numero, vlan)

**Request:**

```bash
GET https://10.80.80.229/api/odf/info-avanzada/?onudesc=74150572
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Parámetros:**
- `onudesc` (obligatorio): onudesc del cliente (búsqueda exacta por `snmp_description`)
- `olt` (opcional): ID de la OLT para filtrar

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/odf/info-avanzada/?onudesc=74150572" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Ejemplo con filtro por OLT:**

```bash
curl -X GET "https://10.80.80.229/api/odf/info-avanzada/?onudesc=74150572&olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "success": true,
  "cliente": {
    "id": 12345,
    "onudesc": "74150572",
    "olt_id": 21,
    "olt_nombre": "OLT-PRINCIPAL",
    "slot": 5,
    "port": 3,
    "logical": 10,
    "snmpindexonu": "4194312192.2",
    "presence": "ENABLED",
    "estado": "ACTIVO",
    "active": true
  },
  "troncal": {
    "nombre_troncal": "CHOSICA-SANTA EULALIA 2 T-24",
    "numero_odf": 3
  },
  "hilo": {
    "slot": 5,
    "port": 3,
    "hilo_numero": 12,
    "vlan": 100
  }
}
```

**Response (404 Not Found - Cliente no encontrado):**

```json
{
  "success": false,
  "message": "No se encontró cliente con onudesc: 74150572 (solo se muestran clientes con presence ENABLED)"
}
```

**Response (400 Bad Request - onudesc faltante):**

```json
{
  "success": false,
  "message": "El parámetro \"onudesc\" es obligatorio"
}
```

**Response (200 OK - Cliente sin ODF asignado):**

```json
{
  "success": true,
  "cliente": {
    "id": 12345,
    "onudesc": "74150572",
    "olt_id": 21,
    "olt_nombre": "OLT-PRINCIPAL",
    "slot": 5,
    "port": 3,
    "logical": 10,
    "snmpindexonu": "4194312192.2",
    "presence": "ENABLED",
    "estado": "ACTIVO",
    "active": true
  },
  "troncal": {
    "nombre_troncal": null,
    "numero_odf": null,
    "mensaje": "Cliente no tiene troncal/ODF asignado"
  },
  "hilo": {
    "slot": null,
    "port": null,
    "hilo_numero": null,
    "vlan": null,
    "mensaje": "Cliente no tiene hilo asignado"
  }
}
```

**Notas:**
- La búsqueda por onudesc es **exacta** (no parcial), por lo que solo encontrará el cliente con `snmp_description` exactamente igual al onudesc proporcionado.
- **Solo se muestran clientes con presence ENABLED** por defecto. Para buscar clientes DISABLED, usa el endpoint `/api/onus/disable/`.
- Si el cliente no tiene ODF asignado, los campos `troncal` y `hilo` mostrarán valores `null` y un mensaje indicando que no tiene troncal/hilo asignado.

---

## 2. Consultar ODFs

**GET** `/api/odfs/`

Obtiene la lista de ODFs disponibles.

**Request:**

```bash
GET https://10.80.80.229/api/odfs/
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/odfs/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Filtrar por OLT:**

```bash
curl -X GET "https://10.80.80.229/api/odfs/?olt=21" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "count": 10,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 15,
      "numero_odf": 3,
      "nombre_troncal": "CHOSICA-SANTA EULALIA 2 T-24",
      "descripcion": "ODF principal zona norte",
      "olt": 21,
      "total_hilos": 12,
      "hilos_ocupados": 8,
      "hilos_disponibles": 4
    }
  ]
}
```

---

## 3. Consultar Hilos de ODF

**GET** `/api/odf-hilos/`

Obtiene la lista de hilos de ODF.

**Request:**

```bash
GET https://10.80.80.229/api/odf-hilos/?odf=15
```

**Headers:**

```
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/odf-hilos/?odf=15" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Response (200 OK):**

```json
{
  "count": 12,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 45,
      "odf": 15,
      "odf_nombre": "CHOSICA-SANTA EULALIA 2 T-24",
      "slot": 5,
      "port": 3,
      "hilo_numero": 12,
      "vlan": 100,
      "estado": "enabled",
      "operativo_noc": true
    }
  ]
}
```

---

## 📚 Referencia Rápida

### Endpoints de ODF

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/odf/info-avanzada/` | Información avanzada por onudesc (troncal, ODF, clientes) |
| `GET` | `/api/odfs/` | Listar ODFs |
| `GET` | `/api/odfs/{id}/` | Detalles de un ODF específico |
| `GET` | `/api/odf-hilos/` | Listar hilos de ODF |
| `GET` | `/api/odf-hilos/?odf=15` | Filtrar hilos por ODF |

### Parámetros de Búsqueda

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `onudesc` | onudesc del cliente (búsqueda exacta) | `?onudesc=74150572` |
| `olt` | Filtrar por OLT | `?olt=21` |
| `odf` | Filtrar hilos por ODF | `?odf=15` |

---

## 📖 Documentación Completa

Para ver todos los endpoints disponibles y probarlos interactivamente:
- **Swagger UI:** `https://10.80.80.229/api/docs/`
- **ReDoc:** `https://10.80.80.229/api/redoc/`

**⚠️ Nota:** Si usas un navegador, necesitarás aceptar la excepción de seguridad del certificado autofirmado.

