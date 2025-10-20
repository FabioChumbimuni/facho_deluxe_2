# Tablas que se Llenan cuando una Tarea de Descubrimiento es SUCCESS

## 🎯 **Condiciones para SUCCESS**

Una tarea de descubrimiento se marca como **SUCCESS** cuando:

1. **El SNMP Walk se ejecuta correctamente** (sin errores de conexión)
2. **La OLT está habilitada** (`olt.habilitar_olt = True`)
3. **El job_host está habilitado** (`job_host.enabled = True`)
4. **No hay errores críticos** en la ejecución

## 📊 **Tablas que se Llenan/Actualizan**

### **1. Tabla `onu_index_map`**
**Propósito**: Mapea índices crudos SNMP a componentes normalizados

**Campos que se llenan**:
- `olt_id`: ID de la OLT
- `raw_index_key`: Índice crudo del SNMP (ej: "4194312192.2")
- `slot`: Slot de la OLT (si se puede calcular)
- `port`: Puerto de la OLT (si se puede calcular)
- `logical`: Puerto lógico (si se puede calcular)
- `normalized_id`: ID normalizado (ej: "OLT17-4194312192.2")
- `marca_formula`: Fórmula de descomposición por marca
- `created_at`: Timestamp de creación
- `updated_at`: Timestamp de actualización

**Lógica**: Se crea un registro por cada índice único encontrado en el walk

### **2. Tabla `onu_status`**
**Propósito**: Estado actual de cada ONU (sin histórico)

**Campos que se llenan**:
- `onu_index_id`: FK a `onu_index_map`
- `olt_id`: FK a la OLT
- `last_seen_at`: Última vez que se vio la ONU
- `last_state_value`: Valor del estado (1=ACTIVO, 2=SUSPENDIDO)
- `last_state_label`: Etiqueta del estado (ACTIVO/SUSPENDIDO)
- `presence`: ENABLED/DISABLED
- `consecutive_misses`: Contador de ausencias consecutivas
- `last_change_execution_id`: FK a la ejecución que causó el cambio
- `updated_at`: Timestamp de actualización

**Lógica**: 
- Si la ONU aparece en el walk → `presence = ENABLED`, `consecutive_misses = 0`
- Si la ONU no aparece → `consecutive_misses += 1`
- Si `consecutive_misses >= 2` → `presence = DISABLED`


Esta parte sino aparece que aparezca disabled, si aparece enable. Basta que con que no aparezca una vez para deshabilitarlo


### **3. Tabla `onu_inventory`**
**Propósito**: Registro maestro de cada ONU (datos estáticos)

**Campos que se llenan**:
- `onu_index_id`: FK a `onu_index_map` (único)
- `olt_id`: FK a la OLT
- `serial_number`: Número de serie (NULL inicialmente)
- `mac_address`: Dirección MAC (NULL inicialmente)
- `subscriber_id`: ID del suscriptor (NULL inicialmente)
- `snmp_description`: Descripción SNMP (NULL inicialmente)
- `snmp_metadata`: Metadatos adicionales (JSON)
- `snmp_last_collected_at`: Última recolección de datos
- `snmp_last_execution_id`: FK a la ejecución
- `active`: Bandera administrativa (default: True)
- `created_at`: Timestamp de creación
- `updated_at`: Timestamp de actualización

**Lógica**: Se crea un registro maestro por cada ONU nueva encontrada

### **4. Tabla `onu_state_lookup`**
**Propósito**: Mapeo de valores numéricos a etiquetas por marca El snmpindex, type job y OLT traen la marca de ahi puedes sacarlo

**Campos que se llenan**:
- `value`: Valor numérico (1, 2, etc.)
- `label`: Etiqueta (ACTIVO, SUSPENDIDO, etc.)
- `description`: Descripción del estado
- `marca_id`: FK a la marca (opcional) ojo no confundirla marca de la ONU PUEDE ser diferente a la OLT

**Lógica**: Se crean registros de lookup para mapear estados

## 🔄 **Flujo de Procesamiento**

### **Fase 1: SNMP Walk**
1. Ejecutar walk sobre el OID configurado
2. Guardar resultados en memoria (sin procesar)
3. Marcar `walk_successful = True` si no hay errores

### **Fase 2: Procesamiento (Solo si SUCCESS)**
1. **Crear/Actualizar `onu_index_map`**:
   - Por cada resultado del walk
   - Intentar descomponer índice por fórmula de marca
   - Generar `normalized_id` único

2. **Crear/Actualizar `onu_inventory`**:
   - Un registro maestro por ONU
   - Campos de descripción inicialmente NULL
   - `active = True` por defecto

3. **Actualizar `onu_status`**:
   - ONUs encontradas → `presence = ENABLED`
   - ONUs no encontradas → incrementar `consecutive_misses`
   - Si `consecutive_misses >= 2` → `presence = DISABLED`

4. **Crear `onu_state_lookup`**:
   - Mapear valores numéricos a etiquetas
   - Por marca si es necesario

## ⚠️ **Casos Especiales**

### **Walk con 0 resultados**
- **SUCCESS**: Sí (walk técnicamente funcionó)
- **Tablas**: No se llenan (no hay datos que procesar)
- **Causa**: OLT sin ONUs o OID incorrecto

### **OLT Deshabilitada**
- **SUCCESS**: No (se marca como FAILED)
- **Tablas**: No se llenan
- **Causa**: `olt.habilitar_olt = False`

### **Errores SNMP**
- **SUCCESS**: No (se marca como FAILED)
- **Tablas**: No se llenan
- **Causa**: Timeout, comunidad incorrecta, etc.

## 📈 **Métricas Registradas**

En `snmp_executions.result_summary`:
- `walk_successful`: Boolean
- `total_found`: Número de ONUs encontradas
- `enabled_count`: ONUs marcadas como ENABLED
- `disabled_count`: ONUs marcadas como DISABLED
- `new_index_created`: Nuevos índices creados
- `errors`: Lista de errores
- `duration_ms`: Duración en milisegundos

## 🎯 **Resumen**

**Para que se llenen las tablas**:
1. ✅ Tarea debe ser SUCCESS
2. ✅ Walk debe devolver resultados > 0
3. ✅ OLT debe estar habilitada
4. ✅ Job_host debe estar habilitado

**Si alguna condición falla**:
- ❌ Tablas no se llenan
- ❌ Tarea se marca como FAILED
- ❌ Solo se registra el error en `snmp_executions`









TENER EN CUENTA QUE LOS SNMPINDEXONU tiene marca


ahora los equipos conectados ahi puede que no pero eso se vera mas adelante, ahora priorizar que se llene las tablas