from django.contrib import admin
from django.utils.html import format_html
from .models import Area, NivelPrivilegio, Personal, HistorialAcceso


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'descripcion_corta', 'activa', 'personal_count', 'created_at']
    list_filter = ['activa', 'created_at']
    search_fields = ['nombre', 'descripcion']
    ordering = ['nombre']
    
    def descripcion_corta(self, obj):
        """Descripción truncada"""
        if obj.descripcion:
            return obj.descripcion[:50] + "..." if len(obj.descripcion) > 50 else obj.descripcion
        return "-"
    descripcion_corta.short_description = "Descripción"
    
    def personal_count(self, obj):
        """Cuenta de personal en esta área"""
        count = obj.personal_set.count()
        return f"{count} persona(s)"
    personal_count.short_description = "Personal Asignado"


@admin.register(NivelPrivilegio) 
class NivelPrivilegioAdmin(admin.ModelAdmin):
    list_display = ['nivel', 'nombre', 'activo', 'created_at']
    list_filter = ['activo', 'nivel']
    ordering = ['nivel']
    search_fields = ['nombre', 'descripcion']  # Requerido para autocomplete


@admin.register(Personal)
class PersonalAdmin(admin.ModelAdmin):
    list_display = ['nombre_completo', 'codigo_empleado', 'area_display', 'nivel_privilegio', 'cargo', 'estado_display']
    list_filter = ['area', 'nivel_privilegio', 'estado', 'fecha_ingreso']
    search_fields = ['nombres', 'apellidos', 'codigo_empleado', 'email', 'cargo']
    ordering = ['apellidos', 'nombres']
    
    # Para autocomplete en otros admins
    autocomplete_fields = ['area', 'nivel_privilegio']
    
    def area_display(self, obj):
        """Muestra el área con formato"""
        return format_html('<strong>{}</strong>', obj.area.nombre)
    area_display.short_description = "Área"
    
    def estado_display(self, obj):
        """Estado con colores"""
        colors = {
            'activo': 'green',
            'inactivo': 'gray', 
            'suspendido': 'red'
        }
        color = colors.get(obj.estado, 'black')
        return format_html(
            '<span style="color: {};">{}</span>',
            color, obj.get_estado_display()
        )
    estado_display.short_description = "Estado"


@admin.register(HistorialAcceso)
class HistorialAccesoAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'personal', 'accion', 'ip_address']
    list_filter = ['accion', 'timestamp']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']