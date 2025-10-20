# Programador de Tareas SNMP

## Descripción General
El programador de tareas SNMP permite configurar y automatizar consultas SNMP a múltiples OLTs. Cada tarea se configura para consultar un OID específico en una o más OLTs a intervalos definidos.

## Modelos Relacionados

### SnmpJob
Modelo principal que representa una tarea SNMP programada.
```python
class SnmpJob(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    marca = models.ForeignKey("brands.Brand", on_delete=models.PROTECT)
    job_type = models.CharField(max_length=20, choices=JOB_TYPES)
    interval_raw = models.CharField(max_length=16)
    enabled = models.BooleanField(default=True)
    olts = models.ManyToManyField("hosts.OLT", through="SnmpJobHost")
    oid = models.ForeignKey("oids.OID", on_delete=models.PROTECT)
```

### SnmpJobHost (Through Model)
Modelo intermedio para la relación SnmpJob-OLT.
```python
class SnmpJobHost(models.Model):
    snmp_job = models.ForeignKey(SnmpJob)
    olt = models.ForeignKey("hosts.OLT")
    enabled = models.BooleanField(default=True)
    queue_name = models.CharField(max_length=64)
```

## Campos del Formulario

### Nombre
- **Tipo**: CharField
- **Máximo**: 150 caracteres
- **Requerido**: Sí
- **Descripción**: Identificador único y descriptivo para la tarea
- **Ejemplo**: "Consulta ONUs Huawei"
- **Visualización en lista**: Campo principal

### Descripción
- **Tipo**: TextField
- **Requerido**: No
- **Descripción**: Detalles adicionales sobre el propósito de la tarea
- **Ejemplo**: "Consulta diaria de ONUs activas en OLTs Huawei"
- **Visualización en lista**: Tooltip al pasar el mouse sobre el nombre

### Marca
- **Tipo**: ForeignKey (Brand)
- **Widget**: Select
- **Requerido**: Sí
- **Descripción**: Marca del fabricante de las OLTs
- **Comportamiento**: Al seleccionar una marca, se filtran automáticamente las OLTs y OID compatibles
- **Fuente de datos**: Tabla `brands`
- **Visualización en lista**: Columna "Marca"

### OLTs
- **Tipo**: ManyToManyField
- **Widget**: FilteredSelectMultiple (Dual Select)
- **Requerido**: Sí
- **Descripción**: OLTs en las que se ejecutará la tarea
- **Filtrado**: Solo muestra OLTs de la marca seleccionada donde `habilitar_olt=True`
- **Fuente de datos**: Tabla `olt` filtrada por `marca_id`
- **Visualización**: Dos cuadros de selección:
  - Izquierdo: OLTs disponibles
  - Derecho: OLTs seleccionadas
- **Visualización en lista**: Columna "OLTs" mostrando cantidad y tooltip con lista

### OID
- **Tipo**: ForeignKey
- **Widget**: Select
- **Requerido**: Sí
- **Descripción**: OID que será consultado en la tarea
- **Filtrado**: Solo muestra OIDs compatibles con la marca seleccionada
- **Fuente de datos**: Tabla `oids` filtrada por `marca_id`
- **Visualización**: Lista desplegable con:
  - Nombre del OID
  - Valor del OID entre paréntesis
  - Ejemplo: "ONUs Activas (1.3.6.1.4.1.2011.6.128.1.1.2.21)"
- **Comportamiento**:
  - Se actualiza automáticamente al cambiar la marca
  - Solo muestra OIDs de la marca seleccionada
  - Es obligatorio seleccionar un OID
  - Se guarda la referencia al OID seleccionado en la base de datos
- **Visualización en lista**: Columna "OID" mostrando nombre y valor

### Intervalo
- **Tipo**: CharField
- **Formato**: `<número><unidad>`
- **Unidades válidas**:
  - `s`: segundos
  - `m`: minutos
  - `h`: horas
  - `d`: días
  - `w`: semanas
- **Ejemplos válidos**:
  - "30s" (30 segundos)
  - "5m" (5 minutos)
  - "1h" (1 hora)
  - "2d" (2 días)
  - "1w" (1 semana)
- **Validación**: Expresión regular `^(\d+)([smhdw])$`
- **Visualización en lista**: Columna "Intervalo"

### Tipo de Consulta
- **Tipo**: CharField (choices)
- **Widget**: Select
- **Opciones**:
  - `descubrimiento`: Descubrimiento de ONUs
  - `walk`: SNMP Walk
  - `get`: SNMP Get
  - `table`: SNMP Table
  - `bulk`: SNMP Bulk
- **Default**: "descubrimiento"
- **Visualización en lista**: Columna "Tipo"

### Habilitado
- **Tipo**: BooleanField
- **Widget**: Checkbox
- **Default**: True
- **Descripción**: Indica si la tarea está activa y debe ejecutarse
- **Visualización en lista**: Columna con ícono ✓/✗

## Visualización de Tareas

