#!/bin/bash
# ============================================
# SCRIPT DE DESPLIEGUE INTELIGENTE - FACHO DELUXE v2
# ============================================
# 
# Solo instala/configura lo que falta:
# - Verifica e instala Gunicorn si falta
# - Configura HTTPS si está en el archivo
# - Actualiza Supervisor si hay cambios
# - NO ejecuta migraciones si ya están aplicadas
# - NO crea BD si ya existe
#
# Uso: sudo ./deploy_backend.sh
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
echo -e "${GREEN}  DESPLIEGUE INTELIGENTE FACHO DELUXE v2${NC}"
echo -e "${GREEN}  Solo instala/configura lo necesario${NC}"
echo -e "${GREEN}========================================${NC}"

# 1. Verificar permisos
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# 2. Leer configuración
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_CONFIG="/etc/facho_deluxe_2/backend.conf"
HTTPS_CONFIG="/etc/facho_deluxe_2/https.conf"
OLD_CONFIG="/etc/facho_deluxe_2/deploy.conf"

# Función para leer configuración
read_config() {
    local config_file=$1
    local section=$2
    local key=$3
    awk -F' = ' "/^\[$section\]/,/^\[/ {
        if (\$0 ~ /^#/ || \$0 ~ /^$/) next
        if (\$1 == \"$key\") {
            gsub(/[[:space:]]*#.*$/, \"\", \$2)
            gsub(/^[[:space:]]+|[[:space:]]+$/, \"\", \$2)
            print \$2
            exit
        }
    }" "$config_file"
}

# Migrar de deploy.conf antiguo a los nuevos archivos si existe
if [ -f "$OLD_CONFIG" ] && [ ! -f "$BACKEND_CONFIG" ]; then
    echo -e "${YELLOW}Migrando configuración de deploy.conf a backend.conf y https.conf...${NC}"
    
    # Leer valores del archivo antiguo
    OLD_DB_NAME=$(read_config "$OLD_CONFIG" "database" "name" || echo "Facho_BD")
    OLD_DB_USER=$(read_config "$OLD_CONFIG" "database" "user" || echo "")
    OLD_DB_PASSWORD=$(read_config "$OLD_CONFIG" "database" "password" || echo "")
    OLD_DB_HOST=$(read_config "$OLD_CONFIG" "database" "host" || echo "127.0.0.1")
    OLD_DB_PORT=$(read_config "$OLD_CONFIG" "database" "port" || echo "5432")
    OLD_API_IP=$(read_config "$OLD_CONFIG" "api" "api_ip" || echo "0.0.0.0")
    OLD_API_PORT=$(read_config "$OLD_CONFIG" "api" "api_port" || echo "8000")
    OLD_PROTOCOL=$(read_config "$OLD_CONFIG" "api" "protocol" || echo "http")
    OLD_HTTPS_DOMAIN=$(read_config "$OLD_CONFIG" "api" "https_domain" 2>/dev/null || echo "")
    OLD_SYSTEM_USER=$(read_config "$OLD_CONFIG" "system" "system_user" || echo "noc")
    OLD_SYSTEM_GROUP=$(read_config "$OLD_CONFIG" "system" "system_group" || echo "www-data")
    OLD_PROJECT_DIR=$(read_config "$OLD_CONFIG" "system" "project_directory" || echo "/opt/facho_deluxe_2")
    OLD_SUPERVISOR_PORT=$(read_config "$OLD_CONFIG" "supervisor" "supervisor_port" || echo "9001")
    OLD_SUPERVISOR_USER=$(read_config "$OLD_CONFIG" "supervisor" "supervisor_user" || echo "admin")
    OLD_SUPERVISOR_PASSWORD=$(read_config "$OLD_CONFIG" "supervisor" "supervisor_password" || echo "facho2025")
    
    # Crear backend.conf
    mkdir -p /etc/facho_deluxe_2
    cat > "$BACKEND_CONFIG" <<EOF
# ============================================
# CONFIGURACIÓN BACKEND - FACHO DELUXE v2
# ============================================
# Migrado desde deploy.conf el $(date '+%Y-%m-%d %H:%M:%S')
# Este archivo contiene información sensible. NO compartir ni subir a git.

[database]
name = $OLD_DB_NAME
user = $OLD_DB_USER
password = $OLD_DB_PASSWORD
host = $OLD_DB_HOST
port = $OLD_DB_PORT

[api]
api_ip = $OLD_API_IP
api_port = $OLD_API_PORT

[pollers]
max_pollers_per_olt = 10
max_consultas_simultaneas = 5
tamano_lote_inicial = 200

[supervisor]
supervisor_port = $OLD_SUPERVISOR_PORT
supervisor_user = $OLD_SUPERVISOR_USER
supervisor_password = $OLD_SUPERVISOR_PASSWORD

[system]
system_user = $OLD_SYSTEM_USER
system_group = $OLD_SYSTEM_GROUP
project_directory = $OLD_PROJECT_DIR

[django]
django_username = 
django_email = 
EOF
    
    chmod 600 "$BACKEND_CONFIG"
    chown root:root "$BACKEND_CONFIG"
    
    # Crear https.conf si hay configuración HTTPS
    if [ "$OLD_PROTOCOL" = "https" ] && [ -n "$OLD_HTTPS_DOMAIN" ]; then
        cat > "$HTTPS_CONFIG" <<EOF
# ============================================
# CONFIGURACIÓN HTTPS - FACHO DELUXE v2
# ============================================
# Migrado desde deploy.conf el $(date '+%Y-%m-%d %H:%M:%S')
# Este archivo contiene información sensible. NO compartir ni subir a git.

[https]
protocol = https
https_domain = $OLD_HTTPS_DOMAIN
https_port = 443
ssl_cert_path = /etc/ssl/facho_deluxe_2/facho-backend.crt
ssl_key_path = /etc/ssl/facho_deluxe_2/facho-backend.key
ssl_cert_days = 365
EOF
        chmod 600 "$HTTPS_CONFIG"
        chown root:root "$HTTPS_CONFIG"
    fi
    
    echo -e "${GREEN}✓ Configuración migrada${NC}"
    echo -e "${BLUE}→ Backup del archivo antiguo: ${OLD_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)${NC}"
    cp "$OLD_CONFIG" "${OLD_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
fi

if [ ! -f "$BACKEND_CONFIG" ]; then
    echo -e "${RED}Error: No se encontró: $BACKEND_CONFIG${NC}"
    echo -e "${YELLOW}Ejecuta primero el despliegue inicial o crea el archivo manualmente.${NC}"
    exit 1
fi

echo -e "\n${YELLOW}[1/8] Leyendo configuración...${NC}"

# Leer valores desde backend.conf
DB_NAME=$(read_config "$BACKEND_CONFIG" "database" "name" || echo "Facho_BD")
API_IP=$(read_config "$BACKEND_CONFIG" "api" "api_ip" || echo "0.0.0.0")
API_PORT=$(read_config "$BACKEND_CONFIG" "api" "api_port" || echo "8000")
SYSTEM_USER=$(read_config "$BACKEND_CONFIG" "system" "system_user" || echo "noc")
SYSTEM_GROUP=$(read_config "$BACKEND_CONFIG" "system" "system_group" || echo "www-data")
PROJECT_DIR=$(read_config "$BACKEND_CONFIG" "system" "project_directory" || echo "/opt/facho_deluxe_2")
SUPERVISOR_PORT=$(read_config "$BACKEND_CONFIG" "supervisor" "supervisor_port" || echo "9001")
SUPERVISOR_USER=$(read_config "$BACKEND_CONFIG" "supervisor" "supervisor_user" || echo "admin")
SUPERVISOR_PASSWORD=$(read_config "$BACKEND_CONFIG" "supervisor" "supervisor_password" || echo "facho2025")

# Leer configuración HTTPS (opcional)
if [ -f "$HTTPS_CONFIG" ]; then
    PROTOCOL=$(read_config "$HTTPS_CONFIG" "https" "protocol" || echo "http")
    HTTPS_DOMAIN=$(read_config "$HTTPS_CONFIG" "https" "https_domain" 2>/dev/null || echo "")
else
    PROTOCOL="http"
    HTTPS_DOMAIN=""
fi

VENV_DIR="$PROJECT_DIR/venv"

echo -e "${GREEN}✓ Configuración leída${NC}"
echo -e "${BLUE}  Protocolo: $PROTOCOL${NC}"
echo -e "${BLUE}  API: $API_IP:$API_PORT${NC}"

# 3. Verificar e instalar Gunicorn
echo -e "\n${YELLOW}[2/8] Verificando Gunicorn...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}⚠️ Entorno virtual no existe. Creándolo...${NC}"
    sudo -u $SYSTEM_USER python3 -m venv "$VENV_DIR"
fi

if "$VENV_DIR/bin/pip" show gunicorn > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Gunicorn ya está instalado${NC}"
else
    echo -e "${BLUE}→ Instalando Gunicorn...${NC}"
    sudo -u $SYSTEM_USER "$VENV_DIR/bin/pip" install --upgrade pip > /dev/null 2>&1
    sudo -u $SYSTEM_USER "$VENV_DIR/bin/pip" install gunicorn
    echo -e "${GREEN}✓ Gunicorn instalado${NC}"
fi

# 4. Verificar dependencias críticas
echo -e "\n${YELLOW}[3/8] Verificando dependencias críticas...${NC}"
MISSING=()

for pkg in django psycopg2-binary celery; do
    if ! "$VENV_DIR/bin/pip" show "$pkg" > /dev/null 2>&1; then
        MISSING+=("$pkg")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo -e "${BLUE}→ Instalando: ${MISSING[*]}...${NC}"
    sudo -u $SYSTEM_USER "$VENV_DIR/bin/pip" install "${MISSING[@]}"
    echo -e "${GREEN}✓ Dependencias instaladas${NC}"
else
    echo -e "${GREEN}✓ Dependencias críticas OK${NC}"
fi

# 5. Verificar migraciones (solo si hay pendientes)
echo -e "\n${YELLOW}[4/8] Verificando migraciones...${NC}"
cd "$PROJECT_DIR"
PENDING=$(("$VENV_DIR/bin/python" manage.py showmigrations --plan 2>/dev/null | grep -c "\[ \]" || echo "0"))

if [ "$PENDING" -gt 0 ]; then
    echo -e "${BLUE}→ Aplicando $PENDING migración(es) pendiente(s)...${NC}"
    sudo -u $SYSTEM_USER "$VENV_DIR/bin/python" manage.py migrate --noinput
    echo -e "${GREEN}✓ Migraciones aplicadas${NC}"
else
    echo -e "${GREEN}✓ No hay migraciones pendientes${NC}"
fi

# 6. Actualizar archivos estáticos
echo -e "\n${YELLOW}[5/8] Actualizando archivos estáticos...${NC}"
sudo -u $SYSTEM_USER "$VENV_DIR/bin/python" manage.py collectstatic --noinput --clear > /dev/null 2>&1
echo -e "${GREEN}✓ Archivos estáticos actualizados${NC}"

# 7. Configurar/Actualizar Supervisor
echo -e "\n${YELLOW}[6/8] Configurando Supervisor...${NC}"

# Crear logs si no existe
mkdir -p "$PROJECT_DIR/logs"
chown -R $SYSTEM_USER:$SYSTEM_GROUP "$PROJECT_DIR/logs"

# Actualizar configuración de Supervisor
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

# 8. Configuración HTTPS (verificar que Django la lea)
echo -e "\n${YELLOW}[7/8] Verificando configuración HTTPS...${NC}"
if [ "$PROTOCOL" = "https" ]; then
    echo -e "${GREEN}✓ HTTPS configurado en https.conf${NC}"
    echo -e "${BLUE}→ Django configurará automáticamente headers de seguridad${NC}"
    if [ -n "$HTTPS_DOMAIN" ]; then
        echo -e "${BLUE}→ Dominio: $HTTPS_DOMAIN${NC}"
    fi
    echo -e "${YELLOW}⚠️  Configura NGINX para terminar SSL (ver DEPLOY_HTTPS.md)${NC}"
else
    echo -e "${BLUE}→ Protocolo HTTP (sin HTTPS)${NC}"
fi

# 9. Actualizar servicios de Supervisor
echo -e "\n${YELLOW}[8/8] Actualizando servicios...${NC}"
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
echo -e "${GREEN}  DESPLIEGUE COMPLETADO${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Estado:${NC}"
supervisorctl status facho_deluxe_v2:* 2>/dev/null | head -5
echo -e "\n${BLUE}API:${NC} $PROTOCOL://$API_IP:$API_PORT"
if [ "$PROTOCOL" = "https" ]; then
    echo -e "${BLUE}Dominio HTTPS:${NC} ${HTTPS_DOMAIN:-'No configurado'}"
fi
echo -e "${BLUE}Supervisor UI:${NC} http://$API_IP:$SUPERVISOR_PORT"
echo -e "${GREEN}════════════════════════════════════════${NC}"
