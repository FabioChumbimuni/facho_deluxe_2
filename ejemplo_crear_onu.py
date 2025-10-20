#!/usr/bin/env python3
"""
====================================================================
EJEMPLOS DE CREACIÓN DE ONUs VIA API REST (Python)
====================================================================
Proyecto: Facho Deluxe v2
Descripción: Ejemplos de cómo crear ONUs proporcionando datos mínimos
             y opcionales. El sistema generará automáticamente el 
             raw_index_key usando la fórmula SNMP de la OLT.
====================================================================
"""

import requests
import random
import json
from datetime import datetime

# CONFIGURACIÓN
API_URL = "http://192.168.56.222:8000/api/v1"
TOKEN = "992f9d275d8b5852d5449988b2419f467f1fe932"  # Token del usuario NOC

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}


def generar_serial_random():
    """Genera un número de serie aleatorio"""
    return f"HWTC{random.randint(10000000, 99999999)}"


def generar_mac_random():
    """Genera una dirección MAC aleatoria"""
    return ":".join([f"{random.randint(0, 255):02X}" for _ in range(6)])


def generar_dni_random():
    """Genera un DNI aleatorio de 8 dígitos"""
    return str(random.randint(10000000, 99999999))


def crear_onu_minimo():
    """
    EJEMPLO 1: Crear ONU con datos MÍNIMOS
    
    Campos OBLIGATORIOS:
        - olt: ID de la OLT (el sistema usa su marca para calcular el raw_index_key)
        - slot: Número de slot
        - port: Número de puerto
        - logical: Número lógico de ONU
        - active: true (activo) o false (suspendido)
    """
    print("=" * 60)
    print("EJEMPLO 1: Crear ONU con datos MÍNIMOS")
    print("=" * 60)
    print()
    print("OLT: SD-3 (ID=21)")
    print("Posición: 5/3/10")
    print("Estado: Activo")
    print()
    
    data = {
        "olt": 21,
        "slot": 5,
        "port": 3,
        "logical": 10,
        "active": True
    }
    
    response = requests.post(f"{API_URL}/onus/", headers=headers, json=data)
    
    if response.status_code == 201:
        onu = response.json()
        print("✅ ONU creada exitosamente!")
        print(f"   ID: {onu['id']}")
        print(f"   Posición: {onu['slot']}/{onu['port']}/{onu['logical']}")
        print(f"   Normalizado: {onu['normalized_id']}")
        print(f"   Raw Index Key: {onu['raw_index_key']}")
        print(f"   Active: {onu['active']}")
        print()
        print("✅ Se crearon automáticamente:")
        print("   1. OnuIndexMap (con raw_index_key calculado según la fórmula de Huawei)")
        print("   2. OnuStatus (con presence=ENABLED porque active=true)")
        print("   3. OnuInventory (con los datos proporcionados)")
    else:
        print(f"❌ Error: {response.status_code}")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    
    print()
    input("Presiona Enter para continuar...")
    print()


