#!/usr/bin/env python
"""
Script de prueba para el sistema de fórmulas SNMP
Ejecutar: python manage.py shell < snmp_formulas/test_formulas.py
"""

from snmp_formulas.models import IndexFormula
from brands.models import Brand

def test_huawei_formula():
    """Prueba la fórmula de Huawei con casos conocidos"""
    print("\n" + "="*60)
    print("🧪 PROBANDO FÓRMULA HUAWEI")
    print("="*60)
    
    try:
        huawei = Brand.objects.get(nombre__iexact='huawei')
        formula = IndexFormula.objects.get(marca=huawei, modelo__isnull=True)
        
        print(f"✅ Fórmula encontrada: {formula.nombre}")
        print(f"   Modo: {formula.get_calculation_mode_display()}")
        print(f"   Base: {formula.base_index:,}")
        print(f"   Step Slot: {formula.step_slot:,}")
        print(f"   Step Port: {formula.step_port:,}")
        print(f"   Formato: {formula.normalized_format}")
        print()
        
        # Casos de prueba
        test_cases = [
            # (raw_index_key, expected_slot, expected_port, expected_logical)
            ("4194312448.2", 1, 1, 2),      # Caso básico
            ("4194316032.10", 1, 15, 10),   # Puerto alto
            ("4194338304.1", 4, 6, 1),      # Slot 4, puerto 6
            ("4194338304.2", 4, 6, 2),      # Slot 4, puerto 6, ONU 2
            ("4194338304.3", 4, 6, 3),      # Slot 4, puerto 6, ONU 3
        ]
        
        print("📊 CASOS DE PRUEBA:")
        print("-" * 60)
        
        all_passed = True
        for raw_index, exp_slot, exp_port, exp_logical in test_cases:
            result = formula.calculate_components(raw_index)
            
            slot_ok = result['slot'] == exp_slot
            port_ok = result['port'] == exp_port
            logical_ok = result['logical'] == exp_logical
            passed = slot_ok and port_ok and logical_ok
            
            status = "✅" if passed else "❌"
            print(f"{status} Índice: {raw_index}")
            print(f"   Esperado: slot={exp_slot}, port={exp_port}, logical={exp_logical}")
            print(f"   Obtenido: slot={result['slot']}, port={result['port']}, logical={result['logical']}")
            
            # Mostrar ID normalizado
            normalized = formula.get_normalized_id(result['slot'], result['port'], result['logical'])
            print(f"   Normalizado: {normalized}")
            print()
            
            if not passed:
                all_passed = False
        
        if all_passed:
            print("🎉 ¡TODOS LOS TESTS PASARON!")
        else:
            print("⚠️ ALGUNOS TESTS FALLARON")
        
        return all_passed
        
    except Brand.DoesNotExist:
        print("❌ ERROR: Marca Huawei no encontrada")
        return False
    except IndexFormula.DoesNotExist:
        print("❌ ERROR: Fórmula Huawei no encontrada")
        print("   Ejecuta: python manage.py migrate snmp_formulas")
        return False
    except Exception as e:
        print(f"❌ ERROR INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        return False


def list_all_formulas():
    """Lista todas las fórmulas configuradas"""
    print("\n" + "="*60)
    print("📋 FÓRMULAS CONFIGURADAS")
    print("="*60)
    
    formulas = IndexFormula.objects.all().select_related('marca')
    
    if not formulas.exists():
        print("⚠️ No hay fórmulas configuradas")
        return
    
    for formula in formulas:
        status = "✅ ACTIVA" if formula.activo else "❌ INACTIVA"
        print(f"\n{status} {formula}")
        print(f"   Marca: {formula.marca.nombre}")
        if formula.modelo:
            print(f"   Modelo: {formula.modelo}")
        print(f"   Modo: {formula.get_calculation_mode_display()}")
        
        if formula.calculation_mode == 'linear':
            print(f"   Base: {formula.base_index:,}")
            print(f"   Step Slot: {formula.step_slot:,}")
            print(f"   Step Port: {formula.step_port:,}")
        else:
            print(f"   Shift Slot: {formula.shift_slot_bits} bits")
            print(f"   Shift Port: {formula.shift_port_bits} bits")
        
        print(f"   Formato: {formula.normalized_format}")


def show_example_zte():
    """Muestra ejemplo de cómo configurar ZTE"""
    print("\n" + "="*60)
    print("📝 EJEMPLO: CÓMO CONFIGURAR ZTE")
    print("="*60)
    print("""
Para configurar ZTE (ejemplo con índice 268566784 = slot 2, port 1):

1. Ir a Django Admin → SNMP Formulas → Index Formulas → Agregar

2. Configurar:
   - Marca: ZTE
   - Modelo: (vacío para genérico)
   - Nombre: ZTE - Fórmula Estándar
   - Activo: ✓
   
   - Calculation Mode: linear
   - Base Index: [NECESITA INVESTIGACIÓN]
   - Step Slot: [NECESITA INVESTIGACIÓN]
   - Step Port: [NECESITA INVESTIGACIÓN]
   
   - ONU Offset: 0
   - Has Dot Notation: ✗ (si no usa punto)
   
   - Slot Max: 64
   - Port Max: 64
   - ONU Max: 128
   
   - Normalized Format: {slot}/{port}

3. Guardar

4. El sistema lo usará automáticamente para OLTs marca ZTE

NOTA: Necesitas investigar la fórmula exacta de ZTE para completar
      los valores de base_index, step_slot y step_port.
    """)


if __name__ == "__main__":
    # Ejecutar todas las pruebas
    list_all_formulas()
    test_huawei_formula()
    show_example_zte()
    
    print("\n" + "="*60)
    print("✅ VERIFICACIÓN COMPLETA")
    print("="*60)

