# 📊 Consumo de Pollers: Zabbix vs Nuestro Sistema

## 🔍 Configuración en Zabbix

### Ubicación
**Archivo**: `/etc/zabbix/zabbix_server.conf` (o `/usr/local/etc/zabbix_server.conf`)

### Parámetro Principal
```ini
StartPollers=20
```

Este parámetro define cuántos procesos de poller se ejecutan simultáneamente.

### Otros Parámetros Relacionados
```ini
StartPollers=20          # Pollers generales
StartPollersUnreachable=5  # Pollers para hosts inalcanzables
StartTrappers=5          # Trappers (agentes activos)
StartPingers=1          # Pollers ICMP
StartDiscoverers=1       # Descubridores
StartHTTPPollers=1      # Pollers HTTP
```

## 💾 Consumo de Recursos de un Poller

### Memoria
- **Por proceso**: ~10-50 MB (depende de la carga)
- **Base**: ~10-15 MB por proceso
- **Con carga**: Puede llegar a 30-50 MB si procesa muchos items

### CPU
- **Idle**: < 1% CPU
- **Activo**: 5-15% CPU por poller (depende de frecuencia de checks)
- **Saturado**: Puede llegar a 20-30% si procesa muchos items simultáneamente

### Ejemplo de Cálculo
```
10 pollers × 20 MB = ~200 MB RAM
10 pollers × 10% CPU = ~100% CPU (1 core completo)
```

**Nota**: Los pollers son procesos ligeros, pero el consumo total depende de:
- Cantidad de items monitoreados
- Frecuencia de checks (intervalos)
- Complejidad de los checks (SNMP, HTTP, scripts, etc.)

## ⚙️ Configuración en Nuestro Sistema

### Ubicación
**Archivo**: `/opt/facho_deluxe_2/zabbix_pollers/tasks.py`

### Valor Actual
```python
_poller_manager = PollerManager(start_pollers=10)  # Línea 20
```

**Por defecto: 10 pollers**

### Cómo Cambiar
Editar `zabbix_pollers/tasks.py`:
```python
def get_poller_manager():
    """Obtener instancia singleton del PollerManager"""
    global _poller_manager
    if _poller_manager is None:
        from .poller_manager import PollerManager
        _poller_manager = PollerManager(start_pollers=15)  # Cambiar aquí
    return _poller_manager
```

## 📊 Comparativa: Zabbix vs Nuestro Sistema

| Aspecto | Zabbix | Nuestro Sistema |
|---------|--------|----------------|
| **Configuración** | `zabbix_server.conf` → `StartPollers=20` | `tasks.py` → `start_pollers=10` |
| **Tipo** | Procesos del sistema | Threads Python (más ligeros) |
| **Memoria por poller** | ~10-50 MB | ~5-20 MB (threads) |
| **CPU por poller** | 5-15% | 3-10% (más eficiente) |
| **Consumo total (10 pollers)** | ~200-500 MB RAM | ~50-200 MB RAM |
| **Recomendación uso** | > 75% busy → aumentar | > 75% busy → aumentar |

## 🎯 Recomendaciones

### Para Nuestro Sistema

1. **Inicio Conservador**: 10 pollers (actual)
   - Adecuado para ~20 OLTs con intervalos de 15 minutos
   - Consumo estimado: ~100-200 MB RAM, ~50-100% CPU

2. **Carga Media**: 15-20 pollers
   - Para ~30-40 OLTs con intervalos variados
   - Consumo estimado: ~150-400 MB RAM, ~75-150% CPU

3. **Carga Alta**: 25-30 pollers
   - Para ~50+ OLTs con intervalos cortos (5-10 min)
   - Consumo estimado: ~250-600 MB RAM, ~125-300% CPU

### Monitoreo

**Métricas a observar**:
- `busy_percentage > 75%` → Aumentar pollers
- `queue_size > (start_pollers * 2)` → Aumentar pollers
- `tasks_delayed` creciendo → Aumentar pollers

**API para monitorear**:
```bash
curl -H "Authorization: Token TU_TOKEN" \
  http://192.168.56.222:8000/api/v1/pollers/stats/
```

## 🔧 Ajuste Dinámico

### Actualmente
El número de pollers es **fijo** al iniciar el sistema.

### Futuro (Opcional)
Se podría implementar ajuste dinámico basado en:
- `busy_percentage`
- `queue_size`
- `tasks_delayed`

Pero por ahora, **10 pollers es un buen punto de partida**.

## 📝 Notas Importantes

1. **Pollers son Threads, no Procesos**
   - Más ligeros que procesos de Zabbix
   - Comparten memoria del proceso Python
   - Menor overhead de creación/destrucción

2. **Protección OLT**
   - Solo 1 nodo a la vez por OLT
   - Esto limita el paralelismo real
   - 10 pollers pueden manejar 10 OLTs simultáneamente

3. **Pollers Internos Separados**
   - `get_poller_task` usa sus propios workers de Celery
   - NO se combinan con pollers del sistema
   - No afectan el consumo de nuestros pollers

## 🎯 Conclusión

**Configuración Actual**:
- **10 pollers** (configurable en `tasks.py`)
- **Consumo estimado**: ~100-200 MB RAM, ~50-100% CPU
- **Adecuado para**: ~20 OLTs con intervalos normales

**Para ajustar**:
1. Monitorear `GET /api/v1/pollers/stats/`
2. Si `busy_percentage > 75%` → Aumentar en `tasks.py`
3. Reiniciar worker `celery_zabbix_scheduler`

