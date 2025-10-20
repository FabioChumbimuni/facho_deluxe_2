# SNMP GET - Sistema de Pollers

## Configuración desde Admin

**Administrar configuración GET**:
```
http://127.0.0.1:8000/admin/configuracion_avanzada/configuracionsnmp/
```

### Configuraciones por Tipo

| Tipo | Timeout | Reintentos | Pollers | Lote | Semáforo |
|------|---------|------------|---------|------|----------|
| descubrimiento | 10s | 0 | N/A | N/A | N/A |
| **get** | 5s | 2 | 10 | 200 | 5 |

## Ejemplo: 5000 ONUs

```
División: 5000 / 200 = 25 lotes
Simultáneos: 10 pollers (MAX)
Subdivisión: 200 → 50 → 1 (si falla)
Carga OLT: 10 × 5 = 50 consultas SNMP máximo
```

## Uso Rápido

```bash
# 1. Iniciar workers
./start_celery_get_workers.sh

# 2. Crear tarea GET en admin
# 3. Monitorear
tail -f logs/celery-get_poller.log
```

## Ajustar Configuración

Admin → Config GET Predeterminada → Modificar:
- `max_pollers_por_olt`: 10 (estándar) a 5 (conservador) o 15 (agresivo)
- `max_consultas_snmp_simultaneas`: 5 (seguro) a 3 (lenta) o 8 (rápida)
- `tamano_lote_inicial`: 200 (óptimo) a 100 (conservador) o 300 (agresivo)

**Los cambios aplican inmediatamente** sin reiniciar workers.

## Docs

- `CONFIGURACION_GET.md` - Guía completa de configuración
- `RESUMEN_FINAL.md` - Detalles de implementación