def crear_onu_completo():
    """
    EJEMPLO 2: Crear ONU con DATOS COMPLETOS
    
    Campos OPCIONALES adicionales:
        - serial_number: Número de serie de la ONU
        - mac_address: Dirección MAC
        - modelo_onu: Modelo del equipo (ej: "HG8310M", "F601")
        - plan_onu: Plan de servicio (ej: "100MB", "50MB")
        - distancia_onu: Distancia en metros
        - snmp_description: Descripción personalizada (DNI, nombre, etc.)
        - subscriber_id: ID del suscriptor en el sistema
    """
    print("=" * 60)
    print("EJEMPLO 2: Crear ONU con DATOS COMPLETOS")
    print("=" * 60)
    print()
    
    serial = generar_serial_random()
    mac = generar_mac_random()
    dni = generar_dni_random()
    distancia = random.randint(50, 500)
    
    print("OLT: SD-3 (ID=21)")
    print("Posición: 6/8/15")
    print("Estado: Activo")
    print(f"Serial: {serial}")
    print(f"MAC: {mac}")
    print("Modelo: HG8310M")
    print("Plan: 100MB")
    print(f"Distancia: {distancia}m")
    print(f"SNMP Description: {dni}")
    print()
    
    data = {
        "olt": 21,
        "slot": 6,
        "port": 8,
        "logical": 15,
        "serial_number": serial,
        "mac_address": mac,
        "modelo_onu": "HG8310M",
        "plan_onu": "100MB",
        "distancia_onu": distancia,
        "snmp_description": dni,
        "subscriber_id": f"CLI-2024-{random.randint(10000, 99999)}",
        "active": True
    }
    
    response = requests.post(f"{API_URL}/onus/", headers=headers, json=data)
    
    if response.status_code == 201:
        onu = response.json()
        print("✅ ONU creada exitosamente!")
        print(f"   ID: {onu['id']}")
        print(f"   Posición: {onu['slot']}/{onu['port']}/{onu['logical']}")
        print(f"   Serial: {onu['serial_number']}")
        print(f"   MAC: {onu['mac_address']}")
        print(f"   Modelo: {onu['modelo_onu']}")
        print(f"   Plan: {onu['plan_onu']}")
        print(f"   Distancia: {onu['distancia_onu']}m")
        print(f"   SNMP Description: {onu['snmp_description']}")
        print(f"   Raw Index Key: {onu['raw_index_key']}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    
    print()
    input("Presiona Enter para continuar...")
    print()


def crear_onu_suspendida():
    """
    EJEMPLO 3: Crear ONU SUSPENDIDA (INACTIVA)
    
    El campo "active" define si la ONU está activa o suspendida.
    Esto afecta el campo "presence" en OnuStatus:
        - active=true  → presence=ENABLED
        - active=false → presence=DISABLED
    """
    print("=" * 60)
    print("EJEMPLO 3: Crear ONU SUSPENDIDA")
    print("=" * 60)
    print()
    
    serial = generar_serial_random()
    mac = generar_mac_random()
    dni = generar_dni_random()
    
    print("OLT: SD-3 (ID=21)")
    print("Posición: 7/2/5")
    print("Estado: SUSPENDIDO (active=false)")
    print(f"SNMP Description: {dni}")
    print()
    
    data = {
        "olt": 21,
        "slot": 7,
        "port": 2,
        "logical": 5,
        "serial_number": serial,
        "mac_address": mac,
        "modelo_onu": "F601",
        "plan_onu": "50MB",
        "snmp_description": dni,
        "active": False
    }
    
    response = requests.post(f"{API_URL}/onus/", headers=headers, json=data)
    
    if response.status_code == 201:
        onu = response.json()
        print("✅ ONU creada exitosamente!")
        print(f"   ID: {onu['id']}")
        print(f"   Posición: {onu['slot']}/{onu['port']}/{onu['logical']}")
        print(f"   Active: {onu['active']} ← SUSPENDIDA")
        print()
        print("✅ Esta ONU se creó con presence=DISABLED en OnuStatus")
    else:
        print(f"❌ Error: {response.status_code}")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    
    print()
    input("Presiona Enter para continuar...")
    print()


def crear_onus_masivas():
    """
    EJEMPLO 4: Crear MÚLTIPLES ONUs con datos ALEATORIOS
    """
    print("=" * 60)
    print("EJEMPLO 4: Crear ONUs con datos ALEATORIOS")
    print("=" * 60)
    print()
    print("Se crearán 3 ONUs en diferentes posiciones con datos aleatorios")
    print()
    
    posiciones = [
        {"slot": 8, "port": 4, "logical": 12, "modelo": "HG8310M", "plan": "100MB"},
        {"slot": 9, "port": 1, "logical": 8, "modelo": "F601", "plan": "50MB"},
        {"slot": 10, "port": 5, "logical": 20, "modelo": "HG8310M", "plan": "200MB"}
    ]
    
    onus_creadas = []
    
    for pos in posiciones:
        print(f"→ Creando ONU en {pos['slot']}/{pos['port']}/{pos['logical']}...")
        
        data = {
            "olt": 21,
            "slot": pos["slot"],
            "port": pos["port"],
            "logical": pos["logical"],
            "serial_number": generar_serial_random(),
            "mac_address": generar_mac_random(),
            "modelo_onu": pos["modelo"],
            "plan_onu": pos["plan"],
            "distancia_onu": random.randint(50, 500),
            "snmp_description": generar_dni_random(),
            "active": True
        }
        
        response = requests.post(f"{API_URL}/onus/", headers=headers, json=data)
        
        if response.status_code == 201:
            onu = response.json()
            onus_creadas.append(onu)
            print(f"   ✅ ID: {onu['id']} | Serial: {onu['serial_number']} | "
                  f"SNMP Desc: {onu['snmp_description']}")
        else:
            print(f"   ❌ Error: {response.status_code}")
            print(f"   {response.json()}")
        
        print()
    
    print(f"✅ Se crearon {len(onus_creadas)} ONUs exitosamente!")
    print()
    input("Presiona Enter para continuar...")
    print()


def verificar_onus_creadas():
    """
    EJEMPLO 5: VERIFICAR las ONUs creadas
    """
    print("=" * 60)
    print("VERIFICACIÓN: Listar ONUs de SD-3 (ID=21)")
    print("=" * 60)
    print()
    
    response = requests.get(
        f"{API_URL}/onus/?olt=21&ordering=-id&page_size=10",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        onus = data.get('results', [])
        
        print(f"Total de ONUs encontradas: {data.get('count', 0)}")
        print()
        print(f"{'ID':<8} {'Posición':<12} {'SNMP Desc':<12} {'Serial':<18} "
              f"{'Modelo':<10} {'Plan':<8} {'Active'}")
        print("-" * 90)
        
        for onu in onus:
            print(f"{onu['id']:<8} "
                  f"{onu['slot']}/{onu['port']}/{onu['logical']:<8} "
                  f"{onu.get('snmp_description', 'N/A'):<12} "
                  f"{onu.get('serial_number', 'N/A'):<18} "
                  f"{onu.get('modelo_onu', 'N/A'):<10} "
                  f"{onu.get('plan_onu', 'N/A'):<8} "
                  f"{onu['active']}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
    
    print()


def menu_principal():
    """Menú principal con todas las opciones"""
    print("\n" + "=" * 60)
    print("  EJEMPLOS DE CREACIÓN DE ONUs - Facho Deluxe v2")
    print("=" * 60)
    print()
    print("1. Crear ONU con datos MÍNIMOS")
    print("2. Crear ONU con DATOS COMPLETOS")
    print("3. Crear ONU SUSPENDIDA")
    print("4. Crear MÚLTIPLES ONUs (aleatorias)")
    print("5. VERIFICAR ONUs creadas")
    print("6. Ejecutar TODOS los ejemplos")
    print("0. Salir")
    print()
    
    opcion = input("Selecciona una opción: ")
    
    if opcion == "1":
        crear_onu_minimo()
    elif opcion == "2":
        crear_onu_completo()
    elif opcion == "3":
        crear_onu_suspendida()
    elif opcion == "4":
        crear_onus_masivas()
    elif opcion == "5":
        verificar_onus_creadas()
    elif opcion == "6":
        crear_onu_minimo()
        crear_onu_completo()
        crear_onu_suspendida()
        crear_onus_masivas()
        verificar_onus_creadas()
    elif opcion == "0":
        print("¡Hasta luego!")
        return False
    else:
        print("❌ Opción inválida")
    
    return True


def mostrar_resumen():
    """Muestra un resumen de cómo funciona la creación de ONUs"""
    print()
    print("=" * 60)
    print("  RESUMEN: Cómo funciona la creación de ONUs")
    print("=" * 60)
    print()
    print("📋 DATOS MÍNIMOS REQUERIDOS:")
    print("   • olt (ID de la OLT)")
    print("   • slot, port, logical (posición de la ONU)")
    print("   • active (true=activo, false=suspendido)")
    print()
    print("✅ EL SISTEMA AUTOMÁTICAMENTE:")
    print("   • Busca la fórmula SNMP de la marca de la OLT")
    print("   • Calcula el raw_index_key usando la fórmula inversa")
    print("   • Crea 3 registros relacionados:")
    print("     1. OnuIndexMap (con raw_index_key y slot/port/logical)")
    print("     2. OnuStatus (con presence=ENABLED o DISABLED)")
    print("     3. OnuInventory (con todos los datos proporcionados)")
    print()
    print("📝 CAMPOS OPCIONALES que puedes agregar:")
    print("   • serial_number, mac_address")
    print("   • modelo_onu (ej: HG8310M, F601, AN5506-04-F)")
    print("   • plan_onu (ej: 100MB, 50MB, 200MB)")
    print("   • distancia_onu (en metros)")
    print("   • snmp_description (DNI, nombre, código de cliente)")
    print("   • subscriber_id (ID del suscriptor)")
    print()
    print("⚠️  IMPORTANTE:")
    print("   El cálculo del raw_index_key depende de la FÓRMULA SNMP")
    print("   configurada para la marca de la OLT.")
    print()
    print("   Por ejemplo, para Huawei:")
    print("   • Base: 4194304000")
    print("   • Step Slot: 8192")
    print("   • Step Port: 256")
    print()
    print("   Entonces, para slot=5, port=3, logical=10:")
    print("   raw_index_key = 4194304000 + (5 * 8192) + (3 * 256) + 10")
    print("   raw_index_key = 4194304000 + 40960 + 768 + 10")
    print("   raw_index_key = 4194345738")
    print()
    print("   Si la OLT usa notación con punto (has_dot_notation=True):")
    print("   raw_index_key = 4194345738.10")
    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    mostrar_resumen()
    
    while True:
        continuar = menu_principal()
        if not continuar:
            break
    
    print()
    print("=" * 60)
    print("  FIN DE LOS EJEMPLOS")
    print("=" * 60)
    print()

