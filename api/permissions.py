"""
Permisos personalizados para la API REST
"""
from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permiso personalizado: Los usuarios admin pueden hacer cualquier cosa,
    los usuarios autenticados solo pueden leer.
    """
    
    def has_permission(self, request, view):
        # Permitir lectura a cualquier usuario autenticado
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Permitir escritura solo a admin
        return request.user and request.user.is_staff


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permiso personalizado: Solo el dueño del objeto o un admin puede modificarlo
    """
    
    def has_object_permission(self, request, view, obj):
        # Permitir lectura a cualquier usuario autenticado
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Permitir escritura al dueño o admin
        if hasattr(obj, 'user'):
            return obj.user == request.user or request.user.is_staff
        
        return request.user.is_staff


class IsStaffOrReadOnly(permissions.BasePermission):
    """
    Permiso personalizado: Los usuarios staff pueden hacer cualquier cosa,
    otros usuarios solo pueden leer.
    """
    
    def has_permission(self, request, view):
        # Permitir lectura a cualquier usuario autenticado
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Permitir escritura solo a staff
        return request.user and request.user.is_staff

