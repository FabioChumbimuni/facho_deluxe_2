#!/bin/bash
# Script de diagnóstico para problemas de gunicorn

echo "🔍 DIAGNÓSTICO DE GUNICORN"
echo "=========================="
echo ""

echo "1. Procesos gunicorn activos:"
ps aux | grep "gunicorn.*192.168.56.222:8000" | grep -v grep || echo "   Ninguno"
echo ""

echo "2. Puerto 8000 en uso:"
ss -tlnp | grep :8000 || netstat -tlnp | grep :8000 || echo "   Puerto libre"
echo ""

echo "3. Procesos con PPID=1 (huérfanos):"
ps -eo pid,ppid,cmd | grep "gunicorn.*192.168.56.222:8000" | awk '$2 == 1 {print "   PID " $1 " es huérfano"}' || echo "   Ninguno"
echo ""

echo "4. Estado de supervisor (requiere permisos):"
supervisorctl status gunicorn 2>&1 | head -3 || echo "   No se puede acceder (requiere permisos)"
echo ""

echo "5. Últimos errores en log:"
tail -20 /opt/facho_deluxe_2/logs/gunicorn.log | grep -E "ERROR|Connection|Address" | tail -5 || echo "   No hay errores recientes"
echo ""

echo "6. Procesos de shell Python activos (pueden causar conflictos):"
ps aux | grep "python.*manage.py shell" | grep -v grep | wc -l | xargs echo "   Total:"
echo ""

echo "✅ DIAGNÓSTICO COMPLETO"
echo ""
echo "Si hay conflictos:"
echo "  /opt/facho_deluxe_2/scripts/fix_gunicorn_conflict.sh"

