#!/bin/bash
#
# Script para relacionar automáticamente todos los hilos ODF con las ONUs existentes
# Basándose en slot/port en la misma OLT
#
# Uso:
#   ./relacionar_hilos_onus.sh                    # Relacionar todos los hilos
#   ./relacionar_hilos_onus.sh --dry-run          # Ver qué se haría sin aplicar cambios
#   ./relacionar_hilos_onus.sh --olt-id 21        # Solo para una OLT específica
#   ./relacionar_hilos_onus.sh --hilo-id 1234     # Solo para un hilo específico
#

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directorio del proyecto
PROJECT_DIR="/opt/facho_deluxe_2"
VENV_DIR="${PROJECT_DIR}/venv"

# Verificar si existe el entorno virtual
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}❌ No se encontró el entorno virtual en: $VENV_DIR${NC}"
    exit 1
fi

# Activar entorno virtual
source "${VENV_DIR}/bin/activate"

# Cambiar al directorio del proyecto
cd "$PROJECT_DIR"

echo -e "${GREEN}🔗 RELACIONANDO HILOS ODF CON ONUs${NC}"
echo -e "${BLUE}===================================================${NC}"
echo ""

# Ejecutar el comando de Django con todos los argumentos pasados
python manage.py relacionar_hilos_onus "$@"

# Capturar el código de salida
EXIT_CODE=$?

# Desactivar entorno virtual
deactivate

# Salir con el mismo código de salida del comando Django
exit $EXIT_CODE

