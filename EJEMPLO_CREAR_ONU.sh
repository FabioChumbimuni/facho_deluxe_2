#!/bin/bash
# ====================================================================
# EJEMPLOS DE CREACIÓN DE ONUs VIA API REST
# ====================================================================
# Proyecto: Facho Deluxe v2
# Descripción: Ejemplos de cómo crear ONUs proporcionando datos mínimos
#              y opcionales. El sistema generará automáticamente el 
#              raw_index_key usando la fórmula SNMP de la OLT.
# ====================================================================

# CONFIGURACIÓN
API_URL="http://192.168.56.222:8000/api/v1"
TOKEN="992f9d275d8b5852d5449988b2419f467f1fe932"  # Token del usuario NOC

# ====================================================================
# EJEMPLO 1: CREAR ONU CON DATOS MÍNIMOS
# ====================================================================
# Campos OBLIGATORIOS:
#   - olt: ID de la OLT (el sistema usa su marca para calcular el raw_index_key)
#   - slot: Número de slot
#   - port: Número de puerto
#   - logical: Número lógico de ONU
#   - active: true (activo) o false (suspendido)
# ====================================================================

echo "=================================================="
echo "EJEMPLO 1: Crear ONU con datos MÍNIMOS"
echo "=================================================="
echo ""
echo "OLT: SD-3 (ID=21)"
echo "Posición: 5/3/10"
echo "Estado: Activo"
echo ""

curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot": 5,
    "port": 3,
    "logical": 10,
    "active": true
  }' | jq

echo ""
echo "✅ Se crearon automáticamente:"
echo "   1. OnuIndexMap (con raw_index_key calculado según la fórmula de Huawei)"
echo "   2. OnuStatus (con presence=ENABLED porque active=true)"
echo "   3. OnuInventory (con los datos proporcionados)"
echo ""
read -p "Presiona Enter para continuar..."
echo ""

# ====================================================================
# EJEMPLO 2: CREAR ONU CON DATOS OPCIONALES
# ====================================================================
# Campos OPCIONALES adicionales:
#   - serial_number: Número de serie de la ONU
#   - mac_address: Dirección MAC
#   - modelo_onu: Modelo del equipo (ej: "HG8310M", "F601")
#   - plan_onu: Plan de servicio (ej: "100MB", "50MB")
#   - distancia_onu: Distancia en metros
#   - snmp_description: Descripción personalizada (DNI, nombre, etc.)
#   - subscriber_id: ID del suscriptor en el sistema
# ====================================================================

echo "=================================================="
echo "EJEMPLO 2: Crear ONU con DATOS COMPLETOS"
echo "=================================================="
echo ""
echo "OLT: SD-3 (ID=21)"
echo "Posición: 6/8/15"
echo "Estado: Activo"
echo "Serial: HWTC12345678"
echo "MAC: AA:BB:CC:DD:EE:FF"
echo "Modelo: HG8310M"
echo "Plan: 100MB"
echo "Distancia: 250m"
echo "SNMP Description: 74150572"
echo ""

curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot": 6,
    "port": 8,
    "logical": 15,
    "serial_number": "HWTC12345678",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "modelo_onu": "HG8310M",
    "plan_onu": "100MB",
    "distancia_onu": 250,
    "snmp_description": "74150572",
    "subscriber_id": "CLI-2024-00123",
    "active": true
  }' | jq

echo ""
read -p "Presiona Enter para continuar..."
echo ""

# ====================================================================
# EJEMPLO 3: CREAR ONU SUSPENDIDA (INACTIVA)
# ====================================================================
# El campo "active" define si la ONU está activa o suspendida.
# Esto afecta el campo "presence" en OnuStatus:
#   - active=true  → presence=ENABLED
#   - active=false → presence=DISABLED
# ====================================================================

echo "=================================================="
echo "EJEMPLO 3: Crear ONU SUSPENDIDA"
echo "=================================================="
echo ""
echo "OLT: SD-3 (ID=21)"
echo "Posición: 7/2/5"
echo "Estado: SUSPENDIDO (active=false)"
echo "SNMP Description: 75139456"
echo ""

curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot": 7,
    "port": 2,
    "logical": 5,
    "serial_number": "HWTC87654321",
    "mac_address": "11:22:33:44:55:66",
    "modelo_onu": "F601",
    "plan_onu": "50MB",
    "snmp_description": "75139456",
    "active": false
  }' | jq

echo ""
echo "✅ Esta ONU se creó con presence=DISABLED en OnuStatus"
echo ""
read -p "Presiona Enter para continuar..."
echo ""

