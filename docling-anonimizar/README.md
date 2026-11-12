# docling-anonimizar

Formulario n8n para convertir PDF largos con docling y, si se pide, anonimizarlos **sin IA generativa**.

## Por dónde vamos (2026-11-12)

**Funciona de punta a punta en el servidor.** Prueba buena: PDF de Eventalista
(`WC-2026-EVNT-PLT-004 ...`, 224 páginas, 16 MB, LibreOffice). Ejecución 1316: 9 tramos en unos 9 min,
docling por debajo de 2,5 GB, tramos temporales borrados, botón de descarga OK y fichero descargado.

Desplegado:

- Servicio `anonimizador`: App de Easypanel en `ia-support`, creada por la API de Easypanel con
  origen *Upload* y build por Dockerfile.
- Flujo `DoclingAnonim001`: en el proyecto personal de n8n (`njbPRUnMI5G0izCw`), activo.

**PARA RETOMAR:**

1. El usuario tiene que revisar la **calidad de la anonimización** sobre el resultado de Eventalista
   (nombres que se escapan, falsos positivos) y decidir si cambia las casillas por defecto.
   Ajustes en `api/anonimizar.py` y `api/nombres.txt`; antes y después, `pruebas/test_anonimizar.py`.
2. **Al cerrar el proyecto, borrar el token de la API de Easypanel**: `/root/easypanel_token` en el
   servidor, solo root, y revocarlo en Easypanel → Settings. Se dejó a petición del usuario.
3. Formulario con Basic Auth *Albaranes IA - Basic Auth* (usuario `revision`). Si se quiere una
   credencial propia, crearla en n8n y cambiar `CRED_BASIC` en `n8n/build_workflow.py`.
4. `docling-anonimizar/` no está commiteado en git.

Lo que costó llegar aquí, en orden. Cada punto tiene su detalle más abajo.

- **docling por memoria (OOM).** PDF con 228 imágenes en recursos compartidos → troceo real con poda
  de `XObject`, en lugar de `page_range`.
- **La descarga automática no llegaba.** La página final va con CSP sandbox → botón de descarga.
- **`Task request timed out` en el tramo 7.** Unos 40 MB de base64 en la ejecución → los PDF ya no
  pasan por n8n: los envía el anonimizador.
- **docling rechaza URL internas** (SSRF). Por eso no se usa `kind: http`.
- **Orden de reinicio en `desplegar.sh`.** El runner se reinicia después de que n8n esté activo.
  Esto no causaba el fallo, pero es lo correcto según el README del VPS.
- **Los "idle timeout" del runner son normales.**

## Uso

https://ia-support-n8n.kw2y1s.easypanel.host/form/docling-anonimizar (Basic Auth: la credencial
*Albaranes IA - Basic Auth*, la misma de la revisión de albaranes).

1. Se sube el PDF y se marca si hay que anonimizar.
2. Si se anonimiza, una segunda página pide los **términos concretos** (uno por línea) y **qué datos
   personales** detectar. Por defecto: personas, teléfonos, emails, DNI/NIE/CIF/pasaporte, cuentas y
   tarjetas, y direcciones. Lugares, organizaciones y webs van desmarcados porque suelen sobrar.
3. Al terminar, la pantalla final tiene un botón **Descargar** del `.md` y una vista previa del texto.
   No se usa "Return Binary File" del nodo Form: n8n sirve esa página con CSP `sandbox` y Chrome
   bloquea sin avisar la descarga automática (sin clic del usuario). Pasó en la primera prueba buena.
   La pantalla final resume páginas, tramos, si hubo OCR y las sustituciones por tipo.

## Cómo funciona

| Paso | Detalle |
|---|---|
| Troceo | El formulario sube el PDF **como fichero** a `anonimizador /trocear`, que guarda en disco **un PDF independiente por tramo de 25 páginas** (cada página solo con las imágenes que dibuja) y devuelve un id |
| Envío a docling | `anonimizador /trozos/{id}/{n}/docling` lee el tramo y lo manda a docling; n8n solo recibe el `task_id`. Al final, `DELETE /trozos/{id}` (y los huérfanos caducan a las 6 h) |
| OCR | Sondeo de las 5 primeras páginas sin OCR: con menos de 200 caracteres se trata como escaneado (igual que en la ingesta del helpdesk) |
| docling | Cada tramo va en modo asíncrono (`/v1/convert/source/async`) y se consulta su estado cada 15 s, con un máximo de 20 min por tramo |
| Unión | Markdown en orden, con `<!-- páginas a-b -->` entre tramos. **Si falta un tramo, el fichero lo avisa en la primera línea** y la pantalla final también |
| Anonimizar | `anonimizador /anonimizar` (abajo) |

Imágenes: `image_export_mode: placeholder`. El resultado es texto, y las imágenes podrían
llevar datos personales que no se anonimizan.

