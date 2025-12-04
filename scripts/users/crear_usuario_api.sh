#!/bin/bash
# ============================================
# CREAR USUARIO PARA API CON TOKEN
# ============================================
# 
# Este script crea un usuario de Django con permisos
# de lectura y escritura y genera su token de autenticación.
#
# Uso: sudo ./crear_usuario_api.sh [username] [password]
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
echo -e "${GREEN}  CREAR USUARIO PARA API${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# Obtener parámetros
USERNAME="${1:-fiberops}"
PASSWORD="${2}"

if [ -z "$PASSWORD" ]; then
    read -s -p "$(echo -e ${BLUE}Contraseña para $USERNAME: ${NC})" PASSWORD
    echo ""
    if [ -z "$PASSWORD" ]; then
        echo -e "${RED}Error: La contraseña no puede estar vacía${NC}"
        exit 1
    fi
fi

PROJECT_DIR="/opt/facho_deluxe_2"
VENV_DIR="$PROJECT_DIR/venv"
BACKEND_CONFIG="/etc/facho_deluxe_2/backend.conf"

# Leer configuración
read_config() {
    local config_file=$1
    local section=$2
    local key=$3
    if [ -f "$config_file" ]; then
        sed -n "/^\[$section\]/,/^\[/p" "$config_file" | grep "^$key" | cut -d'=' -f2 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/[[:space:]]*#.*$//'
    fi
}

SYSTEM_USER=$(read_config "$BACKEND_CONFIG" "system" "system_user" || echo "noc")
API_IP=$(read_config "$BACKEND_CONFIG" "api" "api_ip" || echo "10.80.80.229")

echo -e "${YELLOW}[1/4] Verificando entorno...${NC}"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}Error: Entorno virtual no encontrado${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Entorno virtual encontrado${NC}"

# Crear script de Python para crear usuario y token
TEMP_SCRIPT=$(mktemp)

cat > "$TEMP_SCRIPT" <<EOF
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.authtoken.models import Token

username = '$USERNAME'
password = '$PASSWORD'

print(f"Creando usuario: {username}")

# Crear o obtener usuario
user, created = User.objects.get_or_create(
    username=username,
    defaults={
        'email': f'{username}@facho.com',
        'is_staff': True,  # Necesario para permisos de escritura
        'is_active': True,
    }
)

if created:
    user.set_password(password)
    user.save()
    print(f"✓ Usuario {username} creado")
else:
    user.set_password(password)
    user.save()
    print(f"✓ Usuario {username} actualizado")

# Asignar permisos de lectura y escritura
# Obtener todos los content types de las apps principales
apps = [
    'hosts', 'snmp_jobs', 'executions', 'discovery',
    'brands', 'olt_models', 'oids', 'odf_management',
    'personal', 'zabbix_config'
]

print("\nAsignando permisos...")

# Dar permisos completos (read, write, delete) para todas las apps
for app in apps:
    try:
        content_types = ContentType.objects.filter(app_label=app)
        for ct in content_types:
            permissions = Permission.objects.filter(content_type=ct)
            user.user_permissions.add(*permissions)
        print(f"✓ Permisos para {app}")
    except Exception as e:
        print(f"⚠ No se encontró app: {app}")

# También hacer staff para que tenga acceso a todo
user.is_staff = True
user.is_superuser = False  # No admin completo, solo API
user.save()

# Crear o regenerar token
token, created = Token.objects.get_or_create(user=user)
if not created:
    token.delete()
    token = Token.objects.create(user=user)

print(f"\n✓ Token generado: {token.key}")
print(f"\nUsuario: {username}")
print(f"Token: {token.key}")
EOF

echo -e "\n${YELLOW}[2/4] Creando usuario...${NC}"

# Ejecutar script de Python
cd "$PROJECT_DIR"
sudo -u "$SYSTEM_USER" "$VENV_DIR/bin/python" "$TEMP_SCRIPT"

# Obtener token del output
TOKEN=$(sudo -u "$SYSTEM_USER" "$VENV_DIR/bin/python" "$TEMP_SCRIPT" 2>&1 | grep "Token:" | awk '{print $2}')

# Limpiar
rm -f "$TEMP_SCRIPT"

echo -e "\n${YELLOW}[3/4] Verificando usuario...${NC}"

# Verificar que el usuario existe
cd "$PROJECT_DIR"
USER_EXISTS=$(sudo -u "$SYSTEM_USER" "$VENV_DIR/bin/python" manage.py shell -c "from django.contrib.auth.models import User; print(User.objects.filter(username='$USERNAME').exists())" 2>/dev/null || echo "False")

if [ "$USER_EXISTS" = "True" ]; then
    echo -e "${GREEN}✓ Usuario verificado${NC}"
else
    echo -e "${RED}Error: No se pudo verificar el usuario${NC}"
    exit 1
fi

echo -e "\n${YELLOW}[4/4] Generando información de acceso...${NC}"

# Obtener token real
cd "$PROJECT_DIR"
ACTUAL_TOKEN=$(sudo -u "$SYSTEM_USER" "$VENV_DIR/bin/python" manage.py shell -c "from django.contrib.auth.models import User; from rest_framework.authtoken.models import Token; user = User.objects.get(username='$USERNAME'); token, _ = Token.objects.get_or_create(user=user); print(token.key)" 2>/dev/null)

echo -e "${GREEN}✓ Token obtenido${NC}"

# Resumen final
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  USUARIO CREADO EXITOSAMENTE${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Información del usuario:${NC}"
echo -e "  ${BLUE}Usuario:${NC} $USERNAME"
echo -e "  ${BLUE}Token:${NC} $ACTUAL_TOKEN"
echo -e "  ${BLUE}Permisos:${NC} Lectura y Escritura"
echo -e "\n${YELLOW}Ejemplos de uso:${NC}"
echo -e "\n${BLUE}1. Obtener lista de OLTs:${NC}"
echo -e "curl -X GET \"https://$API_IP/api/v1/olts/\" \\\\"
echo -e "  -H \"Authorization: Token $ACTUAL_TOKEN\""
echo -e "\n${BLUE}2. Obtener lista de ONUs:${NC}"
echo -e "curl -X GET \"https://$API_IP/api/v1/onus/\" \\\\"
echo -e "  -H \"Authorization: Token $ACTUAL_TOKEN\""
echo -e "\n${BLUE}3. Crear una OLT:${NC}"
echo -e "curl -X POST \"https://$API_IP/api/v1/olts/\" \\\\"
echo -e "  -H \"Authorization: Token $ACTUAL_TOKEN\" \\\\"
echo -e "  -H \"Content-Type: application/json\" \\\\"
echo -e "  -d '{\"abreviatura\": \"OLT-TEST\", \"ip_address\": \"192.168.1.1\", \"marca_id\": 1}'"
echo -e "\n${GREEN}════════════════════════════════════════${NC}"

