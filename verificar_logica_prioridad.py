#!/usr/bin/env python
"""
Script para verificar la lógica de prioridad de fórmulas SNMP
Ejecutar: python verificar_logica_prioridad.py
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
from hosts.models import OLT
from discovery.models import OnuIndexMap

def mostrar_prioridad_formulas():
    """Muestra la lógica de prioridad de fórmulas"""
    print("\n" + "="*60)
    print("🎯 LÓGICA DE PRIORIDAD DE FÓRMULAS")
    print("="*60)
    print("""
📋 PRIORIDAD DE BÚSQUEDA (de mayor a menor):

1. 🥇 PRIORIDAD 1: Fórmula específica por marca + modelo
   - Busca: marca=X, modelo=Y
   - Ejemplo: Huawei + MA5800

2. 🥈 PRIORIDAD 2: Fórmula genérica por marca
   - Busca: marca=X, modelo=NULL
   - Ejemplo: Huawei + (sin modelo)

3. 🥉 PRIORIDAD 3: Fórmula completamente genérica
   - Busca: marca=NULL, modelo=NULL
   - Ejemplo: (sin marca) + (sin modelo)

4. ❌ SIN FÓRMULA: No calcula componentes
   - Si no hay ninguna fórmula configurada
   - slot/port/logical = NULL (se requiere fórmula)

💡 CASOS DE USO:
   - OLT con marca y modelo → Prioridad 1
   - OLT con marca sin modelo → Prioridad 2
   - OLT sin marca → Prioridad 3
   - OLT Huawei sin fórmulas → Fallback legacy
    """)


def simular_busqueda_formula(olt, raw_index_key="4194312448.2"):
    """Simula la búsqueda de fórmula para una OLT específica"""
    print(f"\n🔍 SIMULANDO BÚSQUEDA PARA: {olt.abreviatura}")
    print(f"   Marca: {olt.marca.nombre if olt.marca else 'Sin marca'}")
    print(f"   Modelo: {olt.modelo.nombre if olt.modelo else 'Sin modelo'}")
    print(f"   Índice: {raw_index_key}")
    print("-" * 50)
    
    formula_encontrada = None
    prioridad_usada = None
    
    # PRIORIDAD 1: Marca + Modelo específico
    if olt.modelo:
        formula = IndexFormula.objects.filter(
            marca=olt.marca,
            modelo=olt.modelo,
            activo=True
        ).first()
        
        if formula:
            formula_encontrada = formula
            prioridad_usada = "🥇 PRIORIDAD 1: Específica (marca + modelo)"
            print(f"✅ {prioridad_usada}")
            print(f"   Fórmula: {formula}")
            return formula_encontrada, prioridad_usada
    
    # PRIORIDAD 2: Marca genérica
    if olt.marca:
        formula = IndexFormula.objects.filter(
            marca=olt.marca,
            modelo__isnull=True,
            activo=True
        ).first()
        
        if formula:
            formula_encontrada = formula
            prioridad_usada = "🥈 PRIORIDAD 2: Genérica por marca"
            print(f"✅ {prioridad_usada}")
            print(f"   Fórmula: {formula}")
            return formula_encontrada, prioridad_usada
    
    # PRIORIDAD 3: Completamente genérica
    formula = IndexFormula.objects.filter(
        marca__isnull=True,
        modelo__isnull=True,
        activo=True
    ).first()
    
    if formula:
        formula_encontrada = formula
        prioridad_usada = "🥉 PRIORIDAD 3: Completamente genérica"
        print(f"✅ {prioridad_usada}")
        print(f"   Fórmula: {formula}")
        return formula_encontrada, prioridad_usada
    
    # Sin fórmula
    prioridad_usada = "❌ SIN FÓRMULA"
    print(f"❌ {prioridad_usada}")
    print(f"   No hay fórmula disponible")
    return None, prioridad_usada


def probar_casos_olt():
    """Prueba diferentes casos de OLT"""
    print("\n" + "="*60)
    print("🧪 PROBANDO CASOS DE OLT")
    print("="*60)
    
    # Obtener algunas OLTs para probar
    olts = OLT.objects.all().select_related('marca', 'modelo')[:5]
    
    if not olts.exists():
        print("⚠️ No hay OLTs para probar")
        return
    
    for olt in olts:
        formula, prioridad = simular_busqueda_formula(olt)
        print()


def mostrar_formulas_por_prioridad():
    """Muestra las fórmulas organizadas por prioridad"""
    print("\n" + "="*60)
    print("📋 FÓRMULAS POR PRIORIDAD")
    print("="*60)
    
    # PRIORIDAD 1: Específicas
    formulas_especificas = IndexFormula.objects.filter(
        modelo__isnull=False,
        activo=True
    ).select_related('marca', 'modelo')
    
    print(f"\n🥇 PRIORIDAD 1 - FÓRMULAS ESPECÍFICAS ({formulas_especificas.count()}):")
    for formula in formulas_especificas:
        print(f"   • {formula.marca.nombre} + {formula.modelo.nombre} → {formula.nombre}")
    
    # PRIORIDAD 2: Genéricas por marca
    formulas_genericas_marca = IndexFormula.objects.filter(
        marca__isnull=False,
        modelo__isnull=True,
        activo=True
    ).select_related('marca')
    
    print(f"\n🥈 PRIORIDAD 2 - GENÉRICAS POR MARCA ({formulas_genericas_marca.count()}):")
    for formula in formulas_genericas_marca:
        print(f"   • {formula.marca.nombre} (genérica) → {formula.nombre}")
    
    # PRIORIDAD 3: Completamente genéricas
    formulas_genericas_universales = IndexFormula.objects.filter(
        marca__isnull=True,
        modelo__isnull=True,
        activo=True
    )
    
    print(f"\n🥉 PRIORIDAD 3 - COMPLETAMENTE GENÉRICAS ({formulas_genericas_universales.count()}):")
    for formula in formulas_genericas_universales:
        print(f"   • (sin marca) → {formula.nombre}")


def crear_formula_universal_ejemplo():
    """Crea una fórmula universal de ejemplo"""
    print("\n" + "="*60)
    print("🌍 CREAR FÓRMULA UNIVERSAL DE EJEMPLO")
    print("="*60)
    
    # Verificar si ya existe
    formula_universal = IndexFormula.objects.filter(
        marca__isnull=True,
        modelo__isnull=True,
        activo=True
    ).first()
    
    if formula_universal:
        print(f"✅ Ya existe fórmula universal: {formula_universal}")
        return formula_universal
    
    # Crear fórmula universal basada en Huawei
    try:
        formula_huawei = IndexFormula.objects.filter(
            marca__nombre='Huawei',
            activo=True
        ).first()
        
        if formula_huawei:
            formula_universal = IndexFormula.objects.create(
                marca=None,  # Sin marca
                modelo=None,  # Sin modelo
                nombre='Fórmula Universal - Basada en Huawei',
                activo=True,
                calculation_mode=formula_huawei.calculation_mode,
                base_index=formula_huawei.base_index,
                step_slot=formula_huawei.step_slot,
                step_port=formula_huawei.step_port,
                shift_slot_bits=formula_huawei.shift_slot_bits,
                shift_port_bits=formula_huawei.shift_port_bits,
                mask_slot=formula_huawei.mask_slot,
                mask_port=formula_huawei.mask_port,
                onu_offset=formula_huawei.onu_offset,
                has_dot_notation=formula_huawei.has_dot_notation,
                dot_is_onu_number=formula_huawei.dot_is_onu_number,
                slot_max=formula_huawei.slot_max,
                port_max=formula_huawei.port_max,
                onu_max=formula_huawei.onu_max,
                normalized_format=formula_huawei.normalized_format,
                descripcion='Fórmula universal para OLTs sin marca específica. Basada en parámetros Huawei.'
            )
            
            print(f"✅ Fórmula universal creada: {formula_universal}")
            return formula_universal
        else:
            print("⚠️ No hay fórmula Huawei para usar como base")
            return None
            
    except Exception as e:
        print(f"❌ Error creando fórmula universal: {e}")
        return None


def mostrar_instrucciones_uso():
    """Muestra instrucciones de uso del sistema"""
    print("\n" + "="*60)
    print("📖 INSTRUCCIONES DE USO")
    print("="*60)
    print("""
