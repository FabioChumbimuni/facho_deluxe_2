# 🚨 Lista de Errores Zabbix ODF Management

## 🔴 **Error 1: Puerto Presente en Zabbix Sin Estado Administrativo**

### **Código de Error:** `Error 1`
### **Color:** Rojo
### **Severidad:** High

### **Descripción:**
Puerto presente en Zabbix pero sin estado administrativo.

### **Condiciones:**
- `obj.en_zabbix = True`
- `obj.zabbix_port` existe
- `obj.zabbix_port.estado_administrativo` es `None` o `0`

### **Ubicación en Código:**
**Archivo:** `odf_management/admin.py` (línea 872)

### **Causas Comunes:**
1. Item Master incompleto (falta OID `.1.3.6.1.2.1.2.2.1.7`)
2. Problemas de conectividad SNMP
3. Errores de parsing en `zabbix_service.py`
4. Puerto creado manualmente sin estado

### **Acceso a Logs:**
```bash
# Log principal de sincronización Zabbix
tail -f celery_odf_final.log

# Buscar errores específicos
grep "estado_administrativo" celery_odf_final.log
grep "Error parseando" celery_odf_final.log
grep "Error procesando puerto" celery_odf_final.log
```

### **Comando de Diagnóstico:**
```python
from odf_management.models import ODFHilos

# Verificar hilo específico
hilo = ODFHilos.objects.get(id=X)
print(f"en_zabbix: {hilo.en_zabbix}")
print(f"zabbix_port: {hilo.zabbix_port}")
if hilo.zabbix_port:
    print(f"estado_administrativo: {hilo.zabbix_port.estado_administrativo}")

# Contar hilos con Error 1
error_1_count = ODFHilos.objects.filter(
    en_zabbix=True,
    zabbix_port__isnull=False,
    zabbix_port__estado_administrativo__isnull=True
).count()
print(f"Hilos con Error 1: {error_1_count}")
```

### **Solución Rápida:**
```python
from odf_management.tasks import sync_single_olt_ports
from hosts.models import OLT

# Ejecutar sincronización manual
olt = OLT.objects.get(abreviatura='NOMBRE_OLT')
result = sync_single_olt_ports(olt.id)
```

---

## 📝 **Próximos Errores a Documentar**

- **Error 2:** [Por definir]
- **Error 3:** [Por definir]
- **Error 4:** [Por definir]

---

## 🔧 **Logs Relevantes**

- `celery_odf_final.log` - Logs de sincronización Zabbix
- `celery_beat_new.log` - Logs de programación de tareas
- Django Admin logs - Logs de cambios manuales