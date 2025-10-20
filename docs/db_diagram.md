///////////////////////////////////////////////
// FASE 1 DJANGO
/////////////////////////////////////////////

// NOTA: Este diagrama incluye solo las tablas personalizadas del proyecto.
// Las tablas estándar de Django (auth_user, django_session, etc.) no están incluidas
// pero son referenciadas en las relaciones ForeignKey.
Table marcas {
  id int [pk]
  nombre varchar(255) [not null, unique]
  descripcion text
}

Table olt {
  id int [pk]
  abreviatura varchar(255)
  marca_id int
  modelo_id int [null, note: "FK a olt_models. Modelo específico de la OLT"]
  ip_address varchar(45)
  descripcion text
  habilitar_olt boolean [default: true]
  comunidad_snmp varchar(255)

  Note: 'habilitar_olt indica si la OLT está disponible para consultas SNMP. modelo_id permite especificar fórmulas de cálculo de índice por modelo específico'
}

Table olt_models {
  id int [pk, increment]
  nombre varchar(100) [not null, unique, note: "Nombre del modelo (ej: MA5800, C320)"]
  marca_id int [not null]
  descripcion text [not null]
  activo boolean [default: true]
  
  // Campos opcionales técnicos
  tipo_olt varchar(50) [null, note: "GPON, EPON, XG-PON, XGS-PON"]
  capacidad_puertos int [null, note: "Número máximo de puertos"]
  capacidad_onus int [null, note: "Número máximo de ONUs por puerto"]
  slots_disponibles int [null, note: "Número de slots para tarjetas"]
  
  // Campos opcionales de configuración
  version_firmware_minima varchar(50) [null]
  comunidad_snmp_default varchar(50) [null]
  puerto_snmp_default int [null, default: 161]
  
  // Campos opcionales de documentación
  url_documentacion varchar(200) [null]
  url_manual_usuario varchar(200) [null]
  notas_tecnicas text [null]
  
  // Campos opcionales de soporte
  soporte_tecnico_contacto varchar(255) [null]
  fecha_lanzamiento date [null]
  fecha_fin_soporte date [null]
  
  created_at timestamp
  updated_at timestamp

  indexes {
    (marca_id, activo) [name: 'olt_models_marca_activo_idx']
    (activo) [name: 'olt_models_activo_idx']
    (nombre) [name: 'olt_models_nombre_idx']
  }

  Note: 'Modelos específicos de OLT con características técnicas. Permite organizar y categorizar modelos por marca con campos obligatorios y opcionales.'
}

Table index_formulas {
  id int [pk, increment]
  marca_id int [not null]
  modelo_id int [null, note: "FK a olt_models. NULL = fórmula genérica para toda la marca"]
  nombre varchar(255) [not null, note: "Nombre descriptivo de la fórmula"]
  activo boolean [default: true]
  
  // Configuración de cálculo
  calculation_mode varchar(20) [default: "linear", note: "linear o bitshift"]
  
  // Parámetros modo LINEAL (BASE + STEPS)
  base_index bigint [default: 0, note: "Base del índice SNMP (ej: 4194304000 para Huawei)"]
  step_slot int [default: 0, note: "Incremento por slot (ej: 8192 para Huawei)"]
  step_port int [default: 0, note: "Incremento por puerto (ej: 256 para Huawei)"]
  
  // Parámetros modo BITSHIFT
  shift_slot_bits int [default: 0, note: "Bits de desplazamiento para slot"]
  shift_port_bits int [default: 0, note: "Bits de desplazamiento para puerto"]
  mask_slot varchar(20) [null, note: "Máscara hex para slot (ej: 0xFF)"]
  mask_port varchar(20) [null, note: "Máscara hex para puerto (ej: 0xFF)"]
  
  // Parámetros adicionales
  onu_offset int [default: 0, note: "Si numeración ONU empieza en 0 o 1"]
  has_dot_notation boolean [default: false, note: "Si índice incluye .ONU (ej: 4194312448.2)"]
  dot_is_onu_number boolean [default: true, note: "Si parte después del punto es número ONU lógico"]
  
  // Validación
  slot_max int [default: 64]
  port_max int [default: 64]
  onu_max int [default: 128]
  
  // Formato de salida
  normalized_format varchar(50) [default: "{slot}/{port}", note: "Variables: {slot}, {port}, {logical}"]
  
  descripcion text [null]
  created_at timestamp
  updated_at timestamp

  indexes {
    (marca_id, modelo) [unique, name: 'index_formulas_marca_modelo_unique']
    (marca_id, activo) [name: 'index_formulas_marca_activo_idx']
    (activo) [name: 'index_formulas_activo_idx']
  }

  Note: 'Fórmulas configurables para calcular slot/port/logical desde índices SNMP. Permite soportar múltiples marcas sin tocar código. Modo LINEAR: INDEX = BASE + (slot × STEP_SLOT) + (port × STEP_PORT) + onu_id. Modo BITSHIFT: usa desplazamiento de bits. Prioridad: busca primero marca+modelo específico, luego fórmula genérica (modelo=NULL)'
}

