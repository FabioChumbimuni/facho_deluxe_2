# ⚙️ Configuración de Zabbix - Sistema Integrado

## ✅ Resumen Ejecutivo

Se ha creado un **sistema de configuración centralizado para Zabbix** que permite administrar desde el Django Admin la conexión con Zabbix, el item master a usar y la fórmula SNMP para calcular slot/port desde índices SNMP.

---

## 🎯 Características Principales

### **1. Configuración Centralizada** ✅
- ✅ **URL de Zabbix**: Configurable desde el admin
- ✅ **Token de autenticación**: Almacenado de forma segura
- ✅ **Item master**: Clave del item que contiene el SNMP walk completo
- ✅ **Fórmula SNMP**: Selección de la fórmula a usar para calcular componentes

### **2. Una Sola Configuración Activa** ✅
- ⚠️ **Validación automática**: Solo puede haber una configuración activa
- ✅ **Cambio fácil**: Activar/desactivar desde el admin
- ✅ **Sin código**: Todo desde la interfaz administrativa

### **3. Integración con Fórmulas SNMP** ✅
- ✅ **FK a IndexFormula**: Selección de fórmula desde el admin
- ✅ **Uso automático**: `ZabbixService` usa la fórmula configurada
- ✅ **Sin hardcodeo**: No más código hardcodeado en `zabbix_service.py`

---

## 📊 Modelo de Datos

### **Tabla: `zabbix_configuration`**

```sql
CREATE TABLE zabbix_configuration (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    zabbix_url VARCHAR(255) NOT NULL,
    zabbix_token VARCHAR(255) NOT NULL,
    item_key VARCHAR(100) DEFAULT 'port.descover.walk',
    formula_snmp_id INT NOT NULL REFERENCES index_formulas(id),
    activa BOOLEAN DEFAULT TRUE,
    timeout INT DEFAULT 30,
    verificar_ssl BOOLEAN DEFAULT TRUE,
    descripcion TEXT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX zabbix_config_activa_idx ON zabbix_configuration(activa);
CREATE INDEX zabbix_config_nombre_idx ON zabbix_configuration(nombre);
```

### **Campos Principales**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| **nombre** | VARCHAR(100) | Nombre identificador de la configuración |
| **zabbix_url** | VARCHAR(255) | URL completa de la API de Zabbix |
| **zabbix_token** | VARCHAR(255) | Token de autenticación |
| **item_key** | VARCHAR(100) | Clave del item master (default: `port.descover.walk`) |
| **formula_snmp_id** | FK | Fórmula SNMP para calcular slot/port |
| **activa** | BOOLEAN | Solo una puede estar activa |
| **timeout** | INT | Timeout para peticiones (segundos) |
| **verificar_ssl** | BOOLEAN | Verificar certificados SSL |

---

## 🎨 Admin Interface

### **URL del Admin** ✅
```
http://127.0.0.1:8000/admin/zabbix_config/zabbixconfiguration/
```

### **Características del Admin**

#### **1. List Display** ✅
- ✅ **Nombre**: Identificador de la configuración
- ✅ **Estado**: Badge visual (✅ ACTIVA / ⏸️ Inactiva)
- ✅ **Fórmula**: Muestra fórmula con marca y modelo
- ✅ **Item Key**: Clave del item master
- ✅ **URL**: URL de Zabbix (compacta)
- ✅ **Actualizado**: Fecha de última modificación

#### **2. Fieldsets Organizados** ✅

**Información Básica**:
- Nombre
- Descripción
- Estado activa

**Conexión a Zabbix**:
- URL de Zabbix
- Token de autenticación
- Timeout
- Verificar SSL

**Configuración de Datos**:
- Item key
- Fórmula SNMP (autocomplete)

**Metadatos** (colapsado):
- created_at
- updated_at

#### **3. Acciones Disponibles** ✅

**✅ Activar configuración**:
- Activa la configuración seleccionada
- Desactiva automáticamente las demás
- Requiere seleccionar exactamente una

**⏸️ Desactivar configuraciones**:
- Desactiva las configuraciones seleccionadas
- Permite seleccionar múltiples

