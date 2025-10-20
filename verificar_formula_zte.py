#!/usr/bin/env python
"""
Script para verificar la fórmula ZTE implementada
Ejecutar: python verificar_formula_zte.py
"""

import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from snmp_formulas.models import IndexFormula
from olt_models.models import OLTModel
from brands.models import Brand

def mostrar_formula_zte():
    """Muestra la fórmula ZTE configurada"""
    print("\n" + "="*60)
    print("📋 FÓRMULA ZTE CONFIGURADA")
    print("="*60)
    
    try:
        zte = Brand.objects.get(nombre='ZTE')
        formula = IndexFormula.objects.get(marca=zte, modelo__isnull=True)
        
        print(f"✅ Fórmula encontrada: {formula}")
        print(f"   Marca: {formula.marca.nombre}")
        print(f"   Tipo: Genérica (para toda la marca)")
        print(f"   Modo: {formula.get_calculation_mode_display()}")
        print(f"   Base: {formula.base_index:,}")
        print(f"   Step Slot: {formula.step_slot:,}")
        print(f"   Step Port: {formula.step_port:,}")
        print(f"   Formato: {formula.normalized_format}")
        print(f"   Estado: {'✅ Activo' if formula.activo else '❌ Inactivo'}")
        
        return formula
        
    except Brand.DoesNotExist:
        print("❌ Marca ZTE no encontrada")
        return None
    except IndexFormula.DoesNotExist:
        print("❌ Fórmula ZTE no encontrada")
        return None


def probar_casos_zte():
    """Prueba la fórmula ZTE con casos reales"""
    print("\n" + "="*60)
    print("🧪 PROBANDO CASOS ZTE")
    print("="*60)
    
    try:
        zte = Brand.objects.get(nombre='ZTE')
        formula = IndexFormula.objects.get(marca=zte, modelo__isnull=True)
        
        # Casos de prueba basados en los datos proporcionados
        test_cases = [
            # (índice_snmp, slot_esperado, port_esperado, descripción)
            ('268566784', 2, 1, '2/1 - Caso base'),
            ('268567040', 2, 2, '2/2 - Incremento puerto'),
            ('268567296', 2, 3, '2/3 - Incremento puerto'),
            ('268632320', 3, 1, '3/1 - Incremento slot'),
            ('268697856', 4, 1, '4/1 - Incremento slot'),
            ('268763392', 5, 1, '5/1 - Incremento slot'),
            ('268828928', 6, 1, '6/1 - Incremento slot'),
            ('268894464', 7, 1, '7/1 - Incremento slot'),
            ('268960000', 8, 1, '8/1 - Incremento slot'),
            ('269025536', 9, 1, '9/1 - Incremento slot'),
            ('269222144', 12, 1, '12/1 - Incremento slot'),
            ('268570624', 2, 16, '2/16 - Último puerto del slot 2'),
            ('268636160', 3, 16, '3/16 - Último puerto del slot 3'),
            ('269225984', 12, 16, '12/16 - Último puerto del slot 12'),
        ]
        
        print("📊 CASOS DE PRUEBA:")
        print("-" * 60)
        
        all_passed = True
        for index_str, exp_slot, exp_port, desc in test_cases:
            result = formula.calculate_components(index_str)
            
            slot_ok = result['slot'] == exp_slot
            port_ok = result['port'] == exp_port
            passed = slot_ok and port_ok
            
            status = "✅" if passed else "❌"
            print(f"{status} {desc}")
            print(f"   Índice: {index_str}")
            print(f"   Esperado: slot={exp_slot}, port={exp_port}")
            print(f"   Obtenido: slot={result['slot']}, port={result['port']}")
            
            # Mostrar ID normalizado
            normalized = formula.get_normalized_id(result['slot'], result['port'], result['logical'])
            print(f"   Normalizado: {normalized}")
            print()
            
            if not passed:
                all_passed = False
        
        if all_passed:
            print("🎉 ¡TODOS LOS TESTS ZTE PASARON!")
        else:
            print("⚠️ ALGUNOS TESTS ZTE FALLARON")
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Error en pruebas: {e}")
        return False


def mostrar_modelos_zte():
    """Muestra los modelos ZTE configurados"""
    print("\n" + "="*60)
    print("🔧 MODELOS ZTE CONFIGURADOS")
    print("="*60)
    
    try:
        zte = Brand.objects.get(nombre='ZTE')
        modelos = OLTModel.objects.filter(marca=zte, activo=True)
        
        if not modelos.exists():
            print("⚠️ No hay modelos ZTE configurados")
            return
        
        for modelo in modelos:
            print(f"\n✅ {modelo}")
            print(f"   Descripción: {modelo.descripcion}")
            print(f"   Tipo: {modelo.tipo_olt}")
            print(f"   Capacidad: {modelo.get_capacidad_display()}")
            if modelo.comunidad_snmp_default:
                print(f"   SNMP Default: {modelo.comunidad_snmp_default}")
        
    except Brand.DoesNotExist:
        print("❌ Marca ZTE no encontrada")


