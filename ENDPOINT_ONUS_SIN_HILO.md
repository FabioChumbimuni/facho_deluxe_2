# Endpoint: ONUs sin Hilo ODF

## Comandos CURL (Listos para copiar y pegar)

### 1. Listar todas las ONUs sin hilo ODF
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

### 2. Filtrar por OLT específica
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/?olt=21" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

### 3. Solo ONUs que tienen hilos candidatos disponibles
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/?tiene_hilo_candidato=true" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

### 4. Filtrar por OLT y slot específicos
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/?olt=21&slot=1" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

### 5. Filtrar por OLT, slot y port específicos
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/?olt=21&slot=1&port=3" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

### 6. Con paginación (página 1, 25 resultados por página)
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/?page=1&page_size=25" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

### 7. Filtrar por OLT y solo ONUs con hilos candidatos
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/?olt=21&tiene_hilo_candidato=true" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

### 8. Filtrar por slot y port (todas las OLTs)
```bash
curl -X GET "https://10.80.80.229/api/onu-index-map/sin-hilo-odf/?slot=3&port=3" \
     -H "x-api-key: 444b5fd944b13b58fa4141deaab93ede45fdf733" \
     -k
```

---

**Nota:** 
- Usa HTTPS (no HTTP)
- El flag `-k` es necesario para ignorar la verificación del certificado SSL
- Reemplaza `444b5fd944b13b58fa4141deaab93ede45fdf733` con tu API key si es diferente