# ====================================================================
# EJEMPLO 4: CREAR MÚLTIPLES ONUs CON DATOS ALEATORIOS
# ====================================================================

echo "=================================================="
echo "EJEMPLO 4: Crear ONUs con datos ALEATORIOS"
echo "=================================================="
echo ""
echo "Se crearán 3 ONUs en diferentes posiciones con datos aleatorios"
echo ""

# ONU 1
echo "→ Creando ONU en 8/4/12..."
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot": 8,
    "port": 4,
    "logical": 12,
    "serial_number": "HWTC'$(shuf -i 10000000-99999999 -n 1)'",
    "mac_address": "'$(printf "%02X:%02X:%02X:%02X:%02X:%02X" $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)))'",
    "modelo_onu": "HG8310M",
    "plan_onu": "100MB",
    "distancia_onu": '$(shuf -i 50-500 -n 1)',
    "snmp_description": "'$(shuf -i 10000000-99999999 -n 1)'",
    "active": true
  }' | jq -c '{id, slot, port, logical, serial_number, snmp_description}'

echo ""

# ONU 2
echo "→ Creando ONU en 9/1/8..."
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot": 9,
    "port": 1,
    "logical": 8,
    "serial_number": "HWTC'$(shuf -i 10000000-99999999 -n 1)'",
    "mac_address": "'$(printf "%02X:%02X:%02X:%02X:%02X:%02X" $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)))'",
    "modelo_onu": "F601",
    "plan_onu": "50MB",
    "distancia_onu": '$(shuf -i 50-500 -n 1)',
    "snmp_description": "'$(shuf -i 10000000-99999999 -n 1)'",
    "active": true
  }' | jq -c '{id, slot, port, logical, serial_number, snmp_description}'

echo ""

# ONU 3
echo "→ Creando ONU en 10/5/20..."
curl -X POST "${API_URL}/onus/" \
  -H "Authorization: Token ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 21,
    "slot": 10,
    "port": 5,
    "logical": 20,
    "serial_number": "HWTC'$(shuf -i 10000000-99999999 -n 1)'",
    "mac_address": "'$(printf "%02X:%02X:%02X:%02X:%02X:%02X" $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)))'",
    "modelo_onu": "HG8310M",
    "plan_onu": "200MB",
    "distancia_onu": '$(shuf -i 50-500 -n 1)',
    "snmp_description": "'$(shuf -i 10000000-99999999 -n 1)'",
    "active": true
  }' | jq -c '{id, slot, port, logical, serial_number, snmp_description}'

echo ""
echo "✅ ONUs creadas exitosamente!"
echo ""
read -p "Presiona Enter para continuar..."
echo ""

# ====================================================================
# EJEMPLO 5: VERIFICAR LAS ONUs CREADAS
# ====================================================================

echo "=================================================="
echo "VERIFICACIÓN: Listar ONUs de SD-3 (ID=21)"
echo "=================================================="
echo ""

curl -X GET "${API_URL}/onus/?olt=21&ordering=-id&page_size=10" \
  -H "Authorization: Token ${TOKEN}" | \
  jq -r '.results[] | "\(.id) | \(.slot)/\(.port)/\(.logical) | \(.snmp_description // "N/A") | \(.serial_number // "N/A") | \(.modelo_onu // "N/A") | \(.plan_onu // "N/A") | Active: \(.active)"'

echo ""
echo "=================================================="
echo "FIN DE LOS EJEMPLOS"
echo "=================================================="
echo ""
echo "📋 RESUMEN:"
echo ""
echo "✅ Para crear una ONU solo necesitas:"
echo "   - olt (ID)"
echo "   - slot, port, logical"
echo "   - active (true/false)"
echo ""
echo "✅ El sistema automáticamente:"
echo "   - Calcula el raw_index_key según la fórmula de la marca de OLT"
echo "   - Crea OnuIndexMap, OnuStatus y OnuInventory"
echo "   - Establece presence=ENABLED o DISABLED según 'active'"
echo ""
echo "✅ Campos opcionales que puedes agregar:"
echo "   - serial_number, mac_address"
echo "   - modelo_onu, plan_onu, distancia_onu"
echo "   - snmp_description (DNI, nombre, código de cliente, etc.)"
echo "   - subscriber_id"
echo ""
echo "⚠️  IMPORTANTE:"
echo "   El raw_index_key se calcula usando la fórmula SNMP de la marca"
echo "   de la OLT. Si no existe fórmula activa, la creación fallará."
echo ""