**🔍 Probar conexión**:
- Prueba la conexión con Zabbix
- Obtiene versión de Zabbix como verificación
- Muestra resultado en mensaje

---

## 🚀 Uso en el Código

### **Antes** (hardcodeado):
```python
# En zabbix_service.py
from legacy_files.huawei_calculations import calculate_huawei_components

# Buscar fórmula hardcodeada
huawei = Brand.objects.get(nombre='Huawei')
formula = IndexFormula.objects.filter(
    marca=huawei,
    modelo__isnull=True,
    activo=True
).first()

components = calculate_huawei_components(snmp_index)
```

### **Ahora** (configurable):
```python
# En zabbix_service.py
def _get_configured_formula(self):
    """
    Obtiene la fórmula SNMP configurada en la configuración activa de Zabbix.
    """
    from zabbix_config.models import ZabbixConfiguration
    
    config = ZabbixConfiguration.get_active_config()
    
    if config and config.formula_snmp:
        return config.formula_snmp
    return None

# Uso en _parse_interface_description
formula = self._get_configured_formula()
components = formula.calculate_components(snmp_index)
```

### **Obtener Configuración Activa**
```python
from zabbix_config.models import ZabbixConfiguration

# Método 1: Usando método de clase
config = ZabbixConfiguration.get_active_config()

# Método 2: Usando queryset
config = ZabbixConfiguration.objects.filter(activa=True).first()

# Acceder a los datos
if config:
    url = config.zabbix_url
    token = config.zabbix_token
    item_key = config.item_key
    formula = config.formula_snmp
    
    # Crear servicio de Zabbix
    zabbix_service = config.get_service()
```

---

## 🔧 Configuración Inicial

### **Configuración Por Defecto** ✅

Se crea automáticamente durante las migraciones:

```python
{
    'nombre': 'Configuración Principal',
    'zabbix_url': 'http://localhost/zabbix/api_jsonrpc.php',
    'zabbix_token': 'INSERTAR_TOKEN_AQUI',
    'item_key': 'port.descover.walk',
    'formula_snmp': <Fórmula Huawei genérica o Universal>,
    'activa': True,
    'timeout': 30,
    'verificar_ssl': True
}
```

### **Pasos para Configurar**

1. **Ir al Admin**:
   ```
   http://127.0.0.1:8000/admin/zabbix_config/zabbixconfiguration/
   ```

2. **Editar configuración**:
   - Actualizar `zabbix_url` con la URL correcta
   - Actualizar `zabbix_token` con el token válido
   - Verificar `item_key` (default: `port.descover.walk`)
   - Seleccionar `formula_snmp` adecuada

3. **Probar conexión**:
   - Seleccionar la configuración
   - Ejecutar acción "🔍 Probar conexión con Zabbix"
   - Verificar mensaje de éxito

4. **Activar**:
   - Si la configuración está inactiva, ejecutar "✅ Activar configuración"

---

## 🎯 Validaciones

### **1. Una Sola Configuración Activa** ✅

```python
def clean(self):
    """Validación: Solo una configuración puede estar activa"""
    if self.activa:
        existing_active = ZabbixConfiguration.objects.filter(
            activa=True
        ).exclude(pk=self.pk)
        
        if existing_active.exists():
            raise ValidationError(
                'Ya existe una configuración activa. '
                'Desactiva la configuración actual antes de activar otra.'
            )
```

**Resultado**:
- ❌ **Error**: Si intentas activar dos configuraciones simultáneamente
- ✅ **OK**: Si usas la acción "Activar configuración" (desactiva automáticamente las demás)

### **2. Fórmula Requerida** ✅

- ⚠️ El campo `formula_snmp` es obligatorio
- ✅ Se valida en el modelo con `on_delete=models.PROTECT`
- ✅ No se puede eliminar una fórmula si está en uso

---

## 📋 Ejemplos de Uso

### **Ejemplo 1: Configuración para Huawei**

