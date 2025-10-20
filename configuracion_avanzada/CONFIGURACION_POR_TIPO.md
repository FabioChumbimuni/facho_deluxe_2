# Configuración SNMP por Tipo de Operación

## Problema Resuelto

**Error anterior**:
```
❌ get() returned more than one ConfiguracionSNMP -- it returned 2!
```

**Causa**: Había 2 configuraciones activas sin distinguir por tipo

**Solución**: Ahora cada configuración tiene `tipo_operacion` específico

## Configuraciones Actuales

### ID 1: Descubrimiento (SNMP Walk)
```
Nombre: configuracion_por_defecto
Tipo: descubrimiento
Timeout: 10s
Reintentos: 0
Aplica a: Tareas con job_type='descubrimiento'
```

### ID 3: GET (Consultas Individuales)
```
Nombre: Config GET Predeterminada
Tipo: get
Timeout: 5s
Reintentos: 2
Max pollers: 10
Lote inicial: 200
Subdivisión: 50
Semáforo: 5
Aplica a: Tareas con job_type='get'
```

## Cómo Funciona

### Discovery llama:
```python
from configuracion_avanzada.services import get_snmp_timeout, get_snmp_retries

# Sin parámetros → usa 'descubrimiento' por defecto
timeout = get_snmp_timeout()  # → 10s (Config ID 1)
retries = get_snmp_retries()  # → 0 (Config ID 1)
```

### GET llama:
```python
from configuracion_avanzada.models import ConfiguracionSNMP

# Explícitamente pide tipo 'get'
config = ConfiguracionSNMP.get_config_for_tipo('get')
timeout = config.timeout  # → 5s (Config ID 3)
retries = config.reintentos  # → 2 (Config ID 3)
```

## Flujo de Búsqueda

```python
ConfiguracionSNMP.get_config_for_tipo('get'):
    1. Busca tipo_operacion='get' AND activo=True
       ✅ Encuentra: "Config GET Predeterminada"
    2. Si no existe, busca tipo_operacion='general'
    3. Si tampoco, retorna None

ConfiguracionSNMP.get_config_for_tipo('descubrimiento'):
    1. Busca tipo_operacion='descubrimiento' AND activo=True
       ✅ Encuentra: "configuracion_por_defecto"
    2. Si no existe, busca tipo_operacion='general'
    3. Si tampoco, retorna None
```

## Verificación

```bash
python manage.py shell

from configuracion_avanzada.services import get_snmp_timeout, get_snmp_retries

# Para descubrimiento
print(get_snmp_timeout('descubrimiento'))  # → 10
print(get_snmp_retries('descubrimiento'))  # → 0

# Para GET
print(get_snmp_timeout('get'))  # → 5
print(get_snmp_retries('get'))  # → 2
```

## Actualizar Configuraciones

### Cambiar Config de Descubrimiento
```
Admin → configuracion_por_defecto
  - Timeout: 15s (si las OLTs son lentas)
  - Guardar
```

### Cambiar Config de GET
```
Admin → Config GET Predeterminada
  - Max pollers: 15 (si la OLT aguanta más)
  - Semáforo: 8 (más consultas simultáneas)
  - Guardar
```

## Funciones Actualizadas

```python
# configuracion_avanzada/services.py

def get_snmp_timeout(tipo_operacion='descubrimiento'):
    """
    Default 'descubrimiento' → Para discovery
    Pasar 'get' → Para GET operations
    """
    config = ConfiguracionSNMP.get_config_for_tipo(tipo_operacion)
    return config.timeout if config else 5

def get_snmp_retries(tipo_operacion='descubrimiento'):
    """
    Default 'descubrimiento' → Para discovery
    Pasar 'get' → Para GET operations
    """
    config = ConfiguracionSNMP.get_config_for_tipo(tipo_operacion)
    return config.reintentos if config else 0
```

## Resultado

✅ Discovery usa: timeout=10s, retries=0
✅ GET usa: timeout=5s, retries=2, pollers=10, semáforo=5
✅ NO más errores de múltiples configuraciones
✅ Configuraciones independientes por tipo de operación

