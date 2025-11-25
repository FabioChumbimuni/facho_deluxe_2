# 📊 Análisis del Coordinador y Mejoras Implementadas

## 🔍 Análisis de Ejecuciones Actual

### Problemas Detectados:

1. **Cuota al 100%**: 6 nodos alcanzaron el máximo de 4 ejecuciones/hora
   - ✅ **RESUELTO**: Se verifica cuota ANTES de ejecutar
   - ✅ **RESUELTO**: Si alcanza cuota, salta a siguiente hora completa

2. **Colisiones Masivas**: 17 nodos programados para las 11:15 (máximo recomendado: 5)
   - ✅ **RESUELTO**: Límite global de 6 ejecuciones por minuto
   - ✅ **RESUELTO**: Redistribución automática cuando hay >6 nodos en mismo minuto

3. **Falta verificación de cuota antes de ejecutar**
   - ✅ **RESUELTO**: Verificación en `get_ready_tasks()`

4. **Falta postergar ejecuciones cuando hay nodos RUNNING**
   - ✅ **RESUELTO**: Posterga ejecuciones del mismo tipo cuando hay RUNNING

## ✅ Mejoras Implementadas

### 1. Verificación de Cuota ANTES de Ejecutar

**Ubicación**: `get_ready_tasks()` en `dynamic_scheduler.py`

**Lógica**:
- Verifica cuota máxima por hora: `3600 / interval_seconds`
- Cuenta ejecuciones en última hora (SUCCESS, FAILED, INTERRUPTED)
- Si `recent_executions >= max_executions_per_hour`, **NO ejecuta**
- Log: `"⏸️ Nodo alcanzó cuota máxima, omitiendo"`

**Beneficio**: Evita ejecuciones que excedan la cuota

### 2. Postergar Ejecuciones cuando hay Nodos RUNNING

**Ubicación**: `get_ready_tasks()` en `dynamic_scheduler.py`

**Lógica**:
- Verifica ejecuciones RUNNING del mismo tipo (`job_type`) en la OLT
- Si hay ejecución RUNNING del mismo tipo, **posterga** esta ejecución
- Log: `"⏸️ Nodo postergado: hay ejecución RUNNING del tipo X"`

**Beneficio**: Evita saturación y ejecuciones simultáneas del mismo tipo

### 3. Límite Global de Ejecuciones por Minuto

**Ubicación**: `distribute_workflow_executions()` en `dynamic_scheduler.py`

**Lógica**:
- **Máximo 6 ejecuciones por minuto** (configurable: `MAX_EXECUTIONS_PER_MINUTE`)
- Si hay >6 nodos en mismo minuto, redistribuye automáticamente
- Distribuye en ventana de ±3 minutos desde hora base

**Beneficio**: Evita colisiones masivas (como las 17 ejecuciones a las 11:15)

### 4. Mejora en Distribución de Colisiones

**Ubicación**: `distribute_workflow_executions()` en `dynamic_scheduler.py`

**Lógica**:
- Detecta colisiones: >6 nodos en mismo minuto
- Redistribuye uniformemente en rango de ±180 segundos
- Solo actualiza si cambio es significativo (>30 segundos)

**Beneficio**: Distribución más uniforme y evita saturación

## 📈 Estadísticas del Sistema

### Ejecuciones por Hora:
- **Total ejecuciones (última hora)**: 119
- **Nodos analizados**: 20
- **Nodos con cuota >= 80%**: 6
- **Nodos con cuota >= 100%**: 6

### Colisiones Detectadas:
- **11:15**: 17 nodos (⚠️ CRÍTICO - ahora se redistribuye automáticamente)

### Estado Actual:
- **Ejecuciones PENDING**: 1
- **Ejecuciones RUNNING**: 0

## 🎯 Recomendaciones Adicionales

### 1. Monitoreo de Cuota en Tiempo Real

**Implementar**: Dashboard que muestre:
- Cuota actual por nodo (ej: 3/4 ejecuciones)
- Porcentaje de uso (ej: 75%)
- Alertas cuando cuota >= 90%

### 2. Límite de Ejecuciones Simultáneas por Tipo

