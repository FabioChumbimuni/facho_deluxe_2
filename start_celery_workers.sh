#!/bin/bash

# Script de gestión de Workers de Celery para Facho Deluxe v2
# Autor: Sistema de Descubrimiento SNMP
# Versión: 2.0

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuración
PROJECT_DIR="/opt/facho_deluxe_v2"
VENV_PATH="$PROJECT_DIR/venv"
LOG_DIR="/tmp"

# Archivos PID
PID_DEFAULT="$LOG_DIR/celery-default.pid"
PID_MAIN="$LOG_DIR/celery-discovery_main.pid"
PID_PRIORITY="$LOG_DIR/celery-discovery_priority.pid"
PID_CLEANUP="$LOG_DIR/celery-cleanup.pid"
PID_BACKGROUND_DELETES="$LOG_DIR/celery-background_deletes.pid"
PID_BEAT="$LOG_DIR/celerybeat.pid"

# Archivos de log
LOG_DEFAULT="$LOG_DIR/celery-default.log"
LOG_MAIN="$LOG_DIR/celery-discovery_main.log"
LOG_PRIORITY="$LOG_DIR/celery-discovery_priority.log"
LOG_CLEANUP="$LOG_DIR/celery-cleanup.log"
LOG_BACKGROUND_DELETES="$LOG_DIR/celery-background_deletes.log"
LOG_BEAT="$LOG_DIR/celerybeat.log"

# Función para mostrar mensajes
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_header() {
    echo -e "${CYAN}$1${NC}"
}

# Función para verificar si Redis está funcionando
check_redis() {
    if redis-cli ping > /dev/null 2>&1; then
        print_status "Redis está funcionando"
        return 0
    else
        print_error "Redis NO está funcionando"
        return 1
    fi
}

