"""
Autenticación personalizada para la API REST
Usa el header x-api-key en lugar de Authorization: Token
"""
from rest_framework import authentication, exceptions
from rest_framework.authtoken.models import Token


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Autenticación basada en API Key usando el header x-api-key.
    
    El cliente debe enviar el token en el header:
        x-api-key: <token>
    
    En lugar del formato estándar:
        Authorization: Token <token>
    """
    
    def authenticate(self, request):
        """
        Autentica la petición usando el header x-api-key.
        
        Returns:
            tuple: (user, token) si la autenticación es exitosa
            None: si no se proporciona el header
        """
        # Obtener el token del header x-api-key
        api_key = request.META.get('HTTP_X_API_KEY') or request.META.get('X_API_KEY')
        
        if not api_key:
            # Si no hay x-api-key, retornar None para permitir otros métodos de autenticación
            return None
        
        # Validar y obtener el token
        return self.authenticate_credentials(api_key)
    
    def authenticate_credentials(self, key):
        """
        Valida el token y retorna el usuario asociado.
        
        Args:
            key: El token a validar
            
        Returns:
            tuple: (user, token)
            
        Raises:
            AuthenticationFailed: Si el token es inválido o el usuario está inactivo
        """
        try:
            token = Token.objects.select_related('user').get(key=key)
        except Token.DoesNotExist:
            raise exceptions.AuthenticationFailed('Token inválido.')
        
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('Usuario inactivo o eliminado.')
        
        return (token.user, token)
    
    def authenticate_header(self, request):
        """
        Retorna el header que se debe usar para autenticación.
        """
        return 'x-api-key'

