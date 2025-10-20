from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count, Q
from .models import (
    ZabbixPortData, 
    ZabbixCollectionSchedule, 
    ZabbixCollectionOLT,
    ODF, 
    ODFHilos
)
from .forms import ZabbixCollectionScheduleForm


class ZabbixCollectionOLTInline(admin.TabularInline):
    """Inline para gestionar OLTs en una programación"""
    model = ZabbixCollectionOLT
    extra = 0
    min_num = 0
    fields = ['olt', 'habilitado', 'ultimo_estado_display', 'ultima_recoleccion', 'ultimo_error_corto']
    readonly_fields = ['ultimo_estado_display', 'ultima_recoleccion', 'ultimo_error_corto']
    
    def ultimo_estado_display(self, obj):
        """Muestra el último estado con iconos"""
        if not obj or not obj.pk:
            return "-"
        
        icons = {
            'success': '✅',
            'error': '❌', 
            'pending': '⏳'
        }
        
        icon = icons.get(obj.ultimo_estado, '❓')
        return format_html('{} {}', icon, obj.get_ultimo_estado_display())
    ultimo_estado_display.short_description = "Estado"
    
    def ultimo_error_corto(self, obj):
        """Muestra error truncado"""
        if obj and obj.ultimo_error:
            error = obj.ultimo_error[:50] + "..." if len(obj.ultimo_error) > 50 else obj.ultimo_error
            return format_html('<span style="color: red; font-size: 11px;">{}</span>', error)
        return "-"
    ultimo_error_corto.short_description = "Último Error"
    
    def get_queryset(self, request):
        """Optimizar consultas del inline"""
        return super().get_queryset(request).select_related('olt')


