from django.contrib import admin
from django.contrib import messages
from django.utils.html import mark_safe
from django.utils.translation import gettext_lazy as _
from .models import IndexFormula


@admin.register(IndexFormula)
class IndexFormulaAdmin(admin.ModelAdmin):
    """Admin para fórmulas de cálculo de índices SNMP"""
    
    change_form_template = 'admin/snmp_formulas/change_form.html'
    
    list_display = (
        'nombre', 
        'get_marca_display', 
        'get_modelo_display', 
        'get_mode_badge', 
        'get_params_summary',
        'get_status_badge',
        'updated_at'
    )
    list_filter = ('marca', 'calculation_mode', 'activo', 'has_dot_notation')
    search_fields = ('nombre', 'descripcion', 'modelo__nombre')
    list_per_page = 20
    actions = ['duplicar_formula']
    
    # Configuración para formulario de selección limitado
    autocomplete_fields = ['marca', 'modelo']
    
    readonly_fields = ('created_at', 'updated_at', 'get_formula_preview')
    
    fieldsets = (
        ('Información Básica', {
            'fields': (
                'marca',
                'modelo',
                'nombre',
                'activo',
                'descripcion',
            )
        }),
        ('Configuración de Cálculo', {
            'fields': (
                'calculation_mode',
                'get_formula_preview',
            ),
        }),
        ('Parámetros Lineales (Base + Pasos)', {
            'fields': (
                'base_index',
                'step_slot',
                'step_port',
            ),
            'description': 'Usado cuando calculation_mode = "linear". Fórmula: INDEX = BASE + (slot × STEP_SLOT) + (port × STEP_PORT) + onu_id',
            'classes': ('collapse',),
        }),
        ('Parámetros Bitshift (Desplazamiento de Bits)', {
            'fields': (
                'shift_slot_bits',
                'shift_port_bits',
                'mask_slot',
                'mask_port',
            ),
            'description': 'Usado cuando calculation_mode = "bitshift"',
            'classes': ('collapse',),
        }),
        ('Parámetros Adicionales', {
            'fields': (
                'onu_offset',
                'has_dot_notation',
                'dot_is_onu_number',
            ),
            'classes': ('collapse',),
        }),
        ('Validación y Límites', {
            'fields': (
                'slot_max',
                'port_max',
                'onu_max',
            ),
            'classes': ('collapse',),
        }),
        ('Formato de Salida', {
            'fields': (
                'normalized_format',
            ),
            'description': 'Variables disponibles: {slot}, {port}, {logical}',
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',),
        }),
    )
    
    def get_marca_display(self, obj):
        """Muestra la marca de forma legible"""
        if obj.marca:
            return mark_safe(
                f'<span style="background:#007bff;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                f'🏷️ {obj.marca.nombre}</span>'
            )
        else:
            return mark_safe(
                '<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                '🌍 Sin Marca</span>'
            )
    get_marca_display.short_description = 'Marca'
    
    def get_modelo_display(self, obj):
        """Muestra el modelo de forma legible"""
        if obj.marca:
            if obj.modelo:
                return mark_safe(
                    f'<span style="background:#6c757d;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                    f'🔧 {obj.modelo.nombre}</span>'
                )
            return mark_safe(
                '<span style="background:#28a745;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                '🌐 Genérico</span>'
            )
        else:
            return mark_safe(
                '<span style="background:#dc3545;color:white;padding:3px 8px;border-radius:3px;font-size:11px;">'
                '🌍 Universal</span>'
            )
    get_modelo_display.short_description = 'Modelo'
    
    def get_mode_badge(self, obj):
        """Muestra badge del modo de cálculo"""
        if obj.calculation_mode == 'linear':
            color = '#17a2b8'
            icon = '📐'
            text = 'Lineal'
        else:
            color = '#6f42c1'
            icon = '🔢'
            text = 'Bitshift'
        
        return mark_safe(
            f'<span style="background:{color};color:white;padding:4px 10px;border-radius:3px;font-size:11px;">'
            f'{icon} {text}</span>'
        )
    get_mode_badge.short_description = 'Modo'
    
    def get_params_summary(self, obj):
        """Muestra resumen de parámetros principales"""
        if obj.calculation_mode == 'linear':
            params = f"Base: {obj.base_index:,} | Step Slot: {obj.step_slot:,} | Step Port: {obj.step_port:,}"
        else:
            params = f"Shift Slot: {obj.shift_slot_bits} bits | Shift Port: {obj.shift_port_bits} bits"
        
        return mark_safe(
            f'<span style="font-family:monospace;font-size:11px;color:#495057;">{params}</span>'
        )
    get_params_summary.short_description = 'Parámetros'
    
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
    
    def get_formula_preview(self, obj):
        """Muestra una vista previa de la fórmula configurada"""
        if obj.calculation_mode == 'linear':
            formula = f"""
            <div class="formula-preview formula-linear">
                <strong class="formula-title">📐 FÓRMULA LINEAL</strong><br><br>
                <code>delta = SNMP_INDEX - {obj.base_index:,}</code><br>
                <code>slot = delta ÷ {obj.step_slot:,}</code><br>
                <code>resto = delta % {obj.step_slot:,}</code><br>
                <code>port = resto ÷ {obj.step_port:,}</code><br>
                <code>onu_id = resto % {obj.step_port:,}</code><br><br>
                <strong>Ejemplo:</strong><br>
                <code>SNMP_INDEX = {obj.base_index + obj.step_slot + obj.step_port:,}</code><br>
                <code>→ slot=1, port=1, onu_id=0</code>
            </div>
            """
        else:
            formula = f"""
            <div class="formula-preview formula-bitshift">
                <strong class="formula-title">🔢 FÓRMULA BITSHIFT</strong><br><br>
                <code>slot = (SNMP_INDEX >> {obj.shift_slot_bits})</code>
                {f" & {obj.mask_slot}" if obj.mask_slot else ""}<br>
                <code>port = (SNMP_INDEX >> {obj.shift_port_bits})</code>
                {f" & {obj.mask_port}" if obj.mask_port else ""}<br>
                <code>onu_id = SNMP_INDEX & 0xFF</code>
            </div>
            """
        
        if obj.has_dot_notation:
            formula += """
            <div class="formula-warning">
                <strong class="warning-title">⚠️ NOTACIÓN CON PUNTO</strong><br>
                El índice incluye ".ONU" al final (ej: "4194312448.2")
            </div>
            """
        
        return mark_safe(formula)
    
    get_formula_preview.short_description = 'Vista Previa de Fórmula'
    
    def save_model(self, request, obj, form, change):
        """Validación adicional al guardar"""
        # Si es modo linear, validar que los parámetros no sean 0
        if obj.calculation_mode == 'linear':
            if obj.step_slot == 0 or obj.step_port == 0:
                messages.warning(
                    request, 
                    '⚠️ En modo lineal, step_slot y step_port no deberían ser 0'
                )
        
        super().save_model(request, obj, form, change)
    
    def duplicar_formula(self, request, queryset):
        """
        Acción para duplicar fórmulas seleccionadas.
        Crea copias con prefijo [COPIA] en el nombre.
        """
        duplicated_count = 0
        
        for formula_original in queryset:
            nombre_copia = f"[COPIA] {formula_original.nombre}"
            
            try:
                # Crear copia con los mismos datos
                nueva_formula = IndexFormula(
                    marca=formula_original.marca,
                    modelo=formula_original.modelo,
                    nombre=nombre_copia,
                    activo=False,  # Inactiva por defecto para revisar
                    calculation_mode=formula_original.calculation_mode,
                    base_index=formula_original.base_index,
                    step_slot=formula_original.step_slot,
                    step_port=formula_original.step_port,
                    shift_slot_bits=formula_original.shift_slot_bits,
                    shift_port_bits=formula_original.shift_port_bits,
                    mask_slot=formula_original.mask_slot,
                    mask_port=formula_original.mask_port,
                    onu_offset=formula_original.onu_offset,
                    has_dot_notation=formula_original.has_dot_notation,
                    dot_is_onu_number=formula_original.dot_is_onu_number,
                    slot_max=formula_original.slot_max,
                    port_max=formula_original.port_max,
                    onu_max=formula_original.onu_max,
                    normalized_format=formula_original.normalized_format,
                    descripcion=f"Copia de: {formula_original.descripcion or 'Sin descripción'}"
                )
                nueva_formula.save()
                duplicated_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Error al duplicar "{formula_original.nombre}": {str(e)}',
                    messages.ERROR
                )
        
        if duplicated_count > 0:
            self.message_user(
                request,
                f'✅ {duplicated_count} fórmula(s) duplicada(s) exitosamente. '
                f'Se crearon con el prefijo "[COPIA]" y estado INACTIVO.',
                messages.SUCCESS
            )
    
    duplicar_formula.short_description = _('📋 Duplicar fórmulas seleccionadas')
