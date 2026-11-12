"""Genera el flujo n8n "Docling - Convertir y anonimizar" en n8n/workflows/.

    python3 n8n/build_workflow.py

Formulario: https://ia-support-n8n.kw2y1s.easypanel.host/form/docling-anonimizar

1. Página 1: se sube el PDF y se elige si anonimizar.
2. Página 2 (solo si se anonimiza): términos concretos a eliminar y qué datos personales detectar.
3. El formulario sube el PDF como fichero al servicio `anonimizador`, que lo trocea en PDFs independientes de PAGINAS_TRAMO páginas,
   cada página solo con las imágenes que dibuja (ver api/trocear.py: con page_range sobre el
   original, un PDF de LibreOffice de 224 páginas tumbaba docling por memoria). Cada tramo va a
   docling en modo asíncrono consultando el estado, y al final se unen.
4. Si se pidió, el texto pasa por el servicio `anonimizador` (Presidio + spaCy, sin LLM).
5. La pantalla final tiene un botón para descargar el .md y una vista previa. Si falta algún tramo, el fichero lo dice arriba, y la pantalla final también.

No se editan a mano los JSON de n8n/workflows/: se regeneran con este script.
"""
import json
import os

RAIZ = os.path.dirname(os.path.abspath(__file__))
ID = "DoclingAnonim001"
DOCLING = "http://ia-support_docling:5001"
ANON = "http://ia-support_anonimizador:8000"
CRED_BASIC = {"httpBasicAuth": {"id": "AlbIaBasicAuth01", "name": "Albaranes IA - Basic Auth"}}
PAGINAS_TRAMO = 25
ESPERA_S = 15          # entre consultas de estado a docling
MAX_CONSULTAS = 80     # 80 x 15 s = 20 min por tramo antes de darlo por perdido
UMBRAL_OCR = 200       # caracteres en las 5 primeras páginas sin OCR; por debajo, es escaneado

# Etiqueta en el formulario -> clave en el servicio (anonimizador/anonimizar.py: CATEGORIAS)
CATEGORIAS = [
    ("Nombres de personas", "personas", True),
    ("Teléfonos", "telefonos", True),
    ("Emails", "emails", True),
    ("DNI / NIE / CIF / pasaporte", "documentos", True),
    ("Cuentas bancarias y tarjetas", "bancarios", True),
    ("Direcciones postales", "direcciones", True),
    ("Lugares (ciudades, provincias...)", "lugares", False),
    ("Organizaciones y empresas", "organizaciones", False),
    ("Webs e IPs", "web", False),
]


class Flujo:
    def __init__(self, id_, nombre):
        self.id, self.nombre, self.nodos, self.con = id_, nombre, [], {}

    def nodo(self, nombre, tipo, version, params, pos, **extra):
        self.nodos.append({"id": f"{self.id}-{len(self.nodos):02d}", "name": nombre, "type": tipo,
                           "typeVersion": version, "position": list(pos), "parameters": params, **extra})
        return nombre

    def unir(self, origen, destino, salida=0):
        m = self.con.setdefault(origen, {"main": []})["main"]
        while len(m) <= salida:
            m.append([])
        m[salida].append({"node": destino, "type": "main", "index": 0})

    def json(self):
        return {"id": self.id, "name": self.nombre, "nodes": self.nodos, "connections": self.con,
                "active": False, "pinData": {},
                # Los documentos llevan datos personales: no se guardan las ejecuciones correctas.
                "settings": {"executionOrder": "v1", "binaryMode": "separate",
                             "saveDataSuccessExecution": "none", "saveManualExecutions": False}}


def code(f, nombre, js, pos):
    return f.nodo(nombre, "n8n-nodes-base.code", 2, {"jsCode": js.strip()}, pos)


def http(f, nombre, metodo, url, pos, body=None, timeout=60000, continuar=False):
    p = {"method": metodo, "url": url, "options": {"timeout": timeout}}
    if body:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify(" + body + ") }}"})
    kw = {"onError": "continueRegularOutput"} if continuar else {}
    return f.nodo(nombre, "n8n-nodes-base.httpRequest", 4.2, p, pos, **kw)