# Función para verificar si un proceso está ejecutándose
is_process_running() {
    local pid_file=$1
    local process_name=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            # PID file existe pero proceso no está ejecutándose
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# Función para iniciar un worker
start_worker() {
    local queue_name=$1
    local concurrency=$2
    local pid_file=$3
    local log_file=$4
    local worker_name=$5
    
    if is_process_running "$pid_file" "$worker_name"; then
        print_warning "Worker $queue_name ya está ejecutándose"
        return 0
    fi
    
    print_info "Iniciando worker para cola: $queue_name (concurrency: $concurrency)"
    
    cd "$PROJECT_DIR"
    source "$VENV_PATH/bin/activate"
    
    nohup celery -A core worker \
        --loglevel=info \
        --queues=$queue_name \
        --concurrency=$concurrency \
        --hostname=worker@$worker_name \
        --pidfile="$pid_file" \
        --logfile="$log_file" \
        > /dev/null 2>&1 &
    
    sleep 2
    
    if is_process_running "$pid_file" "$worker_name"; then
        print_status "Worker $queue_name iniciado correctamente"
        return 0
    else
        print_error "Error al iniciar worker $queue_name"
        return 1
    fi
}

# Función para detener un worker
stop_worker() {
    local queue_name=$1
    local pid_file=$2
    local worker_name=$3
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            print_info "Deteniendo worker $queue_name (PID: $pid)"
            kill "$pid"
            sleep 3
            
            if ps -p "$pid" > /dev/null 2>&1; then
                print_warning "Worker $queue_name no se detuvo, forzando..."
                kill -9 "$pid"
            fi
            
            rm -f "$pid_file"
            print_status "Worker $queue_name detenido"
        else
            print_warning "Worker $queue_name no estaba ejecutándose"
            rm -f "$pid_file"
        fi
    else
        print_warning "Worker $queue_name no estaba ejecutándose"
    fi
}

# Función para mostrar estado detallado
show_detailed_status() {
    print_header "📊 Estado Detallado de Workers y Tareas"
    echo "=================================================="
    
    # Verificar Redis
    if check_redis; then
        print_status "Redis: FUNCIONANDO"
    else
        print_error "Redis: NO FUNCIONA"
        return 1
    fi
    
    echo ""
    print_header "🔍 Workers de Celery:"
    
    # Worker Default
    if is_process_running "$PID_DEFAULT" "default"; then
        local pid=$(cat "$PID_DEFAULT")
        print_status "Worker default: EJECUTÁNDOSE (PID: $pid)"
        print_info "  - Cola: default"
        print_info "  - Concurrency: 2"
        print_info "  - Log: $LOG_DEFAULT"
    else
        print_error "Worker default: NO EJECUTÁNDOSE"
    fi
    
    # Worker Discovery Main
    if is_process_running "$PID_MAIN" "main"; then
        local pid=$(cat "$PID_MAIN")
        print_status "Worker discovery_main: EJECUTÁNDOSE (PID: $pid)"
        print_info "  - Cola: discovery_main"
        print_info "  - Concurrency: 20"
        print_info "  - Log: $LOG_MAIN"
    else
        print_error "Worker discovery_main: NO EJECUTÁNDOSE"
    fi
    
    # Worker Discovery Priority
    if is_process_running "$PID_PRIORITY" "priority"; then
        local pid=$(cat "$PID_PRIORITY")
        print_status "Worker discovery_priority: EJECUTÁNDOSE (PID: $pid)"
        print_info "  - Cola: discovery_priority"
        print_info "  - Concurrency: 5"
        print_info "  - Log: $LOG_PRIORITY"
    else
        print_error "Worker discovery_priority: NO EJECUTÁNDOSE"
    fi
    
    # Worker Cleanup
    if is_process_running "$PID_CLEANUP" "cleanup"; then
        local pid=$(cat "$PID_CLEANUP")
        print_status "Worker cleanup: EJECUTÁNDOSE (PID: $pid)"
        print_info "  - Cola: cleanup"
        print_info "  - Concurrency: 2"
        print_info "  - Log: $LOG_CLEANUP"
    else
        print_error "Worker cleanup: NO EJECUTÁNDOSE"
    fi
    
    # Worker Background Deletes
    if is_process_running "$PID_BACKGROUND_DELETES" "background_deletes"; then
        local pid=$(cat "$PID_BACKGROUND_DELETES")
        print_status "Worker background_deletes: EJECUTÁNDOSE (PID: $pid)"
        print_info "  - Cola: background_deletes"
        print_info "  - Concurrency: 3"
        print_info "  - Log: $LOG_BACKGROUND_DELETES"
    else
        print_error "Worker background_deletes: NO EJECUTÁNDOSE"
    fi
    
    # Celery Beat
    if is_process_running "$PID_BEAT" "beat"; then
        local pid=$(cat "$PID_BEAT")
        print_status "Celery Beat: EJECUTÁNDOSE (PID: $pid)"
        print_info "  - Scheduler automático"
        print_info "  - Log: $LOG_BEAT"
    else
        print_error "Celery Beat: NO EJECUTÁNDOSE"
    fi
    
    echo ""
    print_header "📋 Estado de Colas Redis:"
    
    # Verificar colas
    local main_queue=$(redis-cli LLEN discovery_main 2>/dev/null || echo "0")
    local priority_queue=$(redis-cli LLEN discovery_priority 2>/dev/null || echo "0")
    local default_queue=$(redis-cli LLEN celery 2>/dev/null || echo "0")
    
    print_info "Cola discovery_main: $main_queue tareas pendientes"
    print_info "Cola discovery_priority: $priority_queue tareas pendientes"
    print_info "Cola default: $default_queue tareas pendientes"
    
    echo ""
    print_header "📈 Tareas Recientes (últimas 5 ejecuciones):"
    
    # Mostrar ejecuciones recientes
    cd "$PROJECT_DIR"
    source "$VENV_PATH/bin/activate"
    
    python manage.py shell -c "
from executions.models import Execution
from django.utils import timezone
from datetime import timedelta

# Obtener ejecuciones de las últimas 24 horas
recent_executions = Execution.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=24)
).order_by('-created_at')[:5]

if recent_executions:
    print('Ejecuciones recientes:')
    for exec in recent_executions:
        status_emoji = '✅' if exec.status == 'SUCCESS' else '❌' if exec.status == 'FAILED' else '⏳'
        duration = f'{exec.duration_ms}ms' if exec.duration_ms else 'N/A'
        print(f'  {status_emoji} ID: {exec.id} | OLT: {exec.olt.abreviatura} | Estado: {exec.status} | Duración: {duration}')
else:
    print('No hay ejecuciones recientes')
" 2>/dev/null || print_warning "No se pudieron obtener las ejecuciones recientes"
}

# Función para mostrar logs recientes
show_recent_logs() {
    local log_file=$1
    local lines=${2:-10}
    
    if [ -f "$log_file" ]; then
        print_header "📝 Últimas $lines líneas de $log_file:"
        echo "----------------------------------------"
        tail -n "$lines" "$log_file"
    else
        print_warning "Archivo de log $log_file no existe"
    fi
}

