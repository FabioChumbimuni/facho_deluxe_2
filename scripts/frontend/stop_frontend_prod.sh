#!/bin/bash
# ========================================
# Detener Frontend en Producción
# ========================================
# Este script deshabilita el frontend en nginx
# (no detiene nginx, solo deshabilita el sitio del frontend)

set -e

echo "========================================="
echo "Deteniendo Frontend en Producción"
echo "========================================="

# Verificar si el sitio está habilitado
if [ -L /etc/nginx/sites-enabled/facho-frontend ]; then
    echo "Deshabilitando sitio en nginx..."
    sudo rm /etc/nginx/sites-enabled/facho-frontend
    
    # Verificar configuración de nginx
    echo "Verificando configuración de nginx..."
    if sudo nginx -t; then
        echo "Recargando nginx..."
        sudo systemctl reload nginx
        echo "✅ Frontend deshabilitado en producción"
        echo ""
        echo "El frontend ya no está disponible en producción."
        echo "Para iniciarlo nuevamente:"
        echo "  cd /opt/facho_deluxe_2"
        echo "  sudo ./scripts/frontend/start_frontend_prod.sh"
    else
        echo "❌ Error: La configuración de nginx tiene errores"
        exit 1
    fi
else
    echo "⚠️  El frontend ya está deshabilitado en producción"
    echo ""
    echo "Para iniciarlo:"
    echo "  cd /opt/facho_deluxe_2"
    echo "  sudo ./scripts/frontend/start_frontend_prod.sh"
fi

