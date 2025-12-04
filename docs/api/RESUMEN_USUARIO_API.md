# 🔐 Resumen: Usuario API - fiberops

## ✅ Usuario Creado

**Usuario:** `fiberops`  
**Email:** `fiberops@facho.com`  
**Contraseña:** `fiberops2025`  
**Token:** `444b5fd944b13b58fa4141deaab93ede45fdf733`  
**Permisos:** Lectura y Escritura (is_staff=True)

---

## 🌐 URLs Base

**HTTPS:** `https://10.80.80.229`  
**API:** `https://10.80.80.229/api/v1`

---

## 📡 Ejemplos Rápidos de Solicitudes

### Variables para usar en tus scripts:

```bash
export API_URL="https://10.80.80.229/api/v1"
export TOKEN="444b5fd944b13b58fa4141deaab93ede45fdf733"
```

### 1. Listar OLTs

```bash
curl -k -X GET "${API_URL}/olts/" \
  -H "Authorization: Token ${TOKEN}"
```

### 2. Listar ONUs

```bash
curl -k -X GET "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}"
```

### 3. Buscar ONU por DNI

```bash
curl -k -X GET "${API_URL}/onus/?search=74150572" \
  -H "Authorization: Token ${TOKEN}"
```

### 4. Obtener ONUs de una OLT específica

```bash
curl -k -X GET "${API_URL}/onus/?olt=21" \
  -H "Authorization: Token ${TOKEN}"
```

### 5. Filtrar ONUs activas

```bash
curl -k -X GET "${API_URL}/onus/?active=true" \
  -H "Authorization: Token ${TOKEN}"
```

### 6. Crear una ONU

```bash
curl -k -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 3,
    "logical_input": 10,
    "serial_number": "HWTC12345678",
    "snmp_description": "74150572",
    "estado_input": "ACTIVO",
    "presence_input": "ENABLED"
  }'
```

### 7. Actualizar una ONU

```bash
curl -k -X PATCH "${API_URL}/onus/12345/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "snmp_description": "Nuevo DNI",
    "estado_input": "SUSPENDIDO"
  }'
```

### 8. Estadísticas del Dashboard

```bash
curl -k -X GET "${API_URL}/dashboard/stats/" \
  -H "Authorization: Token ${TOKEN}"
```

---

## 📚 Ver Documentación Completa

- **Swagger UI:** https://10.80.80.229/api/v1/docs/
- **ReDoc:** https://10.80.80.229/api/v1/redoc/

---

## ⚠️ Nota sobre Estilos en /api/v1

La ruta `/api/v1` devuelve JSON puro, no HTML. Por eso no verás estilos.  
Para ver la documentación interactiva con estilos, usa `/api/v1/docs/` (Swagger).

