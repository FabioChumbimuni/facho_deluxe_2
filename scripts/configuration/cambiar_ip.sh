#!/bin/bash
# ============================================
# CAMBIAR IP DE LA APLICACIÓN
# ============================================
# 
# Este script cambia la IP de la aplicación en todos los archivos
# de configuración necesarios.
#
# Uso: sudo ./cambiar_ip.sh [NUEVA_IP]
#
# ============================================

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  CAMBIAR IP DE LA APLICACIÓN${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# Obtener IP actual y nueva
BACKEND_CONFIG="/etc/facho_deluxe_2/backend.conf"

if [ ! -f "$BACKEND_CONFIG" ]; then
    echo -e "${RED}Error: No se encontró $BACKEND_CONFIG${NC}"
    exit 1
fi

# Función para leer configuración
read_config() {
    local config_file=$1
    local section=$2
    local key=$3
    if [ -f "$config_file" ]; then
        sed -n "/^\[$section\]/,/^\[/p" "$config_file" | grep "^$key" | cut -d'=' -f2 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/[[:space:]]*#.*$//'
    fi
}

OLD_IP=$(read_config "$BACKEND_CONFIG" "api" "api_ip")

if [ -z "$OLD_IP" ]; then
    OLD_IP="192.168.56.222"
fi

# Obtener nueva IP
if [ -n "$1" ]; then
    NEW_IP="$1"
else
    echo -e "${YELLOW}IP actual: ${BLUE}$OLD_IP${NC}\n"
    read -p "$(echo -e ${BLUE}Ingresa la nueva IP: ${NC})" NEW_IP
fi

# Validar IP
if [[ ! "$NEW_IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
    echo -e "${RED}Error: IP inválida${NC}"
    exit 1
fi

if [ "$OLD_IP" = "$NEW_IP" ]; then
    echo -e "${YELLOW}La IP ya es $NEW_IP. No hay cambios necesarios.${NC}"
    exit 0
fi

echo -e "\n${YELLOW}Cambiando IP:${NC}"
echo -e "  ${BLUE}De:${NC} $OLD_IP"
echo -e "  ${BLUE}A:${NC} $NEW_IP\n"

read -p "$(echo -e ${YELLOW}¿Continuar? [s/N]: ${NC})" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Ss]$ ]]; then
    echo -e "${BLUE}Operación cancelada${NC}"
    exit 0
fi

echo -e "\n${YELLOW}[1/6] Actualizando archivos de configuración...${NC}"

# 1. backend.conf
if [ -f "$BACKEND_CONFIG" ]; then
    sed -i "s/$OLD_IP/$NEW_IP/g" "$BACKEND_CONFIG"
    echo -e "${GREEN}✓ $BACKEND_CONFIG${NC}"
fi

# 2. https.conf
HTTPS_CONFIG="/etc/facho_deluxe_2/https.conf"
if [ -f "$HTTPS_CONFIG" ]; then
    sed -i "s/$OLD_IP/$NEW_IP/g" "$HTTPS_CONFIG"
    echo -e "${GREEN}✓ $HTTPS_CONFIG${NC}"
fi

# 3. Archivos de ejemplo
echo -e "\n${YELLOW}[2/6] Actualizando archivos de ejemplo...${NC}"
EXAMPLE_FILES=(
    "/opt/facho_deluxe_2/backend.conf.example"
    "/opt/facho_deluxe_2/https.conf.example"
    "/opt/facho_deluxe_2/deploy.conf.example"
)

for file in "${EXAMPLE_FILES[@]}"; do
    if [ -f "$file" ]; then
        sed -i "s/$OLD_IP/$NEW_IP/g" "$file"
        echo -e "${GREEN}✓ $(basename $file)${NC}"
    fi
done

# 4. Scripts
echo -e "\n${YELLOW}[3/6] Actualizando scripts...${NC}"
SCRIPT_DIR="/opt/facho_deluxe_2"
if [ -f "$SCRIPT_DIR/renovar_certificado.sh" ]; then
    sed -i "s/$OLD_IP/$NEW_IP/g" "$SCRIPT_DIR/renovar_certificado.sh"
    echo -e "${GREEN}✓ renovar_certificado.sh${NC}"
fi
if [ -f "$SCRIPT_DIR/crear_config_etc.sh" ]; then
    sed -i "s/$OLD_IP/$NEW_IP/g" "$SCRIPT_DIR/crear_config_etc.sh"
    echo -e "${GREEN}✓ crear_config_etc.sh${NC}"
fi

# 5. Configuración de NGINX
echo -e "\n${YELLOW}[4/6] Actualizando configuración de NGINX...${NC}"
NGINX_CONFIG="/etc/nginx/sites-available/facho-backend"
if [ -f "$NGINX_CONFIG" ]; then
    # Crear backup
    cp "$NGINX_CONFIG" "${NGINX_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Reemplazar IP en server_name
    sed -i "s/server_name $OLD_IP;/server_name $NEW_IP;/g" "$NGINX_CONFIG"
    
    # Reemplazar en proxy_pass si es necesario
    sed -i "s|proxy_pass http://$OLD_IP:|proxy_pass http://$NEW_IP:|g" "$NGINX_CONFIG"
    
    echo -e "${GREEN}✓ NGINX configurado${NC}"
    
    # Verificar configuración
    if nginx -t > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Configuración de NGINX válida${NC}"
    else
        echo -e "${RED}Error en la configuración de NGINX${NC}"
        nginx -t
        exit 1
    fi
fi

# 6. Configuración de Supervisor (Gunicorn y servidor HTTP)
echo -e "\n${YELLOW}[5/6] Actualizando configuración de Supervisor...${NC}"

