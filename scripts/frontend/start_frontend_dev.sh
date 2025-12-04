#!/bin/bash
# ========================================
# Iniciar Frontend en Modo Desarrollo
# ========================================
# Este script inicia el frontend en modo desarrollo
# Usa Vite dev server en el puerto 3000
# Útil para editar y probar cambios en tiempo real

set -e

FRONTEND_DIR="/opt/facho-frontend"

echo "========================================="
echo "Iniciando Frontend en Modo Desarrollo"
echo "========================================="

# Verificar que existe el directorio del frontend
if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ Error: No se encontró el directorio $FRONTEND_DIR"
    exit 1
fi

cd "$FRONTEND_DIR"

# Verificar que Node.js está instalado
if ! command -v node &> /dev/null; then
    echo "❌ Error: Node.js no está instalado"
    echo "   Instala Node.js: sudo apt install nodejs npm"
    exit 1
fi

# Verificar que npm está instalado
if ! command -v npm &> /dev/null; then
    echo "❌ Error: npm no está instalado"
    echo "   Instala npm: sudo apt install npm"
    exit 1
fi

# Instalar dependencias si es necesario
if [ ! -d "node_modules" ]; then
    echo "📦 Instalando dependencias..."
    npm install
fi

# Verificar configuración del backend
CONFIG_FILE="/etc/facho-frontend/frontend.conf"
BACKEND_IP="10.80.80.229"
BACKEND_PORT="8000"

if [ -f "$CONFIG_FILE" ]; then
    echo "📋 Leyendo configuración del backend desde $CONFIG_FILE..."
    BACKEND_IP=$(grep -E "^backend_ip\s*=" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d ' ' || echo "$BACKEND_IP")
    BACKEND_PORT=$(grep -E "^backend_port\s*=" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d ' ' || echo "$BACKEND_PORT")
    echo "   Backend configurado: http://${BACKEND_IP}:${BACKEND_PORT}"
else
    echo "⚠️  Advertencia: No se encontró $CONFIG_FILE"
    echo "   Usando valores por defecto: http://${BACKEND_IP}:${BACKEND_PORT}"
    echo ""
    echo "   Para configurar correctamente, ejecuta:"
    echo "   cd $FRONTEND_DIR && ./scripts/setup-config.sh"
    echo ""
fi

# Verificar que el backend está configurado en vite.config.js
echo "Verificando configuración de desarrollo..."
if ! grep -q "target:" vite.config.js; then
    echo "⚠️  Advertencia: vite.config.js no tiene configuración de proxy"
    echo "   El proxy debe apuntar al backend para desarrollo"
fi

echo ""
echo "🚀 Iniciando servidor de desarrollo..."
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://${BACKEND_IP}:${BACKEND_PORT}"
echo ""
echo "⚠️  NOTA: Este es modo desarrollo. Para producción usa:"
echo "   ./scripts/frontend/start_frontend_prod.sh"
echo ""
echo "   Presiona Ctrl+C para detener el servidor"
echo ""

# Iniciar servidor de desarrollo
npm run dev

