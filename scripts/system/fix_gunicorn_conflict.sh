#!/bin/bash
# Script para limpiar procesos gunicorn huérfanos y reiniciar correctamente

echo "🔍 Buscando procesos gunicorn huérfanos (PPID=1)..."
# Buscar procesos gunicorn y verificar si su PPID es 1 (huérfanos)
ORPHANED_PIDS=$(ps -eo pid,ppid,cmd | grep "gunicorn.*192.168.56.222:8000" | grep -v grep | awk '$2 == 1 {print $1}')

if [ -z "$ORPHANED_PIDS" ]; then
    echo "✅ No se encontraron procesos huérfanos"
else
    echo "⚠️  Encontrados procesos huérfanos: $ORPHANED_PIDS"
    echo "🛑 Deteniendo procesos huérfanos..."
    for pid in $ORPHANED_PIDS; do
        echo "   Matando proceso $pid..."
        kill -TERM $pid 2>/dev/null
        sleep 2
        # Si aún existe, forzar kill
        if ps -p $pid > /dev/null 2>&1; then
            echo "   Forzando kill del proceso $pid..."
            kill -KILL $pid 2>/dev/null
        fi
    done
    echo "✅ Procesos huérfanos eliminados"
fi

# Esperar un momento para que el puerto se libere
sleep 2

# Verificar si el puerto está libre
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  El puerto 8000 aún está en uso. Intentando liberar..."
    # Matar todos los procesos que usan el puerto 8000
    lsof -ti :8000 | xargs -r kill -TERM 2>/dev/null
    sleep 3
    lsof -ti :8000 | xargs -r kill -KILL 2>/dev/null
    sleep 2
fi

# Verificar si supervisor está corriendo
if ! pgrep -f "supervisord" > /dev/null; then
    echo "⚠️  Supervisor no está corriendo. Iniciando..."
    systemctl start supervisor || service supervisor start
    sleep 2
fi

# Recargar configuración de supervisor
echo "🔄 Recargando configuración de supervisor..."
supervisorctl reread
supervisorctl update

# Detener gunicorn en supervisor (si está corriendo)
echo "🛑 Deteniendo gunicorn en supervisor..."
supervisorctl stop gunicorn 2>/dev/null || true
sleep 2

# Iniciar gunicorn en supervisor
echo "▶️  Iniciando gunicorn en supervisor..."
supervisorctl start gunicorn

# Verificar estado
sleep 3
echo ""
echo "📊 Estado final:"
supervisorctl status gunicorn
echo ""
echo "🔍 Procesos gunicorn activos:"
ps aux | grep "gunicorn.*192.168.56.222:8000" | grep -v grep || echo "   Ninguno"

