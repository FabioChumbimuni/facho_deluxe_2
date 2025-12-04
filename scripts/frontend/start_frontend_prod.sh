#!/bin/bash
# ========================================
# Iniciar Frontend en Producción
# ========================================
# Este script inicia el frontend en modo producción
# El frontend se sirve a través de nginx con HTTPS

set -e

FRONTEND_DIR="/opt/facho-frontend"
CONFIG_FILE="/etc/facho-frontend/frontend.conf"

echo "========================================="
echo "Iniciando Frontend en Producción"
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
    exit 1
fi

# Verificar que el frontend está construido
if [ ! -d "dist" ]; then
    echo "⚠️  El frontend no está construido. Construyendo..."
    npm run generate-config
    npm run generate-nginx-config
    npm run build
fi

# Verificar que nginx está configurado
if [ ! -f "/etc/nginx/sites-available/facho-frontend" ]; then
    echo "⚠️  Nginx no está configurado. Configurando..."
    npm run generate-nginx-config
    sudo cp facho-frontend.conf /etc/nginx/sites-available/facho-frontend
    sudo ln -sf /etc/nginx/sites-available/facho-frontend /etc/nginx/sites-enabled/facho-frontend
fi

# Verificar configuración de nginx
echo "Verificando configuración de nginx..."
if ! sudo nginx -t; then
    echo "❌ Error: La configuración de nginx tiene errores"
    exit 1
fi

# Recargar nginx
echo "Recargando nginx..."
sudo systemctl reload nginx

if [ $? -eq 0 ]; then
    echo "✅ Frontend iniciado en producción"
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
    echo "Estado de nginx:"
    sudo systemctl status nginx --no-pager -l | head -5
else
    echo "❌ Error: No se pudo recargar nginx"
    exit 1
fi