Table oids {
  id int [pk]
  nombre varchar(255)
  oid varchar(255)
  marca_id int
  espacio varchar(20) [default: "descubrimiento"]
  target_field varchar(50) [null, note: "Auto-completado según espacio"]
  keep_previous_value boolean [default: false]
  format_mac boolean [default: false]

  Note: 'espacio define el tipo: descubrimiento (excepción va a onu_index_map), descripcion, mac, plan_onu, distancia_onu, modelo_onu, serial, subscriber. target_field se asigna AUTOMÁTICAMENTE según espacio. keep_previous_value=true aplica lógica de mantener valor previo (facho_deluxe). format_mac=true elimina : y espacios de MAC (AC:DC:SD → ACDCSD)'
}

////////////////////////////////////////
// FASE 2 PROGRAMACIÓN DE TAREAS
////////////////////////////////////////
Table snmp_jobs {
  id int [pk, increment]
  nombre varchar(150) [not null]
  descripcion text
  marca_id int [not null]
  oid_id int [not null]
  job_type varchar(20) [not null, default: "descubrimiento"]
  interval_raw varchar(16)
  interval_seconds int
  cron_expr varchar(120)
  enabled boolean [default: true]
  max_retries smallint [default: 2]
  retry_delay_seconds int [default: 120]
  next_run_at timestamp
  last_run_at timestamp
  run_options json
  created_at timestamp
  updated_at timestamp

  Note: 'Una tarea SNMP debe tener exactamente un OID y puede tener múltiples OLTs'
}

Table snmp_job_olts {
  id int [pk, increment]
  snmp_job_id int [not null]
  olt_id int [not null]
  enabled boolean [default: true]
  last_success_at timestamp
  last_failure_at timestamp
  consecutive_failures int [default: 0]
  queue_name varchar(64)
  created_at timestamp

  indexes {
    (olt_id, snmp_job_id) [name: 'snmp_job_olts_olt_snmp_job_idx']
    (snmp_job_id) [name: 'snmp_job_olts_snmp_job_idx']
  }

  Note: 'Relación muchos a muchos entre tareas y OLTs con estado y configuración por OLT'
}

Table snmp_executions {
  id int [pk, increment]
  snmp_job_id int
  job_olt_id int
  olt_id int
  requested_by int
  celery_task_id varchar(255)
  worker_name varchar(255)
  started_at timestamp
  finished_at timestamp
  status varchar(16) [default: "PENDING"]
  attempt smallint [default: 0]
  duration_ms int
  result_summary json
  raw_output json
  error_message text
  created_at timestamp

  indexes {
    (status, created_at) [name: 'snmp_executions_status_created_idx']
  }
}

// FASE 3 LOGICA WALK Y TABLAS GET

// DBDiagram: Tablas adicionales (sin histórico) para implementación SNMP

Table onu_index_map {
  id int [pk, increment]
  olt_id int [not null]           // FK -> olt.id
  raw_index_key varchar(255) [not null]
  slot int                        // Calculado automáticamente para Huawei
  port int                        // Calculado automáticamente para Huawei (port_logico)
  logical int                     // Calculado automáticamente para Huawei (onu_id)
  normalized_id varchar(255) [not null]
  marca_formula text
  created_at timestamp
  updated_at timestamp

  Note: "Mapea y descompone el índice crudo (ej. 4194312192.2) en componentes reutilizables. Unique por (olt_id, raw_index_key). Para Huawei, calcula automáticamente slot, port y logical usando la fórmula: INDEX = BASE + (slot × 8192) + (port × 256) + onu_id"
}

