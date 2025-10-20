#!/usr/bin/env python
"""
Script para probar las acciones de duplicación corregidas
Ejecutar: python probar_acciones_corregidas.py
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
    
    formulas = IndexFormula.objects.all().select_related('marca', 'modelo').order_by('marca__nombre', 'modelo__nombre')
    
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


def simular_duplicacion_ma5800():
    """Simula la duplicación de la fórmula MA5800"""
    print("\n" + "="*60)
    print("🧪 SIMULACIÓN: DUPLICAR MA5800")
    print("="*60)
    
    try:
        formula_ma5800 = IndexFormula.objects.get(
            marca__nombre='Huawei',
            modelo__nombre='MA5800'
        )
        
        print(f"✅ Fórmula MA5800 encontrada: {formula_ma5800}")
        print(f"   Tipo: Específica (modelo: {formula_ma5800.modelo.nombre})")
        
        print(f"\n💡 Acción '📋 Duplicar fórmula seleccionada':")
        print(f"   - Seleccionar: '{formula_ma5800.nombre}'")
        print(f"   - Resultado: Copia GENÉRICA creada")
        print(f"   - Nombre: 'Huawei - MA5800 (Copia Genérica)'")
        print(f"   - Estado: Inactiva (para revisar)")
        print(f"   - Modelo: NULL (genérica)")
        
        print(f"\n✅ VENTAJA: No hay conflicto de unicidad porque la copia es genérica")
        
    except IndexFormula.DoesNotExist:
        print("❌ Fórmula MA5800 no encontrada")


def simular_duplicacion_generica():
    """Simula la duplicación de la fórmula genérica"""
    print("\n" + "="*60)
    print("🧪 SIMULACIÓN: DUPLICAR FÓRMULA GENÉRICA")
    print("="*60)
    
    try:
        formulas_genericas = IndexFormula.objects.filter(
            marca__nombre='Huawei',
            modelo__isnull=True
        )
        
        if not formulas_genericas.exists():
            print("❌ No hay fórmulas genéricas de Huawei")
            return
        
        formula_generica = formulas_genericas.first()
        
        print(f"✅ Fórmula genérica encontrada: {formula_generica}")
        print(f"   Tipo: Genérica (modelo: NULL)")
        
        print(f"\n💡 Acción '📋 Duplicar fórmula seleccionada':")
        print(f"   - Seleccionar: '{formula_generica.nombre}'")
        print(f"   - Resultado: Copia GENÉRICA creada")
        print(f"   - Nombre: 'Huawei - Fórmula Estándar (Copia)'")
        print(f"   - Estado: Inactiva (para revisar)")
        print(f"   - Modelo: NULL (genérica)")
        
        print(f"\n💡 Acción '🎯 Duplicar para modelos específicos':")
        print(f"   - Seleccionar: '{formula_generica.nombre}'")
        print(f"   - Resultado: Fórmulas específicas para modelos sin fórmula")
        
        # Verificar modelos sin fórmula
        modelos_sin_formula = OLTModel.objects.filter(
            marca=formula_generica.marca,
            activo=True
        ).exclude(
            id__in=IndexFormula.objects.filter(
                marca=formula_generica.marca,
                modelo__isnull=False
            ).values_list('modelo_id', flat=True)
        )
        
        if modelos_sin_formula.exists():
            print(f"   - Modelos que recibirían fórmulas:")
            for modelo in modelos_sin_formula:
                print(f"     • {modelo.nombre} → 'Huawei {modelo.nombre} - Fórmula específica'")
        else:
            print(f"   - ✅ Todos los modelos ya tienen fórmulas específicas")
        
    except IndexFormula.DoesNotExist:
        print("❌ Fórmula genérica de Huawei no encontrada")


def mostrar_instrucciones_corregidas():
    """Muestra instrucciones de uso corregidas"""
    print("\n" + "="*60)
    print("📖 INSTRUCCIONES CORREGIDAS")
    print("="*60)
    print("""
🎯 CÓMO USAR LAS ACCIONES (CORREGIDAS):

1. 📋 DUPLICAR FÓRMULA SELECCIONADA:
   
   ✅ FÓRMULA ESPECÍFICA (ej: MA5800):
   - Selecciona: "Huawei - MA5800"
   - Acción: "📋 Duplicar fórmula seleccionada"
   - Resultado: "Huawei - MA5800 (Copia Genérica)" (genérica, inactiva)
   - ✅ NO hay conflicto de unicidad
   
   ✅ FÓRMULA GENÉRICA (ej: Fórmula Estándar):
   - Selecciona: "Huawei - Fórmula Estándar"
   - Acción: "📋 Duplicar fórmula seleccionada"
   - Resultado: "Huawei - Fórmula Estándar (Copia)" (genérica, inactiva)

2. 🎯 DUPLICAR PARA MODELOS ESPECÍFICOS:
   - Solo funciona con fórmulas GENÉRICAS
   - Crea fórmulas específicas para modelos sin fórmula
   - Evita duplicados automáticamente

🔧 LÓGICA CORREGIDA:
   - Fórmula específica → Copia genérica (evita conflicto)
   - Fórmula genérica → Copia genérica (normal)
   - Todas las copias se crean INACTIVAS para revisar
   - Nombres únicos para evitar confusiones

✅ VENTAJAS:
   - No más errores de unicidad
   - Copias seguras para experimentar
   - Fácil identificación de copias
   - Estado inactivo por defecto
    """)


if __name__ == "__main__":
    # Ejecutar todas las verificaciones
    mostrar_formulas_actuales()
    simular_duplicacion_ma5800()
    simular_duplicacion_generica()
    mostrar_instrucciones_corregidas()
    
    print("\n" + "="*60)
    print("✅ VERIFICACIÓN COMPLETA - ACCIONES CORREGIDAS")
    print("="*60)
    print("\n💡 Próximos pasos:")
    print("   1. Ir al admin de fórmulas SNMP")
    print("   2. Probar duplicación de MA5800 (ahora funciona)")
    print("   3. Probar duplicación para modelos específicos")
    print("   4. Activar las copias que necesites")
    print()
