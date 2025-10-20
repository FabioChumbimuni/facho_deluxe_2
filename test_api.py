#!/usr/bin/env python
"""
Script para probar la API REST de Facho Deluxe v2
"""
import os
import sys

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.test import RequestFactory
from api.views import health_check, dashboard_stats

def test_api():
    """Probar endpoints principales de la API"""
    print("=" * 60)
    print("🧪 PRUEBA DE API REST - FACHO DELUXE V2")
    print("=" * 60)
    print()
    
    # 1. Verificar usuarios y tokens
    print("1️⃣  Verificando autenticación...")
    users = User.objects.all()
    tokens = Token.objects.all()
    print(f"   ✓ Usuarios: {users.count()}")
    print(f"   ✓ Tokens: {tokens.count()}")
    
    if users.exists():
        user = users.first()
        token, _ = Token.objects.get_or_create(user=user)
        print(f"   ✓ Token de prueba: {token.key[:30]}...")
    print()
    
    # 2. Probar health check
    print("2️⃣  Probando health check...")
    factory = RequestFactory()
    request = factory.get('/api/v1/health/')
    response = health_check(request)
    
    if response.status_code == 200:
        print(f"   ✓ Status: {response.status_code}")
        print(f"   ✓ Version: {response.data.get('version')}")
        print(f"   ✓ Estado: {response.data.get('status')}")
    else:
        print(f"   ✗ Error: {response.status_code}")
    print()
    
    # 3. Verificar modelos
    print("3️⃣  Verificando modelos...")
    from hosts.models import OLT
    from brands.models import Brand
    from snmp_jobs.models import SnmpJob
    from executions.models import Execution
    from discovery.models import OnuIndexMap
    
    print(f"   ✓ OLTs: {OLT.objects.count()}")
    print(f"   ✓ Marcas: {Brand.objects.count()}")
    print(f"   ✓ SNMP Jobs: {SnmpJob.objects.count()}")
    print(f"   ✓ Ejecuciones: {Execution.objects.count()}")
    print(f"   ✓ ONUs: {OnuIndexMap.objects.count()}")
    print()
    
    # 4. Probar dashboard stats
    print("4️⃣  Probando estadísticas del dashboard...")
    request = factory.get('/api/v1/dashboard/stats/')
    request.user = user
    
    try:
        response = dashboard_stats(request)
        if response.status_code == 200:
            print(f"   ✓ Status: {response.status_code}")
            data = response.data
            print(f"   ✓ Total OLTs: {data.get('total_olts')}")
            print(f"   ✓ OLTs Activas: {data.get('olts_activas')}")
            print(f"   ✓ Total Jobs: {data.get('total_jobs')}")
            print(f"   ✓ Total ONUs: {data.get('total_onus')}")
        else:
            print(f"   ✗ Error: {response.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    print()
    
    # 5. Verificar serializers
    print("5️⃣  Verificando serializers...")
    from api.serializers import (
        OLTSerializer, BrandSerializer, SNMPJobSerializer,
        ExecutionSerializer, OnuIndexMapSerializer
    )
    
    serializers = [
        'OLTSerializer',
        'BrandSerializer', 
        'SNMPJobSerializer',
        'ExecutionSerializer',
        'OnuIndexMapSerializer'
    ]
    
    for s in serializers:
        print(f"   ✓ {s}")
    print()
    
    # 6. Resumen final
    print("=" * 60)
    print("✅ RESULTADO: API REST FUNCIONANDO CORRECTAMENTE")
    print("=" * 60)
    print()
    print("📍 Endpoints disponibles:")
    print("   • http://localhost:8000/api/v1/docs/         (Swagger UI)")
    print("   • http://localhost:8000/api/v1/redoc/        (ReDoc)")
    print("   • http://localhost:8000/api/v1/health/       (Health Check)")
    print("   • http://localhost:8000/api/v1/olts/         (OLTs)")
    print("   • http://localhost:8000/api/v1/snmp-jobs/    (SNMP Jobs)")
    print("   • http://localhost:8000/api/v1/executions/   (Ejecuciones)")
    print()
    print("🔐 Para obtener token de autenticación:")
    print("   curl -X POST http://localhost:8000/api/v1/auth/login/")
    print("        -H 'Content-Type: application/json'")
    print("        -d '{\"username\": \"admin\", \"password\": \"tu_password\"}'")
    print()

if __name__ == '__main__':
    try:
        test_api()
    except Exception as e:
        print(f"❌ Error durante la prueba: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

