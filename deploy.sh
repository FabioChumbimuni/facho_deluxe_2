#!/bin/bash
# Script de despliegue automático para Facho Deluxe v2 con Supervisor
# Basado en el sistema avanzado de /opt/facho_deluxe
# Autor: Sistema de Despliegue v2
# Fecha: $(date +%Y-%m-%d)

set -e  # Detener si hay errores

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sin color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  DESPLIEGUE AUTOMÁTICO FACHO DELUXE v2${NC}"
echo -e "${GREEN}  Con Supervisor Process Manager${NC}"
echo -e "${GREEN}========================================${NC}"

# 1. Verificar permisos de sudo
echo -e "\n${YELLOW}[1/12] Verificando permisos...${NC}"
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: Este script debe ejecutarse con sudo${NC}"
    exit 1
fi

# Variables de configuración
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"
VENV_DIR="$PROJECT_DIR/venv"
USER="noc"
GROUP="www-data"
BIND_PORT="8000"
SUPERVISOR_PORT="9001"

echo -e "\n${BLUE}Directorio del proyecto: $PROJECT_DIR${NC}"

# Solicitar configuración de base de datos completa
echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}   CONFIGURACIÓN DE BASE DE DATOS${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Nombre de la base de datos
echo -e "${YELLOW}Nombre de la base de datos:${NC}"
read -p "$(echo -e ${BLUE}Nombre [Enter para usar 'Facho_BD']: ${NC})" DB_NAME
if [ -z "$DB_NAME" ]; then
    DB_NAME="Facho_BD"
    echo -e "${GREEN}→ Usando nombre por defecto: 'Facho_BD'${NC}"
else
    echo -e "${GREEN}→ Nombre configurado: '$DB_NAME'${NC}"
fi

# Usuario de PostgreSQL
echo -e "\n${YELLOW}Usuario de PostgreSQL:${NC}"
read -p "$(echo -e ${BLUE}Usuario [Enter para usar 'Admin_Facho']: ${NC})" DB_USER
if [ -z "$DB_USER" ]; then
    DB_USER="Admin_Facho"
    echo -e "${GREEN}→ Usando usuario por defecto: 'Admin_Facho'${NC}"
else
    echo -e "${GREEN}→ Usuario configurado: '$DB_USER'${NC}"
fi

# Contraseña
echo -e "\n${YELLOW}Contraseña para el usuario '$DB_USER':${NC}"
read -s -p "$(echo -e ${BLUE}Contraseña [Enter para usar 'facho']: ${NC})" DB_PASSWORD
echo ""
if [ -z "$DB_PASSWORD" ]; then
    DB_PASSWORD="facho"
    echo -e "${GREEN}→ Usando contraseña por defecto: 'facho'${NC}"
else
    echo -e "${GREEN}→ Contraseña personalizada configurada${NC}"
fi

# Host de PostgreSQL
echo -e "\n${YELLOW}Host de PostgreSQL:${NC}"
read -p "$(echo -e ${BLUE}Host [Enter para usar '127.0.0.1']: ${NC})" DB_HOST
if [ -z "$DB_HOST" ]; then
    DB_HOST="127.0.0.1"
    echo -e "${GREEN}→ Usando host por defecto: '127.0.0.1'${NC}"
else
    echo -e "${GREEN}→ Host configurado: '$DB_HOST'${NC}"
fi

# Puerto de PostgreSQL
echo -e "\n${YELLOW}Puerto de PostgreSQL:${NC}"
read -p "$(echo -e ${BLUE}Puerto [Enter para usar '5432']: ${NC})" DB_PORT
if [ -z "$DB_PORT" ]; then
    DB_PORT="5432"
    echo -e "${GREEN}→ Usando puerto por defecto: '5432'${NC}"
else
    echo -e "${GREEN}→ Puerto configurado: '$DB_PORT'${NC}"
fi

echo -e "\n${GREEN}✓ Configuración de base de datos:${NC}"
echo -e "${BLUE}  - Nombre:     $DB_NAME${NC}"
echo -e "${BLUE}  - Usuario:    $DB_USER${NC}"
echo -e "${BLUE}  - Contraseña: ****${NC}"
echo -e "${BLUE}  - Host:       $DB_HOST${NC}"
echo -e "${BLUE}  - Puerto:     $DB_PORT${NC}"

# Obtener IP del servidor
echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}   CONFIGURACIÓN DE RED${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Parámetros: ./deploy.sh [IP] [PUERTO]
if [ -n "$1" ]; then
    # Si se pasó IP como parámetro
    BIND_IP="$1"
    echo -e "${GREEN}→ Usando IP del parámetro: $BIND_IP${NC}"
    
    # Si también se pasó puerto como segundo parámetro
    if [ -n "$2" ]; then
        BIND_PORT="$2"
        echo -e "${GREEN}→ Usando puerto del parámetro: $BIND_PORT${NC}"
    fi
else
    # Mostrar todas las IPs disponibles
    echo -e "\n${YELLOW}IPs disponibles en este servidor:${NC}"
    ALL_IPS=($(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1'))
    
    if [ ${#ALL_IPS[@]} -eq 0 ]; then
        echo -e "${RED}No se detectaron IPs (excepto localhost)${NC}"
        ALL_IPS=("127.0.0.1")
    fi
    
    # Mostrar lista numerada
    for i in "${!ALL_IPS[@]}"; do
        INTERFACE=$(ip -4 addr show | grep -B2 "${ALL_IPS[$i]}" | head -1 | awk '{print $2}' | tr -d ':')
        echo -e "  ${BLUE}[$((i+1))]${NC} ${ALL_IPS[$i]} ${GREEN}(${INTERFACE})${NC}"
    done
    
    # Detectar IP principal (la que usa para Internet)
    DEFAULT_IP=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K[^ ]+' || echo "${ALL_IPS[0]}")
    
    echo -e "\n${YELLOW}→ IP recomendada (para salida a Internet): $DEFAULT_IP${NC}"
    echo -e "${BLUE}Opciones:${NC}"
    echo -e "  - Presiona ${GREEN}Enter${NC} para usar: $DEFAULT_IP"
    echo -e "  - Escribe el ${GREEN}número [1,2,...]${NC} de la lista"
    echo -e "  - Escribe una ${GREEN}IP personalizada${NC}"
    
    read -p "$(echo -e ${BLUE}Tu elección: ${NC})" USER_INPUT
    
    if [ -z "$USER_INPUT" ]; then
        # Enter presionado - usar IP recomendada
        BIND_IP="$DEFAULT_IP"
        echo -e "${GREEN}→ Usando IP recomendada: $BIND_IP${NC}"
    elif [[ "$USER_INPUT" =~ ^[0-9]+$ ]] && [ "$USER_INPUT" -ge 1 ] && [ "$USER_INPUT" -le "${#ALL_IPS[@]}" ]; then
        # Número seleccionado
        BIND_IP="${ALL_IPS[$((USER_INPUT-1))]}"
        echo -e "${GREEN}→ Usando IP seleccionada: $BIND_IP${NC}"
    else
        # IP personalizada
        BIND_IP="$USER_INPUT"
        echo -e "${GREEN}→ Usando IP personalizada: $BIND_IP${NC}"
    fi
fi

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${GREEN}✓ IP configurada: $BIND_IP${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"

# Configurar puerto (solo si no se pasó como parámetro)
if [ -z "$2" ]; then
    echo -e "\n${BLUE}Puerto del servidor web:${NC}"
    read -p "$(echo -e ${BLUE}Puerto [Enter para usar 8000]: ${NC})" USER_PORT
    if [ -n "$USER_PORT" ]; then
        BIND_PORT="$USER_PORT"
        echo -e "${GREEN}→ Puerto configurado: $BIND_PORT${NC}"
    else
        BIND_PORT="8000"
        echo -e "${GREEN}→ Puerto configurado: $BIND_PORT (por defecto)${NC}"
    fi
else
    echo -e "\n${GREEN}✓ Puerto configurado: $BIND_PORT${NC}"
fi

# 2. Crear base de datos PostgreSQL automáticamente
echo -e "\n${YELLOW}[2/12] Creando base de datos PostgreSQL automáticamente...${NC}"
echo -e "${BLUE}→ Verificando si el usuario '$DB_USER' existe...${NC}"
sudo -u postgres psql -tc "SELECT 1 FROM pg_user WHERE usename = '$DB_USER'" | grep -q 1 && {
    echo -e "${BLUE}  Usuario '$DB_USER' ya existe${NC}"
} || {
    echo -e "${BLUE}  Creando usuario '$DB_USER'...${NC}"
    sudo -u postgres psql -c "CREATE USER \"$DB_USER\" WITH PASSWORD '$DB_PASSWORD';"
    echo -e "${GREEN}  ✓ Usuario '$DB_USER' creado${NC}"
}

echo -e "${BLUE}→ Verificando si la base de datos '$DB_NAME' existe...${NC}"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 && {
    echo -e "${BLUE}  Base de datos '$DB_NAME' ya existe${NC}"
} || {
    echo -e "${BLUE}  Creando base de datos '$DB_NAME'...${NC}"
    sudo -u postgres psql -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";"
    echo -e "${GREEN}  ✓ Base de datos '$DB_NAME' creada${NC}"
}

echo -e "${BLUE}→ Otorgando privilegios...${NC}"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \"$DB_NAME\" TO \"$DB_USER\";"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO \"$DB_USER\";"
sudo -u postgres psql -d "$DB_NAME" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO \"$DB_USER\";"
sudo -u postgres psql -d "$DB_NAME" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO \"$DB_USER\";"

echo -e "${GREEN}✓ Base de datos PostgreSQL configurada correctamente${NC}"

# 3. Preparar permisos del proyecto
echo -e "\n${YELLOW}[3/12] Configurando permisos del proyecto...${NC}"
chown -R $USER:$GROUP "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"
echo -e "${GREEN}✓ Permisos configurados${NC}"

# 4. Crear entorno virtual si no existe
echo -e "\n${YELLOW}[4/12] Configurando entorno virtual...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    sudo -u $USER python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Entorno virtual creado${NC}"
fi

# 5. Instalar dependencias
echo -e "\n${YELLOW}[5/12] Instalando dependencias...${NC}"
sudo -u $USER "$VENV_DIR/bin/pip" install --upgrade pip
echo -e "${BLUE}→ Instalando setuptools (requerido)...${NC}"
sudo -u $USER "$VENV_DIR/bin/pip" install setuptools
echo -e "${BLUE}→ Instalando requirements.txt...${NC}"
sudo -u $USER "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
echo -e "${GREEN}✓ Dependencias instaladas${NC}"

# 6. Configurar archivo de configuración (config.ini)
echo -e "\n${YELLOW}[6/12] Creando archivo de configuración...${NC}"
CONFIG_FILE="$PROJECT_DIR/config.ini"

cat > "$CONFIG_FILE" << EOF
[database]
name = $DB_NAME
user = $DB_USER
password = $DB_PASSWORD
host = $DB_HOST
port = $DB_PORT

[deployment]
bind_ip = $BIND_IP
bind_port = $BIND_PORT
supervisor_port = $SUPERVISOR_PORT
EOF

chown $USER:$GROUP "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"  # Solo el usuario puede leer

echo -e "${GREEN}✓ Archivo de configuración creado: config.ini${NC}"
echo -e "${GREEN}  - DB_NAME: $DB_NAME${NC}"
echo -e "${GREEN}  - DB_USER: $DB_USER${NC}"
echo -e "${GREEN}  - DB_HOST: $DB_HOST${NC}"
echo -e "${GREEN}  - DB_PORT: $DB_PORT${NC}"
echo -e "${GREEN}  - DB_PASSWORD: **** (protegido en config.ini)${NC}"

# Asegurar que ALLOWED_HOSTS sea ['*'] en settings.py
SETTINGS_FILE="$PROJECT_DIR/core/settings.py"
if [ -f "$SETTINGS_FILE" ]; then
    echo -e "${BLUE}→ Configurando ALLOWED_HOSTS = ['*']...${NC}"
    sed -i "s/ALLOWED_HOSTS = \[.*\]/ALLOWED_HOSTS = ['*']/" "$SETTINGS_FILE"
    echo -e "${GREEN}✓ ALLOWED_HOSTS configurado${NC}"
fi

# 7. Ejecutar migraciones
echo -e "\n${YELLOW}[7/12] Ejecutando migraciones de base de datos...${NC}"
cd "$PROJECT_DIR"
sudo -u $USER "$VENV_DIR/bin/python" manage.py migrate --noinput
echo -e "${GREEN}✓ Migraciones completadas${NC}"

# 8. Recolectar archivos estáticos
echo -e "\n${YELLOW}[8/12] Recolectando archivos estáticos...${NC}"
sudo -u $USER "$VENV_DIR/bin/python" manage.py collectstatic --noinput --clear
echo -e "${GREEN}✓ Archivos estáticos recolectados${NC}"

# 9. Instalar Supervisor
echo -e "\n${YELLOW}[9/12] Instalando Supervisor...${NC}"
apt-get update -qq
apt-get install -y supervisor
echo -e "${GREEN}✓ Supervisor instalado${NC}"

# 10. Crear directorio de logs
echo -e "\n${YELLOW}[10/12] Creando directorio de logs...${NC}"
mkdir -p "$PROJECT_DIR/logs"
chown -R $USER:$GROUP "$PROJECT_DIR/logs"
echo -e "${GREEN}✓ Directorio de logs creado${NC}"

# 11. Configurar Supervisor
echo -e "\n${YELLOW}[11/12] Configurando Supervisor para Facho Deluxe v2...${NC}"

# Crear archivo de configuración de Supervisor para el proyecto
cat > /etc/supervisor/conf.d/facho_deluxe_v2.conf <<EOF
; ========================================
; Configuración de Supervisor para Facho Deluxe v2
; ========================================

; Grupo para controlar todos los procesos juntos
[group:facho_deluxe_v2]
programs=gunicorn,celery_worker_main,celery_worker_discovery,celery_worker_discovery_manual,celery_worker_get,celery_worker_get_manual,celery_beat,celery_cleanup

; ========================================
; Gunicorn - Servidor Web Django
; ========================================
[program:gunicorn]
command=$VENV_DIR/bin/gunicorn core.wsgi:application --workers 3 --bind $BIND_IP:$BIND_PORT --timeout 120 --keep-alive 2
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/gunicorn.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=DJANGO_SETTINGS_MODULE="core.settings"

; ========================================
; Celery Worker Principal - Colas default, odf_sync, get_main
; ========================================
[program:celery_worker_main]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=default,odf_sync,get_main --concurrency=10 --prefetch-multiplier=1 --max-tasks-per-child=1000 --hostname=main_worker@%%h
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_main.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

; ========================================
; Celery Worker Discovery - Cola discovery_main, discovery_retry
; ========================================
[program:celery_worker_discovery]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=discovery_main,discovery_retry --concurrency=20 --prefetch-multiplier=1 --max-tasks-per-child=500 --hostname=discovery_worker@%%h
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_discovery.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

; ========================================
; Celery Worker Discovery MANUAL - MÁXIMA PRIORIDAD
; ========================================
[program:celery_worker_discovery_manual]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=discovery_manual --concurrency=10 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=discovery_manual_worker@%%h
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_discovery_manual.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

; ========================================
; Celery Worker GET - Colas get_main, get_retry, get_poller
; ========================================
[program:celery_worker_get]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=get_main,get_retry,get_poller --concurrency=15 --prefetch-multiplier=1 --max-tasks-per-child=1000 --hostname=get_worker@%%h
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_get.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

; ========================================
; Celery Worker GET MANUAL - MÁXIMA PRIORIDAD
; ========================================
[program:celery_worker_get_manual]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=get_manual --concurrency=10 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=get_manual_worker@%%h
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_worker_get_manual.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"

; ========================================
; Celery Beat - Scheduler de Tareas
; ========================================
[program:celery_beat]
command=$VENV_DIR/bin/celery -A core beat --loglevel=INFO
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_beat.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=DJANGO_SETTINGS_MODULE="core.settings"

; ========================================
; Celery Worker Cleanup - Colas cleanup, background_deletes
; ========================================
[program:celery_cleanup]
command=$VENV_DIR/bin/celery -A core worker --loglevel=INFO --queues=cleanup,background_deletes --concurrency=3 --prefetch-multiplier=1 --max-tasks-per-child=100 --hostname=cleanup_worker@%%h
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$PROJECT_DIR/logs/celery_cleanup.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
stopwaitsecs=600
environment=DJANGO_SETTINGS_MODULE="core.settings"
EOF

# Habilitar interfaz web de Supervisor
echo -e "${BLUE}→ Configurando interfaz web de Supervisor...${NC}"
cat > /etc/supervisor/supervisord.conf <<EOF
; supervisor config file

[unix_http_server]
file=/var/run/supervisor.sock
chmod=0700

[supervisord]
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid
childlogdir=/var/log/supervisor

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock

; Habilitar interfaz web
[inet_http_server]
port=$BIND_IP:$SUPERVISOR_PORT
username=admin
password=facho2025

[include]
files = /etc/supervisor/conf.d/*.conf
EOF

echo -e "${GREEN}✓ Configuración de Supervisor creada${NC}"

# 12. Reiniciar Supervisor y cargar configuración
echo -e "\n${YELLOW}[12/12] Iniciando servicios con Supervisor...${NC}"

# Reiniciar servicio de Supervisor
systemctl restart supervisor
sleep 2

# Recargar configuración de Supervisor
supervisorctl reread
supervisorctl update

# Iniciar todos los procesos
supervisorctl start facho_deluxe_v2:*

# Verificar estado
echo -e "\n${BLUE}Estado de los procesos:${NC}"
supervisorctl status

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  DESPLIEGUE COMPLETADO EXITOSAMENTE${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Información del despliegue:${NC}"
echo -e "  ${BLUE}Proyecto:${NC} $PROJECT_DIR"
echo -e "\n${YELLOW}📊 Base de datos PostgreSQL:${NC}"
echo -e "  ${BLUE}Nombre:${NC} $DB_NAME"
echo -e "  ${BLUE}Usuario:${NC} $DB_USER"
echo -e "  ${BLUE}Host:${NC} $DB_HOST"
echo -e "  ${BLUE}Puerto:${NC} $DB_PORT"
echo -e "\n${YELLOW}🌐 Servicios Web:${NC}"
echo -e "  ${BLUE}Servidor Web:${NC} http://$BIND_IP:$BIND_PORT"
echo -e "  ${BLUE}Supervisor Web UI:${NC} http://$BIND_IP:$SUPERVISOR_PORT"
echo -e "  ${BLUE}Credenciales UI:${NC} admin / facho2025"

echo -e "\n${YELLOW}Comandos útiles de Supervisor:${NC}"
echo -e "  ${BLUE}Ver estado:${NC} sudo supervisorctl status"
echo -e "  ${BLUE}Reiniciar todo:${NC} sudo supervisorctl restart facho_deluxe_v2:*"
echo -e "  ${BLUE}Ver logs:${NC} sudo supervisorctl tail -f facho_deluxe_v2:celery_worker_main"
echo -e "  ${BLUE}Detener todo:${NC} sudo supervisorctl stop facho_deluxe_v2:*"
echo -e "  ${BLUE}Iniciar todo:${NC} sudo supervisorctl start facho_deluxe_v2:*"

echo -e "\n${YELLOW}📊 Logs de los servicios:${NC}"
echo -e "${BLUE}Ubicación:${NC} $PROJECT_DIR/logs/"
echo -e "\n${BLUE}Archivos de log:${NC}"
echo -e "  • ${GREEN}gunicorn.log${NC}              → Servidor web Django"
echo -e "  • ${GREEN}celery_worker_main.log${NC}     → Worker principal (default, odf_sync, get_main)"
echo -e "  • ${GREEN}celery_worker_discovery.log${NC} → Worker discovery (discovery_main, discovery_retry)"
echo -e "  • ${GREEN}celery_worker_get.log${NC}      → Worker GET (get_main, get_retry, get_poller)"
echo -e "  • ${GREEN}celery_beat.log${NC}            → Scheduler de tareas"
echo -e "  • ${GREEN}celery_cleanup.log${NC}         → Worker cleanup (cleanup, background_deletes)"

echo -e "\n${YELLOW}Ver logs en tiempo real:${NC}"
echo -e "  ${BLUE}Supervisor:${NC} sudo supervisorctl tail -f facho_deluxe_v2:celery_worker_main"
echo -e "  ${BLUE}Directo:${NC}    tail -f $PROJECT_DIR/logs/celery_worker_main.log"

# Mostrar instrucciones para acceder a la interfaz web
echo -e "\n${BLUE}════════════════════════════════════════${NC}"
echo -e "${GREEN}🌐 Interfaz web de Supervisor:${NC}"
echo -e "${BLUE}URL:${NC} http://$BIND_IP:$SUPERVISOR_PORT"
echo -e "${BLUE}Usuario:${NC} admin"
echo -e "${BLUE}Contraseña:${NC} facho2025"
echo -e "${BLUE}════════════════════════════════════════${NC}"

# Preguntar si desea crear superusuario
echo -e "\n${YELLOW}¿Deseas crear un superusuario de Django ahora? [s/N]${NC}"
read -p "$(echo -e ${BLUE}Tu respuesta: ${NC})" CREATE_SUPERUSER

if [[ "$CREATE_SUPERUSER" =~ ^[Ss]$ ]]; then
    echo -e "\n${BLUE}════════════════════════════════════════${NC}"
    echo -e "${GREEN}Creando superusuario de Django Admin${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    
    cd "$PROJECT_DIR"
    sudo -u $USER "$VENV_DIR/bin/python" manage.py createsuperuser
    
    if [ $? -eq 0 ]; then
        echo -e "\n${GREEN}✓ Superusuario creado exitosamente${NC}"
        echo -e "${YELLOW}Accede al Django Admin:${NC} http://$BIND_IP:$BIND_PORT/admin"
    fi
else
    echo -e "\n${YELLOW}Puedes crear el superusuario más tarde ejecutando:${NC}"
    echo -e "  ${BLUE}cd /opt/facho_deluxe_v2${NC}"
    echo -e "  ${BLUE}sudo -u noc venv/bin/python manage.py createsuperuser${NC}"
fi

echo -e "\n${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  🎉 DESPLIEGUE FINALIZADO  🎉${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
