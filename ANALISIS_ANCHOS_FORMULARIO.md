# Análisis Detallado de Anchos en Formulario SnmpJob
## URL: http://192.168.56.222:8000/admin/snmp_jobs/snmpjob/27/change/

---

## 📊 ELEMENTOS Y SUS ANCHOS DEFINIDOS

### 1️⃣ **CONTENEDOR PRINCIPAL DEL SELECTOR DE OLTs**
**Ubicación:** Líneas 45-48
```css
.selector {
    width: 100%;
    max-width: 900px;
}
```
- **Elemento:** Contenedor general del selector dual de OLTs
- **Ancho:** 100% (se ajusta al contenedor padre)
- **Ancho máximo:** 900px
- **Efecto:** Limita el ancho total del selector dual

---

### 2️⃣ **SELECTS DE OLTs (Disponibles y Seleccionadas)**
**Ubicación:** Líneas 49-55
```css
.selector select {
    width: 425px !important;
    height: 300px !important;
}
.selector-available, .selector-chosen {
    width: 380px !important;
}
```
- **Elemento:** Los dos cuadros de selección (izquierdo y derecho)
- **Ancho de cada select:** 425px (forzado con !important)
- **Ancho del contenedor:** 380px (forzado con !important)
- **Altura:** 300px
- **Problema detectado:** ⚠️ El select (425px) es MÁS ANCHO que su contenedor (380px)
- **Efecto:** Causa desbordamiento y apariencia dispareja

**También definido inline en HTML:**
- Línea 426: `style="height: 300px; width: 380px;"`
- Línea 436: `style="height: 300px; width: 380px;"`

---

### 3️⃣ **INPUT DE FILTRO (Búsqueda en OLTs)**
**Ubicación:** Líneas 70-76
```css
.selector-filter input {
    width: 320px;
    margin: 0;
    background: var(--bg-color);
    color: var(--text-color);
    border: 1px solid var(--border-color);
}
```
- **Elemento:** Campo de búsqueda/filtro en OLTs disponibles
- **Ancho:** 320px
- **Efecto:** Más estrecho que el contenedor (380px), deja margen

---

### 4️⃣ **BOTONES DEL SELECTOR (Flechas › ‹)**
**Ubicación:** Líneas 77-83
```css
.selector-chooser {
    width: 22px;
    background-color: var(--disabled-bg);
    border-radius: 10px;
    margin: 10em 5px 0 5px;
    padding: 0;
}
```
- **Elemento:** Contenedor de botones de movimiento entre listas
- **Ancho:** 22px
- **Margen:** 5px a cada lado
- **Efecto:** Muy delgado, puede ser poco visible

---

### 5️⃣ **CAMPO OID (Dropdown)**
**Ubicación:** Líneas 173-181
```css
#id_oid {
    width: 100%;
    max-width: 600px;
}

.oid-unified-container #id_oid {
    width: 50% !important;
    max-width: 400px !important;
    padding-right: 40px !important;
    padding-left: 10px !important;
    padding-top: 6px !important;
    padding-bottom: 6px !important;
    font-size: 12px !important;
    line-height: 1.2 !important;
    box-sizing: border-box !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
    min-height: 32px !important;
    border: 2px solid #4facfe !important;
}
```
- **Elemento:** Campo de selección de OID
- **Ancho base:** 100% (se ajusta al contenedor)
- **Ancho máximo base:** 600px
- **Ancho dentro de contenedor unificado:** 50% (forzado)
- **Ancho máximo dentro de contenedor:** 400px (forzado)
- **Problema detectado:** ⚠️ Dos reglas diferentes pueden causar inconsistencia

---

