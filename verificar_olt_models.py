#!/usr/bin/env python
"""
Script standalone para verificar el sistema de modelos de OLT
Ejecutar: python verificar_olt_models.py
"""

import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from olt_models.models import OLTModel
from brands.models import Brand
from snmp_formulas.models import IndexFormula
from hosts.models import OLT

def list_olt_models():
    """Lista todos los modelos de OLT configurados"""
    print("\n" + "="*60)
    print("📋 MODELOS DE OLT CONFIGURADOS")
    print("="*60)
    
    models = OLTModel.objects.all().select_related('marca')
    
    if not models.exists():
        print("⚠️ No hay modelos de OLT configurados")
        return
    
    for model in models:
        status = "✅ ACTIVO" if model.activo else "❌ INACTIVO"
        print(f"\n{status} {model}")
        print(f"   Marca: {model.marca.nombre}")
        print(f"   Descripción: {model.descripcion}")
        
        if model.tipo_olt:
            print(f"   Tipo: {model.tipo_olt}")
        
        if model.capacidad_puertos and model.capacidad_onus:
            print(f"   Capacidad: {model.capacidad_puertos} puertos × {model.capacidad_onus} ONUs")
        elif model.capacidad_puertos:
            print(f"   Capacidad: {model.capacidad_puertos} puertos")
        
        if model.comunidad_snmp_default:
            print(f"   SNMP Default: {model.comunidad_snmp_default}")
        
        if model.url_documentacion:
            print(f"   Documentación: {model.url_documentacion}")


def test_formulas_with_models():
    """Prueba las fórmulas que usan modelos específicos"""
    print("\n" + "="*60)
    print("🧪 PROBANDO FÓRMULAS CON MODELOS")
    print("="*60)
    
    formulas = IndexFormula.objects.all().select_related('marca', 'modelo')
    
    if not formulas.exists():
        print("⚠️ No hay fórmulas configuradas")
        return
    
    for formula in formulas:
        print(f"\n📐 {formula}")
        print(f"   Marca: {formula.marca.nombre}")
        
        if formula.modelo:
            print(f"   Modelo específico: {formula.modelo.nombre}")
            print(f"   Tipo: {formula.modelo.tipo_olt or 'No especificado'}")
        else:
            print(f"   Modelo: 🌐 Genérico (toda la marca)")
        
        print(f"   Modo: {formula.get_calculation_mode_display()}")
        print(f"   Estado: {'✅ Activo' if formula.activo else '❌ Inactivo'}")


def test_olts_with_models():
    """Prueba las OLTs que tienen modelos asignados"""
    print("\n" + "="*60)
    print("🏢 PROBANDO OLTS CON MODELOS")
    print("="*60)
    
    olts = OLT.objects.all().select_related('marca', 'modelo')
    
    if not olts.exists():
        print("⚠️ No hay OLTs configuradas")
        return
    
    olts_with_model = olts.filter(modelo__isnull=False)
    olts_without_model = olts.filter(modelo__isnull=True)
    
    print(f"\n📊 ESTADÍSTICAS:")
    print(f"   Total OLTs: {olts.count()}")
    print(f"   Con modelo: {olts_with_model.count()}")
    print(f"   Sin modelo: {olts_without_model.count()}")
    
    if olts_with_model.exists():
        print(f"\n✅ OLTS CON MODELO ASIGNADO:")
        for olt in olts_with_model:
            print(f"   {olt.abreviatura} → {olt.modelo.nombre} ({olt.modelo.marca.nombre})")
    
    if olts_without_model.exists():
        print(f"\n⚠️ OLTS SIN MODELO:")
        for olt in olts_without_model:
            print(f"   {olt.abreviatura} ({olt.marca.nombre})")


def show_admin_urls():
    """Muestra las URLs del admin para gestionar modelos"""
    print("\n" + "="*60)
    print("🔗 URLs DEL ADMIN")
    print("="*60)
    print("""
📋 Gestionar Modelos de OLT:
   http://127.0.0.1:8000/admin/olt_models/oltmodel/

📐 Gestionar Fórmulas SNMP:
   http://127.0.0.1:8000/admin/snmp_formulas/indexformula/

🏢 Gestionar OLTs:
   http://127.0.0.1:8000/admin/hosts/olt/

🏷️ Gestionar Marcas:
   http://127.0.0.1:8000/admin/brands/brand/
    """)


def show_usage_examples():
    """Muestra ejemplos de uso del sistema"""
    print("\n" + "="*60)
    print("💡 EJEMPLOS DE USO")
    print("="*60)
    print("""
🎯 FLUJO RECOMENDADO:

1. CREAR MARCA (si no existe):
   - Ir a Brands → Agregar
   - Nombre: "ZTE"
   - Descripción: "ZTE Corporation"

2. CREAR MODELO:
   - Ir a OLT Models → Agregar
   - Nombre: "C320"
   - Marca: ZTE
   - Descripción: "OLT GPON de ZTE"
   - Tipo OLT: GPON
   - Capacidad: 8 puertos × 128 ONUs

3. CREAR FÓRMULA:
   - Ir a SNMP Formulas → Agregar
   - Marca: ZTE
   - Modelo: C320 (opcional, para específico)
   - Configurar parámetros de cálculo

4. ASIGNAR A OLT:
   - Ir a OLTs → Editar
   - Seleccionar modelo: C320
   - El sistema usará la fórmula automáticamente

🔍 VENTAJAS DEL SISTEMA:
   ✅ Formularios de selección limitados (max 10 elementos)
   ✅ Búsqueda por texto en dropdowns
   ✅ Campos obligatorios y opcionales
   ✅ Relaciones FK optimizadas
   ✅ Admin visual con badges y colores
    """)


if __name__ == "__main__":
    # Ejecutar todas las verificaciones
    list_olt_models()
    test_formulas_with_models()
    test_olts_with_models()
    show_admin_urls()
    show_usage_examples()
    
    print("\n" + "="*60)
    print("✅ VERIFICACIÓN COMPLETA")
    print("="*60)
    print("\n💡 Próximos pasos:")
    print("   1. Crear marcas faltantes (ZTE, etc.)")
    print("   2. Agregar más modelos según necesidades")
    print("   3. Configurar fórmulas específicas por modelo")
    print("   4. Asignar modelos a OLTs existentes")
    print()