# 6.1. Actualizar configuración de programas (Gunicorn)
SUPERVISOR_CONFIG="/etc/supervisor/conf.d/facho_deluxe_v2.conf"
if [ -f "$SUPERVISOR_CONFIG" ]; then
    # Crear backup
    cp "$SUPERVISOR_CONFIG" "${SUPERVISOR_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Reemplazar IP en bind de Gunicorn
    sed -i "s|--bind $OLD_IP:|--bind $NEW_IP:|g" "$SUPERVISOR_CONFIG"
    
    echo -e "${GREEN}✓ Configuración de programas actualizada${NC}"
fi

# 6.2. Actualizar configuración principal de Supervisor (servidor HTTP)
SUPERVISOR_MAIN_CONFIG="/etc/supervisor/supervisord.conf"
if [ -f "$SUPERVISOR_MAIN_CONFIG" ]; then
    # Crear backup
    cp "$SUPERVISOR_MAIN_CONFIG" "${SUPERVISOR_MAIN_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Reemplazar IP en inet_http_server (puerto del servidor web de supervisor)
    sed -i "s|port=$OLD_IP:|port=$NEW_IP:|g" "$SUPERVISOR_MAIN_CONFIG"
    
    echo -e "${GREEN}✓ Configuración principal de Supervisor actualizada${NC}"
    
    # Reiniciar supervisor para aplicar cambios en supervisord.conf
    systemctl restart supervisor > /dev/null 2>&1
    sleep 2
    if systemctl is-active --quiet supervisor; then
        echo -e "${GREEN}✓ Supervisor reiniciado${NC}"
    else
        echo -e "${YELLOW}⚠ Supervisor no se reinició automáticamente, puede requerir reinicio manual${NC}"
    fi
fi

# Recargar configuración de programas
if [ -f "$SUPERVISOR_CONFIG" ]; then
    supervisorctl reread > /dev/null 2>&1
    supervisorctl update > /dev/null 2>&1
    echo -e "${GREEN}✓ Programas de Supervisor actualizados${NC}"
fi

# 7. Regenerar certificado SSL (opcional pero recomendado)
echo -e "\n${YELLOW}[6/6] Regenerando certificado SSL...${NC}"
read -p "$(echo -e ${BLUE}¿Regenerar certificado SSL con la nueva IP? [S/n]: ${NC})" REGEN_CERT
if [[ ! "$REGEN_CERT" =~ ^[Nn]$ ]]; then
    HTTPS_DOMAIN=$(read_config "$HTTPS_CONFIG" "https" "https_domain" || echo "$NEW_IP")
    SSL_CERT_PATH=$(read_config "$HTTPS_CONFIG" "https" "ssl_cert_path" || echo "/etc/ssl/facho_deluxe_2/facho-backend.crt")
    SSL_KEY_PATH=$(read_config "$HTTPS_CONFIG" "https" "ssl_key_path" || echo "/etc/ssl/facho_deluxe_2/facho-backend.key")
    SSL_CERT_DAYS=$(read_config "$HTTPS_CONFIG" "https" "ssl_cert_days" || echo "365")
    
    SSL_DIR=$(dirname "$SSL_CERT_PATH")
    mkdir -p "$SSL_DIR"
    
    # Backup del certificado anterior
    if [ -f "$SSL_CERT_PATH" ]; then
        mv "$SSL_CERT_PATH" "${SSL_CERT_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
        mv "$SSL_KEY_PATH" "${SSL_KEY_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Generar nuevo certificado
    openssl req -x509 -nodes -days $SSL_CERT_DAYS -newkey rsa:2048 \
        -keyout "$SSL_KEY_PATH" \
        -out "$SSL_CERT_PATH" \
        -subj "/C=PE/ST=Lima/L=Lima/O=Facho Deluxe/OU=IT/CN=$HTTPS_DOMAIN" \
        2>/dev/null
    
    chmod 600 "$SSL_KEY_PATH"
    chmod 644 "$SSL_CERT_PATH"
    
    echo -e "${GREEN}✓ Certificado SSL regenerado${NC}"
fi

# Reiniciar servicios
echo -e "\n${YELLOW}Reiniciando servicios...${NC}"

# Reiniciar NGINX
systemctl reload nginx || systemctl restart nginx
if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ NGINX reiniciado${NC}"
else
    echo -e "${RED}Error: NGINX no se inició correctamente${NC}"
    systemctl status nginx
    exit 1
fi

# Reiniciar servicios de Supervisor (solo si no se reinició antes)
# Nota: Supervisor ya se reinició en la sección 6.2 si se actualizó supervisord.conf
# Aquí solo reiniciamos los programas (Gunicorn, Celery, etc.)
if [ -f "$SUPERVISOR_CONFIG" ]; then
    supervisorctl restart facho_deluxe_v2:* > /dev/null 2>&1
    sleep 2
    echo -e "${GREEN}✓ Programas de Supervisor reiniciados${NC}"
fi

# Resumen final
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  IP CAMBIADA EXITOSAMENTE${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Resumen:${NC}"
echo -e "  ${BLUE}IP anterior:${NC} $OLD_IP"
echo -e "  ${BLUE}IP nueva:${NC} $NEW_IP"
echo -e "\n${YELLOW}Acceso:${NC}"
echo -e "  ${GREEN}HTTPS:${NC} https://$NEW_IP/admin/"
echo -e "  ${GREEN}HTTP:${NC} http://$NEW_IP/admin/ (redirige a HTTPS)"
echo -e "\n${BLUE}Nota:${NC} Es posible que necesites aceptar el nuevo certificado SSL en tu navegador."
echo -e "\n${GREEN}════════════════════════════════════════${NC}"