def si(f, nombre, expr, pos):
    return f.nodo(nombre, "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": "c1", "leftValue": "={{ " + expr + " }}", "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]},
        "looseTypeValidation": True, "options": {}}, pos)


def fin_texto(f, nombre, titulo, mensaje, pos):
    return f.nodo(nombre, "n8n-nodes-base.form", 2.4, {
        "operation": "completion", "respondWith": "text", "completionTitle": titulo,
        "completionMessage": mensaje, "options": {}}, pos, webhookId=f"docling-anonimizar-{nombre}")


TROCEO = "$('Trocear PDF').first().json"
NOMBRE = "($('Subir documento').first().json.documento?.filename || 'documento.pdf')"


def construir():
    f = Flujo(ID, "Docling - Convertir y anonimizar")

    # ---- formulario ----------------------------------------------------------------------
    f.nodo("Subir documento", "n8n-nodes-base.formTrigger", 2.4, {
        "authentication": "basicAuth",
        "formTitle": "Convertir PDF con docling",
        "formDescription": (f"Sube un PDF (también escaneado). Se convierte a texto en tramos de "
                            f"{PAGINAS_TRAMO} páginas, así que admite documentos largos: cuenta con "
                            "unos minutos por cada 100 páginas. Al terminar se descarga un fichero Markdown."),
        "formFields": {"values": [
            {"fieldLabel": "Documento PDF", "fieldName": "documento", "fieldType": "file",
             "multipleFiles": False, "acceptFileTypes": ".pdf", "requiredField": True},
            {"fieldLabel": "¿Anonimizar el documento?", "fieldName": "anonimizar", "fieldType": "radio",
             "fieldOptions": {"values": [{"option": "Sí"}, {"option": "No"}]}, "defaultValue": "Sí",
             "requiredField": True},
        ]},
        "responseMode": "onReceived",
        "options": {"path": "docling-anonimizar", "buttonLabel": "Continuar", "appendAttribution": False},
    }, (0, 0), webhookId="docling-anonimizar", credentials=CRED_BASIC)

    # El PDF va como fichero (multipart) al anonimizador, que lo trocea a disco y devuelve URLs:
    # así ni el PDF ni los tramos entran en los datos de la ejecución (ver api/main.py).
    f.nodo("Trocear PDF", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{ANON}/trocear?paginas_por_tramo={PAGINAS_TRAMO}",
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [
            {"parameterType": "formBinaryData", "name": "pdf", "inputDataFieldName": "documento"}]},
        "options": {"timeout": 300000}}, (220, 0), onError="continueRegularOutput")
    f.unir("Subir documento", "Trocear PDF")

    si(f, "¿PDF legible?", "Number($json.paginas) > 0", (440, 0))
    f.unir("Trocear PDF", "¿PDF legible?")
    fin_texto(f, "PDF no legible", "No se ha podido leer el PDF",
              "El fichero no parece un PDF válido (o está protegido con contraseña). Prueba con otro.",
              (660, 200))
    f.unir("¿PDF legible?", "PDF no legible", 1)

    si(f, "¿Anonimizar?", "$('Subir documento').first().json.anonimizar === 'Sí'", (660, 0))
    f.unir("¿PDF legible?", "¿Anonimizar?", 0)

    f.nodo("Qué eliminar", "n8n-nodes-base.form", 2.4, {
        "operation": "page",
        "formFields": {"values": [
            {"fieldLabel": "Términos concretos a eliminar (uno por línea)", "fieldName": "terminos",
             "fieldType": "textarea",
             "placeholder": "Nombres de clientes, proyectos, marcas, matrículas...\n"
                            "Se buscan sin distinguir mayúsculas ni tildes."},
            {"fieldLabel": "Datos personales a detectar", "fieldName": "categorias", "fieldType": "checkbox",
             "fieldOptions": {"values": [{"option": e} for e, _, _ in CATEGORIAS]},
             "defaultValue": ",".join(e for e, _, d in CATEGORIAS if d)},
        ]},
        "options": {"formTitle": "Qué anonimizar",
                    "formDescription": ("Cada dato se sustituye por una etiqueta estable: la misma persona es "
                                        "siempre [PERSONA_1], el mismo teléfono [TELEFONO_2]... Los términos "
                                        "concretos se sustituyen por [ELIMINADO]. La detección es automática "
                                        "y sin IA generativa: revisa el resultado antes de compartirlo."),
                    "buttonLabel": "Convertir"},
    }, (880, -120), webhookId="docling-anonimizar-que-eliminar")
    f.unir("¿Anonimizar?", "Qué eliminar", 0)

    mapa = json.dumps({e: k for e, k, _ in CATEGORIAS}, ensure_ascii=False)
    code(f, "Opciones de anonimización", f"""
const r = $input.first().json;
const MAPA = {mapa};
const sel = Array.isArray(r.categorias) ? r.categorias : String(r.categorias || '').split(',');
const terminos = String(r.terminos || '').split(/\\r?\\n|;/).map((t) => t.trim()).filter(Boolean);
return [{{ json: {{ anonimizar: true, terminos, categorias: sel.map((s) => MAPA[s.trim()]).filter(Boolean) }} }}];
""", (1100, -120))
    f.unir("Qué eliminar", "Opciones de anonimización")

    code(f, "Sin anonimizar", "return [{ json: { anonimizar: false, terminos: [], categorias: [] } }];", (880, 120))
    f.unir("¿Anonimizar?", "Sin anonimizar", 1)

    # ---- OCR ------------------------------------------------------------------------------
    # Igual que en la ingesta del helpdesk: 5 páginas sin OCR deciden si es escaneado.
    # El anonimizador le pasa el tramo a docling: el PDF no entra en la ejecución de n8n.
    http(f, "Sondear texto (sin OCR)", "POST", f"={ANON}/trozos/{{{{ {TROCEO}.id }}}}/1/docling?sincrono=true",
         (1320, 0), timeout=300000, continuar=True,
         body="{ to_formats: ['md'], do_ocr: false, image_export_mode: 'placeholder', page_range: [1, 5] }")
    f.unir("Opciones de anonimización", "Sondear texto (sin OCR)")
    f.unir("Sin anonimizar", "Sondear texto (sin OCR)")

    code(f, "Preparar tramos", f"""
// Un item por tramo, ya troceado y guardado por el anonimizador: docling lo descarga por URL.
const {{ paginas, tramos: trozos }} = {TROCEO};
const md = $input.first().json?.document?.md_content || '';
const texto = md.replace(/<!--[^>]*-->/g, '').replace(/\\s+/g, '').length;
// Si el sondeo falla, OCR: tardar de más es mejor que devolver un documento en blanco.
const necesita_ocr = !md || texto < {UMBRAL_OCR};
return trozos.map((t, i) => ({{ json: {{ tramo: i + 1, page_start: t.page_start, page_end: t.page_end,
  paginas, necesita_ocr, id: {TROCEO}.id }} }}));
""", (1540, 0))
    f.unir("Sondear texto (sin OCR)", "Preparar tramos")

    # ---- bucle de tramos -----------------------------------------------------------------
    f.nodo("Loop tramos", "n8n-nodes-base.splitInBatches", 3, {"options": {}}, (1980, 0))
    f.unir("Preparar tramos", "Loop tramos")

    http(f, "Enviar tramo a docling", "POST", f"={ANON}/trozos/{{{{ $json.id }}}}/{{{{ $json.tramo }}}}/docling",
         (2200, 120), timeout=300000, continuar=True,
         body="{ to_formats: ['md'], do_ocr: $json.necesita_ocr === true, image_export_mode: 'placeholder' }")
    f.unir("Loop tramos", "Enviar tramo a docling", 1)

    f.nodo("Esperar docling", "n8n-nodes-base.wait", 1.1, {"amount": ESPERA_S}, (2420, 120),
           webhookId="docling-anonimizar-esperar")
    f.unir("Enviar tramo a docling", "Esperar docling")

    http(f, "Comprobar estado", "GET",
         f"={DOCLING}/v1/status/poll/{{{{ $('Enviar tramo a docling').item.json.task_id }}}}", (2640, 120),
         continuar=True)
    f.unir("Esperar docling", "Comprobar estado")

    code(f, "Evaluar estado", f"""
const envio = $('Enviar tramo a docling').item.json;
const tries = ($('Esperar docling').item.json.tries || 0) + 1;
const status = $json.task_status;
const sin_tarea = !envio.task_id;  // docling rechazó el envío
return [{{ json: {{
  task_status: status, tries, sin_tarea,
  agotado: tries >= {MAX_CONSULTAS} && status !== 'success' && status !== 'failure',
  done: sin_tarea || status === 'success' || status === 'failure' || tries >= {MAX_CONSULTAS},
  error: sin_tarea ? (envio.error?.message || JSON.stringify(envio).slice(0, 300)) : null,
}} }}];
""", (2860, 120))
    f.unir("Comprobar estado", "Evaluar estado")

    si(f, "¿Terminado?", "$json.done", (3080, 120))
    f.unir("Evaluar estado", "¿Terminado?")
    f.unir("¿Terminado?", "Esperar docling", 1)

    http(f, "Obtener resultado", "GET",
         f"={DOCLING}/v1/result/{{{{ $('Enviar tramo a docling').item.json.task_id }}}}", (3300, 40),
         timeout=120000, continuar=True)
    f.unir("¿Terminado?", "Obtener resultado", 0)

    code(f, "Guardar tramo", """
const t = $('Loop tramos').item.json;
const ev = $('Evaluar estado').item.json;
const r = $json;
const ok = r.status === 'success' || r.status === 'partial_success';
let md = ok ? (r.document?.md_content || '') : '';
md = md.replace(/!\\[[^\\]]*\\]\\(data:[^)]*\\)/g, '').replace(/<img[^>]*src="data:[^"]*"[^>]*>/g, '');
let motivo = null;
if (!ok) {
  motivo = ev.sin_tarea ? `docling rechazó el envío: ${ev.error}`
    : ev.agotado ? 'docling no terminó a tiempo'
    : (r.errors?.map((e) => e.error_message || e.message).join('; ') || r.error?.message || `estado ${r.status || ev.task_status}`);
}
return [{ json: { tramo: t.tramo, page_start: t.page_start, page_end: t.page_end,
  ok, md_content: md, motivo, segundos: r.processing_time ?? null } }];
""", (3520, 40))
    f.unir("Obtener resultado", "Guardar tramo")
    f.unir("Guardar tramo", "Loop tramos")

    # ---- unir, anonimizar y devolver ------------------------------------------------------
    code(f, "Combinar tramos", """
const tramos = $input.all().map((i) => i.json).sort((a, b) => a.page_start - b.page_start);
const opc = $('Opciones de anonimización').isExecuted
  ? $('Opciones de anonimización').first().json : { anonimizar: false, terminos: [], categorias: [] };
const md = tramos.map((t) => t.ok
  ? `<!-- páginas ${t.page_start}-${t.page_end} -->\\n\\n${t.md_content}`
  : `<!-- páginas ${t.page_start}-${t.page_end}: FALTAN -->`).join('\\n\\n');
const fallidos = tramos.filter((t) => !t.ok);
return [{ json: { ...opc, texto: md, fallidos, paginas: $('Trocear PDF').first().json.paginas,
  num_tramos: tramos.length, ocr: $('Preparar tramos').first().json.necesita_ocr } }];
""", (2200, -160))
    f.unir("Loop tramos", "Combinar tramos", 0)

    http(f, "Borrar tramos", "DELETE", f"={ANON}/trozos/{{{{ {TROCEO}.id }}}}", (2420, -340), continuar=True)
    f.unir("Combinar tramos", "Borrar tramos")

    si(f, "¿Anonimizar texto?", "$('Combinar tramos').first().json.anonimizar === true && $('Combinar tramos').first().json.texto.length > 0", (2420, -160))
    f.unir("Combinar tramos", "¿Anonimizar texto?")

    http(f, "Anonimizar", "POST", f"{ANON}/anonimizar", (2640, -260), timeout=900000,
         body="(({ texto, terminos, categorias }) => ({ texto, terminos, categorias }))($('Combinar tramos').first().json)")
    f.unir("¿Anonimizar texto?", "Anonimizar", 0)

    code(f, "Componer resultado", f"""
const c = $('Combinar tramos').first().json;
const a = $('Anonimizar').isExecuted ? $('Anonimizar').first().json : null;
const nombre = {NOMBRE}.replace(/\\.pdf$/i, '');
const avisos = c.fallidos.map((t) => `> **Atención:** faltan las páginas ${{t.page_start}}-${{t.page_end}} (${{t.motivo}}).`);
const contenido = (avisos.length ? avisos.join('\\n') + '\\n\\n' : '') + (a ? a.texto : c.texto);
const partes = [`${{c.paginas}} páginas en ${{c.num_tramos}} tramos de {PAGINAS_TRAMO}` + (c.ocr ? ', con OCR' : '') + '.'];
if (a) {{
  const r = Object.entries(a.resumen).map(([k, n]) => `${{k.toLowerCase()}}: ${{n}}`).join(', ');
  partes.push(a.reemplazos ? `Anonimizado: ${{a.reemplazos}} sustituciones (${{r}}).` : 'Anonimizado: no se ha encontrado nada que sustituir.');
}}
if (c.fallidos.length) partes.push(`ATENCIÓN: faltan ${{c.fallidos.length}} tramo(s), están indicados al principio del fichero.`);
const fichero = nombre + (a ? '_anonimizado' : '') + '.md';
// Página final con botón de descarga. NO se usa "Return Binary File" del nodo Form: n8n sirve la
// página con CSP sandbox y Chrome bloquea la descarga automática (sin clic del usuario) sin avisar.
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[c]));
const b64 = Buffer.from(contenido, 'utf8').toString('base64');
// Fragmento: n8n lo inserta dentro del <body> de su plantilla (form-trigger-completion).
const html = `<style>
 body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f5f5f7;color:#1d1d1f;margin:0;padding:24px 16px}}
 .caja{{max-width:820px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
 h1{{font-size:22px;margin:0 0 8px}} p{{line-height:1.5;margin:0 0 20px;color:#444}}
 a.boton{{display:inline-block;background:#0b6bcb;color:#fff;text-decoration:none;padding:12px 20px;border-radius:8px;font-weight:600}}
 a.boton:hover{{background:#095aa8}}
 details{{margin-top:24px}} summary{{cursor:pointer;color:#0b6bcb}}
 pre{{white-space:pre-wrap;word-break:break-word;background:#fafafa;border:1px solid #e5e5e5;border-radius:8px;padding:12px;font-size:12px;max-height:420px;overflow:auto}}
</style><div class="caja">
<h1>Documento listo</h1><p>${{esc(partes.join(' '))}}</p>
<a class="boton" download="${{esc(fichero)}}" href="data:text/markdown;charset=utf-8;base64,${{b64}}">Descargar ${{esc(fichero)}}</a>
<details><summary>Ver el principio del texto</summary><pre>${{esc(contenido.slice(0, 6000))}}${{contenido.length > 6000 ? '\\n…' : ''}}</pre></details>
</div>`;
return [{{ json: {{ fichero, mensaje: partes.join(' '), html }} }}];
""", (2860, -160))
    f.unir("Anonimizar", "Componer resultado")
    f.unir("¿Anonimizar texto?", "Componer resultado", 1)

    f.nodo("Descargar", "n8n-nodes-base.form", 2.4, {
        "operation": "completion", "respondWith": "showText",
        "responseText": "={{ $json.html }}"}, (3080, -160), webhookId="docling-anonimizar-descargar")
    f.unir("Componer resultado", "Descargar")
    return f


if __name__ == "__main__":
    os.makedirs(os.path.join(RAIZ, "workflows"), exist_ok=True)
    ruta = os.path.join(RAIZ, "workflows", "docling_anonimizar.json")
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(construir().json(), fh, ensure_ascii=False, indent=1)
    print(ruta)
