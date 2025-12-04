#!/bin/bash
# ============================================
# CONFIGURAR HTTPS CON CERTIFICADO AUTOFIRMADO
# ============================================
# 
# Este script:
# 1. Lee configuración desde /etc/facho_deluxe_2/backend.conf y https.conf
# 2. Genera certificado SSL autofirmado (genérico/gratuito)
# 3. Instala y configura NGINX como reverse proxy
# 4. Crea/actualiza https.conf para habilitar HTTPS
#
# IMPORTANTE: Este script SOLO genera certificados autofirmados.
# NO usa certificados de pago ni servicios externos como Let's Encrypt.
#
# Uso: sudo ./configurar_https.sh
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
echo -e "${GREEN}  CONFIGURACIÓN HTTPS CON CERTIFICADO${NC}"
echo -e "${GREEN}  AUTOFIRMADO${NC}"
echo -e "${GREEN}========================================${NC}"

# Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# Configuración de archivos
CONFIG_DIR="/etc/facho_deluxe_2"
BACKEND_CONFIG="$CONFIG_DIR/backend.conf"
HTTPS_CONFIG="$CONFIG_DIR/https.conf"

# Crear directorio si no existe
if [ ! -d "$CONFIG_DIR" ]; then
    echo -e "${BLUE}→ Creando directorio de configuración: $CONFIG_DIR${NC}"
    mkdir -p "$CONFIG_DIR"
    chmod 755 "$CONFIG_DIR"
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

echo -e "\n${YELLOW}[1/7] Configurando archivos de configuración...${NC}"

# 1. Verificar/crear backend.conf
if [ ! -f "$BACKEND_CONFIG" ]; then
    echo -e "${YELLOW}⚠️ No se encontró $BACKEND_CONFIG${NC}"
    echo -e "${BLUE}Ejecuta primero: sudo ./deploy_backend.sh${NC}"
    echo -e "${BLUE}O crea el archivo manualmente.${NC}"
    exit 1
fi

# Leer valores del backend.conf
API_IP=$(read_config "$BACKEND_CONFIG" "api" "api_ip")
API_PORT=$(read_config "$BACKEND_CONFIG" "api" "api_port")
SYSTEM_USER=$(read_config "$BACKEND_CONFIG" "system" "system_user" || echo "noc")
PROJECT_DIR=$(read_config "$BACKEND_CONFIG" "system" "project_directory" || echo "/opt/facho_deluxe_2")

# Validar API_IP (es crítico)
if [ -z "$API_IP" ]; then
    echo -e "${YELLOW}⚠️ api_ip no encontrado en $BACKEND_CONFIG${NC}"
    read -p "$(echo -e ${BLUE}Ingresa la IP del backend [Enter para usar 0.0.0.0]: ${NC})" API_IP
    API_IP=${API_IP:-"0.0.0.0"}
fi

API_PORT=${API_PORT:-"8000"}

# 2. Crear/actualizar https.conf
if [ ! -f "$HTTPS_CONFIG" ]; then
    echo -e "${BLUE}→ Creando archivo https.conf...${NC}"
    
    # Solicitar configuración HTTPS interactivamente
    echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}   CONFIGURACIÓN HTTPS${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}"
    
    # Dominio HTTPS
    echo -e "${YELLOW}Dominio o IP para HTTPS:${NC}"
    echo -e "${BLUE}  - Presiona Enter para usar la IP del backend: $API_IP${NC}"
    echo -e "${BLUE}  - O ingresa un dominio personalizado (ej: api.facho.com)${NC}"
    read -p "$(echo -e ${BLUE}Dominio/IP: ${NC})" HTTPS_DOMAIN
    HTTPS_DOMAIN=${HTTPS_DOMAIN:-"$API_IP"}
    
    # Puerto HTTPS
    echo -e "\n${YELLOW}Puerto HTTPS:${NC}"
    read -p "$(echo -e ${BLUE}Puerto [Enter para usar 443]: ${NC})" HTTPS_PORT
    HTTPS_PORT=${HTTPS_PORT:-"443"}
    
    # Rutas de certificados
    echo -e "\n${YELLOW}Rutas de certificados SSL:${NC}"
    echo -e "${BLUE}  - Certificado y clave se generarán automáticamente${NC}"
    SSL_CERT_PATH="/etc/ssl/facho_deluxe_2/facho-backend.crt"
    SSL_KEY_PATH="/etc/ssl/facho_deluxe_2/facho-backend.key"
    SSL_CERT_DAYS="365"
    
    echo -e "${GREEN}✓ Valores configurados${NC}"
    echo -e "${BLUE}  - Dominio/IP: $HTTPS_DOMAIN${NC}"
    echo -e "${BLUE}  - Puerto: $HTTPS_PORT${NC}"
    
    # Crear archivo https.conf
    cat > "$HTTPS_CONFIG" <<EOF
