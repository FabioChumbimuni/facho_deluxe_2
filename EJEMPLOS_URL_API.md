# 📡 Ejemplos de URLs para Solicitar Datos - API REST

## 🔐 Información de Autenticación

**Usuario:** `fiberops`  
**API Key:** `444b5fd944b13b58fa4141deaab93ede45fdf733`  
**URL Base:** `https://10.80.80.229/api`

**Formato de autenticación:**
- **Header:** `x-api-key`
- **Valor:** Solo el token (sin la palabra "Token")

**Ejemplo:**
```bash
x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733
```

---

## 📋 Ejemplos de Solicitudes

### 1. Obtener Lista de OLTs

```bash
curl -X GET "https://10.80.80.229/api/olts/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 2. Obtener Detalles de una OLT Específica

```bash
curl -X GET "https://10.80.80.229/api/olts/1/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 3. Obtener Lista de ONUs

```bash
curl -X GET "https://10.80.80.229/api/onus/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 4. Obtener ONUs de una OLT Específica

```bash
curl -X GET "https://10.80.80.229/api/onus/?olt=1" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 5. Buscar ONUs por DNI/Descripción SNMP

**URL directa para buscar la ONU con descripción 74150572:**

```
https://10.80.80.229/api/onus/?search=74150572
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/?search=74150572" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Desde el navegador (con autenticación):**
Debes agregar el header `x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733`

**Nota:** El parámetro `search` busca en los campos: `serial_number`, `mac_address`, `subscriber_id`, y `snmp_description`

### 6. Buscar ONUs con presence ENABLED

**URL directa para ONUs con presence ENABLED:**

```
https://10.80.80.229/api/onus/?onu_index__status__presence=ENABLED
```

**Combinar búsqueda y filtro de presence:**

```
https://10.80.80.229/api/onus/?search=74150572&onu_index__status__presence=ENABLED
```

**Ejemplo con curl:**

```bash
curl -X GET "https://10.80.80.229/api/onus/?search=74150572&onu_index__status__presence=ENABLED" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Filtrar solo por presence (sin búsqueda):**

```bash
curl -X GET "https://10.80.80.229/api/onus/?onu_index__status__presence=ENABLED" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

**Nota:** 
- `presence=ENABLED` significa que la ONU está físicamente conectada
- `presence=DISABLED` significa que la ONU está físicamente desconectada
- Para filtrar por DISABLED, usa: `?onu_index__status__presence=DISABLED`

### 7. Filtrar ONUs Activas (active=true)

```bash
curl -X GET "https://10.80.80.229/api/onus/?active=true" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 7. Obtener Detalles de una ONU Específica

```bash
curl -X GET "https://10.80.80.229/api/onus/12345/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 8. Obtener Estadísticas del Dashboard

```bash
curl -X GET "https://10.80.80.229/api/dashboard/stats/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 9. Obtener Lista de Trabajos SNMP

```bash
curl -X GET "https://10.80.80.229/api/snmp-jobs/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 10. Obtener Ejecuciones Recientes

```bash
curl -X GET "https://10.80.80.229/api/executions/recent/?limit=10" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 11. Obtener Lista de ODFs

```bash
curl -X GET "https://10.80.80.229/api/odfs/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### 12. Obtener Hilos de ODF

```bash
curl -X GET "https://10.80.80.229/api/odf-hilos/?odf=1" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## ✍️ Ejemplos de Escritura (POST/PUT/PATCH)

### 13. Crear una OLT

```bash
curl -X POST "https://10.80.80.229/api/olts/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -H "Content-Type: application/json" \
  -d '{
    "abreviatura": "OLT-TEST",
    "ip_address": "192.168.1.100",
    "marca_id": 1,
    "modelo_id": 1
  }' \
  -k
```

### 14. Crear una ONU

```bash
curl -X POST "https://10.80.80.229/api/onus/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 1,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 10,
    "serial_number": "HWTC12345678",
    "snmp_description": "74150572",
    "estado_input": "ACTIVO",
    "presence_input": "ENABLED"
  }' \
  -k
```

### 15. Actualizar una ONU

```bash
curl -X PATCH "https://10.80.80.229/api/onus/12345/" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -H "Content-Type: application/json" \
  -d '{
    "snmp_description": "Nuevo DNI",
    "estado_input": "SUSPENDIDO"
  }' \
  -k
```

---

## 🔍 Filtros y Búsquedas Avanzadas

### Filtrar ONUs por Slot y Puerto

```bash
curl -X GET "https://10.80.80.229/api/onus/?olt=1&onu_index__slot=5&onu_index__port=3" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### Paginación

```bash
curl -X GET "https://10.80.80.229/api/onus/?page=2&page_size=50" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

### Ordenar por Fecha

```bash
curl -X GET "https://10.80.80.229/api/onus/?ordering=-created_at" \
  -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
  -k
```

---

## 📚 Documentación Completa

Para ver todos los endpoints disponibles, visita:
- **Swagger UI:** https://10.80.80.229/api/docs/
- **ReDoc:** https://10.80.80.229/api/redoc/

---

## ⚠️ Nota sobre el Certificado SSL

Como estamos usando un certificado autofirmado, necesitas:
- En `curl`: usar la opción `-k` o `--insecure`
- En navegador: aceptar la excepción de seguridad

---

## 🔑 Renovar Token (si es necesario)

Si necesitas regenerar el token:

```bash
curl -X POST "https://10.80.80.229/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{"username": "fiberops", "password": "fiberops2025"}' \
  -k
```

