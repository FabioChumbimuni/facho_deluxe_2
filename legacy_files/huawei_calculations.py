"""
Cálculos específicos para equipos Huawei
Implementa la lógica de cálculo inverso de índices SNMP
"""
import logging

logger = logging.getLogger(__name__)

# Constantes para cálculo de Huawei
HUAWEI_BASE = 4194304000
HUAWEI_STEP_SLOT = 8192
HUAWEI_STEP_PORT = 256


def calculate_huawei_slot_port(snmp_index: int) -> tuple[int, int, int]:
    """
    Calcula slot, puerto y onu_id a partir del índice SNMP de Huawei
    
    Fórmula base de Huawei:
    INDEX = BASE + (slot × STEP_SLOT) + (port × STEP_PORT) + onu_id
    
    Donde:
    - BASE = 4194304000
    - STEP_SLOT = 8192  
    - STEP_PORT = 256
    - onu_id = valor adicional cuando el índice es de una ONU
    
    Args:
        snmp_index: Índice SNMP completo (ej: 4194312448)
        
    Returns:
        tuple: (slot, port, onu_id)
    """
    try:
        # 1. Restar la base
        delta = snmp_index - HUAWEI_BASE
        
        # 2. Calcular el slot
        slot = delta // HUAWEI_STEP_SLOT
        
        # 3. Calcular el resto después de sacar el slot
        resto = delta % HUAWEI_STEP_SLOT
        
        # 4. Calcular el puerto
        port = resto // HUAWEI_STEP_PORT
        
        # 5. Calcular el ONU-ID
        onu_id = resto % HUAWEI_STEP_PORT
        
        logger.debug(f"🔢 Cálculo Huawei: {snmp_index} → slot={slot}, port={port}, onu_id={onu_id}")
        
        return slot, port, onu_id
        
    except Exception as e:
        logger.error(f"❌ Error calculando slot/port para índice {snmp_index}: {e}")
        return None, None, None


def parse_snmp_index(raw_index_key: str) -> tuple[int, int]:
    """
    Parsea el raw_index_key para extraer el índice SNMP numérico y el número de ONU
    
    Args:
        raw_index_key: Clave cruda del índice (ej: "4194312448.2")
        
    Returns:
        tuple: (snmp_index, onu_number) donde onu_number es la parte después del punto
    """
    try:
        # El raw_index_key puede tener formato "4194312448.2" o "4194312448"
        if '.' in raw_index_key:
            snmp_index_str, onu_number_str = raw_index_key.split('.', 1)
            snmp_index = int(snmp_index_str)
            onu_number = int(onu_number_str)
        else:
            snmp_index = int(raw_index_key)
            onu_number = 0  # Si no hay punto, asumir ONU 0
            
        logger.debug(f"🔍 Parseado: '{raw_index_key}' → snmp_index={snmp_index}, onu_number={onu_number}")
        return snmp_index, onu_number
        
    except (ValueError, IndexError) as e:
        logger.error(f"❌ Error parseando índice '{raw_index_key}': {e}")
        return None, None


def calculate_huawei_components(raw_index_key: str) -> dict:
    """
    Calcula todos los componentes Huawei a partir del raw_index_key
    
    Args:
        raw_index_key: Clave cruda del índice (ej: "4194312448.2")
        
    Returns:
        dict: {'slot': int, 'port': int, 'onu_id': int, 'snmp_index': int, 'onu_number': int}
    """
    snmp_index, onu_number = parse_snmp_index(raw_index_key)
    
    if snmp_index is None:
        return {'slot': None, 'port': None, 'onu_id': None, 'snmp_index': None, 'onu_number': None}
    
    slot, port, onu_id = calculate_huawei_slot_port(snmp_index)
    
    return {
        'slot': slot,
        'port': port, 
        'onu_id': onu_id,
        'snmp_index': snmp_index,
        'onu_number': onu_number
    }


def test_huawei_calculation():
    """
    Función de prueba para verificar el cálculo
    """
    test_cases = [
        ("4194312448", 1, 1, 0, 0),  # slot=1, port=1, onu_id=0, onu_number=0
        ("4194316032.10", 1, 15, 0, 10),  # slot=1, port=15, onu_id=0, onu_number=10
        ("4194316032.7", 1, 15, 0, 7),  # slot=1, port=15, onu_id=0, onu_number=7
        ("4194338304.1", 4, 6, 0, 1),  # slot=4, port=6, onu_id=0, onu_number=1
        ("4194338304.2", 4, 6, 0, 2),  # slot=4, port=6, onu_id=0, onu_number=2
        ("4194338304.3", 4, 6, 0, 3),  # slot=4, port=6, onu_id=0, onu_number=3
    ]
    
    print("🧪 PROBANDO CÁLCULOS HUAWEI")
    print("=" * 50)
    
    for raw_index, expected_slot, expected_port, expected_onu_id, expected_onu_number in test_cases:
        result = calculate_huawei_components(raw_index)
        print(f"Índice: {raw_index}")
        print(f"  Esperado: slot={expected_slot}, port={expected_port}, onu_id={expected_onu_id}, onu_number={expected_onu_number}")
        print(f"  Calculado: slot={result['slot']}, port={result['port']}, onu_id={result['onu_id']}, onu_number={result['onu_number']}")
        print(f"  ✅ Correcto: {result['slot'] == expected_slot and result['port'] == expected_port and result['onu_number'] == expected_onu_number}")
        print()


if __name__ == "__main__":
    test_huawei_calculation()
