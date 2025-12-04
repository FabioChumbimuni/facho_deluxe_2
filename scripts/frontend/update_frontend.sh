#!/bin/bash
# ========================================
# Actualizar Frontend
# ========================================
# Este script actualiza el frontend:
# 1. Genera configuración desde /etc/facho-frontend/frontend.conf
# 2. Genera configuración de nginx
# 3. Construye el frontend para producción
# 4. Actualiza y recarga nginx

set -e

FRONTEND_DIR="/opt/facho-frontend"
CONFIG_FILE="/etc/facho-frontend/frontend.conf"

echo "========================================="
echo "Actualizando Frontend"
echo "========================================="

# Verificar que existe el directorio del frontend
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ Error: No se encontró el directorio $FRONTEND_DIR"
    exit 1
fi

cd "$FRONTEND_DIR"

# Verificar que existe la configuración
if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚠️  Advertencia: No se encontró $CONFIG_FILE"
    echo "   Ejecuta primero: cd $FRONTEND_DIR && ./scripts/setup-config.sh"
    echo ""
    read -p "¿Deseas continuar con valores por defecto? (s/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
fi

# Verificar que Node.js está instalado
if ! command -v node &> /dev/null; then
    echo "❌ Error: Node.js no está instalado"
    exit 1
fi

# Verificar que npm está instalado
if ! command -v npm &> /dev/null; then
    echo "❌ Error: npm no está instalado"
    exit 1
fi

# Generar configuración del frontend
echo "📝 Generando configuración del frontend..."
if ! npm run generate-config; then
    echo "❌ Error: No se pudo generar la configuración"
    exit 1
fi

# Generar configuración de nginx
echo "📝 Generando configuración de nginx..."
if ! npm run generate-nginx-config; then
    echo "❌ Error: No se pudo generar la configuración de nginx"
    exit 1
fi

# Construir el frontend
echo "🔨 Construyendo el frontend para producción..."
if ! npm run build; then
    echo "❌ Error: La construcción del frontend falló"
    exit 1
fi

if [ ! -d "dist" ]; then
    echo "❌ Error: La construcción falló. No se creó el directorio dist"
    exit 1
fi

echo "✅ Frontend construido exitosamente"

# Verificar que existe el archivo de configuración de nginx
if [ ! -f "facho-frontend.conf" ]; then
    echo "❌ Error: No se encontró facho-frontend.conf"
    exit 1
fi

# Copiar configuración de nginx
echo "📋 Actualizando configuración de nginx..."
sudo cp facho-frontend.conf /etc/nginx/sites-available/facho-frontend

# Crear enlace simbólico si no existe
if [ ! -L /etc/nginx/sites-enabled/facho-frontend ]; then
    echo "🔗 Creando enlace simbólico en nginx..."
    sudo ln -sf /etc/nginx/sites-available/facho-frontend /etc/nginx/sites-enabled/facho-frontend
fi

# Verificar configuración de nginx
echo "🔍 Verificando configuración de nginx..."
if ! sudo nginx -t; then
    echo "❌ Error: La configuración de nginx tiene errores"
    exit 1
fi

# Recargar nginx
echo "🔄 Recargando nginx..."
if ! sudo systemctl reload nginx; then
    echo "❌ Error: No se pudo recargar nginx"
    exit 1
fi

echo ""
echo "✅ Frontend actualizado exitosamente"
echo ""
echo "El frontend está disponible en:"

# Leer la configuración para mostrar la URL
if [ -f "$CONFIG_FILE" ]; then
    FRONTEND_IP=$(grep -E "^frontend_ip\s*=" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d ' ' || echo "10.80.80.229")
    FRONTEND_PORT=$(grep -E "^frontend_port\s*=" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d ' ' || echo "8443")
    PROTOCOL=$(grep -E "^protocol\s*=" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d ' ' || echo "https")
    echo "   ${PROTOCOL}://${FRONTEND_IP}:${FRONTEND_PORT}"
else
    echo "   https://10.80.80.229:8443"
fi

echo ""
echo "💡 Tip: Si no ves los cambios, presiona Ctrl+Shift+R en el navegador"

