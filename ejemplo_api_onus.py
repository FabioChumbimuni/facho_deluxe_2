#!/usr/bin/env python3
"""
Ejemplos de uso de la API de ONUs con Python
"""
import requests
import json

# Configuración
BASE_URL = "http://192.168.56.222:8000/api/v1"
# Obtener token: requests.post(f"{BASE_URL}/auth/login/", json={"username": "admin", "password": "pass"})
TOKEN = "TU_TOKEN_AQUI"

headers = {
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json"
}


def buscar_por_snmp_description(descripcion):
    """Buscar ONUs por SNMP description (ej: 70540036)"""
    print(f"\n🔍 Buscando ONUs con descripción: {descripcion}")
    print("-" * 60)
    
    response = requests.get(
        f"{BASE_URL}/onus/",
        headers=headers,
        params={"search": descripcion}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Total encontrados: {data['count']}")
        print(f"📄 Resultados en esta página: {len(data['results'])}")
        
        for onu in data['results'][:3]:  # Mostrar primeros 3
            print(f"\n   • ID: {onu['id']}")
            print(f"     OLT: {onu['olt_nombre']}")
            print(f"     Posición: {onu['slot']}/{onu['port']}/{onu['logical']}")
            print(f"     Serial: {onu['serial_number']}")
            print(f"     Descripción: {onu['snmp_description']}")
            print(f"     Modelo: {onu['modelo_onu']}")
            print(f"     Plan: {onu['plan_onu']}")
            print(f"     Estado: {onu['presence']}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def filtrar_por_olt_y_plan(olt_id, plan):
    """Filtrar ONUs por OLT y plan"""
    print(f"\n🎯 Filtrando ONUs de OLT {olt_id} con plan {plan}")
    print("-" * 60)
    
    response = requests.get(
        f"{BASE_URL}/onus/",
        headers=headers,
        params={
            "olt": olt_id,
            "plan_onu": plan
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Total encontrados: {data['count']}")
        
        for onu in data['results'][:5]:  # Mostrar primeros 5
            print(f"   • {onu['normalized_id']} - {onu['serial_number']} - {onu['modelo_onu']}")
    else:
        print(f"❌ Error: {response.status_code}")


def crear_onu_completa():
    """Crear una nueva ONU (crea en las 3 tablas automáticamente)"""
    print(f"\n➕ Creando nueva ONU")
    print("-" * 60)
    
    nueva_onu = {
        "olt": 1,
        "raw_index_key_input": "4194312192.25",  # Índice SNMP
        "serial_number": "HWTC99887766",
        "mac_address": "11:22:33:44:55:66",
        "subscriber_id": "CLI-70540036",
        "plan_onu": "200M",
        "distancia_onu": "3.2",
        "modelo_onu": "HG8546M",
        "snmp_description": "Cliente 70540036 - Maria Lopez",
        "active": True
    }
    
    print("Datos a enviar:")
    print(json.dumps(nueva_onu, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/onus/",
        headers=headers,
        json=nueva_onu
    )
    
    if response.status_code == 201:
        onu = response.json()
        print(f"\n✅ ONU creada exitosamente!")
        print(f"   ID: {onu['id']}")
        print(f"   Posición calculada: {onu['slot']}/{onu['port']}/{onu['logical']}")
        print(f"   Normalized ID: {onu['normalized_id']}")
        print(f"\n   Se crearon automáticamente:")
        print(f"   ✓ OnuIndexMap (ID del índice)")
        print(f"   ✓ OnuStatus (con presence='ENABLED')")
        print(f"   ✓ OnuInventory (con toda la información)")
        return onu['id']
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None


def actualizar_modelo_onu(onu_id, nuevo_modelo, nueva_distancia=None):
    """Actualizar solo el modelo de una ONU (PATCH)"""
    print(f"\n✏️  Actualizando ONU {onu_id}")
    print("-" * 60)
    
    datos_actualizacion = {
        "modelo_onu": nuevo_modelo
    }
    
    if nueva_distancia:
        datos_actualizacion["distancia_onu"] = nueva_distancia
    
    print("Datos a actualizar:")
    print(json.dumps(datos_actualizacion, indent=2))
    
    response = requests.patch(
        f"{BASE_URL}/onus/{onu_id}/",
        headers=headers,
        json=datos_actualizacion
    )
    
    if response.status_code == 200:
        onu = response.json()
        print(f"\n✅ ONU actualizada exitosamente!")
        print(f"   Modelo actualizado: {onu['modelo_onu']}")
        if nueva_distancia:
            print(f"   Distancia actualizada: {onu['distancia_onu']}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)


def obtener_detalles_onu(onu_id):
    """Obtener todos los detalles de una ONU"""
    print(f"\n📋 Obteniendo detalles de ONU {onu_id}")
    print("-" * 60)
    
    response = requests.get(
        f"{BASE_URL}/onus/{onu_id}/",
        headers=headers
    )
    
    if response.status_code == 200:
        onu = response.json()
        print(f"\n✅ Detalles de la ONU:")
        print(f"\n📍 Ubicación:")
        print(f"   OLT: {onu['olt_nombre']} (ID: {onu['olt']})")
        print(f"   Posición: Slot {onu['slot']}, Port {onu['port']}, Logical {onu['logical']}")
        print(f"   Normalized ID: {onu['normalized_id']}")
        
        print(f"\n🔖 Identificación:")
        print(f"   Serial: {onu['serial_number']}")
        print(f"   MAC: {onu['mac_address']}")
        print(f"   Subscriber ID: {onu['subscriber_id']}")
        
        print(f"\n⚙️  Configuración:")
        print(f"   Plan: {onu['plan_onu']}")
        print(f"   Modelo: {onu['modelo_onu']}")
        print(f"   Distancia: {onu['distancia_onu']}")
        
        print(f"\n📡 SNMP:")
        print(f"   Descripción: {onu['snmp_description']}")
        print(f"   Última recolección: {onu['snmp_last_collected_at']}")
        
        print(f"\n📊 Estado:")
        print(f"   Presence: {onu['presence']}")
        print(f"   Estado: {onu['estado_label']}")
        print(f"   Último visto: {onu['last_seen_at']}")
        
        print(f"\n🔧 Control:")
        print(f"   Activo: {onu['active']}")
        print(f"   Creado: {onu['created_at']}")
        print(f"   Actualizado: {onu['updated_at']}")
        
        return onu
    else:
        print(f"❌ Error: {response.status_code}")
        return None


def listar_onus_activas():
    """Listar solo ONUs activas"""
    print(f"\n📋 Listando ONUs activas")
    print("-" * 60)
    
    response = requests.get(
        f"{BASE_URL}/onus/activas/",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Total ONUs activas: {data['count']}")
        print(f"\nPrimeras 10:")
        
        for i, onu in enumerate(data['results'][:10], 1):
            print(f"{i:2}. {onu['olt_nombre']:12} | {onu['slot']}/{onu['port']}/{onu['logical']:2} | "
                  f"{onu['serial_number']:15} | {onu['modelo_onu']:12} | {onu['presence']}")
    else:
        print(f"❌ Error: {response.status_code}")


def listar_onus_por_olt(olt_id):
    """Listar ONUs de una OLT específica"""
    print(f"\n📋 Listando ONUs de OLT {olt_id}")
    print("-" * 60)
    
    response = requests.get(
        f"{BASE_URL}/onus/por_olt/",
        headers=headers,
        params={"olt_id": olt_id}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Total ONUs en OLT {olt_id}: {data['count']}")
        
        # Agrupar por slot/port
        slots = {}
        for onu in data['results']:
            key = f"{onu['slot']}/{onu['port']}"
            if key not in slots:
                slots[key] = []
            slots[key].append(onu)
        
        print(f"\nDistribución por slot/port:")
        for slot_port, onus in sorted(slots.items())[:10]:
            print(f"   {slot_port}: {len(onus)} ONUs")
    else:
        print(f"❌ Error: {response.status_code}")


def main():
    """Ejecutar ejemplos"""
    print("=" * 60)
    print("🚀 EJEMPLOS DE USO DE LA API DE ONUs")
    print("=" * 60)
    
    # Ejemplo 1: Buscar por descripción
    buscar_por_snmp_description("70540036")
    
    # Ejemplo 2: Filtrar por OLT y plan
    filtrar_por_olt_y_plan(olt_id=1, plan="100M")
    
    # Ejemplo 3: Crear nueva ONU
    # nueva_onu_id = crear_onu_completa()
    
    # Ejemplo 4: Actualizar ONU
    # if nueva_onu_id:
    #     actualizar_modelo_onu(nueva_onu_id, "HG8546M_V3", "3.5")
    
    # Ejemplo 5: Obtener detalles
    # if nueva_onu_id:
    #     obtener_detalles_onu(nueva_onu_id)
    
    # Ejemplo 6: Listar ONUs activas
    listar_onus_activas()
    
    # Ejemplo 7: Listar ONUs por OLT
    listar_onus_por_olt(olt_id=1)
    
    print("\n" + "=" * 60)
    print("✅ Ejemplos completados")
    print("=" * 60)


if __name__ == "__main__":
    main()

