#!/bin/bash
# ============================================
# RENOVAR CERTIFICADO SSL AUTOFIRMADO
# ============================================
# 
# Este script renueva el certificado SSL autofirmado
# cuando está próximo a vencer o cuando lo necesites.
#
# IMPORTANTE: Este es un certificado autofirmado (genérico/gratuito).
# Los certificados autofirmados NO se renuevan automáticamente.
# Debes ejecutar este script manualmente cuando sea necesario.
#
# Uso: sudo ./renovar_certificado.sh
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
echo -e "${GREEN}  RENOVACIÓN DE CERTIFICADO SSL${NC}"
echo -e "${GREEN}  AUTOFIRMADO${NC}"
echo -e "${GREEN}========================================${NC}"

# Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# Leer configuración
HTTPS_CONFIG="/etc/facho_deluxe_2/https.conf"
BACKEND_CONFIG="/etc/facho_deluxe_2/backend.conf"

if [ ! -f "$HTTPS_CONFIG" ]; then
    echo -e "${RED}Error: No se encontró: $HTTPS_CONFIG${NC}"
    echo -e "${YELLOW}Ejecuta primero: sudo ./configurar_https.sh${NC}"
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

# Leer valores de configuración
HTTPS_DOMAIN=$(read_config "$HTTPS_CONFIG" "https" "https_domain")
SSL_CERT_PATH=$(read_config "$HTTPS_CONFIG" "https" "ssl_cert_path")
SSL_KEY_PATH=$(read_config "$HTTPS_CONFIG" "https" "ssl_key_path")
SSL_CERT_DAYS=$(read_config "$HTTPS_CONFIG" "https" "ssl_cert_days" || echo "365")

# Valores por defecto si no están configurados
HTTPS_DOMAIN=${HTTPS_DOMAIN:-"192.168.56.222"}
SSL_CERT_PATH=${SSL_CERT_PATH:-"/etc/ssl/facho_deluxe_2/facho-backend.crt"}
SSL_KEY_PATH=${SSL_KEY_PATH:-"/etc/ssl/facho_deluxe_2/facho-backend.key"}
SSL_CERT_DAYS=${SSL_CERT_DAYS:-"365"}

echo -e "\n${YELLOW}[1/4] Verificando certificado actual...${NC}"

# Verificar si existe el certificado
if [ -f "$SSL_CERT_PATH" ]; then
    # Obtener fecha de expiración
    EXPIRY_DATE=$(openssl x509 -enddate -noout -in "$SSL_CERT_PATH" | cut -d= -f2)
    EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s 2>/dev/null || date -j -f "%b %d %H:%M:%S %Y %Z" "$EXPIRY_DATE" +%s 2>/dev/null || echo "0")
    CURRENT_EPOCH=$(date +%s)
    DAYS_UNTIL_EXPIRY=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))
    
    echo -e "${BLUE}  Certificado actual encontrado${NC}"
    echo -e "${BLUE}  Fecha de expiración: $EXPIRY_DATE${NC}"
    
    if [ $DAYS_UNTIL_EXPIRY -gt 0 ]; then
        echo -e "${BLUE}  Días hasta expiración: $DAYS_UNTIL_EXPIRY${NC}"
        
        if [ $DAYS_UNTIL_EXPIRY -gt 30 ]; then
            echo -e "${YELLOW}⚠️  El certificado aún es válido por más de 30 días.${NC}"
            read -p "$(echo -e ${BLUE}¿Deseas renovarlo de todas formas? [s/N]: ${NC})" CONFIRM
            if [[ ! "$CONFIRM" =~ ^[Ss]$ ]]; then
                echo -e "${BLUE}Renovación cancelada.${NC}"
                exit 0
            fi
        elif [ $DAYS_UNTIL_EXPIRY -gt 0 ]; then
            echo -e "${YELLOW}⚠️  El certificado expira en $DAYS_UNTIL_EXPIRY días. Es recomendable renovarlo.${NC}"
        fi
    else
        echo -e "${RED}⚠️  El certificado ha expirado. Es necesario renovarlo.${NC}"
    fi
    
    # Crear backup del certificado actual
    BACKUP_DIR="/etc/ssl/facho_deluxe_2/backups"
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/cert-backup-$(date +%Y%m%d_%H%M%S)"
    
    cp "$SSL_CERT_PATH" "$BACKUP_FILE.crt"
    cp "$SSL_KEY_PATH" "$BACKUP_FILE.key"
    echo -e "${BLUE}  Backup creado: $BACKUP_FILE.{crt,key}${NC}"