### 6️⃣ **BOTÓN DROPDOWN DE OID (Flecha)**
**Ubicación:** Líneas 197-222
```css
.oid-dropdown-btn {
    position: absolute !important;
    right: 5px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    background-color: #4facfe !important;
    border: 2px solid #4facfe !important;
    color: white !important;
    font-size: 14px !important;
    padding: 4px 8px !important;
    cursor: pointer !important;
    border-radius: 4px !important;
    z-index: 100 !important;
    height: 30px !important;
    width: 30px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.3) !important;
}
```
- **Elemento:** Botón de dropdown para buscar OIDs
- **Ancho:** 30px
- **Altura:** 30px
- **Posición:** Absoluta, 5px desde la derecha
- **Efecto:** Botón cuadrado dentro del campo OID

---

### 7️⃣ **RESULTADOS DE BÚSQUEDA OID**
**Ubicación:** Líneas 109-123
```css
.oid-search-results {
    position: absolute !important;
    top: 100% !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 1000 !important;
    background: #2c2c2c !important;
    border: 2px solid #4facfe !important;
    border-top: none !important;
    max-height: 250px !important;
    overflow-y: auto !important;
    width: 100% !important;
    box-shadow: 0 4px 8px rgba(0,0,0,0.5) !important;
    border-radius: 0 0 6px 6px !important;
}
```
- **Elemento:** Lista desplegable de resultados de búsqueda OID
- **Ancho:** 100% (se ajusta al contenedor padre)
- **Altura máxima:** 250px con scroll
- **Posición:** Absoluta, debajo del campo OID

---

## 🔧 PROBLEMAS DETECTADOS

### ❌ **Problema 1: Inconsistencia en selector de OLTs**
- **Archivo:** programar_tarea.html
- **Líneas:** 49-55
- **Descripción:** 
  - `.selector select` tiene `width: 425px`
  - `.selector-available` y `.selector-chosen` tienen `width: 380px`
  - El select es 45px más ancho que su contenedor
- **Solución:** Igualar ambos anchos a 380px

### ❌ **Problema 2: Falta título en primer fieldset**
- **Archivo:** programar_tarea.html
- **Línea:** 381
- **Descripción:** El primer fieldset no tiene `<h2>` de título
- **Solución:** Agregar `<h2>Información Básica</h2>` después de la línea 381

### ⚠️ **Problema 3: Doble definición de ancho en campo OID**
- **Archivo:** programar_tarea.html
- **Líneas:** 173-181
- **Descripción:** Dos reglas CSS diferentes para #id_oid pueden causar conflictos
- **Solución:** Consolidar en una sola regla

---

## 📋 RESUMEN DE ANCHOS POR ELEMENTO

| Elemento | Selector CSS | Ancho Definido | Ubicación (Línea) |
|----------|--------------|----------------|-------------------|
| Contenedor selector | `.selector` | 100% (max 900px) | 45-48 |
| Select OLTs | `.selector select` | 425px !important | 49-51 |
| Contenedor OLTs | `.selector-available/chosen` | 380px !important | 53-55 |
| Filtro búsqueda | `.selector-filter input` | 320px | 70-76 |
| Botones mover | `.selector-chooser` | 22px | 77-83 |
| Campo OID base | `#id_oid` | 100% (max 600px) | 173-176 |
| Campo OID container | `.oid-unified-container #id_oid` | 50% (max 400px) | 178-195 |
| Botón dropdown OID | `.oid-dropdown-btn` | 30px | 197-222 |
| Resultados búsqueda | `.oid-search-results` | 100% | 109-123 |

---

## 🎯 RECOMENDACIONES

1. **Igualar anchos del selector de OLTs:**
   ```css
   .selector select {
       width: 380px !important;  /* Cambiar de 425px a 380px */
       height: 300px !important;
   }
   ```

2. **Agregar título al primer fieldset (línea 382):**
   ```html
   <fieldset class="module aligned">
       <h2>Información Básica</h2>
       <!-- ... resto del contenido ... -->
   ```

3. **Consolidar estilos del campo OID:**
   - Eliminar regla duplicada
   - Mantener solo una definición clara de ancho

---

**Fecha de análisis:** 2025-10-20  
**Archivo analizado:** /opt/facho_deluxe_2/snmp_jobs/templates/admin/snmp_jobs/programar_tarea.html  
**Total de líneas:** 1434