Table onu_status {
  id int [pk, increment]
  onu_index_id int [not null]     // FK -> onu_index_map.id
  olt_id int [not null]           // FK -> olt.id
  last_seen_at timestamp
  last_state_value smallint       // guarda el int observado (1,2)
  last_state_label varchar(50)    // ACTIVO / SUSPENDIDO (resuelto vía lookup)
  presence varchar(20)            // ENABLED / DISABLED (vista consolidada)
  consecutive_misses int [default: 0]
  last_change_execution_id int    // FK -> snmp_executions.id (trazabilidad mínima)
  updated_at timestamp

  Note: "Tabla ligera que representa el estado actual (sin histórico). Se usa para filtrar targets del GET masivo."
}

Table onu_state_lookup {
  id int [pk, increment]
  value smallint                  // Ej: 1
  label varchar(100)              // Ej: ACTIVO
  description text
  marca_id int                    // FK opcional -> marcas.id

  Note: "Lookup para mapear valores numéricos a etiquetas por marca si es necesario."
}

Table onu_inventory {
  id int [pk, increment]
  onu_index_id int [not null]     // FK -> onu_index_map.id (único)
  olt_id int [not null]           // FK -> olt.id
  serial_number varchar(255)
  mac_address varchar(64)
  subscriber_id varchar(255)
  snmp_description text           // campo principal que se actualiza/reescribe por GET masivo
  snmp_metadata json              // datos adicionales devueltos por GET (sin histórico)
  plan_onu varchar(100)           // Plan ONU (con lógica de mantener valor previo)
  distancia_onu varchar(50)       // Distancia ONU en km (con lógica de mantener valor previo y conversión m->km)
  modelo_onu varchar(100)         // Modelo ONU (con lógica de mantener valor previo)
  snmp_last_collected_at timestamp
  snmp_last_execution_id int      // FK -> snmp_executions.id (trazabilidad mínima)
  active boolean [default: true]  // bandera administrativa: si false -> no incluir en GET masivo
  created_at timestamp
  updated_at timestamp

  Note: "Registro maestro (único por ONU conocida). Aquí se guarda la descripción y metadatos sin conservar histórico. Ideal target del GET masivo. Los campos plan_onu, distancia_onu, modelo_onu tienen lógica de mantener valor previo (facho_deluxe)."
}

// Relaciones con marcas
Ref: snmp_jobs.marca_id > marcas.id
Ref: olt.marca_id > marcas.id
Ref: oids.marca_id > marcas.id
Ref: index_formulas.marca_id > marcas.id
Ref: olt_models.marca_id > marcas.id

// Relaciones con modelos de OLT
Ref: olt.modelo_id > olt_models.id
Ref: index_formulas.modelo_id > olt_models.id

// Relaciones con configuración de Zabbix
// NOTA: ZabbixConfiguration ya NO tiene formula_snmp
// La fórmula se obtiene automáticamente de cada OLT según su marca/modelo

// Relaciones de tareas SNMP
Ref: snmp_jobs.oid_id > oids.id [delete: restrict] // Una tarea debe tener un OID
Ref: snmp_job_olts.snmp_job_id > snmp_jobs.id [delete: cascade] // Si se elimina la tarea, se eliminan sus relaciones con OLTs
Ref: snmp_job_olts.olt_id > olt.id [delete: cascade] // Si se elimina una OLT, se eliminan sus relaciones con tareas

// Relaciones de ejecuciones
Ref: snmp_executions.snmp_job_id > snmp_jobs.id [delete: set null] // Si se elimina la tarea, mantener el historial
Ref: snmp_executions.job_olt_id > snmp_job_olts.id [delete: set null] // Si se elimina la relación tarea-OLT, mantener el historial
Ref: snmp_executions.olt_id > olt.id [delete: set null] // Si se elimina la OLT, mantener el historial

// Referencias (asumen que las tablas base ya existen en tu diagrama principal)
Ref: onu_index_map.olt_id > olt.id
Ref: onu_status.onu_index_id > onu_index_map.id
Ref: onu_status.olt_id > olt.id
Ref: onu_status.last_change_execution_id > snmp_executions.id
Ref: onu_state_lookup.marca_id > marcas.id
Ref: onu_inventory.onu_index_id > onu_index_map.id
Ref: onu_inventory.olt_id > olt.id
Ref: onu_inventory.snmp_last_execution_id > snmp_executions.id