```python
{
    'nombre': 'Zabbix - Huawei',
    'zabbix_url': 'http://zabbix.example.com/api_jsonrpc.php',
    'zabbix_token': 'abc123...',
    'item_key': 'port.descover.walk',
    'formula_snmp': <Fórmula Huawei Genérica>,
    'activa': True
}
```

### **Ejemplo 2: Configuración para ZTE**

```python
{
    'nombre': 'Zabbix - ZTE',
    'zabbix_url': 'http://zabbix.example.com/api_jsonrpc.php',
    'zabbix_token': 'abc123...',
    'item_key': 'port.descover.walk',
    'formula_snmp': <Fórmula ZTE Genérica>,
    'activa': True
}
```

### **Ejemplo 3: Configuración Universal**

```python
{
    'nombre': 'Zabbix - Universal',
    'zabbix_url': 'http://zabbix.example.com/api_jsonrpc.php',
    'zabbix_token': 'abc123...',
    'item_key': 'port.descover.walk',
    'formula_snmp': <Fórmula Universal>,
    'activa': True
}
```

---

## 🧪 Testing

### **Probar Conexión con Zabbix**

```python
from zabbix_config.models import ZabbixConfiguration

config = ZabbixConfiguration.get_active_config()

if config:
    # Obtener servicio de Zabbix
    zabbix_service = config.get_service()
    
    # Probar conexión
    result = zabbix_service._make_request("apiinfo.version", {})
    
    if result:
        print(f"✅ Conexión exitosa. Versión Zabbix: {result}")
    else:
        print("❌ Error de conexión")
```

### **Verificar Fórmula Configurada**

```python
from zabbix_config.models import ZabbixConfiguration

config = ZabbixConfiguration.get_active_config()

if config and config.formula_snmp:
    print(f"✅ Fórmula configurada: {config.formula_snmp}")
    print(f"   Marca: {config.formula_snmp.marca}")
    print(f"   Modelo: {config.formula_snmp.modelo}")
else:
    print("⚠️ No hay configuración activa o no tiene fórmula")
```

---

## 🎉 Ventajas del Sistema

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **URL Zabbix** | ❌ Hardcodeada en código | ✅ Configurable desde admin |
| **Token** | ❌ En código o settings | ✅ En BD, seguro |
| **Item Master** | ❌ Hardcodeado | ✅ Configurable |
| **Fórmula SNMP** | ❌ Hardcodeada | ✅ Seleccionable desde admin |
| **Cambios** | ❌ Modificar código | ✅ Solo admin, sin código |
| **Testing** | ❌ Manual | ✅ Acción "Probar conexión" |
| **Múltiples ambientes** | ❌ Difícil | ✅ Crear múltiples configs |

---

## 📞 Soporte

### **Admin URLs**
```
Configuración Zabbix: http://127.0.0.1:8000/admin/zabbix_config/zabbixconfiguration/
Fórmulas SNMP: http://127.0.0.1:8000/admin/snmp_formulas/indexformula/
```

### **Documentación Relacionada**
- `/opt/facho_deluxe_v2/SISTEMA_COMPLETO_IMPLEMENTADO.md`
- `/opt/facho_deluxe_v2/LOGICA_PRIORIDAD_FORMULAS_COMPLETA.md`
- `/opt/facho_deluxe_v2/db_diagram.md`

### **Modelos Relacionados**
- `zabbix_config.ZabbixConfiguration` - Configuración de Zabbix
- `snmp_formulas.IndexFormula` - Fórmulas SNMP
- `odf_management.services.ZabbixService` - Servicio de Zabbix

---

## 🎯 Resumen

**El sistema de configuración de Zabbix está completamente implementado**:

1. ✅ **Modelo creado**: `ZabbixConfiguration` con todos los campos
2. ✅ **Admin funcional**: Con acciones y validaciones
3. ✅ **Integración completa**: `ZabbixService` usa configuración de BD
4. ✅ **Configuración inicial**: Creada automáticamente
5. ✅ **Sin hardcodeo**: URL, token, item y fórmula configurables
6. ✅ **Validaciones**: Solo una configuración activa
7. ✅ **Testing**: Acción "Probar conexión" disponible

**¡Todo configurable desde el Django Admin sin tocar código!** 🚀
