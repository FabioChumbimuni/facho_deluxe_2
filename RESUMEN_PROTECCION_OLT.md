# ✅ PROTECCIÓN OLT: Cambio Mínimo al Modelo Pollers Zabbix

## 🎯 Objetivo

Agregar **solo la condición de "1 nodo a la vez por OLT"** sin cambiar el resto del sistema.

## ✅ Respuesta: SÍ, es posible y NO cambia el funcionamiento normal

### Cambios Requeridos

**Solo se modifica `PollerManager.assign_node()`** agregando una verificación:

```python
def assign_node(self, node: 'Node'):
    # ✅ AGREGAR: Verificar si OLT ya tiene un nodo ejecutándose
    olt_id = node.workflow.olt_id
    if self.is_olt_busy(olt_id):
        # OLT ocupada, encolar (NO ejecutar simultáneamente)
        self.queue.put(node)
        return
    
    # ✅ RESTO DEL CÓDIGO NO CAMBIA
    poller = self.get_free_poller()
    if poller:
        thread = Thread(target=poller.execute_node, args=(node,))
        thread.start()
    else:
        self.queue.put(node)

def is_olt_busy(self, olt_id: int) -> bool:
    """Verificar si OLT tiene un nodo ejecutándose"""
    from executions.models import Execution
    return Execution.objects.filter(
        olt_id=olt_id,
        status__in=['RUNNING', 'PENDING']
    ).exists()
```

### Lo que NO cambia

✅ **Scheduler funciona igual**:
- Identifica nodos listos cada 1 segundo
- Calcula delay
- Marca como delayed si delay > interval
- Envía a cola o asigna a poller

✅ **Pollers funcionan igual**:
- Ejecutan nodos normalmente
- Actualizan lastcheck, nextcheck
- Calculan métricas (busy %, etc.)

✅ **Cola funciona igual**:
- FIFO con priorización
- Sin duplicados
- Detección de overload

✅ **Cálculo de nextcheck igual**:
- `nextcheck = now + interval` (después de ejecutar)
- Sin compensación de atrasos
- Sin anticipación

### Lo que SÍ cambia

✅ **Solo se agrega**:
- Verificación `is_olt_busy(olt_id)` antes de asignar
- Si OLT ocupada → encolar (no ejecutar simultáneamente)
- Si OLT libre → funciona normal

## 📊 Comparativa: Antes vs Después

### Antes (Sin Protección)
```
Scheduler identifica 5 nodos de OLT-1 listos
→ PollerManager asigna los 5 nodos a 5 pollers diferentes
→ 5 consultas SNMP simultáneas a OLT-1
→ ⚠️ OLT puede saturarse
```

### Después (Con Protección)
```
Scheduler identifica 5 nodos de OLT-1 listos
→ PollerManager verifica: is_olt_busy(OLT-1) = False
→ Asigna primer nodo a poller libre
→ PollerManager verifica: is_olt_busy(OLT-1) = True
→ Encola los otros 4 nodos
→ Cuando termina primer nodo, procesa siguiente de cola
→ ✅ Solo 1 consulta SNMP a la vez por OLT
```

## 🔄 Flujo Completo

```
1. SCHEDULER (cada 1 segundo):
   ├─ Identifica nodos con nextcheck <= now
   ├─ Calcula delay
   ├─ Marca como delayed si delay > interval
   └─ Llama a poller_manager.assign_node(node)

2. POLLER MANAGER.assign_node():
   ├─ ✅ NUEVO: Verifica is_olt_busy(olt_id)
   │   SI True → Encolar y RETORNAR
   │   SI False → Continuar
   ├─ Verifica pollers libres
   ├─ Asigna nodo a poller libre
   └─ Si no hay poller libre → Encolar

3. POLLER.execute_node():
   ├─ Ejecuta función del nodo (NO CAMBIA)
   ├─ Actualiza lastcheck, nextcheck (NO CAMBIA)
   └─ Libera poller (NO CAMBIA)

4. COLA:
   ├─ Almacena nodos pendientes (NO CAMBIA)
   └─ Cuando poller se libera, procesa siguiente (NO CAMBIA)
```

## ✅ Conclusión

**SÍ, se puede agregar solo esta condición sin cambiar el resto del sistema.**

- ✅ **Cambio mínimo**: Solo 1 función nueva (`is_olt_busy`) y 1 verificación en `assign_node`
- ✅ **No afecta funcionamiento normal**: Todo lo demás funciona igual
- ✅ **Protección automática**: Evita saturación de OLTs sin configuración manual
- ✅ **Compatible con modelo Zabbix**: Mantiene toda la lógica original

**El sistema funciona exactamente igual, solo agrega la protección de OLT.**