// ==================================================================
// CONFIGURACIÓN SNMP POR TIPO DE OPERACIÓN
// ==================================================================

Table configuracion_snmp {
  id int [pk, increment]
  nombre varchar(100) [unique]
  tipo_operacion varchar(20) [default: 'general'] // descubrimiento, get, bulk, table, general
  timeout int [default: 5] // Timeout SNMP en segundos
  reintentos smallint [default: 0] // Reintentos SNMP
  comunidad varchar(50) [default: 'public']
  version varchar(10) [default: '2c'] // 1, 2c, 3
  
  // Configuración específica para pollers GET
  max_pollers_por_olt smallint [default: 10] // Máximo pollers concurrentes por OLT
  tamano_lote_inicial int [default: 200] // Tamaño del lote inicial de ONUs
  tamano_subdivision smallint [default: 50] // Tamaño al subdividir lotes con errores
  max_reintentos_individuales smallint [default: 2] // Reintentos para ONUs individuales
  delay_entre_reintentos smallint [default: 5] // Segundos entre reintentos
  max_consultas_snmp_simultaneas smallint [default: 5] // Máximo consultas SNMP simultáneas (Semaphore)
  
  activo boolean [default: true]
  fecha_creacion timestamp
  fecha_modificacion timestamp
  
  indexes {
    (tipo_operacion, activo)
  }
  
  Note: 'Configuración SNMP específica por tipo de operación. Tipo GET tiene parámetros adicionales para control de pollers y subdivisión.'
}

// Notas finales:
// - No se incluye tabla de histórico. La presencia/estado consolidado vive en `onu_status`.
// - El GET masivo debe filtrar por `onu_inventory.active = true` y `onu_status.presence = 'ENABLED'` (o `last_state_value = 1` según tu regla).
// - Mantén índice único lógico en (olt_id, raw_index_key) y/o (olt_id, onu_index_id) en la BD real para rendimiento.
// - Configuración SNMP por tipo: Las operaciones GET leen su configuración desde `configuracion_snmp` donde tipo_operacion='get'

// ==================================================================
// SISTEMA DE POLLERS PARA SNMP GET - FASE 3.5
// ==================================================================
// El sistema de pollers para job_type='get' funciona de la siguiente manera:
//
// 1. TAREA PRINCIPAL (get_main_task):
//    - Consulta onu_status filtrando por presence='ENABLED' ← SOLO ONUS ACTIVAS
//    - Divide las ONUs en lotes (batch_size configurable desde BD, default: 200)
//    - Encola múltiples tareas poller (una por lote, max 10 simultáneos por OLT)
//    - Se ejecuta en cola 'get_main'
//    - Usa configuración desde tabla configuracion_snmp con tipo_operacion='get'
//
// 2. TAREAS POLLER (get_poller_task):
//    - Procesa un lote de ONUs en paralelo
//    - Control de carga: Semaphore (max 5 consultas SNMP simultáneas por OLT)
//    - Realiza SNMP GET individual por ONU usando: OID_base.raw_index_key
//    - Actualiza onu_inventory.snmp_description con el valor obtenido
//    - Se ejecuta en cola 'get_poller' (alta concurrencia: 20 workers)
//    - Subdivisión automática si hay errores: 200 → 50 → Individual
//    - Reintentos individuales: hasta 2 veces con backoff exponencial
//
// 3. FLUJO DE EJECUCIÓN:
//    - Dispatcher detecta job_type='get' listo para ejecutar
//    - Crea Execution con status='PENDING'
//    - Encola get_main_task en cola 'get_main'
//    - get_main_task divide trabajo y encola múltiples get_poller_task
//    - Cada poller actualiza onu_inventory.snmp_description independientemente
//
// 4. CONFIGURACIÓN:
//    - OID debe tener espacio='descripcion' (se valida pero no bloquea)
//    - batch_size configurable via run_options (default: 100 ONUs por poller)
//    - timeout, retries y community configurables via run_options
//
// 5. TABLAS ACTUALIZADAS:
//    - onu_inventory.snmp_description: Valor obtenido del SNMP GET
//    - onu_inventory.snmp_last_collected_at: Timestamp de última actualización
//    - onu_inventory.snmp_last_execution_id: FK a la ejecución que actualizó

