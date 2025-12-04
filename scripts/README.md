# 📁 Scripts de Facho Deluxe v2

Este directorio contiene todos los scripts organizados por función.

## 📂 Estructura de Carpetas

### 🚀 `deployment/` - Scripts de Despliegue
Scripts para desplegar y configurar el sistema completo.

- **`deploy.sh`** - Script principal de despliegue completo
- **`deploy_backend.sh`** - Despliegue inteligente del backend (solo instala lo necesario)

### ⚙️ `configuration/` - Scripts de Configuración
Scripts para configurar y ajustar parámetros del sistema.

- **`configurar_backend.sh`** - Configura el backend (BD, API, sistema)
- **`configurar_https.sh`** - Configura HTTPS/SSL
- **`crear_config_etc.sh`** - Crea archivos de configuración en `/etc/`
- **`ajustar_permisos_config.sh`** - Ajusta permisos de archivos de configuración
- **`cambiar_ip.sh`** - Cambia la IP del sistema en todos los servicios

### 🔧 `maintenance/` - Scripts de Mantenimiento
Scripts para mantenimiento y corrección de problemas.

- **`cambiar_usuario_supervisor.sh`** - Cambia usuario y contraseña de Supervisor
- **`fix_supervisor_workflow.sh`** - Corrige problemas con workflows de Supervisor

### 🔒 `ssl/` - Scripts de Certificados SSL
Scripts para gestión de certificados SSL/HTTPS.

- **`renovar_certificado.sh`** - Renueva certificados SSL autofirmados
- **`verificar_certificado.sh`** - Verifica el estado de los certificados SSL

### 👥 `users/` - Scripts de Gestión de Usuarios
Scripts para crear y gestionar usuarios.

- **`crear_usuario_api.sh`** - Crea usuarios con token de API

### 🖥️ `system/` - Scripts del Sistema
Scripts para gestionar servicios del sistema (Celery, Gunicorn, etc.).

- **`start_celery_workers.sh`** - Inicia workers de Celery
- **`start_celery_get_workers.sh`** - Inicia workers específicos de Celery GET
- **`diagnostico_gunicorn.sh`** - Diagnostica problemas con Gunicorn
- **`fix_gunicorn_conflict.sh`** - Corrige conflictos de Gunicorn

### 🎨 `frontend/` - Scripts del Frontend
Scripts para gestionar el frontend React.

- **`start_frontend_prod.sh`** - Inicia el frontend en producción (nginx)
- **`start_frontend_dev.sh`** - Inicia el frontend en modo desarrollo (Vite)
- **`update_frontend.sh`** - Actualiza el frontend (reconstruye y actualiza nginx)

## 📝 Uso General

Todos los scripts deben ejecutarse con `sudo`:

```bash
# Ejemplo: Cambiar IP del sistema
sudo ./scripts/configuration/cambiar_ip.sh

# Ejemplo: Crear usuario de API
sudo ./scripts/users/crear_usuario_api.sh

# Ejemplo: Renovar certificado SSL
sudo ./scripts/ssl/renovar_certificado.sh
```

## 🔍 Buscar Scripts

Para encontrar un script específico:

```bash
# Buscar por nombre
find scripts -name "*script_name*"

# Listar todos los scripts
find scripts -name "*.sh" -type f
```

## 📌 Notas

- Todos los scripts tienen permisos de ejecución (`chmod +x`)
- Los scripts que modifican configuración del sistema requieren `sudo`
- Se recomienda revisar el contenido de los scripts antes de ejecutarlos
- Los scripts de despliegue crean backups automáticos cuando es necesario

