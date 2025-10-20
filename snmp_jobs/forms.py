from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from .models import SnmpJob
from brands.models import Brand
from hosts.models import OLT
from oids.models import OID

class SnmpJobForm(forms.ModelForm):
    """Formulario para programar tareas SNMP"""
    
    marca = forms.ModelChoiceField(
        queryset=Brand.objects.all(),
        empty_label="Seleccione una marca",
        widget=forms.Select(attrs={
            'class': 'form-control select2',
            'id': 'id_marca',
            'data-placeholder': 'Seleccione una marca'
        }),
        label="Marca"
    )
    
    olts = forms.ModelMultipleChoiceField(
        queryset=OLT.objects.none(),
        widget=forms.SelectMultiple(attrs={
            'class': 'filtered',
            'id': 'id_olts',
            'style': 'height: 300px; width: 380px;'
        }),
        label="OLTs",
        help_text="Seleccione uno o más OLTs para esta tarea",
        required=True,
        error_messages={
            'required': 'Debe seleccionar al menos una OLT.'
        }
    )
    
    oid = forms.ModelChoiceField(
        queryset=OID.objects.none(),
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_oid',
        }),
        label="OID",
        help_text="Seleccione el OID a consultar",
        required=True,
        empty_label="Seleccione una marca primero"
    )
    
    oid_espacio_info = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_oid_espacio_info',
            'readonly': True,
            'placeholder': 'Seleccione un OID para ver su espacio'
        }),
        label="Espacio del OID",
        required=False,
        help_text="Muestra el tipo de información que proporciona el OID seleccionado"
    )
    
    
    interval_raw = forms.CharField(
        max_length=16,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: 30s, 5m, 1h',
            'id': 'id_interval_raw'
        }),
        help_text="Formato: número + unidad (s=segundos, m=minutos, h=horas). Solo use esto O cron, no ambos. Preferible mayor a 5 minutos.",
        label="Intervalo",
        required=False
    )
    
    cron_expr = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: 0 8 * * * (todos los días a las 8:00 AM)',
            'id': 'id_cron_expr'
        }),
        help_text="Expresión cron (minuto hora día mes día_semana). Solo use esto O intervalo, no ambos.",
        label="Expresión Cron",
        required=False
    )
    
    schedule_description = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly',
        }),
        label="Descripción del Horario",
        required=False,
        help_text="Descripción automática del horario programado"
    )
    
    job_type = forms.ChoiceField(
        choices=SnmpJob.JOB_TYPES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Tipo de consulta"
    )
    
    enabled = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Habilitar"
    )
    
    class Meta:
        model = SnmpJob
        fields = ['nombre', 'descripcion', 'marca', 'olts', 'oid', 'oid_espacio_info', 'interval_raw', 'cron_expr', 'schedule_description', 'job_type', 'enabled']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def is_valid(self):
        """Override is_valid para manejar el caso sin datos POST"""
        if not self.data:
            # Si no hay datos POST, el formulario es válido para mostrar
            return True
        return super().is_valid()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Inicializar campos
        data = args[0] if args else None
        marca_id = None
        
        # Determinar marca_id según el contexto
        if self.instance and self.instance.pk:
            # Edición: usar marca de la instancia
            marca_id = self.instance.marca_id
            # En edición, la marca es de solo lectura (no disabled para evitar problemas de validación)
            self.fields['marca'].widget.attrs.update({
                'readonly': 'readonly',
                'class': 'form-control select2 readonly'
            })
            # Agregar ayuda específica para edición
            self.fields['marca'].help_text = "La marca no se puede modificar en tareas existentes"
        elif data and 'marca' in data:
            # POST: usar marca del formulario
            marca_id = data['marca']
        elif 'initial' in kwargs and 'marca' in kwargs['initial']:
            # GET con initial data: usar marca inicial
            marca_id = kwargs['initial']['marca'].id if isinstance(kwargs['initial']['marca'], Brand) else kwargs['initial']['marca']
        
        # Filtrar OLTs y OIDs según la marca
        if marca_id:
            # Incluir todas las OLTs de la marca (habilitadas y deshabilitadas)
            self.fields['olts'].queryset = OLT.objects.filter(marca_id=marca_id)
            self.fields['oid'].queryset = OID.objects.filter(marca_id=marca_id)
            
            # Si estamos editando y el OID actual no está en el queryset, agregarlo
            if self.instance and self.instance.pk and self.instance.oid:
                if not self.fields['oid'].queryset.filter(id=self.instance.oid.id).exists():
                    self.fields['oid'].queryset = self.fields['oid'].queryset | OID.objects.filter(id=self.instance.oid.id)
        else:
            # Sin marca seleccionada, mostrar todas las OLTs habilitadas
            self.fields['olts'].queryset = OLT.objects.filter(habilitar_olt=True)
            self.fields['oid'].queryset = OID.objects.all()
            
            # Si estamos editando, mostrar el OID actual aunque no haya marca
            if self.instance and self.instance.pk and self.instance.oid:
                self.fields['oid'].queryset = OID.objects.filter(id=self.instance.oid.id)
    
    def clean_marca(self):
        """Validación personalizada para el campo marca"""
        marca = self.cleaned_data.get('marca')
        
        # Si estamos editando una instancia existente y no se proporcionó marca
        if self.instance and self.instance.pk and not marca:
            # Usar la marca de la instancia existente
            return self.instance.marca
        
        return marca
    
    def clean_interval_raw(self):
        """Validar formato del intervalo"""
        interval = self.cleaned_data['interval_raw']
        if interval:
            # Validar formato: número + unidad
            import re
            pattern = r'^(\d+)([smhd])$'
            if not re.match(pattern, interval):
                raise forms.ValidationError(
                    'Formato inválido. Use: número + unidad (ej: 30s, 5m, 1h, 2d)'
                )
        return interval
    
    def clean_olts(self):
        """Validación personalizada para el campo olts"""
        # Solo validar si hay datos POST (formulario enviado)
        if not self.data:
            return super().clean_olts()
            
        olts = self.cleaned_data.get('olts', [])
        
        # Si estamos editando una instancia existente, no validar OLTs
        # para evitar consultas lentas que causen colgado
        if self.instance and self.instance.pk:
            return olts
        
        # Solo validar en creación
        if not olts:
            raise forms.ValidationError('Debe seleccionar al menos una OLT.')
        
        return olts
    
    def clean(self):
        """
        Validación personalizada: solo intervalo O cron, no ambos
        """
        # Solo validar si hay datos POST (formulario enviado)
        if not self.data:
            # Si no hay datos POST, no validar nada
            return {}
            
        cleaned_data = super().clean()
        
        interval_raw = cleaned_data.get('interval_raw', '').strip()
        cron_expr = cleaned_data.get('cron_expr', '').strip()
        
        # Verificar que solo uno de los dos campos esté lleno
        has_interval = bool(interval_raw)
        has_cron = bool(cron_expr)
        
        if has_interval and has_cron:
            raise forms.ValidationError({
                'interval_raw': 'Solo puede especificar intervalo O cron, no ambos.',
                'cron_expr': 'Solo puede especificar intervalo O cron, no ambos.'
            })
        
        if not has_interval and not has_cron:
            raise forms.ValidationError({
                'interval_raw': 'Debe especificar un intervalo O una expresión cron.',
                'cron_expr': 'Debe especificar un intervalo O una expresión cron.'
            })
        
        # Actualizar descripción del horario
        if has_cron:
            # Crear instancia temporal para obtener descripción
            temp_instance = SnmpJob(cron_expr=cron_expr)
            cleaned_data['schedule_description'] = temp_instance._parse_cron_description()
        elif has_interval:
            temp_instance = SnmpJob(interval_raw=interval_raw)
            cleaned_data['schedule_description'] = temp_instance._parse_interval_description()
        
        return cleaned_data
    
    def clean_oid(self):
        """Validación personalizada para el campo oid"""
        # Solo validar si hay datos POST (formulario enviado)
        if not self.data:
            return super().clean_oid()
            
        oid = self.cleaned_data.get('oid')
        marca = self.cleaned_data.get('marca')

        if not oid:
            raise forms.ValidationError('Debe seleccionar un OID de la lista.')

        # Verificar que el OID pertenezca a la marca seleccionada
        if marca and oid.marca != marca:
            raise forms.ValidationError('El OID seleccionado no pertenece a la marca elegida.')

        return oid
    
