# 📁 Archivos Legacy - Sistema de Fórmulas SNMP

## 📋 Descripción

Esta carpeta contiene archivos que fueron reemplazados por el **sistema de fórmulas SNMP configurables** pero que se mantienen como **fallback** para casos especiales o compatibilidad.

---

## 📄 Archivos en esta carpeta

### `huawei_calculations.py`
- **Descripción**: Lógica hardcoded para cálculos de índices SNMP de Huawei
- **Estado**: **LEGACY** - Reemplazado por sistema de fórmulas configurables
- **Uso actual**: Solo como **fallback** cuando no hay fórmulas configuradas
- **Reemplazado por**: `snmp_formulas.models.IndexFormula`

---

## 🔄 Migración al Sistema de Fórmulas

### **Antes** (hardcoded):
```python
# En huawei_calculations.py
def calculate_huawei_components(raw_index_key: str):
    # Lógica hardcoded para Huawei
    return {'slot': slot, 'port': port, 'onu_id': onu_id}
```

### **Ahora** (configurable):
```python
# En snmp_formulas.models.IndexFormula
def calculate_components(self, raw_index_key: str):
    # Lógica configurable por marca/modelo
    return {'slot': slot, 'port': port, 'logical': logical}
```

---

## 🎯 Lógica de Fallback

### **Prioridad de Uso**:

1. **🥇 PRIORIDAD 1**: Fórmula específica por marca + modelo
   - Usa: `IndexFormula.objects.get(marca=olt.marca, modelo=olt.modelo)`

2. **🥈 PRIORIDAD 2**: Fórmula genérica por marca
   - Usa: `IndexFormula.objects.get(marca=olt.marca, modelo=None)`

3. **🥉 PRIORIDAD 3**: Fórmula universal
   - Usa: `IndexFormula.objects.get(marca=None, modelo=None)`

4. **🔄 FALLBACK**: Código legacy
   - Usa: `huawei_calculations.py` (solo para Huawei)

---

## ⚠️ Notas Importantes

### **¿Cuándo se usa el fallback?**
- Solo cuando **no hay ninguna fórmula** configurada en la BD
- Solo para **marcas Huawei** (otras marcas sin fórmulas = UNKNOWN)
- Como **último recurso** para mantener compatibilidad

### **¿Se puede eliminar?**
- **NO recomendado** hasta que todas las OLTs tengan fórmulas configuradas
- **SÍ se puede** una vez que el sistema esté completamente migrado

---

## 🚀 Ventajas del Sistema Nuevo

| Característica | Legacy (hardcoded) | Nuevo (configurable) |
|----------------|-------------------|---------------------|
| **Flexibilidad** | ❌ Solo Huawei | ✅ Cualquier marca |
| **Configuración** | ❌ Código hardcoded | ✅ Base de datos |
| **Mantenimiento** | ❌ Modificar código | ✅ Admin interface |
| **Escalabilidad** | ❌ Limitado | ✅ Ilimitado |
| **Testing** | ❌ Manual | ✅ Automático |

---

## 📊 Estado de Migración

### **Completamente Migrado** ✅
- ✅ **Huawei MA5800**: Fórmula específica configurada
- ✅ **Huawei MA5680T**: Fórmula específica configurada
- ✅ **ZTE**: Fórmula genérica configurada
- ✅ **Universal**: Fórmula universal configurada

### **Fallback Disponible** ✅
- ✅ **Huawei sin fórmulas**: Usa `huawei_calculations.py`
- ✅ **Compatibilidad**: Sistema existente sigue funcionando

---

## 🔧 Mantenimiento

### **Para el Administrador**:
- **No modificar** archivos en esta carpeta
- **Usar** el sistema de fórmulas en su lugar
- **Configurar** nuevas fórmulas desde el admin

### **Para el Desarrollador**:
- **No agregar** nuevos archivos legacy
- **Migrar** lógica hardcoded a fórmulas configurables
- **Eliminar** referencias cuando sea seguro

---

## 📞 Soporte

**Sistema Principal**:
```
http://127.0.0.1:8000/admin/snmp_formulas/indexformula/
```

**Documentación**:
- `/opt/facho_deluxe_v2/SISTEMA_COMPLETO_IMPLEMENTADO.md`
- `/opt/facho_deluxe_v2/LOGICA_PRIORIDAD_FORMULAS_COMPLETA.md`

**Scripts de Verificación**:
```bash
python verificar_formulas.py
python verificar_logica_prioridad.py
```

---

## 🎉 Conclusión

Los archivos en esta carpeta son **legacy** y se mantienen solo para **compatibilidad**. El sistema principal ahora usa **fórmulas configurables** que son más flexibles, mantenibles y escalables.

**Recomendación**: Usar siempre el sistema de fórmulas configurables para nuevos desarrollos. 🚀
