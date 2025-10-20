# Sistema SNMP GET con Pollers - Implementado ✅

## Resumen

Nueva app `snmp_get` creada con sistema de pollers basado en la lógica de `facho_deluxe`, adaptado para trabajar con las tablas `onu_index_map`, `onu_status` y `onu_inventory`.

## Configuraciones Separadas por Tipo

### Tabla: `configuracion_snmp`

| ID | Nombre | Tipo | Timeout | Reintentos | Pollers | Lote |
|----|--------|------|---------|------------|---------|------|
| 1 | configuracion_por_defecto | descubrimiento | 10s | 0 | N/A | N/A |
| 3 | Config GET Predeterminada | **get** | 5s | 2 | 10 | 200 |

**URL Admin**: `http://127.0.0.1:8000/admin/configuracion_avanzada/configuracionsnmp/`

## Problema Resuelto

**Error**: `get() returned more than one ConfiguracionSNMP -- it returned 2!`

**Causa**: Discovery intentaba obtener config con `.get(activo=True)` sin filtrar por tipo

**Solución**: 
- Agregado campo `tipo_operacion` a `ConfiguracionSNMP`
- Actualizado `get_snmp_timeout()` y `get_snmp_retries()` con default `tipo_operacion='descubrimiento'`
- Discovery usa automáticamente config tipo 'descubrimiento'
- GET usa explícitamente config tipo 'get'

## Sistema de Pollers GET

### Con 5000 ONUs:

```
División: 5000 / 200 = 25 lotes de 200 ONUs

Control 1 (Pollers por OLT):
  - Max 10 pollers simultáneos
  - Lotes 1-10: Procesando
  - Lotes 11-25: En cola

Control 2 (Semáforo SNMP):
  - Max 5 consultas SNMP por poller
  - Protege la OLT de saturación

Carga máxima OLT:
  10 pollers × 5 SNMP = 50 consultas simultáneas
```

### Subdivisión Progresiva:
```
200 ONUs → 3 fallan → 4 sublotes de 50
50 ONUs → 1 falla → 50 consultas individuales
1 ONU → falla → 2 reintentos más (delay 5s, 10s)
```

## Archivos Creados/Modificados

### Nueva App: `snmp_get/`
- `tasks.py` - Sistema de pollers con subdivisión
- `README.md` - Documentación

### Modificados
- `configuracion_avanzada/models.py` - Campo `tipo_operacion` + campos de pollers
- `configuracion_avanzada/admin.py` - Admin mejorado con badges
- `configuracion_avanzada/services.py` - Funciones por tipo ✅ CORREGIDO
- `snmp_jobs/tasks.py` - Dispatcher soporta GET
- `core/settings.py` - App y colas registradas
- `db_diagram.md` - Tabla configuracion_snmp documentada

### Migración
- `configuracion_avanzada/migrations/0002_*.py` ✅ Aplicada

## Iniciar Sistema

```bash
# 1. Workers GET
./start_celery_get_workers.sh

# 2. Crear tarea en admin
# 3. Monitorear
tail -f logs/celery-get_poller.log
```

## Configurar Parámetros

**Admin → configuracion_snmp → Config GET Predeterminada**:

- `timeout`: 5s (ajustar según OLT)
- `reintentos`: 2 (reintentos SNMP)
- `max_pollers_por_olt`: 10 (pollers simultáneos)
- `tamano_lote_inicial`: 200 (ONUs por lote)
- `tamano_subdivision`: 50 (subdivisión)
- `max_consultas_snmp_simultaneas`: 5 (semáforo)

**Los cambios aplican inmediatamente** sin reiniciar workers.

## Verificar Funcionamiento

```bash
# Ver que discovery usa su config
tail -f logs/celery-discovery_main.log | grep "Timeout"

# Ver que GET usa su config
tail -f logs/celery-get_main.log | grep "configuración SNMP"
```

## Estado

✅ App `snmp_get` creada
✅ Configuraciones separadas por tipo
✅ Error de múltiples configs resuelto
✅ Discovery usa timeout 10s, retries 0
✅ GET usa timeout 5s, retries 2, + pollers
✅ Migración aplicada
✅ Documentación actualizada
✅ Todo compilado sin errores

**Sistema listo para usar** 🚀

