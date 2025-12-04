# Scripts de Frontend - Facho Deluxe v2

Scripts para gestionar el frontend de Facho Deluxe v2.

## 📋 Scripts Disponibles

### 🚀 `start_frontend_prod.sh` - Iniciar en Producción

Inicia el frontend en modo producción usando nginx con HTTPS.

**Uso:**
```bash
cd /opt/facho_deluxe_2
sudo ./scripts/frontend/start_frontend_prod.sh
```

**Qué hace:**
- Verifica que el frontend esté construido
- Genera configuración desde `/etc/facho-frontend/frontend.conf`
- Configura nginx si es necesario
- Recarga nginx para servir el frontend

**Requisitos:**
- Frontend construido (`dist/` debe existir)
- Archivo `/etc/facho-frontend/frontend.conf` configurado
- Nginx instalado y configurado

---

### 🛑 `stop_frontend_prod.sh` - Detener Frontend en Producción

Deshabilita el frontend en nginx (no detiene nginx, solo deshabilita el sitio).

**Uso:**
```bash
cd /opt/facho_deluxe_2
sudo ./scripts/frontend/stop_frontend_prod.sh
```

**Qué hace:**
- Deshabilita el sitio `facho-frontend` en nginx
- Recarga nginx
- El frontend deja de estar disponible en producción

**Cuándo usar:**
- Cuando quieres cambiar a modo desarrollo
- Cuando quieres detener el frontend temporalmente

---

### 🛠️ `start_frontend_dev.sh` - Iniciar en Modo Desarrollo

Inicia el frontend en modo desarrollo usando Vite dev server.

**Uso:**
```bash
cd /opt/facho_deluxe_2
./scripts/frontend/start_frontend_dev.sh
```

**Qué hace:**
- Verifica dependencias de Node.js
- Instala dependencias si es necesario
- Inicia el servidor de desarrollo en `http://localhost:3000`
- Habilita Hot Module Replacement (HMR) para cambios en tiempo real

**Requisitos:**
- Node.js y npm instalados
- Dependencias del proyecto instaladas (`npm install`)

**Nota:** Este modo es solo para desarrollo. Los cambios se reflejan automáticamente sin necesidad de reconstruir.

---

### 🔄 `update_frontend.sh` - Actualizar Frontend

Actualiza el frontend: regenera configuración, reconstruye y actualiza nginx.

**Uso:**
```bash
cd /opt/facho_deluxe_2
sudo ./scripts/frontend/update_frontend.sh
```

**Qué hace:**
1. Genera `public/config.json` desde `/etc/facho-frontend/frontend.conf`
2. Genera `facho-frontend.conf` para nginx
3. Construye el frontend para producción (`npm run build`)
4. Actualiza la configuración de nginx
5. Recarga nginx

**Cuándo usar:**
- Después de hacer cambios en el código del frontend
- Después de cambiar `/etc/facho-frontend/frontend.conf`
- Cuando necesites actualizar el frontend en producción

**Requisitos:**
- Node.js y npm instalados
- Archivo `/etc/facho-frontend/frontend.conf` (opcional, usa valores por defecto si no existe)
- Permisos sudo para actualizar nginx

---

## 📝 Flujo de Trabajo Recomendado

### Desarrollo
```bash
# 1. Iniciar en modo desarrollo
cd /opt/facho_deluxe_2
./scripts/frontend/start_frontend_dev.sh

# 2. Editar código en /opt/facho-frontend/src/
# 3. Los cambios se reflejan automáticamente
```

### Producción
```bash
# 1. Hacer cambios en el código
# 2. Actualizar el frontend
cd /opt/facho_deluxe_2
sudo ./scripts/frontend/update_frontend.sh

# 3. El frontend se actualiza automáticamente
```

### Primera Configuración
```bash
# 1. Configurar el frontend
cd /opt/facho-frontend
./scripts/setup-config.sh
sudo nano /etc/facho-frontend/frontend.conf

# 2. Iniciar en producción
cd /opt/facho_deluxe_2
sudo ./scripts/frontend/start_frontend_prod.sh
```

---

## 🔧 Solución de Problemas

### Error: "No se encontró el directorio /opt/facho-frontend"
- Verifica que el frontend esté instalado en `/opt/facho-frontend`
- Si está en otra ubicación, ajusta `FRONTEND_DIR` en los scripts

### Error: "Node.js no está instalado"
```bash
sudo apt update
sudo apt install nodejs npm
```

### Error: "No se encontró /etc/facho-frontend/frontend.conf"
```bash
cd /opt/facho-frontend
./scripts/setup-config.sh
sudo nano /etc/facho-frontend/frontend.conf
```

### Error: "La configuración de nginx tiene errores"
```bash
sudo nginx -t  # Ver errores específicos
# Revisa /etc/nginx/sites-available/facho-frontend
```

### El frontend no se actualiza después de cambios
1. Verifica que ejecutaste `update_frontend.sh`
2. Presiona Ctrl+Shift+R en el navegador (forzar recarga sin caché)
3. Verifica los logs de nginx: `sudo tail -f /var/log/nginx/facho-frontend-error.log`

---

## 📌 Notas

- Los scripts de producción requieren `sudo` para modificar nginx
- El modo desarrollo no requiere `sudo` (solo usa Node.js)
- El frontend en producción son archivos estáticos servidos por nginx
- No hay servicio de Node.js corriendo en producción (solo en desarrollo)

