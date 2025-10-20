#!/bin/bash
# =============================================================================
# EJEMPLOS DE USO DE LA API DE ONUs - Facho Deluxe v2
# =============================================================================

# Configuración
API_URL="http://192.168.56.222:8000/api/v1"
TOKEN="TU_TOKEN_AQUI"  # Obtener con: curl -X POST $API_URL/auth/login/ -d '{"username":"admin","password":"tu_pass"}'

echo "============================================================"
echo "🔍 EJEMPLOS DE CONSULTAS Y OPERACIONES CON API DE ONUs"
echo "============================================================"
echo

# =============================================================================
# 1. BÚSQUEDA POR SNMP DESCRIPTION
# =============================================================================
echo "1️⃣  BUSCAR POR SNMP DESCRIPTION (70540036)"
echo "------------------------------------------------------------"
echo "Comando:"
echo "curl -X GET \"$API_URL/onus/?search=70540036\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo
echo "Resultado: Busca en serial_number, mac_address, subscriber_id y snmp_description"
echo

# =============================================================================
# 2. FILTROS COMBINADOS
# =============================================================================
echo "2️⃣  FILTRAR POR OLT Y BUSCAR"
echo "------------------------------------------------------------"
echo "Comando:"
echo "curl -X GET \"$API_URL/onus/?olt=1&search=70540036\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo

echo "3️⃣  FILTRAR POR PLAN Y MODELO"
echo "------------------------------------------------------------"
echo "# Solo por plan"
echo "curl -X GET \"$API_URL/onus/?plan_onu=100M\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo
echo "# Solo por modelo"
echo "curl -X GET \"$API_URL/onus/?modelo_onu=HG8546M\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo
echo "# Combinado: Plan + Modelo + Búsqueda"
echo "curl -X GET \"$API_URL/onus/?plan_onu=100M&modelo_onu=HG8546M&search=70540036\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo

# =============================================================================
# 4. CREAR UNA NUEVA ONU
# =============================================================================
echo "4️⃣  CREAR NUEVA ONU (Crea en las 3 tablas automáticamente)"
echo "------------------------------------------------------------"
cat << 'EOF'
curl -X POST "http://192.168.56.222:8000/api/v1/onus/" \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 1,
    "raw_index_key_input": "4194312192.15",
    "serial_number": "HWTC87654321",
    "mac_address": "AA:BB:CC:DD:EE:FF",
    "subscriber_id": "CLI-70540036",
    "plan_onu": "200M",
    "distancia_onu": "2.5",
    "modelo_onu": "HG8546M",
    "snmp_description": "Cliente 70540036 - Juan Perez",
    "active": true
  }'

EOF
echo "Esto crea automáticamente:"
echo "  ✓ OnuIndexMap (con slot/port/logical calculados)"
echo "  ✓ OnuStatus (con presence='ENABLED')"
echo "  ✓ OnuInventory (con toda la información)"
echo

# =============================================================================
# 5. ACTUALIZAR UNA ONU
# =============================================================================
echo "5️⃣  ACTUALIZAR UNA ONU (Agregar/Cambiar Modelo)"
echo "------------------------------------------------------------"
cat << 'EOF'
# Actualización completa (PUT)
curl -X PUT "http://192.168.56.222:8000/api/v1/onus/1/" \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "olt": 1,
    "serial_number": "HWTC87654321",
    "plan_onu": "200M",
    "modelo_onu": "HG8546M_V3",
    "distancia_onu": "2.8",
    "snmp_description": "Cliente 70540036 - Juan Perez - Actualizado",
    "active": true
  }'

# Actualización parcial (PATCH) - Solo cambiar el modelo
curl -X PATCH "http://192.168.56.222:8000/api/v1/onus/1/" \
  -H "Authorization: Token TU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "modelo_onu": "HG8546M_V3",
    "distancia_onu": "2.8"
  }'

EOF
echo

# =============================================================================
# 6. OBTENER DETALLES DE UNA ONU
# =============================================================================
echo "6️⃣  OBTENER DETALLES COMPLETOS DE UNA ONU"
echo "------------------------------------------------------------"
echo "curl -X GET \"$API_URL/onus/1/\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo
echo "Retorna:"
echo "  • Información de la OLT"
echo "  • Slot, Port, Logical (calculados)"
echo "  • Serial, MAC, Subscriber ID"
echo "  • Plan, Distancia, Modelo"
echo "  • SNMP Description y Metadata"
echo "  • Presence y Estado (desde OnuStatus)"
echo "  • Fechas de creación y actualización"
echo

# =============================================================================
# 7. OBTENER SOLO ONUs ACTIVAS
# =============================================================================
echo "7️⃣  OBTENER SOLO ONUs ACTIVAS"
echo "------------------------------------------------------------"
echo "curl -X GET \"$API_URL/onus/activas/\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo

# =============================================================================
# 8. OBTENER ONUs POR OLT
# =============================================================================
echo "8️⃣  OBTENER ONUs DE UNA OLT ESPECÍFICA"
echo "------------------------------------------------------------"
echo "curl -X GET \"$API_URL/onus/por_olt/?olt_id=1\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo

# =============================================================================
# 9. PAGINACIÓN
# =============================================================================
echo "9️⃣  PAGINACIÓN (50 resultados por página)"
echo "------------------------------------------------------------"
echo "# Primera página"
echo "curl -X GET \"$API_URL/onus/?page=1\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo
echo "# Segunda página"
echo "curl -X GET \"$API_URL/onus/?page=2\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo

# =============================================================================
# 10. ORDENAMIENTO
# =============================================================================
echo "🔟  ORDENAR RESULTADOS"
echo "------------------------------------------------------------"
echo "# Por fecha de creación (más recientes primero)"
echo "curl -X GET \"$API_URL/onus/?ordering=-created_at\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo
echo "# Por fecha de última recolección SNMP"
echo "curl -X GET \"$API_URL/onus/?ordering=-snmp_last_collected_at\" \\"
echo "  -H \"Authorization: Token $TOKEN\""
echo

# =============================================================================
# RESUMEN DE PARÁMETROS
# =============================================================================
echo "============================================================"
echo "📋 RESUMEN DE PARÁMETROS DISPONIBLES"
echo "============================================================"
echo
echo "🔍 Búsqueda (?search=):"
echo "   • serial_number"
echo "   • mac_address"
echo "   • subscriber_id"
echo "   • snmp_description"
echo
echo "🎯 Filtros (?campo=valor):"
echo "   • olt           - ID de la OLT"
echo "   • active        - true/false"
echo "   • plan_onu      - Ej: 100M, 200M"
echo "   • modelo_onu    - Ej: HG8546M"
echo
echo "📄 Paginación:"
echo "   • page          - Número de página"
echo "   • page_size     - Resultados por página (default: 50)"
echo
echo "⬆️  Ordenamiento (?ordering=):"
echo "   • created_at            - Fecha de creación"
echo "   • -created_at           - Más recientes primero"
echo "   • updated_at            - Fecha de actualización"
echo "   • snmp_last_collected_at - Última recolección SNMP"
echo
echo "============================================================"
echo "✅ Para más información: http://192.168.56.222:8000/api/v1/docs/"
echo "============================================================"

