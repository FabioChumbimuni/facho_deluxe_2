#!/bin/bash
# ============================================
# CAMBIAR USUARIO Y CONTRASEÑA DE SUPERVISOR
# ============================================
# 
# Este script cambia el usuario y contraseña de la interfaz web de Supervisor
#
# Uso: sudo ./cambiar_usuario_supervisor.sh
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
echo -e "${GREEN}  CAMBIAR USUARIO DE SUPERVISOR${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# Archivos de configuración
SUPERVISOR_CONFIG="/etc/supervisor/supervisord.conf"
BACKEND_CONFIG="/etc/facho_deluxe_2/backend.conf"

# Leer valores actuales
if [ -f "$SUPERVISOR_CONFIG" ]; then
    CURRENT_USER=$(grep "^username=" "$SUPERVISOR_CONFIG" | cut -d'=' -f2)
    CURRENT_PASS=$(grep "^password=" "$SUPERVISOR_CONFIG" | cut -d'=' -f2)
    
    echo -e "${YELLOW}Configuración actual:${NC}"
    echo -e "  ${BLUE}Usuario:${NC} $CURRENT_USER"
    echo -e "  ${BLUE}Contraseña:${NC} $CURRENT_PASS"
    echo ""
else
    echo -e "${RED}Error: No se encontró $SUPERVISOR_CONFIG${NC}"
    exit 1
fi

# Solicitar nuevo usuario
echo -e "${YELLOW}Ingresa el nuevo usuario:${NC}"
read -p "$(echo -e ${BLUE}Usuario [Enter para mantener '$CURRENT_USER']: ${NC})" NEW_USER
if [ -z "$NEW_USER" ]; then
    NEW_USER="$CURRENT_USER"
    echo -e "${GREEN}→ Manteniendo usuario: '$NEW_USER'${NC}"
else
    echo -e "${GREEN}→ Nuevo usuario: '$NEW_USER'${NC}"
fi

# Solicitar nueva contraseña
echo -e "\n${YELLOW}Ingresa la nueva contraseña:${NC}"
read -sp "$(echo -e ${BLUE}Contraseña: ${NC})" NEW_PASS
echo ""

if [ -z "$NEW_PASS" ]; then
    echo -e "${RED}Error: La contraseña no puede estar vacía${NC}"
    exit 1
fi

# Confirmar cambios
echo -e "\n${YELLOW}Resumen de cambios:${NC}"
echo -e "  ${BLUE}Usuario:${NC} $CURRENT_USER → $NEW_USER"
echo -e "  ${BLUE}Contraseña:${NC} ******** → ********"
echo ""
read -p "$(echo -e ${YELLOW}¿Continuar? [s/N]: ${NC})" CONFIRM
if [[ ! "$CONFIRM" =~ ^[Ss]$ ]]; then
    echo -e "${BLUE}Operación cancelada${NC}"
    exit 0
fi

# Crear backup
echo -e "\n${YELLOW}[1/3] Creando backup...${NC}"
cp "$SUPERVISOR_CONFIG" "${SUPERVISOR_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
echo -e "${GREEN}✓ Backup creado${NC}"

# Actualizar configuración de supervisor
echo -e "\n${YELLOW}[2/3] Actualizando configuración de Supervisor...${NC}"
sed -i "s/^username=.*/username=$NEW_USER/" "$SUPERVISOR_CONFIG"
sed -i "s/^password=.*/password=$NEW_PASS/" "$SUPERVISOR_CONFIG"
echo -e "${GREEN}✓ Configuración actualizada${NC}"

# Actualizar backend.conf si existe
if [ -f "$BACKEND_CONFIG" ]; then
    echo -e "\n${YELLOW}[3/3] Actualizando backend.conf...${NC}"
    sed -i "s/^supervisor_user = .*/supervisor_user = $NEW_USER/" "$BACKEND_CONFIG"
    sed -i "s/^supervisor_password = .*/supervisor_password = $NEW_PASS/" "$BACKEND_CONFIG"
    echo -e "${GREEN}✓ backend.conf actualizado${NC}"
else
    echo -e "\n${YELLOW}[3/3] backend.conf no encontrado, omitiendo...${NC}"
fi

# Reiniciar supervisor
echo -e "\n${YELLOW}Reiniciando Supervisor...${NC}"
systemctl restart supervisor
sleep 2

if systemctl is-active --quiet supervisor; then
    echo -e "${GREEN}✓ Supervisor reiniciado correctamente${NC}"
else
    echo -e "${RED}Error: Supervisor no se inició correctamente${NC}"
    systemctl status supervisor
    exit 1
fi

# Resumen final
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  USUARIO CAMBIADO EXITOSAMENTE${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Nueva configuración:${NC}"
echo -e "  ${BLUE}Usuario:${NC} $NEW_USER"
echo -e "  ${BLUE}Contraseña:${NC} ********"
echo -e "\n${YELLOW}Acceso a la interfaz web:${NC}"
echo -e "  ${GREEN}URL:${NC} http://10.80.80.229:9001"
echo -e "  ${GREEN}Usuario:${NC} $NEW_USER"
echo -e "\n${BLUE}Nota:${NC} Guarda estas credenciales en un lugar seguro."
echo -e "\n${GREEN}════════════════════════════════════════${NC}"

