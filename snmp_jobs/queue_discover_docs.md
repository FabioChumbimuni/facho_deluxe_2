# Documentación del Sistema de Colas para Descubrimiento de ONUs

## Descripción General

El sistema de colas para descubrimiento de ONUs está diseñado para manejar de forma eficiente y robusta la detección automática de equipos conectados a las OLTs. Utiliza un sistema de doble cola (principal y prioridad) con monitoreo automático del estado de las OLTs, integrado con Celery y Redis.

## Especificaciones del Sistema

### **Configuración Principal**
- **Cola de Descubrimiento**: 20 hilos (workers)
- **Control máximo timeout**: 3 minutos
- **Control de repeticiones**: 3 intentos máximo
- **Intervalo entre repeticiones**: 30 segundos
- **Política de OLTs**: **NO se deshabilitarán OLTs** en caso de fallos
- **Job Type**: Solo tareas con `job_type='descubrimiento'`

## Arquitectura del Sistema

### Sistema de Doble Cola con Celery

#### **Cola Principal (discovery_main)**
- **Workers**: 20 workers Celery
- **Propósito**: Procesamiento inicial de todas las tareas de descubrimiento
- **Capacidad**: Alta capacidad de procesamiento para tareas normales
- **Prioridad**: Baja (procesamiento estándar)
- **Broker**: Redis
- **Timeout**: 3 minutos máximo por tarea

