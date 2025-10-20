"""
Formularios personalizados para ODF Management.
"""

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from .models import ZabbixCollectionSchedule, ZabbixCollectionOLT
from hosts.models import OLT


class ZabbixCollectionScheduleForm(forms.ModelForm):
    """
    Formulario personalizado para ZabbixCollectionSchedule con selección múltiple de OLTs.
    """
    
    olts_seleccionadas = forms.ModelMultipleChoiceField(
        queryset=OLT.objects.filter(habilitar_olt=True),
        widget=FilteredSelectMultiple(
            verbose_name='OLTs',
            is_stacked=False
        ),
        required=False,
        help_text="Selecciona las OLTs que se incluirán en esta programación"
    )
    
    class Meta:
        model = ZabbixCollectionSchedule
        fields = ['nombre', 'intervalo_minutos', 'habilitado', 'olts_seleccionadas']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Si estamos editando un objeto existente, cargar OLTs actuales
        if self.instance.pk:
            self.fields['olts_seleccionadas'].initial = self.instance.zabbixcollectionolt_set.values_list('olt', flat=True)
            
    def save(self, commit=True):
        # Guardar la instancia primero
        instance = super().save(commit=False)
        
        # Siempre calcular próxima ejecución si es nueva
        if not instance.pk and not instance.proxima_ejecucion:
            instance.calcular_proxima_ejecucion()
        
        # Guardar la instancia si commit=True
        if commit:
            instance.save()
        
        # Manejar las OLTs seleccionadas solo si la instancia está guardada
        if commit and instance.pk:
            # Limpiar OLTs existentes para esta programación
            ZabbixCollectionOLT.objects.filter(schedule=instance).delete()
            
            # Agregar OLTs seleccionadas
            olts_seleccionadas = self.cleaned_data.get('olts_seleccionadas', [])
            for olt in olts_seleccionadas:
                ZabbixCollectionOLT.objects.create(
                    schedule=instance,
                    olt=olt,
                    habilitado=True
                )
        
        return instance
    
    class Media:
        css = {
            'all': ('admin/css/widgets.css',),
        }
        js = (
            'admin/js/core.js',
            'admin/js/SelectBox.js',
            'admin/js/SelectFilter2.js',
        )
