#!/usr/bin/env python
"""
Script para probar las acciones de duplicación de fórmulas
Ejecutar: python probar_acciones_formulas.py
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

def mostrar_formulas_actuales():
    """Muestra todas las fórmulas actuales"""
    print("\n" + "="*60)
    print("📋 FÓRMULAS ACTUALES")
    print("="*60)
    
    formulas = IndexFormula.objects.all().select_related('marca', 'modelo')
    
    if not formulas.exists():
        print("⚠️ No hay fórmulas configuradas")
        return
    
    for formula in formulas:
        modelo_display = f"🔧 {formula.modelo.nombre}" if formula.modelo else "🌐 Genérico"
        status = "✅ Activo" if formula.activo else "❌ Inactivo"
        
        print(f"\n{status} {formula}")
        print(f"   Marca: {formula.marca.nombre}")
        print(f"   Modelo: {modelo_display}")
        print(f"   Modo: {formula.get_calculation_mode_display()}")


def mostrar_modelos_sin_formula():
    """Muestra modelos que no tienen fórmula específica"""
    print("\n" + "="*60)
    print("🔍 MODELOS SIN FÓRMULA ESPECÍFICA")
    print("="*60)
    
    # Obtener todas las fórmulas específicas (con modelo)
    formulas_especificas = IndexFormula.objects.filter(
        modelo__isnull=False
    ).values_list('modelo_id', flat=True)
    
    # Modelos sin fórmula específica
    modelos_sin_formula = OLTModel.objects.filter(
        activo=True
    ).exclude(
        id__in=formulas_especificas
    ).select_related('marca')
    
    if not modelos_sin_formula.exists():
        print("✅ Todos los modelos tienen fórmulas específicas")
        return
    
    print(f"📊 Encontrados {modelos_sin_formula.count()} modelos sin fórmula específica:")
    
    for modelo in modelos_sin_formula:
        print(f"   • {modelo.marca.nombre} - {modelo.nombre}")


def simular_duplicacion_para_modelos():
    """Simula la duplicación para modelos específicos"""
    print("\n" + "="*60)
    print("🧪 SIMULACIÓN: DUPLICAR PARA MODELOS ESPECÍFICOS")
    print("="*60)
    
    # Buscar fórmula genérica de Huawei
    try:
        huawei = Brand.objects.get(nombre__iexact='huawei')
        formula_generica = IndexFormula.objects.get(
            marca=huawei,
            modelo__isnull=True
        )
        
        print(f"✅ Fórmula genérica encontrada: {formula_generica}")
        
        # Obtener modelos Huawei sin fórmula específica
        modelos_sin_formula = OLTModel.objects.filter(
            marca=huawei,
            activo=True
        ).exclude(
            id__in=IndexFormula.objects.filter(
                marca=huawei,
                modelo__isnull=False
            ).values_list('modelo_id', flat=True)
        )
        
        if modelos_sin_formula.exists():
            print(f"\n📋 Modelos que recibirían fórmulas específicas:")
            for modelo in modelos_sin_formula:
                print(f"   • {modelo.nombre} → {formula_generica.marca.nombre} {modelo.nombre} - Fórmula específica")
            
            print(f"\n💡 Acción recomendada:")
            print(f"   1. Ir a: http://127.0.0.1:8000/admin/snmp_formulas/indexformula/")
            print(f"   2. Seleccionar: '{formula_generica.nombre}'")
            print(f"   3. Acción: '🎯 Duplicar para modelos específicos'")
            print(f"   4. Ejecutar")
            print(f"   5. Se crearán {modelos_sin_formula.count()} fórmulas específicas")
        else:
            print("✅ Todos los modelos Huawei ya tienen fórmulas específicas")
            
    except Brand.DoesNotExist:
        print("❌ Marca Huawei no encontrada")
    except IndexFormula.DoesNotExist:
        print("❌ Fórmula genérica de Huawei no encontrada")


def mostrar_instrucciones_uso():
    """Muestra instrucciones de uso de las acciones"""
    print("\n" + "="*60)
    print("📖 INSTRUCCIONES DE USO")
    print("="*60)
    print("""
🎯 CÓMO USAR LAS ACCIONES:

1. 📋 DUPLICAR FÓRMULA SELECCIONADA:
   - Selecciona UNA fórmula
   - Acción: "📋 Duplicar fórmula seleccionada"
   - Crea una copia exacta (inactiva por defecto)
   - Útil para hacer modificaciones sin perder la original

2. 🎯 DUPLICAR PARA MODELOS ESPECÍFICOS:
   - Selecciona UNA fórmula GENÉRICA (sin modelo)
   - Acción: "🎯 Duplicar para modelos específicos"
   - Crea fórmulas específicas para todos los modelos de la marca
   - Útil para tener fórmulas por modelo específico

🔍 EJEMPLO PRÁCTICO:

Para crear fórmulas específicas de Huawei:
1. Ir a: http://127.0.0.1:8000/admin/snmp_formulas/indexformula/
2. Seleccionar: "Huawei - Fórmula Estándar" (genérica)
3. Acción: "🎯 Duplicar para modelos específicos"
4. Ejecutar
5. Resultado: Se crean fórmulas para MA5800, MA5608T, AN5516-06

✅ VENTAJAS:
   - Fórmulas específicas por modelo
   - Prioridad automática: específica → genérica
   - Fácil personalización por modelo
   - Mantiene compatibilidad con genéricas
    """)


if __name__ == "__main__":
    # Ejecutar todas las verificaciones
    mostrar_formulas_actuales()
    mostrar_modelos_sin_formula()
    simular_duplicacion_para_modelos()
    mostrar_instrucciones_uso()
    
    print("\n" + "="*60)
    print("✅ VERIFICACIÓN COMPLETA")
    print("="*60)
    print("\n💡 Próximos pasos:")
    print("   1. Ir al admin de fórmulas SNMP")
    print("   2. Probar las acciones de duplicación")
    print("   3. Crear fórmulas específicas por modelo")
    print("   4. Asignar modelos a OLTs")
    print()
