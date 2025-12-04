#!/bin/bash
# Script para ajustar permisos del archivo de configuración
# para que Django pueda leerlo

CONFIG_FILE="/etc/facho_deluxe_2/deploy.conf"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ El archivo $CONFIG_FILE no existe"
    echo "   Ejecuta primero: sudo ./crear_config_etc.sh"
    exit 1
fi

echo "🔧 Ajustando permisos del archivo de configuración..."
echo "   Archivo: $CONFIG_FILE"
echo ""

# Verificar si se ejecuta con sudo
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Este script debe ejecutarse con sudo para cambiar permisos"
    echo ""
    echo "Ejecuta:"
    echo "   sudo chmod 640 $CONFIG_FILE"
    echo "   sudo chgrp www-data $CONFIG_FILE"
    echo ""
    echo "O ejecuta este script con sudo:"
    echo "   sudo ./ajustar_permisos_config.sh"
    exit 1
fi

# Ajustar permisos: propietario puede leer/escribir, grupo puede leer
chmod 640 "$CONFIG_FILE"
chgrp www-data "$CONFIG_FILE"

echo "✅ Permisos ajustados:"
ls -la "$CONFIG_FILE"
echo ""
echo "El archivo ahora es legible por:"
echo "  - Propietario (root): lectura/escritura"
echo "  - Grupo (www-data): lectura"
echo "  - Usuario 'noc' (si está en grupo www-data): lectura"
echo ""
echo "Si el usuario 'noc' no puede leerlo, agrégalo al grupo www-data:"
echo "   sudo usermod -a -G www-data noc"

