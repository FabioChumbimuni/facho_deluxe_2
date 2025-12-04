# 🚀 Guía de Instalación de la REST API

Esta guía te ayudará a completar la instalación y configuración de la REST API en Facho Deluxe v2.

## 📋 Pre-requisitos

- ✅ Django 4.2.16 instalado
- ✅ PostgreSQL configurado
- ✅ Entorno virtual activado

## 🔧 Pasos de Instalación

### 1. Instalar Dependencias

```bash
cd /opt/facho_deluxe_2
source venv/bin/activate  # Activar entorno virtual
pip install -r requirements.txt
```

Esto instalará:
- `djangorestframework==3.15.1`
- `django-cors-headers==4.3.1`
- `django-filter==24.3`
- `drf-spectacular==0.27.2`

### 2. Ejecutar Migraciones

```bash
python manage.py migrate
```

Esto creará las tablas necesarias para:
- Tokens de autenticación (`authtoken`)
- Sesiones de usuario
- Permisos y grupos

### 3. Crear Tokens para Usuarios Existentes

```bash
# Opción 1: Desde el shell de Django
python manage.py shell

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

# Crear token para todos los usuarios
for user in User.objects.all():
    Token.objects.get_or_create(user=user)
    print(f"Token creado para {user.username}")

exit()
```

```bash
# Opción 2: Desde un script
python manage.py drf_create_token <username>
```

### 4. Verificar la Instalación

```bash
# Iniciar el servidor de desarrollo
python manage.py runserver 0.0.0.0:8000
```

Visita en tu navegador:

1. **Documentación Swagger**:
   ```
   http://localhost:8000/api/v1/docs/
   ```

2. **Documentación ReDoc**:
   ```
   http://localhost:8000/api/v1/redoc/
   ```

3. **Health Check**:
   ```
   http://localhost:8000/api/v1/health/
   ```

   Deberías ver:
   ```json
   {
     "status": "ok",
     "timestamp": "2025-10-18T...",
     "version": "2.0.0"
   }
   ```

### 5. Obtener Token de Autenticación

```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "tu_contraseña"}'
```

Respuesta:
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
}
```

### 6. Probar la API

```bash
# Listar OLTs
curl -X GET http://localhost:8000/api/v1/olts/ \
  -H "Authorization: Token TU_TOKEN_AQUI"

# Obtener estadísticas
curl -X GET http://localhost:8000/api/v1/dashboard/stats/ \
  -H "Authorization: Token TU_TOKEN_AQUI"
```

## 🔐 Configuración de CORS (Opcional)

Si vas a acceder a la API desde un frontend en otro puerto/dominio, actualiza en `core/settings.py`:

```python
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',  # Tu frontend
    'http://tu-dominio.com',
    # Agrega más orígenes según necesites
]
```

## 📊 Endpoints Disponibles

Una vez instalado, tendrás acceso a:

### Hosts y Equipos
- `GET /api/v1/olts/` - Listar OLTs
- `GET /api/v1/brands/` - Listar marcas
- `GET /api/v1/olt-models/` - Listar modelos

### Trabajos y Ejecuciones
- `GET /api/v1/snmp-jobs/` - Trabajos SNMP
- `GET /api/v1/executions/` - Ejecuciones

### Discovery
- `GET /api/v1/onus/` - ONUs descubiertas
- `GET /api/v1/onu-states/` - Estados de ONUs

### ODF
- `GET /api/v1/odfs/` - ODFs
- `GET /api/v1/odf-hilos/` - Hilos de ODF

### Configuración
- `GET /api/v1/oids/` - OIDs SNMP
- `GET /api/v1/formulas/` - Fórmulas

### Estadísticas
- `GET /api/v1/dashboard/stats/` - Estadísticas generales
- `GET /api/v1/health/` - Estado de salud

## 🎯 Siguientes Pasos

1. **Crear Usuarios API**: Crea usuarios específicos para la API con permisos limitados
2. **Configurar Rate Limiting**: Ajusta los límites según tu carga
3. **Habilitar HTTPS**: En producción, usa siempre HTTPS
4. **Monitoreo**: Configura logging para las peticiones de API
5. **Caché**: Implementa caché para endpoints frecuentes

## 🛡️ Seguridad en Producción

### 1. Actualizar Settings

En `core/settings.py`:

```python
# Desactivar debug
DEBUG = False

# HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# CORS estricto
CORS_ALLOWED_ORIGINS = [
    'https://tu-dominio.com',
]
```

### 2. Proteger Tokens

- No compartas los tokens
- Rota los tokens periódicamente
- Usa HTTPS siempre en producción

### 3. Rate Limiting

Ajusta según tu necesidad en `core/settings.py`:

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'anon': '50/hour',    # Usuarios anónimos
        'user': '500/hour',   # Usuarios autenticados
    },
}
```

## 🐛 Solución de Problemas

### Error: "No module named 'rest_framework'"
```bash
pip install djangorestframework==3.15.1
```

### Error: "No module named 'drf_spectacular'"
```bash
pip install drf-spectacular==0.27.2
```

### Error: "Table 'authtoken_token' doesn't exist"
```bash
python manage.py migrate
```

### Error 401: Unauthorized
- Verifica que estás enviando el token en el header
- El formato debe ser: `Authorization: Token TU_TOKEN`
- Asegúrate de que el token existe para tu usuario

### Error 403: Forbidden
- Verifica que tu usuario tiene los permisos necesarios
- Los endpoints de escritura requieren `is_staff=True`

## 📝 Comandos Útiles

```bash
# Crear token para un usuario
python manage.py drf_create_token username

# Listar todos los tokens
python manage.py shell
from rest_framework.authtoken.models import Token
for token in Token.objects.all():
    print(f"{token.user.username}: {token.key}")

# Regenerar token
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User
user = User.objects.get(username='admin')
Token.objects.filter(user=user).delete()
Token.objects.create(user=user)
```

## 📚 Documentación Adicional

- **Django REST Framework**: https://www.django-rest-framework.org/
- **drf-spectacular**: https://drf-spectacular.readthedocs.io/
- **Django CORS Headers**: https://github.com/adamchainz/django-cors-headers

## ✅ Checklist de Instalación

- [ ] Dependencias instaladas
- [ ] Migraciones ejecutadas
- [ ] Tokens creados para usuarios
- [ ] Servidor funcionando
- [ ] Health check OK
- [ ] Documentación Swagger accesible
- [ ] Login funcionando
- [ ] Endpoints respondiendo
- [ ] CORS configurado (si aplica)
- [ ] Permisos verificados

¡Tu API REST está lista para usar! 🎉