# ============================================
# CONFIGURACIÓN HTTPS - FACHO DELUXE v2
# ============================================
# Generado automáticamente el $(date '+%Y-%m-%d %H:%M:%S')
# Este archivo contiene información sensible. NO compartir ni subir a git.

[https]
protocol = https
https_domain = $HTTPS_DOMAIN
https_port = $HTTPS_PORT
ssl_cert_path = $SSL_CERT_PATH
ssl_key_path = $SSL_KEY_PATH
ssl_cert_days = $SSL_CERT_DAYS
EOF
    
    chmod 600 "$HTTPS_CONFIG"
    chown root:root "$HTTPS_CONFIG"
    
    echo -e "${GREEN}✓ Archivo https.conf creado${NC}"
else
    echo -e "${GREEN}✓ Archivo https.conf ya existe${NC}"
    
    # Leer valores de https.conf existente
    HTTPS_DOMAIN=$(read_config "$HTTPS_CONFIG" "https" "https_domain")
    HTTPS_PORT=$(read_config "$HTTPS_CONFIG" "https" "https_port" || echo "443")
    SSL_CERT_PATH=$(read_config "$HTTPS_CONFIG" "https" "ssl_cert_path")
    SSL_KEY_PATH=$(read_config "$HTTPS_CONFIG" "https" "ssl_key_path")
    SSL_CERT_DAYS=$(read_config "$HTTPS_CONFIG" "https" "ssl_cert_days" || echo "365")
    
    # Validar y completar valores faltantes
    if [ -z "$HTTPS_DOMAIN" ]; then
        HTTPS_DOMAIN="$API_IP"
        echo -e "${BLUE}→ Dominio no configurado, usando IP: $HTTPS_DOMAIN${NC}"
    fi
    
    if [ -z "$SSL_CERT_PATH" ]; then
        SSL_CERT_PATH="/etc/ssl/facho_deluxe_2/facho-backend.crt"
    fi
    if [ -z "$SSL_KEY_PATH" ]; then
        SSL_KEY_PATH="/etc/ssl/facho_deluxe_2/facho-backend.key"
    fi
fi

echo -e "${GREEN}✓ Configuración completa${NC}"
echo -e "${BLUE}  Dominio/IP: $HTTPS_DOMAIN${NC}"
echo -e "${BLUE}  Puerto HTTPS: $HTTPS_PORT${NC}"
echo -e "${BLUE}  Backend: $API_IP:$API_PORT${NC}"

# 3. Instalar NGINX si no está instalado
echo -e "\n${YELLOW}[2/7] Verificando NGINX...${NC}"
if ! command -v nginx &> /dev/null; then
    echo -e "${BLUE}→ Instalando NGINX...${NC}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y nginx
    echo -e "${GREEN}✓ NGINX instalado${NC}"
else
    echo -e "${GREEN}✓ NGINX ya está instalado${NC}"
fi

# 4. Crear directorio para certificados
echo -e "\n${YELLOW}[3/7] Generando certificado SSL autofirmado (genérico)...${NC}"

# Extraer directorio de las rutas
SSL_DIR=$(dirname "$SSL_CERT_PATH")
mkdir -p "$SSL_DIR"

CERT_FILE="$SSL_CERT_PATH"
KEY_FILE="$SSL_KEY_PATH"

# Generar certificado autofirmado (válido por 365 días)
# NOTA: Este es un certificado genérico autofirmado, NO de pago
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo -e "${BLUE}→ Generando certificado SSL autofirmado (genérico/gratuito)...${NC}"
    
    # Generar certificado autofirmado usando OpenSSL (genérico/gratuito)
    # Este certificado es autofirmado, NO requiere pago ni servicios externos
    openssl req -x509 -nodes -days $SSL_CERT_DAYS -newkey rsa:2048 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -subj "/C=PE/ST=Lima/L=Lima/O=Facho Deluxe/OU=IT/CN=$HTTPS_DOMAIN" \
        2>/dev/null
    
    chmod 600 "$KEY_FILE"
    chmod 644 "$CERT_FILE"
    
    echo -e "${GREEN}✓ Certificado SSL generado${NC}"
    echo -e "${BLUE}  Certificado: $CERT_FILE${NC}"
    echo -e "${BLUE}  Clave: $KEY_FILE${NC}"
else
    echo -e "${GREEN}✓ Certificado SSL ya existe${NC}"
fi

# 5. Configurar NGINX
echo -e "\n${YELLOW}[4/7] Configurando NGINX...${NC}"

NGINX_CONFIG="/etc/nginx/sites-available/facho-backend"

