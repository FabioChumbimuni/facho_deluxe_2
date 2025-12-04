# Cambiar entre Producción y Desarrollo

Guía para cambiar entre modo producción y desarrollo del frontend.

## 🔄 Procedimiento Completo

### 1️⃣ Detener Producción e Iniciar Desarrollo

**⚠️ IMPORTANTE: Siempre ejecuta estos comandos desde `/opt/facho_deluxe_2`**

```bash
# 1. Cambiar al directorio del proyecto
cd /opt/facho_deluxe_2

# 2. Detener el frontend en producción (deshabilita nginx)
sudo ./scripts/frontend/stop_frontend_prod.sh

# 3. Iniciar el frontend en desarrollo
./scripts/frontend/start_frontend_dev.sh
```

**O usando la ruta completa (desde cualquier directorio):**
```bash
# Detener producción
sudo /opt/facho_deluxe_2/scripts/frontend/stop_frontend_prod.sh

# Iniciar desarrollo
/opt/facho_deluxe_2/scripts/frontend/start_frontend_dev.sh
```

**Resultado:**
- ✅ Frontend disponible en: `http://localhost:3000`
- ✅ Logs habilitados (verás todos los console.log)
- ✅ Hot Module Replacement (cambios en tiempo real)
- ✅ No requiere sudo

**Para detener el desarrollo:**
- Presiona `Ctrl+C` en la terminal donde corre `start_frontend_dev.sh`

---

### 2️⃣ Detener Desarrollo e Iniciar Producción

**⚠️ IMPORTANTE: Siempre ejecuta estos comandos desde `/opt/facho_deluxe_2`**

```bash
# 1. Detener desarrollo (si está corriendo)
# Presiona Ctrl+C en la terminal donde corre start_frontend_dev.sh

# 2. Cambiar al directorio del proyecto
cd /opt/facho_deluxe_2

# 3. Construir el frontend para producción
sudo ./scripts/frontend/update_frontend.sh

# 4. Iniciar el frontend en producción
sudo ./scripts/frontend/start_frontend_prod.sh
```

**O usando la ruta completa (desde cualquier directorio):**
```bash
# Actualizar producción
sudo /opt/facho_deluxe_2/scripts/frontend/update_frontend.sh

# Iniciar producción
sudo /opt/facho_deluxe_2/scripts/frontend/start_frontend_prod.sh
```

**Resultado:**
- ✅ Frontend disponible en: `https://10.80.80.229:8443` (o según tu configuración)
- ✅ Logs deshabilitados (no verás console.log en la consola)
- ✅ Optimizado y minificado
- ✅ Servido por nginx con HTTPS

---

## 📋 Resumen de Comandos

**⚠️ IMPORTANTE: Todos los comandos deben ejecutarse desde `/opt/facho_deluxe_2`**

### Desarrollo
```bash
# Cambiar al directorio del proyecto
cd /opt/facho_deluxe_2

# Iniciar desarrollo
./scripts/frontend/start_frontend_dev.sh

# Detener desarrollo
# Presiona Ctrl+C
```

### Producción
```bash
# Cambiar al directorio del proyecto
cd /opt/facho_deluxe_2

# Iniciar producción
sudo ./scripts/frontend/start_frontend_prod.sh

# Detener producción
sudo ./scripts/frontend/stop_frontend_prod.sh

# Actualizar producción (después de cambios)
sudo ./scripts/frontend/update_frontend.sh
```

**Alternativa: Usar rutas completas (desde cualquier directorio)**
```bash
# Desarrollo
/opt/facho_deluxe_2/scripts/frontend/start_frontend_dev.sh

# Producción
sudo /opt/facho_deluxe_2/scripts/frontend/start_frontend_prod.sh
sudo /opt/facho_deluxe_2/scripts/frontend/stop_frontend_prod.sh
sudo /opt/facho_deluxe_2/scripts/frontend/update_frontend.sh
```

---

## 🔍 Verificar Estado Actual

### ¿Está corriendo en producción?
```bash
# Verificar si nginx tiene el sitio habilitado
ls -la /etc/nginx/sites-enabled/facho-frontend

# Si existe el enlace → está en producción
# Si no existe → no está en producción
```

### ¿Está corriendo en desarrollo?
```bash
# Verificar si hay un proceso de Node.js corriendo
ps aux | grep "vite\|node.*3000" | grep -v grep

# Si hay procesos → está en desarrollo
# Si no hay procesos → no está en desarrollo
```

---

## ⚠️ Notas Importantes

1. **No puedes tener ambos corriendo al mismo tiempo** en el mismo puerto
   - Producción usa nginx en puerto 8443
   - Desarrollo usa Vite en puerto 3000
   - Son puertos diferentes, así que técnicamente podrías tener ambos, pero no es recomendado

2. **Desarrollo es solo para editar código**
   - Los cambios se reflejan automáticamente
   - No requiere reconstruir
   - Útil para debugging

3. **Producción es para uso real**
   - Código optimizado y minificado
   - Sin logs en consola
   - Servido por nginx con HTTPS

4. **Después de editar código en desarrollo:**
   - Debes construir para producción: `update_frontend.sh`
   - Luego iniciar producción: `start_frontend_prod.sh`

---

## 🎯 Flujo de Trabajo Recomendado

### Para Editar Código:
```bash
# 1. Detener producción
sudo ./scripts/frontend/stop_frontend_prod.sh

# 2. Iniciar desarrollo
./scripts/frontend/start_frontend_dev.sh

# 3. Editar código en /opt/facho-frontend/src/
# 4. Los cambios se reflejan automáticamente

# 5. Cuando termines, detener desarrollo (Ctrl+C)
# 6. Actualizar y volver a producción
sudo ./scripts/frontend/update_frontend.sh
sudo ./scripts/frontend/start_frontend_prod.sh
```

### Para Solo Ver Producción:
```bash
# Solo iniciar producción (si ya está construido)
sudo ./scripts/frontend/start_frontend_prod.sh
```

