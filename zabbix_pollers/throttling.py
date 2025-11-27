"""
Clases de throttling personalizadas para endpoints de monitoreo
Permiten más peticiones que el límite general ya que son endpoints de polling frecuente
"""
from rest_framework.throttling import UserRateThrottle


class MonitoringRateThrottle(UserRateThrottle):
    """
    Throttling para endpoints de monitoreo (pollers, stats, queue)
    Permite 300 peticiones por minuto (5 peticiones/segundo) por usuario
    Esto es suficiente para polling cada 10 segundos con múltiples endpoints
    
    IMPORTANTE: Solo usuarios con is_superuser=True tienen acceso ilimitado
    """
    scope = 'monitoring'
    
    def allow_request(self, request, view):
        """
        Permite peticiones ilimitadas solo para superusuarios
        """
        # Verificar si el usuario es superusuario
        if request.user and request.user.is_authenticated:
            if request.user.is_superuser:
                # Permitir peticiones ilimitadas para superusuarios
                return True
        
        # Para otros usuarios, aplicar throttling normal
        return super().allow_request(request, view)


class HighFrequencyMonitoringRateThrottle(UserRateThrottle):
    """
    Throttling para endpoints de monitoreo de alta frecuencia
    Permite 600 peticiones por minuto (10 peticiones/segundo) por usuario
    Para casos donde se necesite polling muy frecuente
    
    IMPORTANTE: Solo usuarios con is_superuser=True tienen acceso ilimitado
    """
    scope = 'high_frequency_monitoring'
    
    def allow_request(self, request, view):
        """
        Permite peticiones ilimitadas solo para superusuarios
        """
        # Verificar si el usuario es superusuario
        if request.user and request.user.is_authenticated:
            if request.user.is_superuser:
                # Permitir peticiones ilimitadas para superusuarios
                return True
        
        # Para otros usuarios, aplicar throttling normal
        return super().allow_request(request, view)