// ==================================================================
// NUEVAS TABLAS PARA ODF / HILOS / VLAN - FASE 4
// ==================================================================

Table zabbix_port_data {
  id int [pk, increment]
  olt_id int [not null]            // FK -> olt.id
  snmp_index varchar(50) [not null] // Índice SNMP de la interfaz
  slot int [not null]              // Slot calculado desde SNMP index
  port int [not null]              // Port calculado desde SNMP index
  descripcion_zabbix text          // Descripción cruda desde Zabbix
  interface_name varchar(100)      // Nombre de interfaz (ej: GPON 0/4/15)
  disponible boolean [default: true] // Si el puerto está disponible en la última recolección de Zabbix (item master)
  estado_administrativo int        // Estado administrativo del puerto desde OID .1.3.6.1.2.1.2.2.1.7 (1=ACTIVO, 2=INACTIVO)
  operativo_noc boolean [default: false] // Si el puerto está operativo según NOC (configuración manual)
  last_sync timestamp
  created_at timestamp

  indexes {
    (olt_id, snmp_index) [unique]  // evita duplicados por OLT
    (olt_id, slot, port)           // búsqueda por slot/port
    (snmp_index)                   // búsqueda por índice
    (disponible)                   // filtros por disponibilidad
    (estado_administrativo)        // filtros por estado administrativo
    (operativo_noc)                // filtros por estado operativo NOC
  }

  Note: "Datos básicos extraídos de Zabbix para cada puerto GPON. Incluye estado administrativo del OID .1.3.6.1.2.1.2.2.1.7 y campos de control manual para sincronización con ODFHilos."
}

Table odf {
  id int [pk, increment]
  olt_id int [not null]            // FK -> olt.id
  numero_odf int [not null]        // Número del ODF (1, 2, 3...)
  nombre_troncal varchar(255) [not null] // Ej: "CHOSICA-SANTA EULALIA 2 T-24" (ÚNICO POR OLT)
  descripcion text
  created_at timestamp
  updated_at timestamp

  indexes {
    (olt_id, nombre_troncal) [unique] // Nombre troncal único por OLT
    (olt_id, numero_odf)              // Búsqueda por OLT y número
    (numero_odf)                      // Búsqueda por número
  }

  Note: "Un ODF representa el marco físico de distribución de fibras. Cada ODF tiene un número (puede repetirse) y un nombre_troncal único por OLT."
}

Table odf_hilos {
  id int [pk, increment]
  odf_id int [not null]           // FK -> odf.id
  zabbix_port_id int              // FK opcional -> zabbix_port_data.id
  slot int [not null]             // Puede venir de Zabbix o definirse manualmente
  port int [not null]             // Puede venir de Zabbix o definirse manualmente
  hilo_numero int [not null]      // Número físico del hilo hacia la NAP (MANUAL)
  vlan int [not null]             // VLAN de conexión configurada (MANUAL)
  descripcion_manual text         // Descripción manual del hilo/troncal (MANUAL)
  estado varchar(20) [default: "disabled"] // enabled (en Zabbix) / disabled (no en Zabbix o manual)
  origen varchar(20) [default: "manual"] // zabbix/manual - indica origen de los datos
  en_zabbix boolean [default: false] // Si actualmente aparece en Zabbix
  operativo_noc boolean [default: false] // Si el hilo está operativo según NOC (configuración manual)
  personal_proyectos_id int       // FK opcional -> personal.id
  personal_noc_id int             // FK opcional -> personal.id  
  tecnico_habilitador_id int      // FK opcional -> personal.id
  fecha_habilitacion date [not null] // Fecha de habilitación (OBLIGATORIO, MANUAL)
  hora_habilitacion time              // Hora de habilitación (OPCIONAL, MANUAL)
  created_at timestamp
  updated_at timestamp

  indexes {
    (odf_id, slot, port, hilo_numero) [unique] // evita duplicados por ODF
    (fecha_habilitacion)                       // búsqueda por fecha
    (hora_habilitacion)                        // búsqueda por hora
    (personal_proyectos_id)                    // búsqueda por personal
    (personal_noc_id)                          // búsqueda por personal NOC
    (tecnico_habilitador_id)                   // búsqueda por técnico
    (en_zabbix)                                // filtros por estado en Zabbix
    (operativo_noc)                            // filtros por estado operativo NOC
  }

  Note: "Cada combinación slot/port dentro de un ODF se asocia a un hilo y VLAN. Incluye campos de personal responsable, fecha obligatoria de habilitación y sincronización automática con ZabbixPortData."
}

