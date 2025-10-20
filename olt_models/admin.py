from django.contrib import admin
from django.utils.html import mark_safe, format_html
from django.db import models
from django import forms
from .models import OLTModel


class OLTModelForm(forms.ModelForm):
    """Formulario personalizado para OLTModel con validaciones"""
    
    class Meta:
        model = OLTModel
        fields = '__all__'
    
    def clean_nombre(self):
        """Validar que el nombre del modelo sea único"""
        nombre = self.cleaned_data.get('nombre')
        if nombre:
            # Convertir a mayúsculas para consistencia
            nombre = nombre.upper()
            
            # Verificar unicidad (excluyendo la instancia actual si es edición)
            queryset = OLTModel.objects.filter(nombre=nombre)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise forms.ValidationError(
                    f'Ya existe un modelo con el nombre "{nombre}". '
                    'Los nombres de modelos deben ser únicos.'
                )
        
        return nombre


@admin.register(OLTModel)
class OLTModelAdmin(admin.ModelAdmin):
    """Admin para modelos de OLT con formulario de selección optimizado"""
    
    form = OLTModelForm
    list_display = (
        'nombre', 
        'marca', 
        'get_capacidad_badge',
        'get_tipo_badge',
        'get_estado_soporte_badge',
        'get_status_badge',
        'updated_at'
    )
    list_filter = (
        'marca', 
        'tipo_olt', 
        'activo', 
        'created_at',
        'fecha_lanzamiento'
    )
    search_fields = (
        'nombre', 
        'descripcion', 
        'marca__nombre',
        'tipo_olt',
        'notas_tecnicas'
    )
    list_per_page = 20
    
    # Configuración para formulario de selección limitado
    autocomplete_fields = ['marca']  # Para marca usamos autocomplete
    
    readonly_fields = (
        'created_at', 
        'updated_at',
        'get_estado_soporte_display',
        'get_capacidad_display_field'
    )
    
    fieldsets = (
        ('Información Básica (Obligatorio)', {
            'fields': (
                'nombre',
                'marca',
                'descripcion',
                'activo',
            ),
            'description': 'Campos obligatorios para identificar el modelo'
        }),
        ('Especificaciones Técnicas (Opcional)', {
            'fields': (
                'tipo_olt',
                'capacidad_puertos',
                'capacidad_onus',
                'slots_disponibles',
                'get_capacidad_display_field',
            ),
            'classes': ('collapse',),
            'description': 'Características técnicas del modelo'
        }),
        ('Configuración SNMP (Opcional)', {
            'fields': (
                'version_firmware_minima',
                'comunidad_snmp_default',
                'puerto_snmp_default',
            ),
            'classes': ('collapse',),
            'description': 'Configuraciones SNMP recomendadas para este modelo'
        }),
        ('Documentación y Soporte (Opcional)', {
            'fields': (
                'url_documentacion',
                'url_manual_usuario',
                'notas_tecnicas',
                'soporte_tecnico_contacto',
                'fecha_lanzamiento',
                'fecha_fin_soporte',
                'get_estado_soporte_display',
            ),
            'classes': ('collapse',),
            'description': 'Información de documentación y soporte técnico'
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def get_queryset(self, request):
        """Optimizar consultas con select_related"""
        return super().get_queryset(request).select_related('marca')
    
    def get_capacidad_badge(self, obj):
        """Muestra badge con capacidad del modelo"""
        if obj.capacidad_puertos and obj.capacidad_onus:
            return mark_safe(
                f'<span style="background:#17a2b8;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                f'📡 {obj.capacidad_puertos}×{obj.capacidad_onus}</span>'
            )
        elif obj.capacidad_puertos:
            return mark_safe(
                f'<span style="background:#6c757d;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                f'📡 {obj.capacidad_puertos} puertos</span>'
            )
        return mark_safe('<span style="color:#999;">-</span>')
    get_capacidad_badge.short_description = 'Capacidad'
    
    def get_tipo_badge(self, obj):
        """Muestra badge del tipo de OLT"""
        if obj.tipo_olt:
            color_map = {
                'GPON': '#28a745',
                'EPON': '#007bff',
                'XG-PON': '#6f42c1',
                'XGS-PON': '#fd7e14',
            }
            color = color_map.get(obj.tipo_olt.upper(), '#6c757d')
            return mark_safe(
                f'<span style="background:{color};color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                f'🔌 {obj.tipo_olt}</span>'
            )
        return mark_safe('<span style="color:#999;">-</span>')
    get_tipo_badge.short_description = 'Tipo'
    
    def get_estado_soporte_badge(self, obj):
        """Muestra badge del estado de soporte"""
        estado = obj.get_estado_soporte()
        color = obj.get_estado_soporte_color()
        icon = "✅" if "activo" in estado else "⚠️" if "próximo" in estado else "❌"
        
        return mark_safe(
            f'<span style="background:{color};color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
            f'{icon} {estado}</span>'
        )
    get_estado_soporte_badge.short_description = 'Soporte'
    
    def get_status_badge(self, obj):
        """Muestra estado activo/inactivo"""
        if obj.activo:
            return mark_safe(
                '<span style="background:#28a745;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">✓ Activo</span>'
            )
        return mark_safe(
            '<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">✗ Inactivo</span>'
        )
    get_status_badge.short_description = 'Estado'
    
    def get_capacidad_display_field(self, obj):
        """Campo de solo lectura que muestra la capacidad calculada"""
        return obj.get_capacidad_display()
    get_capacidad_display_field.short_description = 'Capacidad Total'
    
    def get_estado_soporte_display(self, obj):
        """Campo de solo lectura que muestra el estado de soporte"""
        estado = obj.get_estado_soporte()
        color = obj.get_estado_soporte_color()
        return mark_safe(
            f'<span style="color:{color};font-weight:bold;">{estado}</span>'
        )
    get_estado_soporte_display.short_description = 'Estado de Soporte'
    
    def save_model(self, request, obj, form, change):
        """Validaciones adicionales al guardar"""
        # Convertir nombre a mayúsculas
        if obj.nombre:
            obj.nombre = obj.nombre.upper()
        
        # Validar fechas de soporte
        if obj.fecha_lanzamiento and obj.fecha_fin_soporte:
            if obj.fecha_fin_soporte <= obj.fecha_lanzamiento:
                from django.contrib import messages
                messages.warning(
                    request,
                    '⚠️ La fecha de fin de soporte debe ser posterior a la fecha de lanzamiento.'
                )
        
        super().save_model(request, obj, form, change)


# Configuración para autocomplete de marca
class BrandAdmin(admin.ModelAdmin):
    """Configuración para autocomplete de marcas"""
    search_fields = ['nombre']
    list_display = ['nombre', 'descripcion']
    list_per_page = 10  # Limitar a 10 elementos como máximo

# Registrar la configuración de autocomplete para Brand si no está ya registrada
try:
    from brands.admin import BrandAdmin as ExistingBrandAdmin
    # Si ya existe, no hacer nada
except ImportError:
    # Si no existe, registrar nuestra configuración
    from brands.models import Brand
    admin.site.register(Brand, BrandAdmin)