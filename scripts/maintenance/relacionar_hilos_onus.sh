#!/bin/bash
#
# Script para relacionar automáticamente todos los hilos ODF con las ONUs existentes
# Basándose en slot/port en la misma OLT
#
# Descripción:
#   Este script busca todas las ONUs (OnuIndexMap) que coincidan con cada hilo ODF
#   basándose en:
#   - Misma OLT
#   - Mismo Slot
#   - Mismo Port
#   
#   Y las relaciona automáticamente asignando el hilo al campo odf_hilo de OnuIndexMap
#
# Uso:
#   ./relacionar_hilos_onus.sh                    # Relacionar todos los hilos
#   ./relacionar_hilos_onus.sh --dry-run          # Ver qué se haría sin aplicar cambios
#   ./relacionar_hilos_onus.sh --olt-id 21        # Solo para una OLT específica
#   ./relacionar_hilos_onus.sh --hilo-id 1234     # Solo para un hilo específico
#   ./relacionar_hilos_onus.sh --force            # Forzar reasignación incluso si ya tienen hilo
#

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Directorio del proyecto
PROJECT_DIR="/opt/facho_deluxe_2"
VENV_DIR="${PROJECT_DIR}/venv"

# Banner
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     RELACIONAR HILOS ODF CON ONUs AUTOMÁTICAMENTE          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Verificar si existe el entorno virtual
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}❌ No se encontró el entorno virtual en: $VENV_DIR${NC}"
    echo -e "${YELLOW}💡 Asegúrate de estar en el directorio correcto del proyecto${NC}"
    exit 1
fi

# Activar entorno virtual
echo -e "${BLUE}📦 Activando entorno virtual...${NC}"
source "${VENV_DIR}/bin/activate"

# Cambiar al directorio del proyecto
cd "$PROJECT_DIR"

# Mostrar información
echo -e "${BLUE}📂 Directorio del proyecto: ${PROJECT_DIR}${NC}"
echo ""

# Verificar si es dry-run
if [[ "$*" == *"--dry-run"* ]]; then
    echo -e "${YELLOW}⚠️  MODO DRY-RUN - No se aplicarán cambios, solo se mostrará qué se haría${NC}"
    echo ""
fi

# Ejecutar el comando de Django con todos los argumentos pasados
echo -e "${GREEN}🚀 Ejecutando comando de relación...${NC}"
echo ""

python manage.py relacionar_hilos_onus "$@"

# Capturar el código de salida
EXIT_CODE=$?

echo ""

# Desactivar entorno virtual
deactivate

# Mostrar resultado final
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Proceso completado exitosamente${NC}"
else
    echo -e "${RED}❌ El proceso terminó con errores (código: $EXIT_CODE)${NC}"
fi

# Salir con el mismo código de salida del comando Django
exit $EXIT_CODE

