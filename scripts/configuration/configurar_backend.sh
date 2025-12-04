#!/bin/bash
# ============================================
# CONFIGURAR BACKEND - FACHO DELUXE v2
# ============================================
# 
# Este script configura SOLO el backend Django:
# - Instala/actualiza dependencias
# - Ejecuta migraciones
# - Configura Supervisor
# - NO configura HTTPS (usar configurar_https.sh)
#
# Uso: sudo ./configurar_backend.sh
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
echo -e "${GREEN}  CONFIGURACIÓN BACKEND${NC}"
echo -e "${GREEN}  FACHO DELUXE v2${NC}"
echo -e "${GREEN}========================================${NC}"

# Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# Leer configuración
BACKEND_CONFIG="/etc/facho_deluxe_2/backend.conf"

if [ ! -f "$BACKEND_CONFIG" ]; then
    echo -e "${RED}Error: No se encontró: $BACKEND_CONFIG${NC}"
    echo -e "${YELLOW}Ejecuta primero: sudo ./deploy_backend.sh${NC}"
    exit 1
fi

# Función para leer configuración
read_config() {
    local section=$1
    local key=$2
    awk -F' = ' "/^\[$section\]/,/^\[/ {
        if (\$0 ~ /^#/ || \$0 ~ /^$/) next
        if (\$1 == \"$key\") {
            gsub(/[[:space:]]*#.*$/, \"\", \$2)
            gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", \$2)
            print \$2
            exit
        }
    }" "$BACKEND_CONFIG"
}

echo -e "\n${YELLOW}[1/6] Leyendo configuración...${NC}"

API_IP=$(read_config "api" "api_ip" || echo "0.0.0.0")
API_PORT=$(read_config "api" "api_port" || echo "8000")
SYSTEM_USER=$(read_config "system" "system_user" || echo "noc")
SYSTEM_GROUP=$(read_config "system" "system_group" || echo "www-data")
PROJECT_DIR=$(read_config "system" "project_directory" || echo "/opt/facho_deluxe_2")
SUPERVISOR_PORT=$(read_config "supervisor" "supervisor_port" || echo "9001")
SUPERVISOR_USER=$(read_config "supervisor" "supervisor_user" || echo "admin")
SUPERVISOR_PASSWORD=$(read_config "supervisor" "supervisor_password" || echo "facho2025")

VENV_DIR="$PROJECT_DIR/venv"

echo -e "${GREEN}✓ Configuración leída${NC}"
echo -e "${BLUE}  API: $API_IP:$API_PORT${NC}"
echo -e "${BLUE}  Directorio: $PROJECT_DIR${NC}"

# 1. Verificar entorno virtual
echo -e "\n${YELLOW}[2/6] Verificando entorno virtual...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${BLUE}→ Creando entorno virtual...${NC}"
    sudo -u $SYSTEM_USER python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Entorno virtual creado${NC}"
else
    echo -e "${GREEN}✓ Entorno virtual ya existe${NC}"
fi

# 2. Instalar/actualizar dependencias
echo -e "\n${YELLOW}[3/6] Instalando/actualizando dependencias...${NC}"
sudo -u $SYSTEM_USER "$VENV_DIR/bin/pip" install --upgrade pip --quiet
sudo -u $SYSTEM_USER "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet
echo -e "${GREEN}✓ Dependencias instaladas${NC}"

# 3. Verificar migraciones
echo -e "\n${YELLOW}[4/6] Verificando migraciones...${NC}"
cd "$PROJECT_DIR"
PENDING=$("$VENV_DIR/bin/python" manage.py showmigrations --plan 2>/dev/null | grep -c "\[ \]" || echo "0")

if [ "$PENDING" -gt 0 ]; then
    echo -e "${BLUE}→ Aplicando $PENDING migración(es) pendiente(s)...${NC}"
    sudo -u $SYSTEM_USER "$VENV_DIR/bin/python" manage.py migrate --noinput
    echo -e "${GREEN}✓ Migraciones aplicadas${NC}"
else
    echo -e "${GREEN}✓ No hay migraciones pendientes${NC}"
fi

# 4. Recolectar archivos estáticos
echo -e "\n${YELLOW}[5/6] Recolectando archivos estáticos...${NC}"
sudo -u $SYSTEM_USER "$VENV_DIR/bin/python" manage.py collectstatic --noinput --clear > /dev/null 2>&1
echo -e "${GREEN}✓ Archivos estáticos recolectados${NC}"

# 5. Configurar Supervisor
echo -e "\n${YELLOW}[6/6] Configurando Supervisor...${NC}"

# Crear logs si no existe
mkdir -p "$PROJECT_DIR/logs"
chown -R $SYSTEM_USER:$SYSTEM_GROUP "$PROJECT_DIR/logs"

# Crear configuración de Supervisor
cat > /etc/supervisor/conf.d/facho_deluxe_v2.conf <<EOF
[group:facho_deluxe_v2]
programs=gunicorn,celery_worker_main,celery_worker_discovery,celery_worker_discovery_manual,celery_worker_get,celery_worker_get_manual,celery_beat,celery_cleanup

[program:gunicorn]
command=$VENV_DIR/bin/gunicorn core.wsgi:application --workers 3 --bind $API_IP:$API_PORT --timeout 300 --keep-alive 2
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/gunicorn.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=DJANGO_SETTINGS_MODULE="core.settings"

[program:celery_worker_main]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=default,odf_sync,get_main --concurrency=10 --prefetch-multiplier=1 --max-tasks-per-child=1000 --hostname=main_worker@%%h
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_main.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=60
stopasgroup=true
killasgroup=true
environment=DJANGO_SETTINGS_MODULE="core.settings"

[program:celery_worker_discovery]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=discovery_main,discovery_retry --concurrency=20 --prefetch-multiplier=1 --max-tasks-per-child=500 --hostname=discovery_worker@%%h
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_discovery.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

[program:celery_worker_discovery_manual]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=discovery_manual --concurrency=10 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=discovery_manual_worker@%%h
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_discovery_manual.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

[program:celery_worker_get]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=get_main,get_retry,get_poller --concurrency=20 --prefetch-multiplier=1 --max-tasks-per-child=1000 --hostname=get_worker@%%h
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_get.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

[program:celery_worker_get_manual]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=get_manual --concurrency=10 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=get_manual_worker@%%h
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_get_manual.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

[program:celery_beat]
command=$VENV_DIR/bin/celery -A core beat --loglevel=INFO
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_beat.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=DJANGO_SETTINGS_MODULE="core.settings"

[program:celery_cleanup]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=cleanup,background_deletes --concurrency=3 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=cleanup_worker@%%h
directory=$PROJECT_DIR
user=$SYSTEM_USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_cleanup.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"
EOF

# Configurar interfaz web de Supervisor
if ! grep -q "\[inet_http_server\]" /etc/supervisor/supervisord.conf; then
    cat >> /etc/supervisor/supervisord.conf <<EOF

[inet_http_server]
port=$API_IP:$SUPERVISOR_PORT
username=$SUPERVISOR_USER
password=$SUPERVISOR_PASSWORD
EOF
fi

echo -e "${GREEN}✓ Supervisor configurado${NC}"

# Reiniciar Supervisor
systemctl restart supervisor > /dev/null 2>&1 || service supervisor restart > /dev/null 2>&1
sleep 2

supervisorctl reread > /dev/null 2>&1
supervisorctl update > /dev/null 2>&1

# Reiniciar o iniciar servicios
if supervisorctl status facho_deluxe_v2:gunicorn 2>/dev/null | grep -q RUNNING; then
    supervisorctl restart facho_deluxe_v2:* > /dev/null 2>&1
    echo -e "${BLUE}→ Servicios reiniciados${NC}"
else
    supervisorctl start facho_deluxe_v2:* > /dev/null 2>&1
    echo -e "${BLUE}→ Servicios iniciados${NC}"
fi

echo -e "${GREEN}✓ Servicios actualizados${NC}"

# Resumen
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  BACKEND CONFIGURADO EXITOSAMENTE${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Estado:${NC}"
supervisorctl status facho_deluxe_v2:* 2>/dev/null | head -5
echo -e "\n${BLUE}Backend:${NC} http://$API_IP:$API_PORT"
echo -e "${BLUE}Supervisor UI:${NC} http://$API_IP:$SUPERVISOR_PORT"
echo -e "\n${GREEN}════════════════════════════════════════${NC}"