### Lista de Tareas
La vista de lista muestra una tabla con las siguientes columnas:

| Campo     | Descripción                                  | Estilo                                |
|-----------|----------------------------------------------|---------------------------------------|
| Nombre    | Nombre de la tarea (enlace para editar)      | Normal, enlace azul                  |
| Marca     | Fabricante de las OLTs                       | Normal                               |
| OLTs      | Número de OLTs asociadas                     | Centrado, negrita                    |
| OID       | Nombre del OID consultado                    | Normal                               |
| Intervalo | Frecuencia de ejecución                      | Monoespaciado (font-family: monospace)|
| Tipo      | Tipo de consulta SNMP                        | Capitalizado                         |
| Estado    | Si la tarea está habilitada                  | Centrado, ícono ✓/✗                 |

Ejemplo:
```
| Nombre                | Marca   | OLTs | OID           | Intervalo | Tipo           | Estado |
|--------------------- |---------|------|---------------|-----------|----------------|--------|
| Consulta ONUs Huawei | Huawei  | 3    | ONUs Activas  | 5m        | Descubrimiento | ✓      |
| Monitoreo Tráfico    | ZTE     | 2    | IF-MIB In     | 1h        | Get            | ✓      |
| Test Conectividad    | Huawei  | 1    | System Name   | 30s       | Get            | ✗      |
```

#### Características de la Vista
- Encabezados en azul con texto blanco
- Filas alternadas para mejor legibilidad
- Efecto hover al pasar el mouse
- Botón "Programar Nueva Tarea" destacado
- Filtros por Marca, Tipo y Estado
- Búsqueda por Nombre y Descripción

### Edición de Tarea
Al editar una tarea existente:

1. Se usa el mismo formulario que al crear una tarea nueva
2. La marca no se puede modificar (campo de solo lectura)
3. Se pueden editar:
   - Nombre y descripción
   - OLTs asociadas (usando el selector dual)
   - OID consultado (filtrado por la marca)
   - Intervalo de ejecución
   - Tipo de consulta
   - Estado (habilitado/deshabilitado)
4. Los selectores de OLTs y OID:
   - Muestran las opciones filtradas por la marca existente
   - Mantienen las selecciones actuales
   - Permiten agregar/quitar elementos
5. Al guardar:
   - Se actualizan los campos modificados
   - Se mantienen las relaciones con OLTs
   - Se redirige a la lista con mensaje de éxito

### Historial y Ejecuciones
El historial de ejecuciones y detalles técnicos se muestran en una vista separada:
1. Información de ejecución
   - Última ejecución exitosa/fallida por OLT
   - Estado y resultados
   - Errores si los hubo
2. Datos técnicos
   - Nombre descriptivo del OID
   - Valor del OID
   - Tipo de dato esperado

## Comportamiento del Formulario

### Carga Inicial
1. Se cargan todas las marcas disponibles
2. El selector de OLTs y la lista de OIDs están vacíos hasta que se seleccione una marca

### Al Seleccionar Marca
1. Se cargan las OLTs habilitadas de esa marca
2. Se cargan los OIDs compatibles con esa marca
3. Se actualiza el selector dual de OLTs y la lista de OIDs

### Validaciones
1. El nombre es requerido y debe ser único
2. El intervalo debe tener el formato correcto
3. Debe seleccionarse al menos una OLT
4. Debe seleccionarse un OID

### Guardado
1. Se crea el registro en `snmp_jobs`
2. Se crean los registros en `snmp_job_hosts` para cada OLT seleccionada

## Consideraciones Técnicas

### Widgets
- Se usa el widget `FilteredSelectMultiple` nativo de Django Admin para OLTs
- Se usa el widget `Select` estándar para OID y otros campos de selección única

### JavaScript
- La carga dinámica de OLTs y OIDs se maneja mediante AJAX
- Los endpoints retornan datos en formato JSON
- Se mantiene el estado de selección al recargar los datos

### Permisos
- Solo accesible para usuarios staff/admin
- Se requiere autenticación
- Se verifica permisos de creación/edición



### Notas de Implementación

1. Vista de Lista (`/admin/snmp_jobs/snmpjob/`):
   - Usa el template estándar de Django Admin con estilos personalizados
   - Los campos se muestran usando `list_display` en el ModelAdmin
   - Los métodos `get_olts_count` y `get_oid_display` formatean los datos
   - Los estilos CSS mejoran la presentación y legibilidad

2. Vista de Edición (`/admin/snmp_jobs/snmpjob/<id>/change/`):
   - Usa el mismo template que la vista de creación
   - La marca se muestra como campo de solo lectura
   - Los selectores de OLTs y OID se filtran por la marca existente
   - Se preservan las selecciones actuales al cargar el formulario

3. Vista de Creación (`/admin/snmp_jobs/snmpjob/programar-tarea/`):
   - Formulario personalizado con campos específicos
   - Selectores dinámicos que se actualizan según la marca
   - Validaciones en el backend antes de guardar
   - Redirección a la lista tras guardar exitosamente
