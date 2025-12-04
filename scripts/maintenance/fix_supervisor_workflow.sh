#!/bin/bash
# Script para eliminar el worker workflow_main que no existe

CONF_FILE="/etc/supervisor/conf.d/facho_deluxe_v2.conf"
BACKUP_FILE="${CONF_FILE}.backup_$(date +%Y%m%d_%H%M%S)"

echo "🔧 Corrigiendo configuración de Supervisor..."

# Crear backup
sudo cp "$CONF_FILE" "$BACKUP_FILE"
echo "✅ Backup creado: $BACKUP_FILE"

# Eliminar celery_worker_workflow de la lista de programs
sudo sed -i 's/,celery_worker_workflow//g' "$CONF_FILE"
sudo sed -i 's/celery_worker_workflow,//g' "$CONF_FILE"

# Eliminar la sección completa del worker workflow
sudo sed -i '/\[program:celery_worker_workflow\]/,/^$/d' "$CONF_FILE"
sudo sed -i '/; Celery Worker Workflow/,/^$/d' "$CONF_FILE"

# Recargar configuración
sudo supervisorctl reread
sudo supervisorctl update

echo ""
echo "✅ Configuración corregida"
echo ""
echo "📊 Estado de workers:"
sudo supervisorctl status | grep -E "celery_worker|gunicorn|celery_beat|celery_coordinator|celery_cleanup"