cat > "$NGINX_CONFIG" <<EOF
# ========================================
# Configuración NGINX para Facho Deluxe v2
# ========================================

# Redirección HTTP a HTTPS
server {
    listen 80;
    server_name $HTTPS_DOMAIN;
    
    # Redirigir todo a HTTPS
    return 301 https://\$server_name\$request_uri;
}

# Configuración HTTPS
server {
    listen ${HTTPS_PORT} ssl http2;
    server_name $HTTPS_DOMAIN;

    # Certificados SSL autofirmados (genéricos/gratuitos)
    # NOTA: Estos certificados son autofirmados, NO de pago
    ssl_certificate $CERT_FILE;
    ssl_certificate_key $KEY_FILE;

    # Configuración SSL moderna
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Headers de seguridad
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Tamaño máximo de carga
    client_max_body_size 50M;

    # Logs
    access_log /var/log/nginx/facho-backend-access.log;
    error_log /var/log/nginx/facho-backend-error.log;

    # Proxy al backend Django (Gunicorn)
    location / {
        proxy_pass http://$API_IP:$API_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$server_name;
        
        # Timeouts para operaciones largas
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        
        # Buffering
        proxy_buffering off;
        proxy_request_buffering off;
    }

    # Archivos estáticos (servir desde NGINX es más eficiente)
    location /static/ {
        alias $PROJECT_DIR/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
}
EOF

# Habilitar sitio
if [ ! -f "/etc/nginx/sites-enabled/facho-backend" ]; then
    ln -s "$NGINX_CONFIG" /etc/nginx/sites-enabled/
    echo -e "${GREEN}✓ Sitio NGINX habilitado${NC}"
else
    echo -e "${BLUE}→ Sitio NGINX ya está habilitado${NC}"
fi

# Deshabilitar sitio por defecto si existe
if [ -f "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
    echo -e "${BLUE}→ Sitio por defecto deshabilitado${NC}"
fi

echo -e "${GREEN}✓ NGINX configurado${NC}"

# 6. Verificar configuración de NGINX
echo -e "\n${YELLOW}[5/7] Verificando configuración de NGINX...${NC}"
if nginx -t > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Configuración de NGINX válida${NC}"
else
    echo -e "${RED}Error en la configuración de NGINX${NC}"
    nginx -t
    exit 1
fi

# 7. Actualizar configuración HTTPS (ya existe, solo verificar)
echo -e "\n${YELLOW}[6/7] Verificando configuración HTTPS...${NC}"

# Actualizar valores si cambió el dominio
if read_config "$HTTPS_CONFIG" "https" "https_domain" | grep -qv "^$HTTPS_DOMAIN$"; then
    # Backup
    cp "$HTTPS_CONFIG" "$HTTPS_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Actualizar dominio
    sed -i "s|^https_domain = .*|https_domain = $HTTPS_DOMAIN|" "$HTTPS_CONFIG"
    echo -e "${BLUE}→ Dominio HTTPS actualizado${NC}"
fi

echo -e "${GREEN}✓ Configuración HTTPS verificada${NC}"

# 8. Reiniciar NGINX
echo -e "\n${YELLOW}[7/7] Reiniciando NGINX...${NC}"
systemctl restart nginx

if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ NGINX reiniciado correctamente${NC}"
else
    echo -e "${RED}Error: NGINX no se inició correctamente${NC}"
    systemctl status nginx
    exit 1
fi

# Resumen final
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  HTTPS CONFIGURADO EXITOSAMENTE${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Información:${NC}"
echo -e "  ${BLUE}URL HTTPS:${NC} https://$HTTPS_DOMAIN"
echo -e "  ${BLUE}Puerto:${NC} $HTTPS_PORT"
echo -e "  ${BLUE}Backend:${NC} http://$API_IP:$API_PORT (interno)"
echo -e "  ${BLUE}Certificado:${NC} $CERT_FILE"
echo -e "\n${YELLOW}⚠️ IMPORTANTE:${NC}"
echo -e "  ${YELLOW}Este es un certificado autofirmado (genérico).${NC}"
echo -e "  ${YELLOW}Los navegadores mostrarán una advertencia de seguridad.${NC}"
echo -e "  ${YELLOW}Este sistema SOLO usa certificados autofirmados gratuitos.${NC}"
echo -e "  ${YELLOW}NO se usan certificados de pago ni servicios externos.${NC}"
echo -e "\n${BLUE}Próximos pasos:${NC}"
echo -e "  1. Ejecuta: ${GREEN}sudo ./deploy_backend.sh${NC}"
echo -e "  2. Django se configurará automáticamente para HTTPS"
echo -e "  3. Accede a: ${GREEN}https://$HTTPS_DOMAIN${NC}"
echo -e "\n${GREEN}════════════════════════════════════════${NC}"
