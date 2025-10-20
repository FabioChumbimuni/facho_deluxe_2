"""
Comando para probar el rendimiento del admin de Django.
"""

from django.core.management.base import BaseCommand
from django.test import Client
from django.contrib.auth.models import User
import time


class Command(BaseCommand):
    help = 'Prueba el rendimiento de las páginas del admin'

    def handle(self, *args, **options):
        self.stdout.write("🧪 PROBANDO RENDIMIENTO DEL ADMIN")
        self.stdout.write("=" * 50)
        
        # Crear cliente de prueba
        client = Client()
        
        # Crear usuario admin si no existe
        try:
            admin_user = User.objects.get(username='admin')
        except User.DoesNotExist:
            admin_user = User.objects.create_superuser('admin', 'admin@test.com', 'admin')
        
        # Hacer login
        client.force_login(admin_user)
        
        # URLs a probar
        urls_to_test = [
            ('/admin/odf_management/odfhilos/', 'Lista ODFHilos'),
            ('/admin/odf_management/odfhilos/add/', 'Agregar ODFHilo'),
            ('/admin/odf_management/zabbixportdata/', 'Lista ZabbixPortData'),
            ('/admin/odf_management/odf/', 'Lista ODF'),
        ]
        
        for url, description in urls_to_test:
            self.stdout.write(f"\n📊 Probando: {description}")
            self.stdout.write(f"   URL: {url}")
            
            start_time = time.time()
            
            try:
                response = client.get(url)
                end_time = time.time()
                
                if response.status_code == 200:
                    load_time = end_time - start_time
                    self.stdout.write(f"   ✅ Tiempo de carga: {load_time:.3f}s")
                    
                    if load_time > 2.0:
                        self.stdout.write(f"   ⚠️ LENTO (>2s)")
                    elif load_time > 1.0:
                        self.stdout.write(f"   ⚡ MODERADO (>1s)")
                    else:
                        self.stdout.write(f"   🚀 RÁPIDO (<1s)")
                        
                else:
                    self.stdout.write(f"   ❌ Error HTTP {response.status_code}")
                    
            except Exception as e:
                self.stdout.write(f"   ❌ Error: {e}")
        
        # Probar URL específica con parámetros
        self.stdout.write(f"\n📊 Probando: URL con parámetros (problema original)")
        test_url = '/admin/odf_management/odfhilos/add/?zabbix_port=1617&slot=1&port=0'
        
        start_time = time.time()
        try:
            response = client.get(test_url)
            end_time = time.time()
            
            if response.status_code == 200:
                load_time = end_time - start_time
                self.stdout.write(f"   ✅ Tiempo de carga: {load_time:.3f}s")
                
                if load_time > 2.0:
                    self.stdout.write(f"   ⚠️ LENTO (>2s) - Revisar optimizaciones")
                elif load_time > 1.0:
                    self.stdout.write(f"   ⚡ MEJORADO (>1s) - Aceptable")
                else:
                    self.stdout.write(f"   🚀 OPTIMIZADO (<1s) - Excelente")
            else:
                self.stdout.write(f"   ❌ Error HTTP {response.status_code}")
                
        except Exception as e:
            self.stdout.write(f"   ❌ Error: {e}")
        
        self.stdout.write(f"\n💡 RECOMENDACIONES:")
        self.stdout.write(f"   • Si alguna página >2s, revisar raw_id_fields y autocomplete_fields")
        self.stdout.write(f"   • Usar list_select_related para evitar N+1 queries")
        self.stdout.write(f"   • Reducir list_per_page si hay muchos registros")
        self.stdout.write(f"   • Considerar índices adicionales para filtros frecuentes")
        
        self.stdout.write(f"\n✅ Prueba de rendimiento completada")
