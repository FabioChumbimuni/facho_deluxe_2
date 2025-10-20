# Guía de Interfaz - Programador de Tareas SNMP

## Elementos de la Interfaz

### Vista de Lista (`/admin/snmp_jobs/snmpjob/`)

#### Botón "Programar Nueva Tarea SNMP"
- **Ubicación**: Esquina superior derecha
- **Dimensiones**: 
  - Padding: 8px 15px
  - Margen derecho: 5px
  - Border-radius: 4px
- **Colores**:
  - Fondo: #417690
  - Texto: blanco
  - Hover: #205067

### Vista de Edición/Creación (`/admin/snmp_jobs/snmpjob/programar-tarea/`)

#### Selector de OLTs
- **Dimensiones**:
  - Ancho total: 900px (max-width)
  - Ancho de cada selector: 425px
  - Alto de selectores: 300px
  - Espacio entre selectores: 10px

##### Panel Izquierdo "Available OLTs"
- **Elementos**:
  - Título: Fondo #79aec8, texto blanco
  - Campo de filtro: 
    - Ancho: 320px
    - Padding: 8px
    - Borde: 1px solid #ccc
  - Lista de selección: 425px × 300px
  - Botón "Choose all": Parte inferior

##### Panel Derecho "Chosen OLTs"
- **Elementos**:
  - Título: Fondo #79aec8, texto blanco
  - Lista de selección: 425px × 300px
  - Botón "Remove all": Parte inferior

##### Botones Centrales
- **Dimensiones**:
  - Ancho: 22px
  - Margen: 10em 5px 0 5px
  - Border-radius: 10px
- **Elementos**:
  - Botón "Choose →": Mover seleccionados a la derecha
  - Botón "← Remove": Mover seleccionados a la izquierda

#### Selector de OID
- **Dimensiones**:
  - Ancho: 100%
  - Alto: Auto
- **Estilo**:
  - Clase: form-control
  - ID: id_oid

#### Botón "Guardar"
- **Ubicación**: Parte inferior del formulario
- **Dimensiones**:
  - Padding: 10px 15px
  - Border-radius: 4px
- **Colores**:
  - Fondo: #417690
  - Texto: blanco
  - Hover: #205067

## Estilos Generales

### Encabezados de Sección
- **Dimensiones**:
  - Padding: 8px
  - Margen: 0
- **Colores**:
  - Fondo: #79aec8
  - Texto: blanco
- **Tipografía**:
  - Tamaño: 13px
  - Peso: 400

### Campos de Formulario
- **Dimensiones**:
  - Margen entre campos: 10px
  - Padding interno: 8px
- **Estilos**:
  - Borde: 1px solid #ccc
  - Border-radius: 4px
  - Fondo: blanco

### Mensajes de Error/Éxito
- **Dimensiones**:
  - Padding: 10px
  - Margen: 10px 0
- **Colores**:
  - Error: Fondo #fff2f2, Borde #ff8080
  - Éxito: Fondo #f0fff0, Borde #80ff80

## Comportamiento Responsivo
- Los selectores mantienen proporción 16:9
- El ancho máximo se ajusta al contenedor
- Los botones centrales se centran verticalmente
- El campo de filtro se ajusta al ancho del selector
