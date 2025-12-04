#!/bin/bash
# ============================================
# VERIFICAR ESTADO DEL CERTIFICADO SSL
# ============================================
# 
# Este script muestra información sobre el certificado SSL actual
#
# Uso: sudo ./verificar_certificado.sh
#
# ============================================

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ESTADO DEL CERTIFICADO SSL${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Leer configuración
HTTPS_CONFIG="/etc/facho_deluxe_2/https.conf"

if [ ! -f "$HTTPS_CONFIG" ]; then
    echo -e "${RED}Error: No se encontró: $HTTPS_CONFIG${NC}"
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

SSL_CERT_PATH=$(read_config "$HTTPS_CONFIG" "https" "ssl_cert_path")
SSL_CERT_PATH=${SSL_CERT_PATH:-"/etc/ssl/facho_deluxe_2/facho-backend.crt"}

if [ ! -f "$SSL_CERT_PATH" ]; then
    echo -e "${RED}Error: Certificado no encontrado en: $SSL_CERT_PATH${NC}"
    exit 1
fi

# Obtener información del certificado
echo -e "${BLUE}Información del certificado:${NC}\n"

# Fechas
echo -e "${YELLOW}Fechas:${NC}"
NOT_BEFORE=$(openssl x509 -startdate -noout -in "$SSL_CERT_PATH" | cut -d= -f2)
NOT_AFTER=$(openssl x509 -enddate -noout -in "$SSL_CERT_PATH" | cut -d= -f2)

echo -e "  ${BLUE}Válido desde:${NC} $NOT_BEFORE"
echo -e "  ${BLUE}Válido hasta:${NC} $NOT_AFTER"

# Calcular días restantes
if command -v date >/dev/null 2>&1; then
    EXPIRY_EPOCH=$(date -d "$NOT_AFTER" +%s 2>/dev/null || echo "0")
    CURRENT_EPOCH=$(date +%s)
    if [ $EXPIRY_EPOCH -gt 0 ]; then
        DAYS_LEFT=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))
        
        echo -e "\n${YELLOW}Estado:${NC}"
        if [ $DAYS_LEFT -gt 30 ]; then
            echo -e "  ${GREEN}✓ Válido${NC} - Quedan ${GREEN}$DAYS_LEFT días${NC}"
        elif [ $DAYS_LEFT -gt 0 ]; then
            echo -e "  ${YELLOW}⚠ Próximo a expirar${NC} - Quedan ${YELLOW}$DAYS_LEFT días${NC}"
            echo -e "  ${BLUE}→ Renueva ejecutando: sudo ./renovar_certificado.sh${NC}"
        else
            echo -e "  ${RED}✗ EXPIRADO${NC}"
            echo -e "  ${RED}→ Renueva inmediatamente: sudo ./renovar_certificado.sh${NC}"
        fi
    fi
fi

# Información del certificado
echo -e "\n${YELLOW}Detalles:${NC}"
SUBJECT=$(openssl x509 -subject -noout -in "$SSL_CERT_PATH" | cut -d= -f2-)
ISSUER=$(openssl x509 -issuer -noout -in "$SSL_CERT_PATH" | cut -d= -f2-)

echo -e "  ${BLUE}Dominio/IP:${NC} $SUBJECT"
echo -e "  ${BLUE}Emitido por:${NC} $ISSUER"
echo -e "  ${BLUE}Ubicación:${NC} $SSL_CERT_PATH"

# Tipo de certificado
if echo "$ISSUER" | grep -q "Facho Deluxe"; then
    echo -e "\n${YELLOW}Tipo:${NC}"
    echo -e "  ${BLUE}✓ Certificado autofirmado (genérico/gratuito)${NC}"
fi

echo -e "\n${GREEN}════════════════════════════════════════${NC}"

