#!/bin/bash

# Script para iniciar workers de Celery para SNMP GET con sistema de pollers
# Uso: ./start_celery_get_workers.sh

echo "🚀 Iniciando workers de Celery para SNMP GET..."

# Crear directorios si no existen
mkdir -p pids
mkdir -p logs

# Activar entorno virtual
source venv/bin/activate

# Worker para tarea principal GET (baja concurrencia)
echo "📋 Iniciando worker GET Main (cola: get_main)..."
celery -A core worker -Q get_main -n get_main@%h --concurrency=4 \
    --pidfile=pids/celery-get_main.pid \
    --logfile=logs/celery-get_main.log \
    --loglevel=info &

sleep 2

# Worker para ejecuciones manuales GET (máxima prioridad)
echo "🚀 Iniciando worker GET Manual (cola: get_manual)..."
celery -A core worker -Q get_manual -n get_manual@%h --concurrency=10 \
    --pidfile=pids/celery-get_manual.pid \
    --logfile=logs/celery-get_manual.log \
    --loglevel=info &

sleep 2

# Worker para pollers GET (ALTA concurrencia - procesamiento paralelo)
echo "📡 Iniciando worker GET Poller (cola: get_poller)..."
celery -A core worker -Q get_poller -n get_poller@%h --concurrency=20 \
    --pidfile=pids/celery-get_poller.pid \
    --logfile=logs/celery-get_poller.log \
    --loglevel=info &

sleep 2

# Worker para reintentos GET
echo "🔁 Iniciando worker GET Retry (cola: get_retry)..."
celery -A core worker -Q get_retry -n get_retry@%h --concurrency=2 \
    --pidfile=pids/celery-get_retry.pid \
    --logfile=logs/celery-get_retry.log \
    --loglevel=info &

sleep 2

echo ""
echo "✅ Workers de SNMP GET iniciados correctamente"
echo ""
echo "📊 Estado de workers:"
echo "   - get_main:   Concurrencia 4  (Tarea principal automática)"
echo "   - get_manual: Concurrencia 10 (Ejecución manual - Máxima prioridad)"
echo "   - get_poller: Concurrencia 20 (Pollers paralelos)"
echo "   - get_retry:  Concurrencia 2  (Reintentos)"
echo ""
echo "📝 Logs disponibles en:"
echo "   - logs/celery-get_main.log"
echo "   - logs/celery-get_manual.log"
echo "   - logs/celery-get_poller.log"
echo "   - logs/celery-get_retry.log"
echo ""
echo "🛑 Para detener los workers:"
echo "   pkill -F pids/celery-get_main.pid"
echo "   pkill -F pids/celery-get_manual.pid"
echo "   pkill -F pids/celery-get_poller.pid"
echo "   pkill -F pids/celery-get_retry.pid"
echo ""
echo "👀 Para monitorear en tiempo real:"
echo "   tail -f logs/celery-get_poller.log"

