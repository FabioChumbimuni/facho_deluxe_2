from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from personal.models import Area, NivelPrivilegio, Personal


class Command(BaseCommand):
    help = 'Crea datos de ejemplo con personajes de Half-Life para el sistema de personal'

    def handle(self, *args, **options):
        self.stdout.write('🎮 Creando personal de Half-Life...\n')

        # 1. Crear Áreas
        areas_data = [
            {
                'nombre': 'NOC',
                'descripcion': 'Network Operations Center - Monitoreo y control de red'
            },
            {
                'nombre': 'Proyectos', 
                'descripcion': 'Planificación y ejecución de proyectos de infraestructura'
            },
            {
                'nombre': 'Técnico de Campo',
                'descripcion': 'Instalación y mantenimiento en campo'
            }
        ]

        areas = {}
        for area_data in areas_data:
            area, created = Area.objects.get_or_create(
                nombre=area_data['nombre'],
                defaults={'descripcion': area_data['descripcion']}
            )
            areas[area_data['nombre']] = area
            status = "✅ Creada" if created else "🔄 Ya existe"
            self.stdout.write(f"  {status}: {area.nombre}")

        # 2. Crear Niveles de Privilegio
        niveles_data = [
            {
                'nivel': 1,
                'nombre': 'Básico',
                'descripcion': 'Solo lectura de información básica',
                'permisos_odf': {'leer': True, 'gestionar': False},
                'permisos_hilos': {'leer': True, 'gestionar': False}
            },
            {
                'nivel': 2, 
                'nombre': 'Operador',
                'descripcion': 'Lectura y escritura limitada',
                'permisos_odf': {'leer': True, 'gestionar': False},
                'permisos_hilos': {'leer': True, 'gestionar': True}
            },
            {
                'nivel': 3,
                'nombre': 'Supervisor', 
                'descripcion': 'Gestión completa de su área',
                'permisos_odf': {'leer': True, 'gestionar': True},
                'permisos_hilos': {'leer': True, 'gestionar': True}
            },
            {
                'nivel': 4,
                'nombre': 'Administrador',
                'descripcion': 'Gestión completa del sistema',
                'permisos_odf': {'leer': True, 'gestionar': True, 'admin': True},
                'permisos_hilos': {'leer': True, 'gestionar': True, 'admin': True}
            }
        ]

        niveles = {}
        self.stdout.write('\n📊 Niveles de Privilegio:')
        for nivel_data in niveles_data:
            nivel, created = NivelPrivilegio.objects.get_or_create(
                nivel=nivel_data['nivel'],
                defaults={
                    'nombre': nivel_data['nombre'],
                    'descripcion': nivel_data['descripcion'],
                    'permisos_odf': nivel_data['permisos_odf'],
                    'permisos_hilos': nivel_data['permisos_hilos']
                }
            )
            niveles[nivel_data['nivel']] = nivel
            status = "✅ Creado" if created else "🔄 Ya existe"
            self.stdout.write(f"  {status}: Nivel {nivel.nivel} - {nivel.nombre}")

        # 3. Crear Personal de Half-Life
        personal_data = [
            # NOC Team
            {
                'nombres': 'Gordon',
                'apellidos': 'Freeman',
                'documento_identidad': '12345001',
                'email': 'gordon.freeman@blackmesa.com',
                'telefono': '+51-999-001-001',
                'codigo_empleado': 'NOC-001',
                'area': 'NOC',
                'nivel': 4,  # Administrador
                'cargo': 'Jefe de NOC',
                'fecha_ingreso': date(2020, 3, 15),
                'estado': 'activo'
            },
            {
                'nombres': 'Alyx',
                'apellidos': 'Vance',
                'documento_identidad': '12345002', 
                'email': 'alyx.vance@blackmesa.com',
                'telefono': '+51-999-001-002',
                'codigo_empleado': 'NOC-002',
                'area': 'NOC',
                'nivel': 3,  # Supervisor
                'cargo': 'Supervisora de Monitoreo',
                'fecha_ingreso': date(2021, 1, 10),
                'estado': 'activo'
            },
            {
                'nombres': 'Isaac',
                'apellidos': 'Kleiner',
                'documento_identidad': '12345003',
                'email': 'isaac.kleiner@blackmesa.com', 
                'telefono': '+51-999-001-003',
                'codigo_empleado': 'NOC-003',
                'area': 'NOC',
                'nivel': 2,  # Operador
                'cargo': 'Analista de Red',
                'fecha_ingreso': date(2021, 6, 20),
                'estado': 'activo'
            },

            # Proyectos Team
            {
                'nombres': 'Eli',
                'apellidos': 'Vance',
                'documento_identidad': '12345004',
                'email': 'eli.vance@blackmesa.com',
                'telefono': '+51-999-002-001', 
                'codigo_empleado': 'PRY-001',
                'area': 'Proyectos',
                'nivel': 4,  # Administrador
                'cargo': 'Gerente de Proyectos',
                'fecha_ingreso': date(2019, 8, 1),
                'estado': 'activo'
            },
            {
                'nombres': 'Judith',
                'apellidos': 'Mossman',
                'documento_identidad': '12345005',
                'email': 'judith.mossman@blackmesa.com',
                'telefono': '+51-999-002-002',
                'codigo_empleado': 'PRY-002', 
                'area': 'Proyectos',
                'nivel': 3,  # Supervisor
                'cargo': 'Coordinadora de Proyectos',
                'fecha_ingreso': date(2020, 11, 15),
                'estado': 'activo'
            },
            {
                'nombres': 'Wallace',
                'apellidos': 'Breen',
                'documento_identidad': '12345006',
                'email': 'wallace.breen@blackmesa.com',
                'telefono': '+51-999-002-003',
                'codigo_empleado': 'PRY-003',
                'area': 'Proyectos', 
                'nivel': 2,  # Operador
                'cargo': 'Analista de Proyectos',
                'fecha_ingreso': date(2022, 2, 1),
                'estado': 'suspendido'  # Por traición 😄
            },

            # Técnico de Campo Team
            {
                'nombres': 'Barney',
                'apellidos': 'Calhoun',
                'documento_identidad': '12345007',
                'email': 'barney.calhoun@blackmesa.com',
                'telefono': '+51-999-003-001',
                'codigo_empleado': 'TEC-001',
                'area': 'Técnico de Campo',
                'nivel': 3,  # Supervisor
                'cargo': 'Jefe de Técnicos',
                'fecha_ingreso': date(2020, 5, 10),
                'estado': 'activo'
            },
            {
                'nombres': 'Adrian',
                'apellidos': 'Shephard',
                'documento_identidad': '12345008',
                'email': 'adrian.shephard@blackmesa.com',
                'telefono': '+51-999-003-002',
                'codigo_empleado': 'TEC-002',
                'area': 'Técnico de Campo',
                'nivel': 2,  # Operador
                'cargo': 'Técnico Senior',
                'fecha_ingreso': date(2021, 9, 5),
                'estado': 'activo'
            },
            {
                'nombres': 'Gina',
                'apellidos': 'Cross',
                'documento_identidad': '12345009',
                'email': 'gina.cross@blackmesa.com',
                'telefono': '+51-999-003-003',
                'codigo_empleado': 'TEC-003',
                'area': 'Técnico de Campo',
                'nivel': 2,  # Operador
                'cargo': 'Técnico de Instalaciones',
                'fecha_ingreso': date(2022, 1, 20),
                'estado': 'activo'
            },
            {
                'nombres': 'Colette',
                'apellidos': 'Green',
                'documento_identidad': '12345010',
                'email': 'colette.green@blackmesa.com',
                'telefono': '+51-999-003-004',
                'codigo_empleado': 'TEC-004',
                'area': 'Técnico de Campo',
                'nivel': 1,  # Básico
                'cargo': 'Técnico Junior',
                'fecha_ingreso': date(2023, 3, 1),
                'estado': 'activo'
            }
        ]

        self.stdout.write('\n👥 Personal de Half-Life:')
        personal_creado = 0
        for person_data in personal_data:
            try:
                personal, created = Personal.objects.get_or_create(
                    codigo_empleado=person_data['codigo_empleado'],
                    defaults={
                        'nombres': person_data['nombres'],
                        'apellidos': person_data['apellidos'],
                        'documento_identidad': person_data['documento_identidad'],
                        'email': person_data['email'],
                        'telefono': person_data['telefono'],
                        'area': areas[person_data['area']],
                        'nivel_privilegio': niveles[person_data['nivel']],
                        'cargo': person_data['cargo'],
                        'fecha_ingreso': person_data['fecha_ingreso'],
                        'estado': person_data['estado']
                    }
                )
                
                if created:
                    personal_creado += 1
                    status = "✅ Creado"
                else:
                    status = "🔄 Ya existe"
                
                area_icon = {
                    'NOC': '🖥️',
                    'Proyectos': '👨‍💼', 
                    'Técnico de Campo': '🔧'
                }.get(person_data['area'], '👤')
                
                estado_icon = {
                    'activo': '✅',
                    'inactivo': '⏸️',
                    'suspendido': '🚫'
                }.get(person_data['estado'], '❓')
                
                self.stdout.write(
                    f"  {status}: {area_icon} {personal.nombre_completo} - "
                    f"{person_data['cargo']} {estado_icon}"
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ Error creando {person_data['nombres']} {person_data['apellidos']}: {e}")
                )

        # Resumen final
        self.stdout.write('\n' + '='*50)
        self.stdout.write('🎉 RESUMEN DE DATOS CREADOS:')
        self.stdout.write(f"  📁 Áreas: {Area.objects.count()}")
        self.stdout.write(f"  📊 Niveles: {NivelPrivilegio.objects.count()}")
        self.stdout.write(f"  👥 Personal: {Personal.objects.count()}")
        self.stdout.write(f"  ✨ Nuevo personal: {personal_creado}")
        
        self.stdout.write('\n🎮 Personal de Half-Life creado exitosamente!')
        self.stdout.write('💡 Ahora puedes asignar este personal a los hilos ODF.')
        
        # Mostrar distribución por área
        self.stdout.write('\n📈 DISTRIBUCIÓN POR ÁREA:')
        for area in areas.values():
            count = area.personal_set.count()
            activos = area.personal_set.filter(estado='activo').count()
            self.stdout.write(f"  {area.nombre}: {count} personas ({activos} activas)")