🎯 CÓMO USAR EL SISTEMA DE PRIORIDAD:

1. 🏷️ CREAR FÓRMULAS POR PRIORIDAD:
   
   🥇 PRIORIDAD 1 (Específica):
   - Marca: Huawei, Modelo: MA5800
   - Para OLTs con marca y modelo específico
   
   🥈 PRIORIDAD 2 (Genérica por marca):
   - Marca: Huawei, Modelo: (vacío)
   - Para OLTs con marca pero sin modelo
   
   🥉 PRIORIDAD 3 (Universal):
   - Marca: (vacío), Modelo: (vacío)
   - Para OLTs sin marca (solo puede haber UNA)

2. 🔧 CONFIGURAR OLTS:
   - Asignar marca y modelo a OLTs
   - OLTs sin marca usarán fórmula universal
   - OLTs con marca usarán fórmula específica o genérica

3. 🚀 EJECUTAR TAREAS SNMP:
   - El sistema busca automáticamente la fórmula correcta
   - Usa la prioridad más alta disponible
   - Calcula slot/port/logical automáticamente

✅ VENTAJAS:
   - Flexibilidad total de configuración
   - Fallback automático a fórmulas genéricas
   - Compatibilidad con código legacy
   - Una sola fórmula universal para casos especiales
    """)


if __name__ == "__main__":
    # Ejecutar todas las verificaciones
    mostrar_prioridad_formulas()
    mostrar_formulas_por_prioridad()
    crear_formula_universal_ejemplo()
    probar_casos_olt()
    mostrar_instrucciones_uso()
    
    print("\n" + "="*60)
    print("✅ VERIFICACIÓN COMPLETA DE LÓGICA DE PRIORIDAD")
    print("="*60)
    print("\n💡 Próximos pasos:")
    print("   1. Verificar que las tareas SNMP usen la lógica correcta")
    print("   2. Crear fórmulas específicas para modelos faltantes")
    print("   3. Configurar OLTs con marcas y modelos")
    print("   4. Probar con datos reales de descubrimiento")
    print()