else
    echo -e "${YELLOW}⚠️  No se encontró certificado actual. Se generará uno nuevo.${NC}"
fi

# 2. Confirmar valores de renovación
echo -e "\n${YELLOW}[2/4] Configuración de renovación...${NC}"
echo -e "${BLUE}  Dominio/IP: $HTTPS_DOMAIN${NC}"
echo -e "${BLUE}  Días de validez: $SSL_CERT_DAYS${NC}"
echo -e "${BLUE}  Certificado: $SSL_CERT_PATH${NC}"
echo -e "${BLUE}  Clave: $SSL_KEY_PATH${NC}"

# Preguntar si quiere cambiar la validez
read -p "$(echo -e ${BLUE}¿Cambiar días de validez? [Enter para mantener $SSL_CERT_DAYS días]: ${NC})" NEW_DAYS
if [ -n "$NEW_DAYS" ] && [[ "$NEW_DAYS" =~ ^[0-9]+$ ]]; then
    SSL_CERT_DAYS="$NEW_DAYS"
    echo -e "${GREEN}→ Validez actualizada a $SSL_CERT_DAYS días${NC}"
fi

# 3. Generar nuevo certificado
echo -e "\n${YELLOW}[3/4] Generando nuevo certificado SSL autofirmado...${NC}"

# Crear directorio si no existe
SSL_DIR=$(dirname "$SSL_CERT_PATH")
mkdir -p "$SSL_DIR"

# Generar nuevo certificado
echo -e "${BLUE}→ Generando certificado con validez de $SSL_CERT_DAYS días...${NC}"

openssl req -x509 -nodes -days $SSL_CERT_DAYS -newkey rsa:2048 \
    -keyout "$SSL_KEY_PATH" \
    -out "$SSL_CERT_PATH" \
    -subj "/C=PE/ST=Lima/L=Lima/O=Facho Deluxe/OU=IT/CN=$HTTPS_DOMAIN" \
    2>/dev/null

chmod 600 "$SSL_KEY_PATH"
chmod 644 "$SSL_CERT_PATH"

# Verificar que se creó correctamente
if [ -f "$SSL_CERT_PATH" ] && [ -f "$SSL_KEY_PATH" ]; then
    NEW_EXPIRY=$(openssl x509 -enddate -noout -in "$SSL_CERT_PATH" | cut -d= -f2)
    echo -e "${GREEN}✓ Certificado renovado exitosamente${NC}"
    echo -e "${BLUE}  Nueva fecha de expiración: $NEW_EXPIRY${NC}"
else
    echo -e "${RED}Error: No se pudo generar el certificado${NC}"
    exit 1
fi

# 4. Actualizar configuración y reiniciar NGINX
echo -e "\n${YELLOW}[4/4] Actualizando NGINX...${NC}"

# Actualizar días en https.conf si cambió
if [ -n "$NEW_DAYS" ]; then
    sed -i "s|^ssl_cert_days = .*|ssl_cert_days = $SSL_CERT_DAYS|" "$HTTPS_CONFIG"
    echo -e "${BLUE}→ Configuración actualizada${NC}"
fi

# Verificar configuración de NGINX
if nginx -t > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Configuración de NGINX válida${NC}"
else
    echo -e "${RED}Error en la configuración de NGINX${NC}"
    nginx -t
    exit 1
fi

# Reiniciar NGINX
systemctl reload nginx || systemctl restart nginx

if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ NGINX reiniciado correctamente${NC}"
else
    echo -e "${RED}Error: NGINX no se inició correctamente${NC}"
    systemctl status nginx
    exit 1
fi

# Resumen final
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  CERTIFICADO RENOVADO EXITOSAMENTE${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Información:${NC}"
echo -e "  ${BLUE}Certificado:${NC} $SSL_CERT_PATH"
echo -e "  ${BLUE}Clave:${NC} $SSL_KEY_PATH"
echo -e "  ${BLUE}Validez:${NC} $SSL_CERT_DAYS días"
echo -e "  ${BLUE}Expira:${NC} $NEW_EXPIRY"
echo -e "\n${BLUE}Próxima renovación recomendada:${NC}"
if [ $SSL_CERT_DAYS -gt 30 ]; then
    NEXT_RENEWAL=$((SSL_CERT_DAYS - 30))
    echo -e "  ${YELLOW}En aproximadamente $NEXT_RENEWAL días${NC}"
    echo -e "  ${BLUE}O ejecuta: sudo ./renovar_certificado.sh${NC}"
else
    echo -e "  ${YELLOW}Cuando quede menos de 30 días${NC}"
fi
echo -e "\n${GREEN}════════════════════════════════════════${NC}"