Ejecuciones: el flujo **no guarda las ejecuciones correctas** (`saveDataSuccessExecution: none`),
porque llevarían el documento original. Las fallidas sí se guardan, para poder depurar.

### Por qué los PDF no pasan por n8n

Dos ejecuciones seguidas (12/11) fallaron en el tramo 7 de 9 con `Task request timed out`. Con el
PDF y los tramos en base64 dentro de la ejecución (~40 MB), cada nodo Code tardaba más en recibir
sus datos y el runner no aceptaba la tarea en 60 s. Ahora la respuesta de `/trocear` que guarda
n8n ocupa unos 670 bytes. No se usa `kind: http` de docling para que se descargue los tramos:
rechaza las URL de la red interna ("URL is not allowed", protección SSRF), y no conviene abrirla.

Los mensajes del runner "Runner process exited on idle timeout" **son normales** en esta
configuración: salen siempre, también con el runner sano. No confundir con el runner huérfano.

### Por qué se trocea el PDF y no se usa `page_range`

Primera prueba real (12/11, PDF de Eventalista de 224 páginas hecho con LibreOffice, 16 MB): el
kernel mató docling por memoria dos veces (4,8 GB, `exit 137`), **incluso en el sondeo de 5 páginas**.
Todas las páginas compartían un diccionario de recursos con las **228 imágenes** del documento,
aunque cada una dibuja 0 o 1. Al trocear con pypdf y dejar en cada página solo los `XObject` que
usa su contenido, los tramos ocupan entre 0,6 y 3 MB. El más pesado (52 imágenes) se convierte en
22 s con un pico de 2 GB. Ojo al tocar `trocear.py`: un `ContentStream` de pypdf es *falsy*
(se comporta como un diccionario vacío), así que hay que compararlo con `is not None`.

## Anonimizador (`api/`)

FastAPI + [Presidio](https://microsoft.github.io/presidio/) + spaCy `es_core_news_md`. Todo se ejecuta
dentro del contenedor, sin llamadas fuera.

| Dato | Cómo se detecta |
|---|---|
| Términos del usuario | Búsqueda literal sin distinguir mayúsculas ni tildes, palabra completa → `[ELIMINADO]` |
| DNI, NIE, pasaporte | Presidio (`EsNif`, `EsNie`, `EsPassport`), con validación de la letra |
| CIF | Patrón propio con validación del dígito de control |
| Teléfono | Presidio + `phonenumbers` con región ES; los internacionales con `+` también |
| Email, IBAN, tarjeta, URL, IP | Presidio (IBAN y tarjeta con validación) |
| Dirección | Patrón propio: tipo de vía + nombre + número, y el CP y la localidad si van detrás |
| Personas | (a) nombre de pila de `api/nombres.txt` + 1-3 apellidos con mayúscula (también TODO EN MAYÚSCULAS); (b) NER de spaCy, filtrado |
| Lugares, organizaciones | NER de spaCy (desmarcados por defecto) |

Cada valor distinto recibe una etiqueta estable (`[PERSONA_1]`, `[TELEFONO_2]`...) y después **se busca
literalmente en todo el texto**: si el detector lo encuentra una vez, se sustituye en todas sus
apariciones.

**Filtros de spaCy para personas.** Se añadieron porque, sin ellos, el manual Yamaha daba
**1.259 sustituciones**: "Estilo", "Mezclador" y "Yamaha" salían como personas. Con ellos quedan 84,
casi todas nombres reales de los créditos de licencias. Los filtros:

- al menos dos palabras;
- todas con mayúscula inicial;
- sin mezclar palabras en mayúsculas con palabras normales ("Botones ENDING");
- se descarta si todas sus palabras salen también en minúscula en el documento ("Estilo"/"estilo");
- si el tramo cruza una celda de tabla (`|`), cada celda se evalúa por separado.

Límite conocido: un apellido suelto ("el Sr. Pérez") solo se sustituye si antes apareció el nombre
completo. Revisar siempre el resultado antes de compartirlo.

```sh
python3 pruebas/test_anonimizar.py      # necesita presidio-analyzer y es_core_news_md
```

## Desplegar

1. **Hecho (12/11):** la App `anonimizador` de Easypanel (`ia-support`, origen *Upload*, build por
   *Dockerfile*, sin dominio ni puertos). n8n la llama por `http://ia-support_anonimizador:8000`.
   Se creó por la API: `POST /api/trpc/services.app.createService` y luego `deployService`, en
   `127.0.0.1:3000` del servidor con `Authorization: Bearer <token>`.
2. `scripts/desplegar.sh` (o `api` / `n8n` por separado). El flujo se genera con
   `n8n/build_workflow.py`: **no se edita a mano** el JSON.

Al desplegar `n8n` se reinician n8n **y** `n8n-runner`: si solo se reinicia n8n, el runner se queda
huérfano y los nodos Code fallan (ver `docker-ia-support/vps/README.md`, "Trampas del VPS").
