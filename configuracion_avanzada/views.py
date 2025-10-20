from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
import json
from .models import ConfiguracionSistema, ConfiguracionSNMP, ConfiguracionCelery


@staff_member_required
def configuracion_dashboard(request):
    """
    Dashboard principal de configuración avanzada
    """
    # Obtener estadísticas
    total_configs = ConfiguracionSistema.objects.count()
    configs_activas = ConfiguracionSistema.objects.filter(activo=True).count()
    configs_snmp = ConfiguracionSNMP.objects.filter(activo=True).count()
    configs_celery = ConfiguracionCelery.objects.filter(activo=True).count()
    
    # Obtener configuraciones por categoría
    configs_por_categoria = {}
    categoria_choices = ConfiguracionSistema._meta.get_field('categoria').choices
    for categoria, _ in categoria_choices:
        count = ConfiguracionSistema.objects.filter(categoria=categoria, activo=True).count()
        if count > 0:
            configs_por_categoria[categoria] = count
    
    # Obtener configuraciones recientes
    configs_recientes = ConfiguracionSistema.objects.filter(
        activo=True
    ).order_by('-fecha_modificacion')[:10]
    
    context = {
        'total_configs': total_configs,
        'configs_activas': configs_activas,
        'configs_snmp': configs_snmp,
        'configs_celery': configs_celery,
        'configs_por_categoria': configs_por_categoria,
        'configs_recientes': configs_recientes,
    }
    
    return render(request, 'configuracion_avanzada/dashboard.html', context)


@staff_member_required
def configuracion_categoria(request, categoria):
    """
    Vista para mostrar configuraciones por categoría
    """
    configs = ConfiguracionSistema.objects.filter(
        categoria=categoria,
        activo=True
    ).order_by('nombre')
    
    # Obtener el nombre legible de la categoría
    categoria_choices = ConfiguracionSistema._meta.get_field('categoria').choices
    categoria_nombres = dict(categoria_choices)
    categoria_nombre = categoria_nombres.get(categoria, categoria)
    
    context = {
        'configs': configs,
        'categoria': categoria,
        'categoria_nombre': categoria_nombre,
    }
    
    return render(request, 'configuracion_avanzada/categoria.html', context)


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(staff_member_required, name='dispatch')
class ConfiguracionAPIView(View):
    """
    API para obtener y actualizar configuraciones
    """
    
    def get(self, request, nombre=None):
        """
        Obtener configuración por nombre o todas las configuraciones
        """
        if nombre:
            try:
                config = ConfiguracionSistema.objects.get(nombre=nombre, activo=True)
                return JsonResponse({
                    'success': True,
                    'data': {
                        'nombre': config.nombre,
                        'valor': config.get_valor_typed(),
                        'tipo': config.tipo,
                        'categoria': config.categoria,
                        'descripcion': config.descripcion,
                    }
                })
            except ConfiguracionSistema.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Configuración no encontrada'
                }, status=404)
        else:
            # Obtener todas las configuraciones activas
            configs = ConfiguracionSistema.objects.filter(activo=True)
            data = []
            for config in configs:
                data.append({
                    'nombre': config.nombre,
                    'valor': config.get_valor_typed(),
                    'tipo': config.tipo,
                    'categoria': config.categoria,
                    'descripcion': config.descripcion,
                })
            
            return JsonResponse({
                'success': True,
                'data': data
            })
    
    def post(self, request, nombre):
        """
        Actualizar configuración
        """
        try:
            config = ConfiguracionSistema.objects.get(nombre=nombre, activo=True)
            
            if config.solo_lectura:
                return JsonResponse({
                    'success': False,
                    'error': 'Configuración de solo lectura'
                }, status=403)
            
            data = json.loads(request.body)
            nuevo_valor = data.get('valor')
            
            if nuevo_valor is not None:
                config.set_valor_typed(nuevo_valor)
                config.modificado_por = request.user
                config.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Configuración actualizada correctamente',
                    'data': {
                        'nombre': config.nombre,
                        'valor': config.get_valor_typed(),
                        'tipo': config.tipo,
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Valor no proporcionado'
                }, status=400)
                
        except ConfiguracionSistema.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Configuración no encontrada'
            }, status=404)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'JSON inválido'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)


@staff_member_required
def configuracion_snmp_dashboard(request):
    """
    Dashboard específico para configuraciones SNMP
    """
    configs_snmp = ConfiguracionSNMP.objects.filter(activo=True).order_by('nombre')
    
    # Estadísticas SNMP
    total_configs = configs_snmp.count()
    versiones = {}
    for config in configs_snmp:
        version = config.version
        if version not in versiones:
            versiones[version] = 0
        versiones[version] += 1
    
    context = {
        'configs_snmp': configs_snmp,
        'total_configs': total_configs,
        'versiones': versiones,
    }
    
    return render(request, 'configuracion_avanzada/snmp_dashboard.html', context)


@staff_member_required
def configuracion_celery_dashboard(request):
    """
    Dashboard específico para configuraciones Celery
    """
    configs_celery = ConfiguracionCelery.objects.filter(activo=True).order_by('cola', 'nombre')
    
    # Estadísticas Celery
    total_configs = configs_celery.count()
    colas = {}
    total_workers = 0
    
    for config in configs_celery:
        cola = config.cola
        if cola not in colas:
            colas[cola] = 0
        colas[cola] += 1
        total_workers += config.concurrencia
    
    context = {
        'configs_celery': configs_celery,
        'total_configs': total_configs,
        'colas': colas,
        'total_workers': total_workers,
    }
    
    return render(request, 'configuracion_avanzada/celery_dashboard.html', context)