// ==================================================================
// AJUSTES A ONU_INDEX_MAP PARA CONECTARLO CON ODF_HILOS
// ==================================================================

// Se añade campo odf_hilo_id a la tabla existente onu_index_map
// odf_hilo_id int                 // FK opcional -> odf_hilos.id
// Esto enlaza el SNMPINDEX lógico con el puerto/hilo físico

// ==================================================================
// TABLAS DE PROGRAMACIÓN AUTOMÁTICA - CRON SCHEDULER
// ==================================================================

Table zabbix_collection_schedule {
  id int [pk, increment]
  nombre varchar(100) [not null]      // Nombre descriptivo
  intervalo_minutos int [not null]     // 5, 10, 15, 20, 30, 60 minutos
  habilitado boolean [default: true]   // Si está activa la programación
  proxima_ejecucion timestamp          // Próxima ejecución calculada
  ultima_ejecucion timestamp           // Última ejecución completada
  created_at timestamp
  updated_at timestamp

  Note: "Programaciones de recolección automática. Se ejecuta cada minuto verificando si hay schedules pendientes."
}

Table zabbix_collection_olt {
  id int [pk, increment]
  schedule_id int [not null]           // FK -> zabbix_collection_schedule.id
  olt_id int [not null]                // FK -> olt.id
  habilitado boolean [default: true]   // Si esta OLT está habilitada
  ultima_recoleccion timestamp         // Última recolección exitosa
  ultimo_estado varchar(20) [default: "pending"] // success/error/pending
  ultimo_error text                    // Último error si existe
  created_at timestamp

  indexes {
    (schedule_id, olt_id) [unique]     // Una OLT por programación
  }

  Note: "Asociación entre programaciones y OLTs específicas. Permite habilitar/deshabilitar OLTs individualmente."
}

// ==================================================================
// TABLAS DE PERSONAL - APP PERSONAL
// ==================================================================

Table personal_area {
  id int [pk, increment]
  nombre varchar(100) [not null, unique] // Nombre único del área
  descripcion text
  activa boolean [default: true]
  created_at timestamp
  updated_at timestamp

  Note: "Áreas de trabajo (ej: Proyectos, NOC, Técnico de Campo). Flexible sin códigos predefinidos."
}

Table personal_nivel_privilegio {
  id int [pk, increment]
  nivel int [not null, unique] // Nivel de privilegio (1=Básico, 5=Administrador)
  nombre varchar(100) [not null] // Nombre del nivel
  descripcion text
  activo boolean [default: true]
  created_at timestamp
  updated_at timestamp

  Note: "Niveles de privilegio para control de acceso."
}

Table personal_personal {
  id int [pk, increment]
  user_id int [not null, unique] // FK -> django.contrib.auth.User (tabla auth_user)
  nombre_completo varchar(255) [not null]
  area_id int // FK opcional -> personal_area.id
  nivel_privilegio_id int // FK opcional -> personal_nivel_privilegio.id
  telefono varchar(20)
  email varchar(255)
  activo boolean [default: true]
  created_at timestamp
  updated_at timestamp

  indexes {
    (area_id) // búsqueda por área
    (nivel_privilegio_id) // búsqueda por nivel
    (activo) // filtros por estado
  }

  Note: "Personal del sistema con información de contacto y asignación a áreas. Referencia a la tabla de usuarios de Django (auth_user)."
}

Table personal_historial_acceso {
  id int [pk, increment]
  personal_id int [not null] // FK -> personal_personal.id
  accion varchar(100) [not null] // Acción realizada
  descripcion text
  ip_address varchar(45)
  user_agent text
  created_at timestamp

  indexes {
    (personal_id, created_at) // búsqueda por personal y fecha
    (created_at) // búsqueda por fecha
  }

  Note: "Historial de accesos y acciones del personal para auditoría."
}