# Función principal
case "$1" in
    start)
        print_header "🚀 Iniciando Workers de Celery para Facho Deluxe v2"
        echo "=================================================="
        
        if ! check_redis; then
            exit 1
        fi
        
        # Activar entorno virtual
        cd "$PROJECT_DIR"
        source "$VENV_PATH/bin/activate"
        
        # Iniciar workers
        start_worker "default" 2 "$PID_DEFAULT" "$LOG_DEFAULT" "default"
        start_worker "discovery_main" 20 "$PID_MAIN" "$LOG_MAIN" "main"
        start_worker "discovery_priority" 5 "$PID_PRIORITY" "$LOG_PRIORITY" "priority"
        start_worker "cleanup" 2 "$PID_CLEANUP" "$LOG_CLEANUP" "cleanup"
        start_worker "background_deletes" 3 "$PID_BACKGROUND_DELETES" "$LOG_BACKGROUND_DELETES" "background_deletes"
        
        # Iniciar Celery Beat
        print_info "Iniciando Celery Beat (scheduler)..."
        nohup celery -A core beat \
            --loglevel=info \
            --pidfile="$PID_BEAT" \
            --logfile="$LOG_BEAT" \
            --detach > /dev/null 2>&1
        
        sleep 3
        
        if is_process_running "$PID_BEAT" "beat"; then
            print_status "Celery Beat iniciado correctamente"
        else
            print_error "Error al iniciar Celery Beat"
        fi
        
        echo ""
        print_header "🎉 Sistema de Workers Iniciado Correctamente!"
        print_info "📝 Logs disponibles en: $LOG_DIR/celery-*.log"
        ;;
        
    stop)
        print_header "🛑 Deteniendo Workers de Celery"
        echo "=================================================="
        
        stop_worker "default" "$PID_DEFAULT" "default"
        stop_worker "discovery_main" "$PID_MAIN" "main"
        stop_worker "discovery_priority" "$PID_PRIORITY" "priority"
        stop_worker "cleanup" "$PID_CLEANUP" "cleanup"
        stop_worker "background_deletes" "$PID_BACKGROUND_DELETES" "background_deletes"
        
        # Detener Celery Beat
        if [ -f "$PID_BEAT" ]; then
            local beat_pid=$(cat "$PID_BEAT")
            if ps -p "$beat_pid" > /dev/null 2>&1; then
                print_info "Deteniendo Celery Beat (PID: $beat_pid)"
                kill "$beat_pid"
                rm -f "$PID_BEAT"
                print_status "Celery Beat detenido"
            fi
        fi
        
        print_status "Todos los workers detenidos"
        ;;
        
    restart)
        print_header "🔄 Reiniciando Workers de Celery"
        echo "=================================================="
        
        $0 stop
        sleep 2
        $0 start
        ;;
        
    status)
        show_detailed_status
        ;;
        
    logs)
        case "$2" in
            main)
                show_recent_logs "$LOG_MAIN" "${3:-20}"
                ;;
            priority)
                show_recent_logs "$LOG_PRIORITY" "${3:-20}"
                ;;
            default)
                show_recent_logs "$LOG_DEFAULT" "${3:-20}"
                ;;
            beat)
                show_recent_logs "$LOG_BEAT" "${3:-20}"
                ;;
            *)
                print_header "📝 Logs Disponibles:"
                echo "main - Workers de descubrimiento principal"
                echo "priority - Workers de descubrimiento de prioridad"
                echo "default - Workers por defecto"
                echo "beat - Scheduler de Celery"
                echo ""
                print_info "Uso: $0 logs [main|priority|default|beat] [líneas]"
                ;;
        esac
        ;;
        
    test)
        print_header "🧪 Ejecutando Pruebas del Sistema"
        echo "=================================================="
        
        cd "$PROJECT_DIR"
        source "$VENV_PATH/bin/activate"
        
        if python test_simple_discovery.py; then
            print_status "Pruebas pasaron exitosamente"
        else
            print_error "Pruebas fallaron"
        fi
        ;;
        
    *)
        print_header "🔧 Script de Gestión de Workers Celery - Facho Deluxe v2"
        echo "=================================================="
        echo ""
        echo "Comandos disponibles:"
        echo "  start    - Iniciar todos los workers y Celery Beat"
        echo "  stop     - Detener todos los workers y Celery Beat"
        echo "  restart  - Reiniciar todos los workers y Celery Beat"
        echo "  status   - Mostrar estado detallado de workers y tareas"
        echo "  logs     - Mostrar logs de workers específicos"
        echo "  test     - Ejecutar pruebas del sistema"
        echo ""
        echo "Ejemplos:"
        echo "  $0 start"
        echo "  $0 status"
        echo "  $0 logs main 50"
        echo "  $0 test"
        echo ""
        ;;
esac