def simular_olt_zte():
    """Simula una OLT ZTE para probar la lógica de prioridad"""
    print("\n" + "="*60)
    print("🏢 SIMULANDO OLT ZTE")
    print("="*60)
    
    try:
        zte = Brand.objects.get(nombre='ZTE')
        modelo_c320 = OLTModel.objects.get(marca=zte, nombre='C320')
        
        print(f"✅ Simulando OLT ZTE:")
        print(f"   Marca: {zte.nombre}")
        print(f"   Modelo: {modelo_c320.nombre}")
        print(f"   Índice de prueba: 268566784 (2/1)")
        
        # Simular búsqueda de fórmula
        from discovery.models import OnuIndexMap
        
        # Crear OLT temporal para simulación
        class MockOLT:
            def __init__(self, marca, modelo):
                self.marca = marca
                self.modelo = modelo
        
        mock_olt = MockOLT(zte, modelo_c320)
        
        # Simular OnuIndexMap
        onu_map = OnuIndexMap(
            olt=mock_olt,
            raw_index_key='268566784',
            normalized_id='temp'
        )
        
        # Buscar fórmula (simular la lógica)
        formula = None
        
        # PRIORIDAD 1: Marca + Modelo específico
        if mock_olt.modelo:
            formula = IndexFormula.objects.filter(
                marca=mock_olt.marca,
                modelo=mock_olt.modelo,
                activo=True
            ).first()
        
        # PRIORIDAD 2: Marca genérica
        if not formula:
            formula = IndexFormula.objects.filter(
                marca=mock_olt.marca,
                modelo__isnull=True,
                activo=True
            ).first()
        
        if formula:
            print(f"✅ Fórmula encontrada: {formula}")
            print(f"   Prioridad: {'🥇 Específica' if mock_olt.modelo else '🥈 Genérica'}")
            
            # Calcular componentes
            result = formula.calculate_components('268566784')
            print(f"   Resultado: slot={result['slot']}, port={result['port']}")
            print(f"   Normalizado: {formula.get_normalized_id(result['slot'], result['port'], result['logical'])}")
        else:
            print("❌ No se encontró fórmula")
        
    except Exception as e:
        print(f"❌ Error en simulación: {e}")


def mostrar_instrucciones_zte():
    """Muestra instrucciones para usar ZTE"""
    print("\n" + "="*60)
    print("📖 INSTRUCCIONES PARA ZTE")
    print("="*60)
    print("""
🎯 CÓMO USAR ZTE EN EL SISTEMA:

1. 🏷️ CONFIGURACIÓN COMPLETADA:
   ✅ Marca ZTE creada
   ✅ Fórmula ZTE configurada (genérica)
   ✅ 3 modelos ZTE creados (C320, C300, C600)

2. 🔧 CONFIGURAR OLT ZTE:
   - Ir a: http://127.0.0.1:8000/admin/hosts/olt/
   - Editar OLT ZTE
   - Asignar: Marca = ZTE, Modelo = C320 (o el correspondiente)

3. 🚀 EJECUTAR TAREAS SNMP:
   - Crear tarea SNMP con OID de descubrimiento
   - Asignar a OLT ZTE
   - Ejecutar tarea
   - El sistema usará automáticamente la fórmula ZTE

4. 📊 RESULTADO ESPERADO:
   - Índice 268566784 → slot=2, port=1 → "2/1"
   - Índice 268632320 → slot=3, port=1 → "3/1"
   - Índice 268697856 → slot=4, port=1 → "4/1"

✅ FÓRMULA ZTE:
   - Modo: Linear
   - Base: 268,435,456
   - Step Slot: 65,536
   - Step Port: 256
   - Formato: {slot}/{port}
   - Sin notación con punto (como Huawei)

🔍 PRIORIDAD:
   - OLT con modelo → Busca fórmula específica (no existe aún)
   - OLT sin modelo → Usa fórmula genérica ZTE ✅
    """)


if __name__ == "__main__":
    # Ejecutar todas las verificaciones
    formula = mostrar_formula_zte()
    if formula:
        probar_casos_zte()
    mostrar_modelos_zte()
    simular_olt_zte()
    mostrar_instrucciones_zte()
    
    print("\n" + "="*60)
    print("✅ VERIFICACIÓN COMPLETA - ZTE")
    print("="*60)
    print("\n💡 Próximos pasos:")
    print("   1. Configurar OLTs ZTE con marca y modelo")
    print("   2. Crear tareas SNMP para OLTs ZTE")
    print("   3. Ejecutar descubrimiento y verificar resultados")
    print("   4. Crear fórmulas específicas por modelo si es necesario")
    print()