Table zabbix_configuration {
  id int [pk, increment]
  nombre varchar(100) [not null, unique, note: "Nombre identificador de la configuración"]
  zabbix_url varchar(255) [not null, note: "URL completa de la API de Zabbix"]
  zabbix_token varchar(255) [not null, note: "Token de autenticación de Zabbix"]
  item_key varchar(100) [not null, default: 'port.descover.walk', note: "Clave del item master en Zabbix"]
  activa boolean [default: true, note: "Solo una configuración puede estar activa"]
  timeout int [default: 30, note: "Timeout para peticiones a Zabbix (segundos)"]
  verificar_ssl boolean [default: true, note: "Verificar certificados SSL"]
  descripcion text [null]
  created_at timestamp
  updated_at timestamp

  indexes {
    (activa) [name: 'zabbix_config_activa_idx']
    (nombre) [name: 'zabbix_config_nombre_idx']
  }

  Note: 'Configuración de conexión con Zabbix. La fórmula SNMP se obtiene automáticamente de cada OLT según su marca/modelo desde index_formulas. Solo puede haber una configuración activa a la vez.'
}

// ==================================================================
// REFERENCIAS NUEVAS
// ==================================================================

Ref: zabbix_port_data.olt_id > olt.id
Ref: odf.olt_id > olt.id
Ref: odf_hilos.odf_id > odf.id
Ref: odf_hilos.zabbix_port_id > zabbix_port_data.id
Ref: odf_hilos.personal_proyectos_id > personal_personal.id
Ref: odf_hilos.personal_noc_id > personal_personal.id
Ref: odf_hilos.tecnico_habilitador_id > personal_personal.id
Ref: zabbix_collection_schedule.id < zabbix_collection_olt.schedule_id
Ref: zabbix_collection_olt.olt_id > olt.id
// Ref: personal_personal.user_id > auth_user.id (tabla de Django no incluida en este diagrama)
Ref: personal_personal.area_id > personal_area.id
Ref: personal_personal.nivel_privilegio_id > personal_nivel_privilegio.id
Ref: personal_historial_acceso.personal_id > personal_personal.id
// Ref: onu_index_map.odf_hilo_id > odf_hilos.id (se añadirá en migración)

// ==================================================================
// LÓGICA DE SINCRONIZACIÓN AUTOMÁTICA
// ==================================================================

// SINCRONIZACIÓN BIDIRECCIONAL ENTRE ZABBIX_PORT_DATA Y ODF_HILOS:
//
// 1. ZabbixPortData.disponible ↔ ODFHilos.en_zabbix
//    - Cuando Zabbix cosecha datos y cambia 'disponible'
//    - Automáticamente se sincroniza con 'en_zabbix' del hilo relacionado
//    - Implementado en ZabbixPortData.save() y ZabbixService._update_odf_hilos_status()
//
// 2. ODFHilos.operativo_noc → ZabbixPortData.operativo_noc
//    - El hilo es la fuente de verdad para operativo_noc (configuración manual NOC)
//    - Al cambiar operativo_noc en el hilo, se sincroniza al puerto Zabbix
//    - Implementado en ODFHilos.sincronizar_operativo_noc()
//
// 3. REGLAS DE SINCRONIZACIÓN:
//    - operativo_noc es SOLO MANUAL - nunca se modifica automáticamente por Zabbix
//    - disponible/en_zabbix se sincroniza automáticamente durante cosecha
//    - Si un puerto desaparece de Zabbix: disponible=False, en_zabbix=False, operativo_noc se mantiene
//    - Si un puerto reaparece: disponible=True, en_zabbix=True, operativo_noc se copia del hilo
//
// 4. MÉTODOS DE SINCRONIZACIÓN:
//    - ZabbixPortData.save(): Detecta cambios en 'disponible' y sincroniza hilos
//    - ODFHilos.sincronizar_operativo_noc(): Sincroniza operativo_noc del hilo al puerto
//    - ZabbixService._update_odf_hilos_status(): Sincroniza durante cosecha de Zabbix
//    - ZabbixService._sync_operativo_noc_states(): Sincroniza operativo_noc masivamente
//
// 5. HERRAMIENTAS DE PRUEBA:
//    - simulate_zabbix_harvest: Simula cosechas de Zabbix
//    - test_bidirectional_sync: Prueba sincronización bidireccional
//    - sync_operativo_noc: Sincronización masiva cuando sea necesario