**Implementar**: 
- Máximo 10 ejecuciones simultáneas de `descubrimiento`
- Máximo 20 ejecuciones simultáneas de `get`
- Postergar nuevas ejecuciones si se alcanza el límite

### 3. Distribución Inteligente por Prioridad

**Implementar**:
- Nodos de mayor prioridad se ejecutan primero
- Nodos de menor prioridad se distribuyen más ampliamente
- Evitar que todos los nodos de alta prioridad se ejecuten al mismo tiempo

### 4. Verificación de Cuota en Distribución

**Implementar**:
- Al distribuir, verificar que no se exceda cuota
- Si un nodo está cerca de su cuota (>= 80%), distribuirlo más tarde
- Priorizar nodos con cuota disponible

### 5. Logs Detallados de Cuota

**Implementar**:
- Log cuando nodo alcanza 80% de cuota (WARNING)
- Log cuando nodo alcanza 100% de cuota (INFO)
- Log cuando nodo se salta ejecución por cuota (DEBUG)

## 🔧 Casos que Pueden Suceder

### Caso 1: Múltiples Nodos Alcanzan Cuota Simultáneamente

**Escenario**: 10 nodos alcanzan cuota al mismo tiempo

**Comportamiento Actual**:
- Todos saltan a siguiente hora completa
- Pueden colisionar en la siguiente hora

**Mejora Sugerida**:
- Distribuir los saltos a siguiente hora en ventana de ±3 minutos
- Evitar que todos salten al mismo minuto

### Caso 2: Nodo RUNNING por Mucho Tiempo

**Escenario**: Nodo RUNNING por más de 5 minutos

**Comportamiento Actual**:
- Otros nodos del mismo tipo se posterguen indefinidamente

**Mejora Sugerida**:
- Timeout: Si RUNNING > 5 minutos, permitir siguiente ejecución
- Log de advertencia cuando ejecución tarda mucho

### Caso 3: Colisión Masiva al Iniciar Sistema

**Escenario**: Sistema reiniciado, todos los nodos tienen `next_run_at` similar

**Comportamiento Actual**:
- Distribución automática cada 2 minutos
- Puede tomar tiempo distribuir todos

**Mejora Sugerida**:
- Al iniciar, distribuir inmediatamente todos los nodos
- Usar distribución más agresiva en primer minuto

### Caso 4: Nodo con Intervalo Muy Corto (< 5 minutos)

**Escenario**: Nodo con intervalo de 2 minutos (30 ejecuciones/hora)

**Comportamiento Actual**:
- Se ejecuta normalmente
- Puede saturar el sistema

**Mejora Sugerida**:
- Limitar ejecuciones por minuto para nodos de intervalo corto
- Agrupar ejecuciones de nodos de intervalo corto

## 📊 Límites Recomendados

### Ejecuciones por Minuto:
- **Máximo global**: 6 ejecuciones/minuto (implementado)
- **Óptimo**: 3-5 ejecuciones/minuto
- **Mínimo**: 1 ejecución/minuto (para evitar inactividad)

### Ejecuciones Simultáneas:
- **Descubrimiento**: Máximo 10 simultáneas
- **GET**: Máximo 20 simultáneas
- **Total**: Máximo 30 ejecuciones simultáneas

### Cuota por Nodo:
- **Verificación**: Cada vez que se va a ejecutar
- **Alerta**: Cuando cuota >= 80%
- **Bloqueo**: Cuando cuota >= 100%

## 🎯 Próximos Pasos

1. ✅ Verificación de cuota antes de ejecutar
2. ✅ Postergar ejecuciones cuando hay RUNNING
3. ✅ Límite global de ejecuciones por minuto
4. ⏳ Monitoreo de cuota en tiempo real (dashboard)
5. ⏳ Límite de ejecuciones simultáneas por tipo
6. ⏳ Distribución inteligente por prioridad
7. ⏳ Logs detallados de cuota

## 📝 Notas Técnicas

- **Cuota se calcula**: `3600 / interval_seconds` ejecuciones/hora
- **Ventana de cuota**: Última hora (rolling window)
- **Estados contados**: SUCCESS, FAILED, INTERRUPTED
- **Estados NO contados**: PENDING, RUNNING (aún no terminaron)

