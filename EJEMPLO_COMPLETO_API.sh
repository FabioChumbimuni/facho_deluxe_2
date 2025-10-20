#!/bin/bash
# ========================================================
# EJEMPLO COMPLETO: CREAR Y BORRAR CLIENTE VIA API
# ========================================================

# Configuración
TOKEN="992f9d275d8b5852d5449988b2419f467f1fe932"
API_URL="http://192.168.56.222:8000/api/v1"

echo "========================================"
echo "📋 EJEMPLO COMPLETO DE API - CLIENTE"
echo "========================================"
echo ""

# ========================================================
# 1️⃣ CREAR CLIENTE NUEVO
# ========================================================
echo "1️⃣  CREANDO CLIENTE NUEVO..."
echo "----------------------------------------"

RESPONSE=$(curl -s -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot_input": 5,
    "port_input": 10,
    "logical_input": 25,
    "snmp_description": "12345678",
    "serial_number": "HWTC99887766",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "modelo_onu": "HG8310M",
    "plan_onu": "100MB",
    "distancia_onu": 250,
    "estado_input": "ACTIVO"
  }')

# Extraer ID de la ONU creada
ONU_ID=$(echo "$RESPONSE" | jq -r '.id')

echo "✅ Cliente creado exitosamente!"
echo "$RESPONSE" | jq '{
  id, 
  olt_nombre, 
  "posicion": "\(.slot)/\(.port)/\(.logical)",
  snmp_description,
  serial_number,
  plan_onu,
  presence,
  estado_display
}'
echo ""

# ========================================================
# 2️⃣ CONSULTAR CLIENTE CREADO
# ========================================================
echo "2️⃣  CONSULTANDO CLIENTE CREADO..."
echo "----------------------------------------"

curl -s -X GET "${API_URL}/onus/${ONU_ID}/" \
  -H "Authorization: Token ${TOKEN}" | jq '{
  id,
  olt_nombre,
  "posicion": "\(.slot)/\(.port)/\(.logical)",
  snmp_description,
  serial_number,
  plan_onu,
  presence,
  estado_display,
  created_at
}'
echo ""

# ========================================================
# 3️⃣ BUSCAR CLIENTE POR DNI
# ========================================================
echo "3️⃣  BUSCANDO CLIENTE POR DNI (12345678)..."
echo "----------------------------------------"

curl -s -X GET "${API_URL}/onus/?search=12345678" \
  -H "Authorization: Token ${TOKEN}" | jq '.results[] | {
  id,
  olt_nombre,
  "posicion": "\(.slot)/\(.port)/\(.logical)",
  snmp_description,
  presence,
  estado_display
}'
echo ""

# ========================================================
# 4️⃣ SUSPENDER CLIENTE (Estado Administrativo)
# ========================================================
echo "4️⃣  SUSPENDIENDO ESTADO DEL CLIENTE..."
echo "----------------------------------------"

curl -s -X POST "${API_URL}/onus/${ONU_ID}/suspender-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq '{
  message,
  id,
  presence,
  estado: .estado
}'
echo ""

# ========================================================
# 5️⃣ REACTIVAR CLIENTE
# ========================================================
echo "5️⃣  REACTIVANDO ESTADO DEL CLIENTE..."
echo "----------------------------------------"

curl -s -X POST "${API_URL}/onus/${ONU_ID}/activar-estado/" \
  -H "Authorization: Token ${TOKEN}" | jq '{
  message,
  id,
  presence,
  estado: .estado
}'
echo ""

# ========================================================
# 6️⃣ ACTUALIZAR DATOS DEL CLIENTE
# ========================================================
echo "6️⃣  ACTUALIZANDO PLAN DEL CLIENTE..."
echo "----------------------------------------"

curl -s -X PATCH "${API_URL}/onus/${ONU_ID}/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"plan_onu": "200MB"}' | jq '{
  id,
  snmp_description,
  plan_onu,
  presence,
  estado_display
}'
echo ""

# ========================================================
# 7️⃣ OPCIÓN A: BORRADO SUAVE (Soft Delete)
# ========================================================
echo "7️⃣  OPCIÓN A: BORRADO SUAVE (Soft Delete)..."
echo "----------------------------------------"
echo "⚠️  Esto desactiva el cliente pero mantiene el historial"
echo ""

read -p "¿Ejecutar Soft Delete? (s/n): " SOFT_DELETE

if [ "$SOFT_DELETE" = "s" ]; then
    curl -s -X POST "${API_URL}/onus/${ONU_ID}/desactivar/" \
      -H "Authorization: Token ${TOKEN}" | jq '{
      message,
      id,
      presence,
      estado: .estado
    }'
    echo ""
    echo "✅ Cliente desactivado (soft delete)"
    echo "   - Los datos se mantienen en la base de datos"
    echo "   - presence=DISABLED, estado=SUSPENDIDO"
    echo ""
fi

# ========================================================
# 8️⃣ OPCIÓN B: BORRADO PERMANENTE (Hard Delete)
# ========================================================
echo "8️⃣  OPCIÓN B: BORRADO PERMANENTE (Hard Delete)..."
echo "----------------------------------------"
echo "⚠️  ⚠️  ⚠️  ADVERTENCIA ⚠️  ⚠️  ⚠️"
echo "Esto ELIMINA PERMANENTEMENTE el cliente de la base de datos"
echo "Esta acción NO se puede deshacer"
echo ""

read -p "¿Ejecutar Hard Delete? (ESCRIBE 'CONFIRMAR' para continuar): " HARD_DELETE

if [ "$HARD_DELETE" = "CONFIRMAR" ]; then
    curl -s -X DELETE "${API_URL}/onus/${ONU_ID}/eliminar-permanente/" \
      -H "Authorization: Token ${TOKEN}" | jq
    
    echo ""
    echo "✅ Cliente eliminado permanentemente"
    echo "   - Borrado de OnuInventory"
    echo "   - Borrado de OnuStatus"
    echo "   - Borrado de OnuIndexMap"
    echo ""
    
    # Verificar que fue eliminado
    echo "9️⃣  VERIFICANDO ELIMINACIÓN..."
    echo "----------------------------------------"
    
    VERIFY=$(curl -s -X GET "${API_URL}/onus/${ONU_ID}/" \
      -H "Authorization: Token ${TOKEN}" | jq -r '.detail // "existe"')
    
    if [ "$VERIFY" = "No encontrado." ]; then
        echo "✅ CONFIRMADO: Cliente eliminado de la base de datos"
    else
        echo "❌ ERROR: El cliente aún existe"
    fi
else
    echo "❌ Hard Delete cancelado"
fi

echo ""
echo "========================================"
echo "✅ EJEMPLO COMPLETO FINALIZADO"
echo "========================================"

