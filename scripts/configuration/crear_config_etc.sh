#!/bin/bash
# Script auxiliar para crear el archivo de configuración en /etc/
# usando los valores actuales de config.ini

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}Creando archivo de configuración en /etc/${NC}"

# Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_INI="$SCRIPT_DIR/config.ini"
CONFIG_DIR="/etc/facho_deluxe_2"
CONFIG_FILE="$CONFIG_DIR/deploy.conf"

# Crear directorio si no existe
if [ ! -d "$CONFIG_DIR" ]; then
    echo -e "${BLUE}→ Creando directorio: $CONFIG_DIR${NC}"
    mkdir -p "$CONFIG_DIR"
    chmod 755 "$CONFIG_DIR"
fi

# Leer valores del config.ini actual
if [ ! -f "$CONFIG_INI" ]; then
    echo -e "${RED}Error: No se encontró config.ini en $SCRIPT_DIR${NC}"
    exit 1
fi

echo -e "${BLUE}→ Leyendo valores desde: $CONFIG_INI${NC}"

# Función para leer valores
read_ini() {
    local section=$1
    local key=$2
    awk -F' = ' "/^\[$section\]/,/^\[/ {
        if (\$0 ~ /^#/ || \$0 ~ /^$/) next
        if (\$1 == \"$key\") {
            gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", \$2)
            print \$2
            exit
        }
    }" "$CONFIG_INI"
}

# Leer valores
DB_NAME=$(read_ini "database" "name")
DB_USER=$(read_ini "database" "user")
DB_PASSWORD=$(read_ini "database" "password")
DB_HOST=$(read_ini "database" "host")
DB_PORT=$(read_ini "database" "port")
BIND_IP=$(read_ini "deployment" "bind_ip")
BIND_PORT=$(read_ini "deployment" "bind_port")
SUPERVISOR_PORT=$(read_ini "deployment" "supervisor_port")

# Valores por defecto
DB_NAME=${DB_NAME:-"fiberprodata"}
DB_USER=${DB_USER:-"fiberproadmin"}
DB_PASSWORD=${DB_PASSWORD:-"noc12363"}
DB_HOST=${DB_HOST:-"192.168.56.222"}
DB_PORT=${DB_PORT:-"5432"}
BIND_IP=${BIND_IP:-"192.168.56.222"}
BIND_PORT=${BIND_PORT:-"8000"}
SUPERVISOR_PORT=${SUPERVISOR_PORT:-"9001"}

echo -e "${BLUE}→ Valores detectados:${NC}"
echo -e "  - BD: $DB_NAME"
echo -e "  - Usuario: $DB_USER"
echo -e "  - Host: $DB_HOST"
echo -e "  - IP API: $BIND_IP"
echo -e "  - Puerto API: $BIND_PORT"

# Crear archivo de configuración
cat > "$CONFIG_FILE" << EOF
# ============================================
# CONFIGURACIÓN DE DESPLIEGUE - FACHO DELUXE v2
# ============================================
# Generado desde config.ini actual el $(date '+%Y-%m-%d %H:%M:%S')
# Este archivo contiene información sensible. NO compartir ni subir a git.

[database]
name = $DB_NAME
user = $DB_USER
password = $DB_PASSWORD
host = $DB_HOST
port = $DB_PORT

[api]
api_ip = $BIND_IP
api_port = $BIND_PORT
protocol = http

[pollers]
max_pollers_per_olt = 10
max_consultas_simultaneas = 5
tamano_lote_inicial = 200

[supervisor]
supervisor_port = $SUPERVISOR_PORT
supervisor_user = admin
supervisor_password = facho2025

[system]
system_user = noc
system_group = www-data
project_directory = /opt/facho_deluxe_2

[django]
django_username = 
django_email = 
EOF

# Configurar permisos
chmod 600 "$CONFIG_FILE"
chown root:root "$CONFIG_FILE"

echo -e "${GREEN}✓ Archivo creado: $CONFIG_FILE${NC}"
echo -e "${GREEN}✓ Permisos configurados (solo root puede leer)${NC}"
echo -e "\n${BLUE}Puedes verificar con:${NC}"
echo -e "${GREEN}sudo cat $CONFIG_FILE${NC}"