@admin.register(ZabbixCollectionSchedule)
class ZabbixCollectionScheduleAdmin(admin.ModelAdmin):
    """Admin para gestionar programaciones de recolección"""
    
    form = ZabbixCollectionScheduleForm
    
    list_display = [
        'nombre',
        'intervalo_display',
        'estado_display',
        'olts_count',
        'proxima_ejecucion',
        'ultima_ejecucion',
        'descripcion_intervalo'
    ]
    

    # inlines = [ZabbixCollectionOLTInline]  # Quitado - se maneja con el widget
    
    list_filter = [
        'habilitado',
        'intervalo_minutos',
        'created_at'
    ]
    
    search_fields = ['nombre']
    ordering = ['-habilitado', 'intervalo_minutos', 'nombre']
    readonly_fields = ['created_at', 'updated_at', 'descripcion_intervalo']
    
    fieldsets = (
        ('Configuración Básica', {
            'fields': ('nombre', 'intervalo_minutos', 'habilitado')
        }),
        ('Selección de OLTs', {
            'fields': ('olts_seleccionadas',),
            'description': 'Selecciona las OLTs que se incluirán en esta programación de recolección.'
        }),
        ('Programación', {
            'fields': ('proxima_ejecucion', 'ultima_ejecucion', 'descripcion_intervalo'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        """Guardar el modelo y manejar las OLTs seleccionadas"""
        super().save_model(request, obj, form, change)
        
        # Limpiar OLTs existentes
        ZabbixCollectionOLT.objects.filter(schedule=obj).delete()
        
        # Agregar OLTs seleccionadas
        if 'olts_seleccionadas' in form.cleaned_data:
            olts_seleccionadas = form.cleaned_data['olts_seleccionadas']
            for olt in olts_seleccionadas:
                ZabbixCollectionOLT.objects.create(
                    schedule=obj,
                    olt=olt,
                    habilitado=True
                )
        
        # Calcular próxima ejecución si es nueva programación
        if not obj.proxima_ejecucion:
            obj.calcular_proxima_ejecucion(primera_vez=True)
            obj.save()

    def intervalo_display(self, obj):
        """Muestra el intervalo con icono"""
        return f"⏰ {obj.get_intervalo_minutos_display()}"
    intervalo_display.short_description = "Intervalo"

    def estado_display(self, obj):
        """Muestra el estado con color"""
        if obj.habilitado:
            return format_html('<span style="color: green;">✅ Activa</span>')
        return format_html('<span style="color: red;">❌ Inactiva</span>')
    estado_display.short_description = "Estado"

    def olts_count(self, obj):
        """Cuenta las OLTs asociadas"""
        count = obj.olts_asociadas_count
        if count > 0:
            url = reverse('admin:odf_management_zabbixcollectionolt_changelist')
            return format_html(
                '<a href="{}?schedule__id__exact={}">{} OLT(s)</a>',
                url, obj.id, count
            )
        return "0 OLTs"
    olts_count.short_description = "OLTs"

    # Acciones personalizadas
    actions = [
        'ejecutar_recoleccion_inmediata',
        'calcular_proximas_ejecuciones', 
        'habilitar_programaciones', 
        'deshabilitar_programaciones',
        'agregar_todas_las_olts',
        'limpiar_olts_programacion'
    ]

    def calcular_proximas_ejecuciones(self, request, queryset):
        """Recalcula las próximas ejecuciones"""
        count = 0
        for schedule in queryset:
            schedule.calcular_proxima_ejecucion()
            schedule.save()
            count += 1
        self.message_user(request, f'Recalculadas {count} programaciones.')
    calcular_proximas_ejecuciones.short_description = "Recalcular próximas ejecuciones"

    def habilitar_programaciones(self, request, queryset):
        """Habilita las programaciones seleccionadas"""
        updated = queryset.update(habilitado=True)
        self.message_user(request, f'{updated} programaciones habilitadas.')
    habilitar_programaciones.short_description = "Habilitar programaciones"

    def deshabilitar_programaciones(self, request, queryset):
        """Deshabilita las programaciones seleccionadas"""
        updated = queryset.update(habilitado=False)
        self.message_user(request, f'{updated} programaciones deshabilitadas.')
    deshabilitar_programaciones.short_description = "Deshabilitar programaciones"

    def ejecutar_recoleccion_inmediata(self, request, queryset):
        """Ejecuta recolección inmediata para las programaciones seleccionadas"""
        from .tasks import sync_single_olt_ports
        
        total_olts = 0
        for schedule in queryset:
            olts = schedule.zabbixcollectionolt_set.filter(habilitado=True)
            for olt_config in olts:
                # Ejecutar tarea de sincronización
                sync_single_olt_ports.delay(olt_config.olt.id, schedule.id)
                total_olts += 1
        
        self.message_user(request, f'🚀 Recolección inmediata iniciada para {total_olts} OLTs.')
    ejecutar_recoleccion_inmediata.short_description = "🚀 Ejecutar recolección inmediata"

    def agregar_todas_las_olts(self, request, queryset):
        """Agrega todas las OLTs disponibles a las programaciones seleccionadas"""
        from hosts.models import OLT
        
        total_agregadas = 0
        for schedule in queryset:
            olts_disponibles = OLT.objects.filter(habilitar_olt=True)
            for olt in olts_disponibles:
                olt_config, created = ZabbixCollectionOLT.objects.get_or_create(
                    schedule=schedule,
                    olt=olt,
                    defaults={'habilitado': True}
                )
                if created:
                    total_agregadas += 1
        
        self.message_user(request, f'✅ {total_agregadas} OLTs agregadas a las programaciones.')
    agregar_todas_las_olts.short_description = "➕ Agregar todas las OLTs"

    def limpiar_olts_programacion(self, request, queryset):
        """Limpia todas las OLTs de las programaciones seleccionadas"""
        total_eliminadas = 0
        for schedule in queryset:
            count = schedule.zabbixcollectionolt_set.count()
            schedule.zabbixcollectionolt_set.all().delete()
            total_eliminadas += count
        
        self.message_user(request, f'🗑️ {total_eliminadas} OLTs eliminadas de las programaciones.')
    limpiar_olts_programacion.short_description = "🗑️ Limpiar OLTs"


@admin.register(ZabbixCollectionOLT)
class ZabbixCollectionOLTAdmin(admin.ModelAdmin):
    """Admin para gestionar OLTs en programaciones"""
    
    list_display = [
        'olt',
        'schedule',
        'habilitado_display',
        'estado_display',
        'ultima_recoleccion',
        'tiempo_transcurrido'
    ]
    
    list_filter = [
        'schedule',
        'habilitado',
        'ultimo_estado',
        'ultima_recoleccion'
    ]
    
    search_fields = [
        'olt__abreviatura',
        'olt__ip_address',
        'schedule__nombre'
    ]
    
    ordering = ['schedule', 'olt']
    readonly_fields = ['created_at', 'tiempo_transcurrido']
    
    fieldsets = (
        ('Asociación', {
            'fields': ('schedule', 'olt', 'habilitado')
        }),
        ('Estado de Recolección', {
            'fields': ('ultimo_estado', 'ultima_recoleccion', 'ultimo_error', 'tiempo_transcurrido')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )

    def habilitado_display(self, obj):
        """Estado habilitado con color"""
        if obj.habilitado:
            return format_html('<span style="color: green;">✅ Habilitado</span>')
        return format_html('<span style="color: orange;">⏸️ Deshabilitado</span>')
    habilitado_display.short_description = "Estado"

    def estado_display(self, obj):
        """Estado de la última recolección"""
        icons = {
            'success': '✅',
            'error': '❌',
            'pending': '⏳'
        }
        colors = {
            'success': 'green',
            'error': 'red',
            'pending': 'orange'
        }
        icon = icons.get(obj.ultimo_estado, '❓')
        color = colors.get(obj.ultimo_estado, 'gray')
        
        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_ultimo_estado_display()
        )
    estado_display.short_description = "Último Estado"

    def tiempo_transcurrido(self, obj):
        """Tiempo desde la última recolección"""
        if not obj.ultima_recoleccion:
            return "Nunca ejecutado"
        
        from django.utils import timezone
        delta = timezone.now() - obj.ultima_recoleccion
        
        if delta.days > 0:
            return f"Hace {delta.days} días"
        elif delta.seconds > 3600:
            horas = delta.seconds // 3600
            return f"Hace {horas} horas"
        elif delta.seconds > 60:
            minutos = delta.seconds // 60
            return f"Hace {minutos} minutos"
        else:
            return "Hace menos de 1 minuto"
    tiempo_transcurrido.short_description = "Última Ejecución"

    # Acciones personalizadas
    actions = ['habilitar_olts', 'deshabilitar_olts', 'resetear_estados']

    def habilitar_olts(self, request, queryset):
        """Habilita las OLTs seleccionadas"""
        updated = queryset.update(habilitado=True)
        self.message_user(request, f'{updated} OLTs habilitadas para recolección.')
    habilitar_olts.short_description = "Habilitar OLTs seleccionadas"

    def deshabilitar_olts(self, request, queryset):
        """Deshabilita las OLTs seleccionadas"""
        updated = queryset.update(habilitado=False)
        self.message_user(request, f'{updated} OLTs deshabilitadas para recolección.')
    deshabilitar_olts.short_description = "Deshabilitar OLTs seleccionadas"

    def resetear_estados(self, request, queryset):
        """Resetea el estado a pendiente"""
        updated = queryset.update(ultimo_estado='pending', ultimo_error=None)
        self.message_user(request, f'Estados de {updated} OLTs reseteados.')
    resetear_estados.short_description = "Resetear estados a pendiente"


@admin.register(ZabbixPortData)
class ZabbixPortDataAdmin(admin.ModelAdmin):
    """Admin para visualizar datos básicos extraídos de Zabbix"""
    
    list_display = [
        'olt_info',
        'slot',
        'port',
        'interface_name',
        'descripcion_corta',
        'estado_administrativo_display',
        'info_display',
        'registrado_display',
        'acciones_rapidas',
        'last_sync'
    ]
    
    # Optimización de consultas
    list_select_related = ['olt']
    list_prefetch_related = ['odfhilos_set']
    
    # Paginación para mejorar rendimiento
    list_per_page = 50
    list_max_show_all = 200
    
    # Para raw_id_fields
    search_fields = ['snmp_index', 'interface_name', 'descripcion_zabbix', 'olt__abreviatura']
    
    list_filter = [
        'olt',
        'slot',
        'port',
        'disponible',
        'estado_administrativo',
        'operativo_noc',
        'last_sync',
        'created_at'
    ]
    
    search_fields = [
        'snmp_index',
        'descripcion_zabbix',
        'interface_name',
        'olt__abreviatura',
        'olt__ip_address'
    ]
    
    ordering = ['olt', 'slot', 'port']
    
    readonly_fields = ['created_at', 'last_sync']
    
    fieldsets = (
        ('Información de Puerto', {
            'fields': ('olt', 'snmp_index', 'slot', 'port', 'interface_name'),
            'description': 'Datos básicos del puerto extraídos de Zabbix'
        }),
        ('Estados del Puerto', {
            'fields': ('disponible', 'estado_administrativo', 'operativo_noc'),
            'description': 'Estados del puerto: disponible (en item master), administrativo (OID .1.3.6.1.2.1.2.2.1.7), operativo NOC (manual)'
        }),
        ('Descripción', {
            'fields': ('descripcion_zabbix',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('last_sync', 'created_at'),
            'classes': ('collapse',)
        })
    )

    def olt_info(self, obj):
        """Información de la OLT"""
        return f"{obj.olt.abreviatura} ({obj.olt.ip_address})"
    olt_info.short_description = "OLT"

    def descripcion_corta(self, obj):
        """Descripción truncada"""
        desc = obj.descripcion_limpia
        if desc:
            return desc[:60] + "..." if len(desc) > 60 else desc
        return "-"
    descripcion_corta.short_description = "Descripción"

    def disponible_display(self, obj):
        """Muestra si el puerto está disponible en Zabbix con solo un check"""
        if obj.disponible:
            return format_html('<span style="color: green; font-size: 16px;">✅</span>')
        return format_html('<span style="color: red; font-size: 16px;">❌</span>')
    disponible_display.short_description = "En Zabbix"
    
    def estado_administrativo_display(self, obj):
        """Muestra el estado administrativo del puerto"""
        if obj.estado_administrativo == 1:
            return format_html('<span style="color: green; font-weight: bold;">ACTIVO</span>')
        elif obj.estado_administrativo == 2:
            return format_html('<span style="color: red; font-weight: bold;">INACTIVO</span>')
        return format_html('<span style="color: gray;">-</span>')
    estado_administrativo_display.short_description = "Estado Administrativo"
    
    def info_display(self, obj):
        """Muestra si el puerto fue encontrado en el item master"""
        if obj.disponible:
            return format_html('<span style="color: green; font-weight: bold;">Encontrado</span>')
        return format_html('<span style="color: red; font-weight: bold;">No encontrado</span>')
    info_display.short_description = "Info"
    
    def registrado_display(self, obj):
        """Muestra si el puerto tiene hilos ODF registrados y su estado operativo NOC"""
        hilo_count = obj.odfhilos_set.count()
        if hilo_count > 0:
            # Mostrar operativo NOC junto con registrado
            operativo_icon = "✅" if obj.operativo_noc else "❌"
            return format_html(
                '<span style="color: green; font-weight: bold;">Registrado</span> {}<br>'
                '<small style="color: gray;">({} hilo(s))</small>',
                operativo_icon, hilo_count
            )
        return format_html('<span style="color: gray;">No registrado</span>')
    registrado_display.short_description = "Registrado / Operativo NOC"

    def tiene_hilo_asociado(self, obj):
        """Indica si tiene un hilo ODF asociado"""
        hilo_count = obj.odfhilos_set.count()
        if hilo_count > 0:
            return format_html(
                '<span style="color: green;">✓ {} hilo(s)</span>',
                hilo_count
            )
        return format_html('<span style="color: orange;">📋 Disponible</span>')
    tiene_hilo_asociado.short_description = "Estado"

    def acciones_rapidas(self, obj):
        """Acciones rápidas para cada puerto"""
        if obj.odfhilos_set.count() == 0:
            # Puerto disponible - mostrar botón para crear hilo
            return format_html(
                '<a href="/admin/odf_management/odfhilos/add/?zabbix_port={}&slot={}&port={}" '
                'style="background: #417690; color: white; padding: 3px 8px; text-decoration: none; '
                'border-radius: 3px; font-size: 11px;">➕ Crear Hilo</a>',
                obj.id, obj.slot, obj.port
            )
        else:
            # Puerto ocupado - mostrar enlace a hilos
            hilo_url = reverse('admin:odf_management_odfhilos_changelist')
            return format_html(
                '<a href="{}?zabbix_port__id__exact={}" '
                'style="background: #28a745; color: white; padding: 3px 8px; text-decoration: none; '
                'border-radius: 3px; font-size: 11px;">👁️ Ver Hilos</a>',
                hilo_url, obj.id
            )
    acciones_rapidas.short_description = "Acciones"

    # Acciones personalizadas
    actions = ['mostrar_resumen_seleccionados', 'filtrar_puertos_disponibles', 'agrupar_por_slot', 'sincronizar_operativo_noc']
    
    def save_model(self, request, obj, form, change):
        """
        Guardar puerto Zabbix y sincronizar con hilos relacionados.
        """
        # Guardar primero
        super().save_model(request, obj, form, change)
        
        # Verificar cambios en disponible y sincronizar con hilos
        hilos_relacionados = obj.odfhilos_set.all()
        
        if hilos_relacionados.exists():
            cambios_sincronizados = 0
            
            for hilo in hilos_relacionados:
                # Sincronizar estado "en_zabbix" con "disponible" del puerto
                if hilo.en_zabbix != obj.disponible:
                    hilo.en_zabbix = obj.disponible
                    hilo.save()
                    cambios_sincronizados += 1
            
            count = hilos_relacionados.count()
            
            if cambios_sincronizados > 0:
                if obj.disponible:
                    self.message_user(request, 
                        f"✅ {cambios_sincronizados} hilo(s) ODF marcado(s) como 'EN ZABBIX' (disponible)")
                else:
                    self.message_user(request, 
                        f"❌ {cambios_sincronizados} hilo(s) ODF marcado(s) como 'NO EN ZABBIX' (no disponible)")
            else:
                self.message_user(request, 
                    f"ℹ️ Este puerto tiene {count} hilo(s) ODF asociado(s) - Estados ya sincronizados")
        else:
            # Sin hilos relacionados
            if change and 'disponible' in form.changed_data:
                estado = "disponible" if obj.disponible else "no disponible"
                self.message_user(request, f"🔄 Puerto marcado como {estado} en Zabbix")

    def mostrar_resumen_seleccionados(self, request, queryset):
        """Muestra resumen de puertos seleccionados para agrupamiento"""
        count = queryset.count()
        disponibles = queryset.filter(odfhilos__isnull=True).count()
        ocupados = count - disponibles
        
        # Agrupar por slot
        slots_info = {}
        for port in queryset:
            slot = port.slot
            if slot not in slots_info:
                slots_info[slot] = {'total': 0, 'disponibles': 0}
            slots_info[slot]['total'] += 1
            if not port.odfhilos_set.exists():
                slots_info[slot]['disponibles'] += 1
        
        slots_resumen = []
        for slot, info in sorted(slots_info.items()):
            slots_resumen.append(f"Slot {slot}: {info['disponibles']}/{info['total']} disponibles")
        
        mensaje = (
            f"📊 RESUMEN DE SELECCIÓN:\n"
            f"• Total: {count} puertos\n"
            f"• Disponibles: {disponibles} puertos\n"
            f"• Ya ocupados: {ocupados} puertos\n"
            f"• Por slots: {', '.join(slots_resumen)}"
        )
        
        self.message_user(request, mensaje)
    mostrar_resumen_seleccionados.short_description = "📊 Mostrar resumen para agrupamiento"

    def filtrar_puertos_disponibles(self, request, queryset):
        """Información sobre puertos disponibles para crear hilos"""
        disponibles = queryset.filter(odfhilos__isnull=True)
        count = disponibles.count()
        
        if count == 0:
            self.message_user(request, "❌ No hay puertos disponibles en la selección.")
        else:
            self.message_user(
                request, 
                f"✅ {count} puertos disponibles listos para crear hilos ODF. "
                f"Use los botones '➕ Crear Hilo' para configurarlos individualmente."
            )
    filtrar_puertos_disponibles.short_description = "🔍 Verificar disponibilidad"

    def agrupar_por_slot(self, request, queryset):
        """Muestra agrupación por slot para facilitar organización"""
        slots = {}
        for port in queryset:
            slot = port.slot
            if slot not in slots:
                slots[slot] = []
            slots[slot].append(f"Port {port.port}")
        
        agrupacion = []
        for slot in sorted(slots.keys()):
            ports_str = ", ".join(sorted(slots[slot]))
            agrupacion.append(f"🔌 Slot {slot}: {ports_str}")
        
        mensaje = "📋 AGRUPACIÓN POR SLOTS:\n" + "\n".join(agrupacion)
        self.message_user(request, mensaje)
    agrupar_por_slot.short_description = "📋 Agrupar por slots"
    
    def sincronizar_operativo_noc(self, request, queryset):
        """Sincroniza el estado operativo NOC entre puertos Zabbix y sus hilos ODF asociados"""
        total_sincronizados = 0
        
        for puerto in queryset:
            hilos_relacionados = puerto.odfhilos_set.all()
            for hilo in hilos_relacionados:
                if hilo.operativo_noc != puerto.operativo_noc:
                    hilo.operativo_noc = puerto.operativo_noc
                    hilo.save()
                    total_sincronizados += 1
        
        if total_sincronizados > 0:
            self.message_user(request, f'🔄 {total_sincronizados} hilo(s) ODF sincronizado(s) con sus puertos Zabbix.')
        else:
            self.message_user(request, f'✅ Todos los hilos ya estaban sincronizados.')
    sincronizar_operativo_noc.short_description = "🔄 Sincronizar Operativo NOC"

    def get_queryset(self, request):
        """Optimiza las consultas"""
        return super().get_queryset(request).select_related('olt').prefetch_related('odfhilos_set')


@admin.register(ODF)
class ODFAdmin(admin.ModelAdmin):
    # Para autocomplete
    search_fields = ['nombre_troncal', 'olt__abreviatura']
    """Admin para gestionar ODFs"""
    
    list_display = [
        'identificador_completo', 
        'olt_info',
        'numero_odf',
        'nombre_troncal',
        'cantidad_hilos',
        'created_at'
    ]
    
    list_filter = [
        'olt',
        'numero_odf',
        'created_at'
    ]
    
    search_fields = [
        'nombre_troncal',
        'descripcion',
        'olt__abreviatura',
        'olt__ip_address'
    ]
    
    ordering = ['olt', 'numero_odf', 'nombre_troncal']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('olt', 'numero_odf', 'nombre_troncal', 'descripcion')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def olt_info(self, obj):
        """Información de la OLT"""
        return f"{obj.olt.abreviatura}"
    olt_info.short_description = "OLT"

    def descripcion_corta(self, obj):
        """Descripción truncada"""
        if obj.descripcion:
            return obj.descripcion[:50] + "..." if len(obj.descripcion) > 50 else obj.descripcion
        return "-"
    descripcion_corta.short_description = "Descripción"

    def cantidad_hilos(self, obj):
        """Cantidad de hilos asociados"""
        count = obj.odfhilos_set.count()
        if count > 0:
            url = reverse('admin:odf_management_odfhilos_changelist')
            return format_html(
                '<a href="{}?odf__id__exact={}">{} hilo(s)</a>',
                url, obj.id, count
            )
        return "0 hilos"
    cantidad_hilos.short_description = "Hilos"


@admin.register(ODFHilos)
class ODFHilosAdmin(admin.ModelAdmin):
    """Admin principal para gestionar hilos ODF con toda la información"""
    
    list_display = [
        'identificador_completo',
        'olt_info',
        'odf',
        'slot',
        'port', 
        'hilo_numero',
        'vlan',
        'personal_proyectos_display',
        'personal_noc_display',
        'tecnico_habilitador_display',
        'fecha_habilitacion',
        'hora_habilitacion',
        'en_zabbix_display',
        'operativo_noc_display',
        'updated_at'
    ]
    
    # Optimización de consultas para evitar N+1 queries
    list_select_related = [
        'odf',
        'odf__olt',
        'zabbix_port',
        'personal_proyectos',
        'personal_noc',
        'tecnico_habilitador'
    ]
    
    # Paginación optimizada
    list_per_page = 25
    list_max_show_all = 100
    
    # Optimizar formularios para evitar carga lenta de opciones
    raw_id_fields = ['zabbix_port']
    autocomplete_fields = ['odf', 'personal_proyectos', 'personal_noc', 'tecnico_habilitador']
    
    list_filter = [
        'odf__olt',
        'odf',
        'slot',
        'personal_proyectos',
        'personal_noc',
        'tecnico_habilitador',
        'en_zabbix',
        'operativo_noc', # Nuevo filtro para operativo NOC
        'fecha_habilitacion',
        'hora_habilitacion',
        'created_at'
    ]
    
    search_fields = [
        'odf__nombre_troncal',
        'odf__olt__abreviatura',
        'descripcion_manual',
        'zabbix_port__descripcion_zabbix',
        'vlan',
        'hilo_numero'
    ]
    
    ordering = ['odf', 'slot', 'port', 'hilo_numero']
    readonly_fields = ['created_at', 'updated_at', 'descripcion_zabbix_info', 'zabbix_port_info']
    
    fieldsets = (
        ('Información del Hilo', {
            'fields': ('odf', 'hilo_numero', 'vlan', 'fecha_habilitacion', 'hora_habilitacion', 'operativo_noc')
        }),
        ('Personal Responsable', {
            'fields': ('personal_proyectos', 'personal_noc', 'tecnico_habilitador'),
            'description': 'Asignar personal responsable para cada área'
        }),
        ('Asociación con Puerto Zabbix', {
            'fields': ('zabbix_port', 'zabbix_port_info'),
            'description': 'Usar el ícono de búsqueda para seleccionar puerto Zabbix'
        }),
        ('Datos de Puerto (Manual o Auto)', {
            'fields': ('slot', 'port'),
            'description': 'Se llenan automáticamente si hay puerto Zabbix asociado'
        }),
        ('Descripción y Comentarios', {
            'fields': ('descripcion_manual',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_form(self, request, obj=None, **kwargs):
        """Optimizar formulario y pre-llenar campos"""
        form = super().get_form(request, obj, **kwargs)
        
        # Pre-llenar desde parámetros GET
        if not obj and request.GET:
            zabbix_port_id = request.GET.get('zabbix_port')
            slot = request.GET.get('slot')
            port = request.GET.get('port')
            
            if zabbix_port_id:
                try:
                    from .models import ZabbixPortData
                    zabbix_port = ZabbixPortData.objects.select_related('olt').get(id=zabbix_port_id)
                    form.base_fields['zabbix_port'].initial = zabbix_port
                    form.base_fields['slot'].initial = zabbix_port.slot
                    form.base_fields['port'].initial = zabbix_port.port
                    
                    # Mensaje informativo en el formulario
                    desc_preview = zabbix_port.descripcion_zabbix[:50] if zabbix_port.descripcion_zabbix else "Sin descripción"
                    if zabbix_port.descripcion_zabbix and len(zabbix_port.descripcion_zabbix) > 50:
                        desc_preview += "..."
                    # TAMAÑO DEL TEXTO DEL MENSAJE INFORMATIVO
                    form.base_fields['zabbix_port'].help_text = mark_safe(f'<span style="font-size: 26px; font-weight: bold; color: #28a745;">✅ Puerto pre-seleccionado: {zabbix_port.olt.abreviatura} - Slot {zabbix_port.slot}/Port {zabbix_port.port} - {desc_preview}</span>') 
                    
                except ZabbixPortData.DoesNotExist:
                    pass
            elif slot and port:
                try:
                    form.base_fields['slot'].initial = int(slot)
                    form.base_fields['port'].initial = int(port)
                except (ValueError, TypeError):
                    pass
        
        return form
    
    def save_model(self, request, obj, form, change):
        """Sincronizar estados entre ODFHilos y ZabbixPortData al guardar"""
        super().save_model(request, obj, form, change)
        
        # Usar el método de sincronización inteligente del modelo
        if hasattr(obj, 'sincronizar_operativo_noc'):
            sincronizado = obj.sincronizar_operativo_noc(forzar_direccion='hilo_a_puerto')
            
            if sincronizado:
                if obj.operativo_noc:
                    self.message_user(request, f"✅ Puerto Zabbix {obj.zabbix_port.id} sincronizado como OPERATIVO por NOC")
                else:
                    self.message_user(request, f"❌ Puerto Zabbix {obj.zabbix_port.id} sincronizado como NO OPERATIVO por NOC")
            elif not obj.zabbix_port:
                self.message_user(request, f"⚠️ No se encontró puerto Zabbix asociado para sincronizar. Verifica la asociación manual.")
            else:
                self.message_user(request, f"ℹ️ Estados ya sincronizados correctamente.")

    def olt_info(self, obj):
        """Información de la OLT"""
        return obj.odf.olt.abreviatura
    olt_info.short_description = "OLT"

    def personal_proyectos_display(self, obj):
        """Muestra personal de proyectos"""
        if obj.personal_proyectos:
            return format_html(
                '<span style="color: blue;">👨‍💼 {}</span>',
                obj.personal_proyectos.nombre_completo
            )
        return format_html('<span style="color: gray;">-</span>')
    personal_proyectos_display.short_description = "Personal Proyectos"
    
    def personal_noc_display(self, obj):
        """Muestra personal NOC"""
        if obj.personal_noc:
            return format_html(
                '<span style="color: green;">🖥️ {}</span>',
                obj.personal_noc.nombre_completo
            )
        return format_html('<span style="color: gray;">-</span>')
    personal_noc_display.short_description = "Personal NOC"
    
    def tecnico_habilitador_display(self, obj):
        """Muestra técnico habilitador"""
        if obj.tecnico_habilitador:
            return format_html(
                '<span style="color: orange;">🔧 {}</span>',
                obj.tecnico_habilitador.nombre_completo
            )
        return format_html('<span style="color: gray;">-</span>')
    tecnico_habilitador_display.short_description = "Técnico Habilitador"

    def en_zabbix_display(self, obj):
        """Muestra si está en Zabbix combinando info y estado administrativo"""
        if not obj.en_zabbix:
            return format_html('<span style="color: gray; font-weight: bold;">No presente en Zabbix</span>')
        
        # Si está en Zabbix, verificar estado administrativo del puerto asociado
        if obj.zabbix_port and obj.zabbix_port.estado_administrativo:
            if obj.zabbix_port.estado_administrativo == 1:
                return format_html('<span style="color: green; font-weight: bold;">ACTIVO</span>')
            elif obj.zabbix_port.estado_administrativo == 2:
                return format_html('<span style="color: orange; font-weight: bold;">NO ACTIVO</span>')
        
        # Si está en Zabbix pero no tiene estado administrativo
        return format_html('<span style="color: red; font-weight: bold;">Error 1</span>')
    en_zabbix_display.short_description = "En Zabbix"
    
    def operativo_noc_display(self, obj):
        """Muestra si el hilo está operativo según NOC"""
        if obj.operativo_noc:
            return format_html('<span style="color: green; font-size: 16px;">✅</span>')
        return format_html('<span style="color: red; font-size: 16px;">❌</span>')
    operativo_noc_display.short_description = "Operativo NOC"

    def descripcion_zabbix_info(self, obj):
        """Muestra información de Zabbix si está disponible"""
        if obj.zabbix_port:
            return format_html(
                '<strong>SNMP Index:</strong> {}<br>'
                '<strong>Interface:</strong> {}<br>'
                '<strong>Descripción:</strong> {}',
                obj.zabbix_port.snmp_index,
                obj.zabbix_port.interface_name or 'N/A',
                obj.zabbix_port.descripcion_limpia or 'N/A'
            )
        return "No hay puerto Zabbix asociado"
    descripcion_zabbix_info.short_description = "Info Zabbix"
    
    def zabbix_port_info(self, obj):
        """Muestra información completa del puerto Zabbix seleccionado"""
        if obj.zabbix_port:
            port = obj.zabbix_port
            disponible_icon = "✅" if port.disponible else "❌"
            
            # Determinar si está operativo según NOC
            operativo_noc_icon = "✅" if port.operativo_noc else "❌"
            
            info_html = f"""
            <div style="background: var(--body-bg, #f8f9fa); border: 1px solid var(--border-color, #dee2e6); border-radius: 5px; padding: 15px; margin: 10px 0; color: var(--body-fg, #333);">
                <h4 style="margin: 0 0 10px 0; color: var(--link-fg, #28a745);">📋 Información del Puerto Zabbix</h4>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                    <div>
                        <strong style="color: var(--body-fg, #333);">🏢 OLT:</strong> {port.olt.abreviatura}<br>
                        <strong style="color: var(--body-fg, #333);">📍 Slot/Port:</strong> {port.slot}/{port.port}<br>
                        <strong style="color: var(--body-fg, #333);">🔢 SNMP Index:</strong> {port.snmp_index}<br>
                        <strong style="color: var(--body-fg, #333);">🔌 Interface:</strong> {port.interface_name}
                    </div>
                    <div>
                        <strong style="color: var(--body-fg, #333);">📶 En Zabbix:</strong> {disponible_icon}<br>
                        <strong style="color: var(--body-fg, #333);">🔧 Operativo NOC:</strong> {operativo_noc_icon}<br>
                        <strong style="color: var(--body-fg, #333);">🕐 Última Sync:</strong> <span style="color: var(--body-quiet-color, #666);">{port.last_sync.strftime('%d/%m/%Y %H:%M') if port.last_sync else 'Nunca'}</span><br>
                        <strong style="color: var(--body-fg, #333);">📝 Descripción:</strong><br>
                        <em style="color: var(--body-quiet-color, #666); font-size: 12px;">{port.descripcion_zabbix[:100] if port.descripcion_zabbix else 'Sin descripción'}{'...' if port.descripcion_zabbix and len(port.descripcion_zabbix) > 100 else ''}</em>
                    </div>
                </div>
                
                <div style="margin-top: 10px; padding: 8px; background: var(--darkened-bg, #e7f3ff); border-radius: 3px;">
                    <strong style="color: var(--body-fg, #333);">📋 Descripción Completa:</strong><br>
                    <span style="font-family: monospace; font-size: 11px; color: var(--body-quiet-color, #333);">
                        {port.descripcion_zabbix or 'Sin descripción disponible'}
                    </span>
                </div>
                
                <div style="margin-top: 10px; padding: 8px; background: var(--selected-bg, #f0f8ff); border-left: 3px solid var(--link-fg, #007bff); font-size: 12px;">
                    <strong style="color: var(--body-fg, #333);">🔄 Para cambiar puerto:</strong> <span style="color: var(--body-quiet-color, #666);">Usa el ícono de lupa (🔍) arriba para seleccionar otro puerto. La información se actualizará automáticamente al guardar.</span>
                </div>
            </div>
            """
            return format_html(info_html)
        else:
            return ""  # No mostrar nada cuando no hay puerto seleccionado
    zabbix_port_info.short_description = "Información del Puerto Zabbix"

    # Acciones personalizadas
    actions = ['habilitar_hilos', 'deshabilitar_hilos', 'exportar_configuracion']

    def habilitar_hilos(self, request, queryset):
        """Habilita los hilos seleccionados"""
        updated = queryset.update(estado='enabled')
        self.message_user(request, f'{updated} hilos habilitados correctamente.')
    habilitar_hilos.short_description = "Habilitar hilos seleccionados"

    def deshabilitar_hilos(self, request, queryset):
        """Deshabilita los hilos seleccionados"""
        updated = queryset.update(estado='disabled')
        self.message_user(request, f'{updated} hilos deshabilitados correctamente.')
    deshabilitar_hilos.short_description = "Deshabilitar hilos seleccionados"

    def exportar_configuracion(self, request, queryset):
        """Exporta configuración de hilos seleccionados"""
        count = queryset.count()
        # Aquí se podría implementar exportación a CSV o similar
        self.message_user(request, f'Configuración de {count} hilos lista para exportar.')
    exportar_configuracion.short_description = "Exportar configuración"

    # Filtros personalizados
    def get_queryset(self, request):
        """Optimiza las consultas"""
        return super().get_queryset(request).select_related(
            'odf', 'odf__olt', 'zabbix_port'
        )


# Personalización del admin site
admin.site.site_header = "Gestión de ODFs y Hilos"
admin.site.site_title = "ODF Management"
admin.site.index_title = "Panel de Administración - ODFs"