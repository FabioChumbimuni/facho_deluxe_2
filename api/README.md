# API REST de Facho Deluxe v2

API REST completa para la gestión de SNMP, ONUs, ODF y Zabbix.

## 📋 Índice

- [Características](#características)
- [Autenticación](#autenticación)
- [Endpoints Disponibles](#endpoints-disponibles)
- [Documentación Interactiva](#documentación-interactiva)
- [Ejemplos de Uso](#ejemplos-de-uso)

## 🎯 Características

- ✅ Autenticación con Token
- ✅ Paginación automática
- ✅ Filtros y búsquedas
- ✅ Documentación interactiva (Swagger y ReDoc)
- ✅ CORS habilitado
- ✅ Rate limiting (throttling)
- ✅ Permisos granulares
- ✅ Serialización optimizada

## 🔐 Autenticación

La API utiliza autenticación basada en tokens. Para obtener un token:

### Obtener Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "tu_usuario", "password": "tu_contraseña"}'
```

Respuesta:
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
}
```

### Usar el Token

Incluye el token en el header `Authorization` de todas tus peticiones:

```bash
curl -X GET http://localhost:8000/api/v1/olts/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

## 📡 Endpoints Disponibles

### Base URL
```
http://localhost:8000/api/v1/
```

### Autenticación
- `POST /auth/login/` - Obtener token de autenticación

### Hosts y Equipos
- `GET /olts/` - Listar OLTs
- `GET /olts/{id}/` - Obtener detalles de una OLT
- `POST /olts/` - Crear nueva OLT (requiere permisos)
- `PUT /olts/{id}/` - Actualizar OLT completa
- `PATCH /olts/{id}/` - Actualizar OLT parcialmente
- `DELETE /olts/{id}/` - Eliminar OLT
- `GET /olts/{id}/stats/` - Estadísticas de una OLT
- `POST /olts/{id}/toggle/` - Habilitar/deshabilitar OLT

### Marcas y Modelos
- `GET /brands/` - Listar marcas
- `GET /olt-models/` - Listar modelos de OLT

### Trabajos SNMP
- `GET /snmp-jobs/` - Listar trabajos SNMP
- `GET /snmp-jobs/{id}/` - Obtener detalles de un trabajo
- `POST /snmp-jobs/` - Crear nuevo trabajo
- `POST /snmp-jobs/{id}/execute/` - Ejecutar trabajo manualmente

### Ejecuciones
- `GET /executions/` - Listar ejecuciones
- `GET /executions/{id}/` - Obtener detalles de una ejecución
- `GET /executions/recent/` - Obtener ejecuciones recientes

### Discovery (ONUs)
- `GET /onus/` - Listar ONUs descubiertas
- `GET /onus/{id}/` - Obtener detalles de una ONU
- `GET /onu-states/` - Listar estados de ONUs

### OIDs y Fórmulas
- `GET /oids/` - Listar OIDs SNMP
- `GET /formulas/` - Listar fórmulas de índices

### ODF
- `GET /odfs/` - Listar ODFs
- `GET /odf-hilos/` - Listar hilos de ODF
- `GET /zabbix-ports/` - Listar datos de puertos Zabbix

### Personal
- `GET /personal/` - Listar personal
- `GET /areas/` - Listar áreas

### Estadísticas
- `GET /dashboard/stats/` - Estadísticas generales del sistema
- `GET /health/` - Estado de salud de la API

### Usuarios (solo admin)
- `GET /users/` - Listar usuarios
- `GET /users/me/` - Información del usuario actual

## 📚 Documentación Interactiva

### Swagger UI
Interfaz interactiva para explorar y probar la API:
```
http://localhost:8000/api/v1/docs/
```

### ReDoc
Documentación detallada en formato ReDoc:
```
http://localhost:8000/api/v1/redoc/
```

### Schema OpenAPI
Esquema OpenAPI 3.0 en formato JSON:
```
http://localhost:8000/api/v1/schema/
```

## 🚀 Ejemplos de Uso

### 1. Listar OLTs

```bash
curl -X GET "http://localhost:8000/api/v1/olts/" \
  -H "Authorization: Token TU_TOKEN"
```

Respuesta:
```json
{
  "count": 10,
  "next": "http://localhost:8000/api/v1/olts/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "abreviatura": "OLT-001",
      "marca_nombre": "Huawei",
      "ip_address": "192.168.1.100",
      "habilitar_olt": true,
      "estado": "Activo"
    }
  ]
}
```

### 2. Obtener Estadísticas del Dashboard

```bash
curl -X GET "http://localhost:8000/api/v1/dashboard/stats/" \
  -H "Authorization: Token TU_TOKEN"
```

Respuesta:
```json
{
  "total_olts": 15,
  "olts_activas": 12,
  "total_jobs": 25,
  "jobs_activos": 20,
  "total_ejecuciones_hoy": 150,
  "ejecuciones_exitosas_hoy": 145,
  "ejecuciones_fallidas_hoy": 5,
  "total_onus": 5000,
  "total_odfs": 50,
  "hilos_ocupados": 300,
  "hilos_disponibles": 200
}
```

### 3. Crear un Trabajo SNMP

```bash
curl -X POST "http://localhost:8000/api/v1/snmp-jobs/" \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nombre": "Discovery OLT-001",
    "descripcion": "Descubrimiento de ONUs",
    "olt": 1,
    "tipo": "discovery",
    "horario_inicio": "08:00:00",
    "horario_fin": "20:00:00",
    "intervalo_minutos": 30,
    "habilitada": true
  }'
```

### 4. Filtrar ONUs por OLT

```bash
curl -X GET "http://localhost:8000/api/v1/onus/?olt=1" \
  -H "Authorization: Token TU_TOKEN"
```

### 5. Buscar ONUs por Serial

```bash
curl -X GET "http://localhost:8000/api/v1/onus/?search=HWTC12345678" \
  -H "Authorization: Token TU_TOKEN"
```

### 6. Obtener Ejecuciones Recientes

```bash
curl -X GET "http://localhost:8000/api/v1/executions/recent/?limit=5" \
  -H "Authorization: Token TU_TOKEN"
```

### 7. Habilitar/Deshabilitar una OLT

```bash
curl -X POST "http://localhost:8000/api/v1/olts/1/toggle/" \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"habilitar": false}'
```

## 🔧 Parámetros de Consulta

### Paginación
```bash
?page=2&page_size=50
```

### Filtros
```bash
?marca=1&habilitar_olt=true
```

### Búsqueda
```bash
?search=OLT-001
```

### Ordenamiento
```bash
?ordering=-fecha_creacion
```

## 🛡️ Permisos

- **Lectura**: Cualquier usuario autenticado
- **Escritura**: Solo usuarios staff/admin
- **Eliminación**: Solo usuarios admin

## 📊 Rate Limiting

- **Usuarios anónimos**: 100 peticiones/hora
- **Usuarios autenticados**: 1000 peticiones/hora

## 🌐 CORS

CORS está habilitado para los siguientes orígenes:
- http://localhost:3000 (React/Next.js)
- http://localhost:4200 (Angular)
- http://localhost:8080 (Vue.js)

## 🐛 Códigos de Estado HTTP

- `200 OK` - Petición exitosa
- `201 Created` - Recurso creado exitosamente
- `204 No Content` - Recurso eliminado exitosamente
- `400 Bad Request` - Datos inválidos
- `401 Unauthorized` - No autenticado
- `403 Forbidden` - Sin permisos
- `404 Not Found` - Recurso no encontrado
- `429 Too Many Requests` - Límite de peticiones excedido
- `500 Internal Server Error` - Error del servidor

## 📝 Notas

1. Todos los endpoints requieren autenticación, excepto `/health/`
2. Las fechas están en formato ISO 8601: `YYYY-MM-DD HH:MM:SS`
3. Los tokens no expiran automáticamente (puedes implementar expiración si lo necesitas)
4. La documentación interactiva incluye ejemplos de todas las peticiones

## 🎓 Ejemplos con Python

### Usando requests

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000/api/v1"

# Obtener token
response = requests.post(
    f"{BASE_URL}/auth/login/",
    json={"username": "admin", "password": "password"}
)
token = response.json()["token"]

# Headers con token
headers = {"Authorization": f"Token {token}"}

# Listar OLTs
response = requests.get(f"{BASE_URL}/olts/", headers=headers)
olts = response.json()

# Crear trabajo SNMP
data = {
    "nombre": "Discovery Test",
    "descripcion": "Test",
    "olt": 1,
    "tipo": "discovery",
    "horario_inicio": "08:00:00",
    "horario_fin": "20:00:00",
    "intervalo_minutos": 30,
    "habilitada": True
}
response = requests.post(f"{BASE_URL}/snmp-jobs/", headers=headers, json=data)
```

## 🎯 Próximos Pasos

1. Visita la documentación interactiva en `/api/v1/docs/`
2. Obtén tu token de autenticación
3. Explora los endpoints disponibles
4. Lee los ejemplos específicos para tu caso de uso

¡La API está lista para usar! 🚀

