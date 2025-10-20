# Facho Deluxe v2 - Sistema de Monitoreo SNMP para OLTs

## Descripción General

Facho Deluxe v2 es un sistema de monitoreo SNMP diseñado específicamente para OLTs (Optical Line Terminals). El sistema permite la recolección automatizada de datos SNMP, su almacenamiento y visualización a través de una interfaz administrativa.

## Estructura Actual del Proyecto

### Apps Django

1. **brands/** 
   - Gestión de marcas de equipos
   - Modelo: `Brand`

2. **hosts/**
   - Gestión de OLTs
   - Modelo principal: `OLT`
   - Campos clave: IP, comunidad SNMP, marca

3. **oids/**
   - Gestión de OIDs SNMP
   - Modelo: `OID`
   - Almacena los identificadores SNMP a consultar

4. **snmp_jobs/**
   - Core del sistema de tareas SNMP
   - Modelos principales:
     * `SnmpJob`: Definición de tareas SNMP
     * `SnmpJobHost`: Relación job-OLT
     * `SnmpJobOID`: Relación job-OID
     * `Execution`: Registro de ejecuciones
     * `ExecutionAttempt`: Historial de intentos
     * `OnuData`: Datos recolectados

5. **executions/**
   - Manejo de ejecuciones y resultados

### Tecnologías Implementadas

- **Django**: Framework web principal
- **Celery**: Sistema de tareas asíncronas
- **Redis**: Broker de mensajes y sistema de locks
- **SNMP**: Protocolo de gestión de red

## Estado Actual de Implementación

### Completado
1. Modelos de datos (models.py)
   - Estructura completa de tablas
   - Relaciones entre modelos
   - Campos necesarios para SNMP y monitoreo

### En Desarrollo
1. Sistema de Tareas SNMP
   - Dispatcher periódico (Celery Beat)
   - Worker para ejecución SNMP
   - Sistema de reintentos
   - Manejo de fallos

2. Interfaz Administrativa
   - Vista de jobs SNMP
   - Programación de tareas
   - Monitoreo de ejecuciones

### Pendiente
1. Implementación SNMP
   - Conexión con equipos
   - Manejo de timeouts
   - Parseo de respuestas

2. Sistema de Notificaciones
   - Alertas por fallo
   - Notificaciones de estado

## Arquitectura del Sistema

### Flujo de Datos
1. Usuario crea tarea SNMP en admin
2. Celery Beat detecta tareas programadas
3. Worker ejecuta consultas SNMP
4. Resultados se almacenan en BD
5. Admin muestra estado y resultados

SE USARA SNMP V2

## Próximos Pasos

Termines primero el formulario no bloquear el admin

1. Completar implementación de tareas Celery
4. Pruebas con equipos reales
5. Documentación de API y uso

## Configuración Actual

### Base de Datos
-Desarrollado en Postgresql


Solo se usara la interfaz nativa de django


### Celery
- Redis como broker
- Sistema de locks por host

#### Colas de Celery
1. **Cola Principal (default)**
   - Maneja la distribución inicial de tareas
   - Prioriza y organiza el flujo de trabajo
   - Capacidad: Alta prioridad

2. **Cola Discovery (discovery)**
   - Dedicada a tareas de descubrimiento de ONUs
   - Operaciones intensivas de escaneo
   - Rate limit: 2 tareas por worker
   - Timeout: 300 segundos
   - Reintentos: 3 máximo

3. **Cola Polling (polling)**
   - Consultas SNMP periódicas
   - Monitoreo de estado y métricas
   - Rate limit: 5 tareas por worker
   - Timeout: 60 segundos
   - Reintentos: 2 máximo

4. **Cola Retry (retry)**
   - Manejo exclusivo de reintentos
   - Backoff exponencial
   - Prioridad: Baja
   - Máximo reintentos: 3
   - Delay entre reintentos: 300, 600, 1200 segundos





#### Control de Tareas
- Locks por OLT para evitar sobrecarga
- Monitoreo de estado en tiempo real
- Sistema de notificaciones por fallo
- Logging detallado de operaciones

### Admin Django
- Interfaces personalizadas
- Acciones por lote
- Filtros y búsquedas

## Consideraciones Técnicas

1. **Escalabilidad**
   - Diseño modular
   - Optimización de consultas
   - Control de concurrencia

2. **Mantenibilidad**
   - Código documentado
   - Pruebas unitarias
   - Logs detallados

3. **Seguridad**
   - Autenticación robusta
   - Cifrado de datos sensibles
   - Validación de entrada

## Roadmap

### Corto Plazo
1. Completar sistema de tareas
2. Implementar interfaz de monitoreo
3. Pruebas iniciales

### Mediano Plazo
1. Sistema de reportes
2. Dashboard en tiempo real
3. API REST

### Largo Plazo
1. Integración con otros sistemas
2. Análisis predictivo
3. Automatización avanzada
