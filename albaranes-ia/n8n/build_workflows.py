"""Genera los flujos de n8n de albaranes-ia en n8n/workflows/.

    python3 n8n/build_workflows.py

Las páginas HTML se mantienen en web/ y se incrustan en los nodos Code.
Hosts internos (red easypanel-ia-support) y credenciales de n8n por id:
cambiar las constantes de abajo si se despliega en otro sitio.
"""
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "http://ia-support_albaranes-api:8000"
OCR = "http://ia-support_barcode-ocr:8000"
N8N_INTERNO = "http://127.0.0.1:5678"  # el propio n8n, para reutilizar el flujo de ingesta
CRED_BASIC = {"httpBasicAuth": {"id": "AlbIaBasicAuth01", "name": "Albaranes IA - Basic Auth"}}
CRED_IA = {"httpHeaderAuth": {"id": "t9FUZIt3bCUbzN4K", "name": "Openrouter Header Auth account"}}
PATRON_ALBARAN = r"^[A-Z0-9]+/(OUT|IN|INT)/\d+$"
HTTP_FOTOS = 4.1  # versión del nodo HTTP que envía las fotos: ver campos_fotos()
MAX_FOTOS = 10  # fotos (páginas) por albarán: igual que MAX_PAGINAS en albaranes-api


def web(nombre):
    return open(os.path.join(RAIZ, "web", nombre), encoding="utf-8").read()


class Flujo:
    def __init__(self, id_, nombre):
        self.id, self.nombre, self.nodos, self.con = id_, nombre, [], {}
        self.x, self.y = 0, 0

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
                "active": False, "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all"},
                "pinData": {}}


def webhook(f, nombre, metodo, ruta, pos):
    return f.nodo(nombre, "n8n-nodes-base.webhook", 2, {
        "httpMethod": metodo, "path": ruta, "authentication": "basicAuth",
        "responseMode": "responseNode", "options": {}}, pos,
        # n8n publica las rutas con parámetros como /webhook/<webhookId>/<ruta>: con el mismo webhookId
        # "albaranes" todas quedan bajo /webhook/albaranes/ (no chocan: difieren en método o longitud).
        webhookId="albaranes" if ":" in ruta else f"albaranes-{ruta.replace('/', '-')}-{metodo.lower()}",
        credentials=CRED_BASIC)


def http(f, nombre, metodo, url, pos, body=None, completa=False, timeout=60000, error=None, **extra):
    """body: expresión n8n que devuelve un objeto (se manda como JSON)."""
    p = {"method": metodo, "url": url, "options": {"timeout": timeout}}
    if body is not None:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify(" + body + ") }}"})
    if completa:
        p["options"]["response"] = {"response": {"fullResponse": True, "neverError": True}}
    p.update(extra.pop("params", {}))
    kw = {}
    if error:
        kw["onError"] = error
    return f.nodo(nombre, "n8n-nodes-base.httpRequest", 4.2, p, pos, **kw, **extra)


def campos_fotos():
    """Multipart con todas las fotos del item. El webhook las deja como foto0, foto1… y el nodo
    HTTP solo admite un fichero por campo, así que hay MAX_FOTOS campos fijos (foto_1…): los que
    quedan sin fichero (nombre vacío) n8n no los envía, pero solo en el nodo HTTP 4.1 (HTTP_FOTOS);
    en 4.2 un campo vacío rompe la petición. `paginas` permite a la API detectar que sobraban fotos."""
    orden = ("Object.keys($binary || {}).sort((a, b) => (parseInt(a.replace(/\\D/g, '')) || 0) - "
             "(parseInt(b.replace(/\\D/g, '')) || 0))")
    return [{"parameterType": "formBinaryData", "name": f"foto_{i + 1}",
             "inputDataFieldName": "={{ " + orden + f"[{i}] || '' }}}}"} for i in range(MAX_FOTOS)] + [
        {"name": "paginas", "value": "={{ String(Object.keys($binary || {}).length) }}"}]


def ia(f, nombre, peticion, pos, timeout=180000):
    """Llamada al proveedor de IA con la petición que prepara la API (expresión `peticion`)."""
    return http(f, nombre, "POST", "={{ " + peticion + ".url }}", pos, body=peticion + ".body", timeout=timeout,
                error="continueErrorOutput", params={"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
                                                    "sendHeaders": True, "specifyHeaders": "json",
                                                    "jsonHeaders": "={{ JSON.stringify(" + peticion + ".cabeceras || {}) }}"},
                credentials=CRED_IA)


def si(f, nombre, condicion, pos):
    """Nodo If con una condición booleana (expresión n8n)."""
    return f.nodo(nombre, "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                       "combinator": "and", "conditions": [{
                           "id": "c", "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                           "leftValue": "={{ " + condicion + " }}", "rightValue": ""}]},
        "options": {}}, pos)


def code(f, nombre, js, pos):
    return f.nodo(nombre, "n8n-nodes-base.code", 2, {"mode": "runOnceForAllItems", "jsCode": js}, pos)


def responder(f, nombre, pos):
    return f.nodo(nombre, "n8n-nodes-base.respondToWebhook", 1.1, {
        "respondWith": "text", "responseBody": "={{ $json.cuerpo }}",
        "options": {"responseCode": "={{ $json.codigo }}",
                    "responseHeaders": {"entries": [{"name": "Content-Type", "value": "={{ $json.tipo }}"},
                                                    {"name": "Cache-Control", "value": "no-store"}]}}}, pos)


# Utilidades JS comunes a los nodos Code
JS_COMUN = r"""
const incrustar = (plantilla, datos, extra = {}) => {
  let h = plantilla.replace('__DATOS__', JSON.stringify(datos).replace(/</g, '\\u003c'));
  for (const [k, v] of Object.entries(extra)) h = h.split(k).join(v);
  return h;
};
const html = (cuerpo, codigo = 200) => [{ json: { cuerpo, codigo, tipo: 'text/html; charset=utf-8' } }];
const json = (obj, codigo = 200) => [{ json: { cuerpo: JSON.stringify(obj), codigo, tipo: 'application/json; charset=utf-8' } }];
const detalle = (r) => {
  if (!r) return 'Error desconocido';
  const b = r.body ?? r;
  if (b && typeof b === 'object') return typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail ?? b);
  return String(b);
};
"""


# ============================================================ Ingesta
def ingesta():
    f = Flujo("AlbIaIngesta0001", "Albaranes IA - Ingesta")
    plantilla_resultado = json.dumps(web("resultado.html"))

    # Formulario de subida
    w0 = webhook(f, "Formulario de subida", "GET", "albaranes/subir", (0, -300))
    c0 = code(f, "Página de subida", "return [{ json: { cuerpo: " + json.dumps(web("subir.html")) +
              ", codigo: 200, tipo: 'text/html; charset=utf-8' } }];", (220, -300))
    r0 = responder(f, "Responder formulario", (440, -300))
    f.unir(w0, c0); f.unir(c0, r0)

    w = webhook(f, "Subir foto", "POST", "albaranes/ingesta", (0, 0))
    g = f.nodo("Guardar incidencia", "n8n-nodes-base.httpRequest", HTTP_FOTOS, {
        "method": "POST", "url": f"{API}/incidencias", "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": campos_fotos() + [
            {"name": "reprocesar", "value": "={{ String(($json.query || {}).reprocesar || ($json.body || {}).reprocesar || 'false') }}"},
            {"name": "tipo", "value": "={{ String(($json.query || {}).tipo || ($json.body || {}).tipo || 'propio') }}"},
            {"name": "referencias", "value": "={{ String(($json.query || {}).referencias || ($json.body || {}).referencias || '') }}"}]},
        "options": {"timeout": 60000}}, (220, 0), onError="continueErrorOutput")
    f.unir(w, g)

    dup = f.nodo("¿Ya procesada?", "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                       "combinator": "and", "conditions": [{
                           "id": "dup", "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                           "leftValue": "={{ $json.duplicada === true && !['recibida', 'procesando'].includes($json.estado) }}",
                           "rightValue": ""}]},
        "options": {}}, (440, 0))
    f.unir(g, dup)

    fe = http(f, "Ficha existente", "GET", f"={API}/incidencias/{{{{ $json.id }}}}", (660, -160))
    f.unir(dup, fe, 0)
    rd = code(f, "Respuesta duplicada", JS_COMUN + "const P = " + plantilla_resultado + r""";
const i = $input.first().json;
const quiereHtml = String(($('Subir foto').first().json.query || {}).html || '') === '1';
const d = i.decision || {};
const datos = {
  titulo: 'Foto ya procesada', duplicada: true, incidencia_id: i.id, estado: i.estado, marca: i.marca,
  albaran: i.albaran_numero, cliente: (((i.erp || {}).albaranes || [i.erp || {}])[0] || {}).cliente?.nombre, origen_numero: i.origen_numero,
  paginas: (i.paginas || []).length, tipo: i.tipo, emisor: ((i.lectura || {}).emisor || {}).nombre, documento: (i.lectura || {}).numero_documento,
  tabla: (d.lineas || []).map(l => ({ articulo: (l.referencia ? '[' + l.referencia + '] ' : '') + l.producto,
    erp: l.erp, ia: l.cantidad_final, confianza: l.confianza, estado: l.estado, motivos: (l.motivos || []).join(', ') })),
  error: i.error, enlace: '/webhook/albaranes/revision/' + i.id, enlace_texto: 'Abrir revisión',
  revision_url: d.revision_url,
};
return quiereHtml ? html(incrustar(P, datos, { '__BASE__': '/webhook/albaranes/' })) : json(datos);""", (880, -160))
    f.unir(fe, rd)

    # Código de barras: se busca en cada foto (un item por página) y se queda el primero.
    propio = si(f, "¿Albarán propio?", "($('Guardar incidencia').first().json.tipo || 'propio') === 'propio'", (500, 80))
    f.unir(dup, propio, 1)
    pags = code(f, "Páginas", r"""const n = $('Guardar incidencia').first().json.paginas || 1;
return Array.from({ length: n }, (_, i) => ({ json: { pagina: i + 1 } }));""", (550, 80))
    f.unir(propio, pags, 0)
    foto = http(f, "Foto normalizada", "GET", f"={API}/incidencias/{{{{ $('Guardar incidencia').first().json.id }}}}/imagen?pagina={{{{ $json.pagina }}}}",
                (660, 80), params={"options": {"timeout": 60000, "response": {"response": {"responseFormat": "file", "outputPropertyName": "foto"}}}})
    f.unir(pags, foto)
    ocr = f.nodo("Leer código de barras", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": f"{OCR}/decode", "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "patron", "value": PATRON_ALBARAN}]},
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [{"parameterType": "formBinaryData", "name": "foto", "inputDataFieldName": "foto"}]},
        "options": {"timeout": 60000}}, (880, 80), onError="continueRegularOutput")
    f.unir(foto, ocr)
    elegir = code(f, "Elegir código", r"""// Primer código leído; `codigos` (distintos) sirve para avisar de fotos de otro albarán.
const lecturas = $input.all().map((it, i) => ({ pagina: i + 1, ...it.json }));
const codigos = [...new Set(lecturas.map(l => l.codigo).filter(Boolean))];
return [{ json: { codigo: codigos[0] || '', codigos, lecturas } }];""", (990, 80))
    f.unir(ocr, elegir)

    hay = f.nodo("¿Hay código de barras?", "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                       "combinator": "and", "conditions": [{
                           "id": "cod", "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
                           "leftValue": "={{ $json.codigo || '' }}", "rightValue": ""}]},
        "options": {}}, (1100, 80))
    f.unir(elegir, hay)

    set_cod = f.nodo("Número por código", "n8n-nodes-base.set", 3.4, {
        "mode": "raw", "jsonOutput": "={{ JSON.stringify({ numero: $json.codigo, origen: 'codigo_barras', lectura_codigo: $json }) }}",
        "options": {}}, (1320, -20))
    f.unir(hay, set_cod, 0)

    # Número por visión en dos intentos: primero solo la primera foto, pequeña y con el modelo ligero
    # (VISION_MODEL_NUMERO); si no lo lee, todas las fotos a tamaño normal con el modelo de la lectura.
    pn = http(f, "Petición número", "POST", f"{API}/vision/peticion", (1320, 180),
              body="{ incidencia_id: $('Guardar incidencia').first().json.id, tipo: 'numero', intento: 1 }",
              error="continueErrorOutput")
    f.unir(hay, pn, 1)
    ian = ia(f, "IA: número de albarán", "$json", (1540, 180), timeout=120000)
    f.unir(pn, ian)
    itn = http(f, "Interpretar número", "POST", f"{API}/vision/interpretar", (1760, 180),
               body="{ tipo: 'numero', proveedor: $('Petición número').first().json.proveedor, respuesta: $json }",
               error="continueErrorOutput")
    f.unir(ian, itn)
    leido = si(f, "¿Número leído?", "!!($json.lectura.numero_albaran || '').trim()", (1980, 180))
    f.unir(itn, leido)
    pn2 = http(f, "Petición número 2", "POST", f"{API}/vision/peticion", (1980, 360),
               body="{ incidencia_id: $('Guardar incidencia').first().json.id, tipo: 'numero', intento: 2 }",
               error="continueErrorOutput")
    f.unir(leido, pn2, 1)
    ian2 = ia(f, "IA: número de albarán 2", "$json", (2200, 360), timeout=120000)
    f.unir(pn2, ian2)
    itn2 = http(f, "Interpretar número 2", "POST", f"{API}/vision/interpretar", (2420, 360),
                body="{ tipo: 'numero', proveedor: $('Petición número 2').first().json.proveedor, respuesta: $json }",
                error="continueErrorOutput")
    f.unir(ian2, itn2)
    # ia_numero: modelo, tokens y coste de cada intento (en lectura_codigo, que ya se guarda).
    intentos = ("[$('Interpretar número').first().json.lectura].concat($('Interpretar número 2').isExecuted ? "
                "[$('Interpretar número 2').first().json.lectura] : []).map(l => Object.assign({ numero: l.numero_albaran }, l.meta))")
    set_vis = f.nodo("Número por visión", "n8n-nodes-base.set", 3.4, {
        "mode": "raw", "jsonOutput": "={{ JSON.stringify({ numero: $json.lectura.numero_albaran || '', origen: 'vision', "
        "lectura_codigo: Object.assign({}, $('Elegir código').first().json, { ia_numero: " + intentos + " }), lectura_numero: $json.lectura }) }}",
        "options": {}}, (2200, 180))
    f.unir(leido, set_vis, 0); f.unir(itn2, set_vis)

    erp = http(f, "Albarán en el ERP", "GET", f"={API}/erp/albaran", (2200, 80), error="continueErrorOutput",
               params={"sendQuery": True, "queryParameters": {"parameters": [{"name": "numero", "value": "={{ $json.numero }}"}]}})
    f.unir(set_cod, erp); f.unir(set_vis, erp)

    # Otros reconocimientos del mismo albarán (otra foto): solo es un aviso, no para el flujo.
    prev = http(f, "Reconocimientos previos", "GET", f"={API}/incidencias", (2310, -100), error="continueRegularOutput",
                params={"sendQuery": True, "queryParameters": {"parameters": [
                    {"name": "albaran", "value": "={{ $json.numero }}"}, {"name": "tipo", "value": "propio"},
                    {"name": "excluir", "value": "={{ $('Guardar incidencia').first().json.id }}"}]}})
    f.unir(erp, prev)

    pl = http(f, "Petición lectura", "POST", f"{API}/vision/peticion", (2420, 80),
              body="{ incidencia_id: $('Guardar incidencia').first().json.id, tipo: 'lectura', albaran: $('Albarán en el ERP').first().json }",
              error="continueErrorOutput")
    f.unir(prev, pl)
    ial = ia(f, "IA: leer albarán", "$json", (2640, 80))
    f.unir(pl, ial)
    itl = http(f, "Interpretar lectura", "POST", f"{API}/vision/interpretar", (2860, 80),
               body="{ tipo: 'lectura', proveedor: $('Petición lectura').first().json.proveedor, respuesta: $json }",
               error="continueErrorOutput")
    f.unir(ial, itl)

    decidir = code(f, "Decidir", r"""// Reglas: cada línea del ERP se compara con la lectura de la IA.
const ins = $input.first().json;
const lect = ins.lectura, reglas = ins.reglas;
const erp = $('Albarán en el ERP').first().json;
const inc = $('Guardar incidencia').first().json;
const num = ($('Número por código').isExecuted ? $('Número por código') : $('Número por visión')).first().json;
const umbral = reglas.umbral, varMax = reglas.variacion_sospechosa;
const npag = inc.paginas || 1;
const leidas = lect.lineas || [];
const ids = new Set(erp.lineas.map(l => l.id));
const lineas = erp.lineas.map(l => {
  const r = leidas.find(x => x.move_id === l.id);
  const motivos = [];
  let final = r ? r.cantidad_final : null;
  if (!r) motivos.push('no_leida');
  else {
    if (final == null) motivos.push(r.tachado ? 'tachon_ilegible' : 'no_leida');
    if (r.confianza < umbral) motivos.push('baja_confianza');
    if (r.dudoso) motivos.push('dudosa');
    if (final != null && final !== l.cantidad) {
      motivos.push('modificada');
      if (l.cantidad > 0 && Math.abs(final - l.cantidad) / l.cantidad > varMax) motivos.push('variacion_sospechosa');
      if (final > l.cantidad_pedida) motivos.push('supera_pedido');
    }
    if (r.tachado && final != null && final === l.cantidad) motivos.push('tachado_sin_cambio');
  }
  return {
    linea_id: l.id, referencia: l.referencia, producto: l.producto, unidad: l.unidad,
    pedida: l.cantidad_pedida, erp: l.cantidad,
    impreso: r ? r.impreso : null, tachado: r ? r.tachado : false, manuscrito: r ? r.manuscrito : null,
    cantidad_final: final, confianza: r ? r.confianza : null, dudoso: r ? r.dudoso : true,
    motivo_ia: r ? r.motivo : null, bbox: r ? r.bbox : null,
    pagina: r ? Math.min(Math.max(r.pagina || 1, 1), npag) : null,
    estado: motivos.length ? 'pendiente_revision' : 'verificado', motivos,
  };
});
const extras = leidas.filter(x => !ids.has(x.move_id));
const avisos = [];
if (extras.length) avisos.push(extras.length + ' línea(s) leídas que no están en el ERP');
if (lect.numero_albaran && lect.numero_albaran.replace(/\s/g, '') !== erp.numero) avisos.push('El número leído en la foto (' + lect.numero_albaran + ') no coincide con ' + erp.numero);
if (lect.calidad_imagen === 'mala') avisos.push('Calidad de imagen mala: conviene repetir la foto');
// Varias fotos: alguna puede ser de otro albarán (número impreso o código de barras distinto).
const sinEsp = s => String(s || '').replace(/\s/g, '');
const otras = npag > 1 ? (lect.paginas || []).filter(p => p.numero_albaran && sinEsp(p.numero_albaran) !== erp.numero) : [];
if (otras.length) avisos.push('Foto de otro albarán: ' + otras.map(p => 'foto ' + p.pagina + ' (' + p.numero_albaran + ')').join(', '));
const codigos = $('Elegir código').first().json.codigos || [];
if (codigos.length > 1) avisos.push('Las fotos tienen códigos de barras distintos: ' + codigos.join(', '));
const estado = lineas.every(l => l.estado === 'verificado') && !extras.length && lect.calidad_imagen !== 'mala' && avisos.length === 0
  ? 'verificado' : 'pendiente_revision';
// Aviso de reconocimientos previos del mismo albarán: se informa, pero no cambia el estado.
const previos = ($('Reconocimientos previos').first().json.resultados || [])
  .map(r => ({ id: r.id, estado: r.estado, creada: r.creada }));
const ESTADO_TXT = { recibida: 'recibido', procesando: 'procesando', verificado: 'por revisar', pendiente_revision: 'por revisar',
  error: 'con error', aprobada: 'aprobado', corregida: 'corregido', rechazada: 'rechazado', rectificada: 'rectificado en el ERP' };
const dia = c => String(c || '').slice(0, 10).split('-').reverse().join('/');
if (previos.length) avisos.push('Este albarán ya se había reconocido antes: ' +
  previos.map(r => '#' + r.id + ' del ' + dia(r.creada) + ' (' + (ESTADO_TXT[r.estado] || r.estado) + ')').join(', '));
const revision_url = (ins.url_revision || '') + '/' + inc.id;
// Original / Modificado según lo que detecta la IA (tras aprobar, la API lo recalcula con lo aprobado).
const marca = lineas.some(l => l.cantidad_final != null && l.cantidad_final !== l.erp) || extras.length ? 'modificado' : 'original';
const decision = { estado, marca, umbral, variacion_sospechosa: varMax, lineas, extras, avisos, previos, revision_url };

// Nota para el historial del albarán
const e = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f = n => n == null ? '?' : String(n).replace('.', ',');
const MOT = { modificada: 'cambiada a mano', tachon_ilegible: 'tachón sin número legible', baja_confianza: 'confianza baja',
  dudosa: 'lectura dudosa', variacion_sospechosa: 'variación grande', supera_pedido: 'supera lo pedido', no_leida: 'no leída',
  tachado_sin_cambio: 'tachado sin cambio' };
const revisar = lineas.filter(l => l.estado !== 'verificado');
let nota = '<p><b>' + (npag > 1 ? npag + ' fotos del albarán leídas' : 'Foto del albarán leída') + ' por IA</b> (reconocimiento #' + inc.id + '): <b>' +
  (marca === 'modificado' ? 'Modificado' : 'Original') + '</b>, ' +
  (estado === 'verificado' ? 'coincide con el ERP' : 'por revisar') + '.</p>';
if (revisar.length) nota += '<ul>' + revisar.map(l => '<li>' + e((l.referencia ? '[' + l.referencia + '] ' : '') + l.producto) + ': ERP ' +
  f(l.erp) + ' → foto ' + f(l.cantidad_final) + ' (' + e(l.motivos.map(m => MOT[m] || m).join(', ')) +
  (l.confianza != null ? ', confianza ' + Math.round(l.confianza * 100) + '%' : '') + ')</li>').join('') + '</ul>';
for (const a of avisos) nota += '<p>' + e(a) + '</p>';
if (estado !== 'verificado') nota += '<p>Revisar en: ' + e(revision_url) + '</p>';

return [{ json: {
  incidencia_id: inc.id, albaran_id: erp.id, nota,
  patch: { estado, albaran_numero: erp.numero, albaran_id: erp.id, origen_numero: num.origen,
           lectura_codigo: num.lectura_codigo || null, erp, lectura: lect, decision, evento: 'lectura' },
} }];""", (3080, 80))
    f.unir(itl, decidir)

    gr = http(f, "Guardar resultado", "PATCH", f"={API}/incidencias/{{{{ $json.incidencia_id }}}}", (3300, 80),
              body="$json.patch", error="continueErrorOutput")
    f.unir(decidir, gr)
    nota = http(f, "Nota en el albarán", "POST", f"={API}/erp/albaranes/{{{{ $('Decidir').first().json.albaran_id }}}}/nota",
                (3520, 80), body="{ html: $('Decidir').first().json.nota }", error="continueRegularOutput")
    f.unir(gr, nota)
    rl = code(f, "Respuesta lectura", JS_COMUN + "const P = " + plantilla_resultado + r""";
const d = $('Decidir').first().json;
const p = d.patch, dec = p.decision;
const quiereHtml = String(($('Subir foto').first().json.query || {}).html || '') === '1';
const notaOk = !$input.first().json.error;
const tabla = dec.lineas.map(l => ({ articulo: (l.referencia ? '[' + l.referencia + '] ' : '') + l.producto,
  erp: l.erp, ia: l.cantidad_final, confianza: l.confianza, estado: l.estado, motivos: l.motivos.join(', ') }));
const datos = {
  titulo: 'Lectura del albarán', incidencia_id: d.incidencia_id, estado: p.estado, marca: dec.marca, albaran: p.albaran_numero,
  cliente: (p.erp.cliente || {}).nombre, origen_numero: p.origen_numero, tabla,
  paginas: $('Guardar incidencia').first().json.paginas,
  avisos: dec.avisos.concat(notaOk ? [] : ['No se pudo añadir la nota en el albarán del ERP']),
  extras: dec.extras, revision_url: dec.revision_url, modelo: (p.lectura.meta || {}).modelo,
  tokens: (p.lectura.meta || {}).tokens,
  enlace: '/webhook/albaranes/revision/' + d.incidencia_id, enlace_texto: p.estado === 'verificado' ? 'Ver detalle' : 'Revisar ahora',
};
return quiereHtml ? html(incrustar(P, datos, { '__BASE__': '/webhook/albaranes/' })) : json(datos);""", (3740, 80))
    f.unir(nota, rl)

    # Albaranes de terceros (entrada de proveedor o entrega con el albarán del cliente): se
    # transcribe su albarán, se buscan en el ERP nuestros albaranes escritos a mano y se comparan.
    # Solo se lee el ERP: ni nota en el historial ni rectificación.
    tp = http(f, "Petición lectura terceros", "POST", f"{API}/vision/peticion", (720, -560),
              body="{ incidencia_id: $('Guardar incidencia').first().json.id, tipo: 'terceros' }", error="continueErrorOutput")
    f.unir(propio, tp, 1)
    tia = ia(f, "IA: leer albarán de terceros", "$json", (940, -560))
    f.unir(tp, tia)
    tit = http(f, "Interpretar lectura terceros", "POST", f"{API}/vision/interpretar", (1160, -560),
               body="{ tipo: 'terceros', proveedor: $('Petición lectura terceros').first().json.proveedor, respuesta: $json }",
               error="continueErrorOutput")
    f.unir(tia, tit)
    tgl = http(f, "Guardar lectura terceros", "PATCH", f"={API}/incidencias/{{{{ $('Guardar incidencia').first().json.id }}}}",
               (1380, -560), body="{ estado: 'procesando', lectura: $json.lectura, evento: 'lectura' }", error="continueErrorOutput")
    f.unir(tit, tgl)
    tb = http(f, "Buscar en el ERP", "POST", f"={API}/terceros/{{{{ $('Guardar incidencia').first().json.id }}}}/emparejar",
              (1600, -560), body="{}", error="continueErrorOutput")
    f.unir(tgl, tb)
    tsi = si(f, "¿Emparejar con IA?", "!!$json.peticion", (1820, -560))
    f.unir(tb, tsi)
    tie = ia(f, "IA: emparejar líneas", "$json.peticion", (2040, -660), timeout=120000)
    f.unir(tsi, tie, 0)
    tc = http(f, "Comparar", "POST", f"={API}/terceros/{{{{ $('Guardar incidencia').first().json.id }}}}/comparar", (2260, -660),
              body="{ busqueda: $('Buscar en el ERP').first().json, proveedor: $('Buscar en el ERP').first().json.peticion.proveedor, respuesta: $json }",
              error="continueErrorOutput")
    f.unir(tie, tc)
    tc2 = http(f, "Comparar sin IA", "POST", f"={API}/terceros/{{{{ $('Guardar incidencia').first().json.id }}}}/comparar", (2260, -460),
               body="{ busqueda: $('Buscar en el ERP').first().json }", error="continueErrorOutput")
    f.unir(tsi, tc2, 1)
    rt = code(f, "Respuesta terceros", JS_COMUN + "const P = " + plantilla_resultado + r""";
const i = $input.first().json;
const d = i.decision || {};
const quiereHtml = String(($('Subir foto').first().json.query || {}).html || '') === '1';
const datos = {
  titulo: i.tipo === 'entrada' ? 'Albarán de proveedor' : 'Albarán del cliente', incidencia_id: i.id, estado: i.estado, marca: i.marca,
  tipo: i.tipo, albaran: i.albaran_numero, emisor: ((i.lectura || {}).emisor || {}).nombre, documento: (i.lectura || {}).numero_documento,
  cliente: ((((i.erp || {}).albaranes || [])[0] || {}).cliente || {}).nombre, origen_numero: i.origen_numero,
  referencias: (i.erp || {}).referencias || [], valorado: d.valorado, paginas: $('Guardar incidencia').first().json.paginas,
  tabla: (d.lineas || []).map(l => ({ articulo: (l.referencia ? '[' + l.referencia + '] ' : '') + l.producto, erp: l.erp, ia: l.cantidad_doc,
    precio_erp: l.precio_erp, precio_doc: l.precio_doc, confianza: l.confianza, estado: l.estado, motivos: (l.motivos || []).join(', ') })),
  avisos: d.avisos || [], extras: d.extras || [], revision_url: d.revision_url, modelo: ((i.lectura || {}).meta || {}).modelo,
  enlace: '/webhook/albaranes/revision/' + i.id, enlace_texto: i.estado === 'verificado' ? 'Ver detalle' : 'Revisar ahora',
};
return quiereHtml ? html(incrustar(P, datos, { '__BASE__': '/webhook/albaranes/' })) : json(datos);""", (2480, -560))
    f.unir(tc, rt); f.unir(tc2, rt)

    # Errores: se marca la incidencia y se responde. El id y el paso se fijan con expresiones
    # first(0): "Guardar incidencia" también conecta aquí por su salida de error (vacía), y sin
    # índice n8n leería esa salida.
    idn = f.nodo("Datos del error", "n8n-nodes-base.set", 3.4, {
        "mode": "manual", "includeOtherFields": True, "options": {},
        "assignments": {"assignments": [
            {"id": "inc", "name": "incidencia_id", "type": "number",
             "value": "={{ $('Guardar incidencia').isExecuted ? ($('Guardar incidencia').first(0)?.json?.id ?? null) : null }}"},
            {"id": "paso", "name": "paso", "type": "string", "value": "={{ $prevNode.name }}"}]}}, (2420, 420))
    err = code(f, "Preparar error", JS_COMUN + r"""
const it = $input.first().json;
let msg = it.error ? (it.error.description || it.error.message || JSON.stringify(it.error)) : detalle(it);
const m = /^\d{3} - (.*)$/s.exec(String(msg));
if (m) { try { let b = JSON.parse(m[1]); if (typeof b === 'string') b = JSON.parse(b); msg = typeof b.detail === 'string' ? b.detail : JSON.stringify(b); } catch (e) { msg = m[1]; } }
return [{ json: { incidencia_id: it.incidencia_id, error: it.paso + ': ' + String(msg).slice(0, 500) } }];""", (2640, 420))
    for n in (erp, pl, ial, itl, pn, ian, itn, pn2, ian2, itn2, g, gr, tp, tia, tit, tgl, tb, tie, tc, tc2):
        f.unir(n, idn, 1)
    f.unir(idn, err)
    me = http(f, "Marcar error", "PATCH", f"={API}/incidencias/{{{{ $json.incidencia_id }}}}", (2860, 420),
              body="{ estado: 'error', error: $json.error, evento: 'error' }", error="continueRegularOutput")
    f.unir(err, me)
    re_ = code(f, "Respuesta error", JS_COMUN + "const P = " + plantilla_resultado + r""";
const e = $('Preparar error').first().json;
const quiereHtml = String(($('Subir foto').first().json.query || {}).html || '') === '1';
const datos = { titulo: 'No se ha podido leer el albarán', estado: 'error', marca: 'error', incidencia_id: e.incidencia_id, error: e.error,
  mensaje: 'Las fotos quedan guardadas. Puedes reintentarlo, eliminarlo o subir otras mejores.',
  enlace: e.incidencia_id ? '/webhook/albaranes/revision/' + e.incidencia_id : null, enlace_texto: 'Reintentar o eliminar' };
return quiereHtml ? html(incrustar(P, datos, { '__BASE__': '/webhook/albaranes/' }), 422) : json(datos, 422);""", (3080, 420))
    f.unir(me, re_)

    resp = responder(f, "Responder", (3960, 80))
    for n in (rl, rd, re_, rt):
        f.unir(n, resp)
    return f.json()


# ============================================================ Revisión
def revision():
    f = Flujo("AlbIaRevision001", "Albaranes IA - Revisión")
    resp = responder(f, "Responder", (1100, 200))

    # Lista
    w1 = webhook(f, "GET revision", "GET", "albaranes/revision", (0, 0))
    l1 = http(f, "Listar incidencias", "GET", f"{API}/incidencias", (220, 0), completa=True, params={
        "sendQuery": True, "queryParameters": {"parameters": [
            {"name": "estado", "value": "={{ $json.query.estado ?? 'pendiente_revision,verificado,error' }}"},
            {"name": "desde", "value": "={{ $json.query.desde || '' }}"},
            {"name": "hasta", "value": "={{ $json.query.hasta || '' }}"},
            {"name": "tipo", "value": "={{ $json.query.tipo || '' }}"},
            {"name": "limite", "value": "500"}]}})
    c1 = code(f, "Página lista", JS_COMUN + "const P = " + json.dumps(web("lista.html")) + r""";
const r = $input.first().json;
const q = $('GET revision').first().json.query;
const d = r.statusCode === 200 ? r.body : { resultados: [], error: detalle(r) };
d.estado = q.estado ?? 'pendiente_revision,verificado,error';
d.desde = q.desde || ''; d.hasta = q.hasta || ''; d.tipo = q.tipo || '';
return html(incrustar(P, d));""", (440, 0))
    f.unir(w1, l1); f.unir(l1, c1); f.unir(c1, resp)

    # Pantalla de revisión
    w2 = webhook(f, "GET revision/:id", "GET", "revision/:id", (0, 200))
    l2 = http(f, "Ficha con foto", "GET", f"={API}/incidencias/{{{{ $json.params.id }}}}?imagen=true", (220, 200), completa=True)
    c2 = code(f, "Página revisión", JS_COMUN + "const P = " + json.dumps(web("revision.html")) + r""";
const r = $input.first().json;
return html(incrustar(P, r.statusCode === 200 ? r.body : null), r.statusCode === 200 ? 200 : 404);""", (440, 200))
    f.unir(w2, l2); f.unir(l2, c2); f.unir(c2, resp)

    # API JSON de la incidencia (con la imagen como data URL)
    w3 = webhook(f, "GET api/incidencia/:id", "GET", "api/incidencia/:id", (0, 400))
    l3 = http(f, "Ficha JSON", "GET", f"={API}/incidencias/{{{{ $json.params.id }}}}?imagen=true", (220, 400), completa=True)
    c3 = code(f, "Respuesta JSON", JS_COMUN + r"""
const r = $input.first().json;
return json(r.body, r.statusCode);""", (440, 400))
    f.unir(w3, l3); f.unir(l3, c3); f.unir(c3, resp)

    # Reconocimientos con error. La página va en sandbox sin allow-same-origin (fetch no lleva
    # la Basic Auth), así que usa formularios POST a estas rutas de 2 segmentos (no chocan con
    # POST api/incidencia/:id/resolver).
    # Reintentar (o volver a leer con otro tipo de albarán): las fotos originales (misma huella)
    # vuelven a pasar por el flujo de ingesta.
    w5 = webhook(f, "POST reintentar/:id", "POST", "reintentar/:id", (0, 880))
    f5 = http(f, "Ficha para reintentar", "GET", f"={API}/incidencias/{{{{ $json.params.id }}}}", (180, 880))
    p5 = code(f, "Páginas a reenviar", r"""const i = $input.first().json;
return (i.paginas && i.paginas.length ? i.paginas : [{ pagina: 1 }]).map(p => ({ json: { id: i.id, pagina: p.pagina } }));""", (360, 880))
    l5 = http(f, "Foto original", "GET", f"={API}/incidencias/{{{{ $json.id }}}}/imagen?original=true&pagina={{{{ $json.pagina }}}}", (540, 880),
              params={"options": {"timeout": 60000, "response": {"response": {"responseFormat": "file", "outputPropertyName": "foto"}}}})
    j5 = code(f, "Juntar fotos", r"""// Todas las páginas en un solo item (foto0, foto1…), como las deja el webhook de ingesta.
const binary = {};
$input.all().forEach((it, i) => { binary['foto' + i] = it.binary.foto; });
return [{ json: {}, binary }];""", (720, 880))
    l6 = f.nodo("Ingesta con reprocesar", "n8n-nodes-base.httpRequest", HTTP_FOTOS, {
        "method": "POST", "url": f"{N8N_INTERNO}/webhook/albaranes/ingesta?html=1",
        "authentication": "genericCredentialType", "genericAuthType": "httpBasicAuth",
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": campos_fotos() + [
            {"name": "reprocesar", "value": "true"},
            {"name": "tipo", "value": "={{ ($('POST reintentar/:id').first().json.body || {}).tipo || $('Ficha para reintentar').first().json.tipo || 'propio' }}"},
            {"name": "referencias", "value": "={{ ($('POST reintentar/:id').first().json.body || {}).referencias || '' }}"}]},
        "options": {"timeout": 300000, "response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": "text"}}}},
        (900, 880), credentials=CRED_BASIC)
    c6 = code(f, "Respuesta reintentar", JS_COMUN + r"""
const r = $input.first().json;
return html(String(r.body ?? r.data ?? ''), r.statusCode || 502);""", (1080, 880))
    f.unir(w5, f5); f.unir(f5, p5); f.unir(p5, l5); f.unir(l5, j5); f.unir(j5, l6); f.unir(l6, c6); f.unir(c6, resp)

    # Terceros: buscar en el ERP las referencias escritas en la pantalla y volver a comparar
    # (sin volver a leer las fotos). Responde con la pantalla de revisión actualizada.
    w7 = webhook(f, "POST buscar/:id", "POST", "buscar/:id", (0, 1300))
    b1 = http(f, "Buscar referencias", "POST", f"={API}/terceros/{{{{ $json.params.id }}}}/emparejar", (200, 1300),
              body="{ referencias: String(($json.body || {}).referencias || '') }", error="continueErrorOutput")
    b2 = si(f, "¿Emparejar con IA?", "!!$json.peticion", (400, 1300))
    b3 = ia(f, "IA: emparejar líneas", "$json.peticion", (600, 1200), timeout=120000)
    b4 = http(f, "Comparar", "POST", f"={API}/terceros/{{{{ $('POST buscar/:id').first().json.params.id }}}}/comparar", (800, 1200),
              body="{ busqueda: $('Buscar referencias').first().json, proveedor: $('Buscar referencias').first().json.peticion.proveedor, respuesta: $json }",
              error="continueErrorOutput")
    b5 = http(f, "Comparar sin IA", "POST", f"={API}/terceros/{{{{ $('POST buscar/:id').first().json.params.id }}}}/comparar", (800, 1400),
              body="{ busqueda: $('Buscar referencias').first().json }", error="continueErrorOutput")
    b6 = http(f, "Ficha tras buscar", "GET", f"={API}/incidencias/{{{{ $('POST buscar/:id').first().json.params.id }}}}?imagen=true",
              (1000, 1300), completa=True)
    b7 = code(f, "Página revisión tras buscar", JS_COMUN + "const P = " + json.dumps(web("revision.html")) + r""";
const r = $input.first().json;
return html(incrustar(P, r.statusCode === 200 ? r.body : null), r.statusCode === 200 ? 200 : 404);""", (1200, 1300))
    b8 = code(f, "Error al buscar", JS_COMUN + "const P = " + json.dumps(web("resultado.html")) + r""";
const it = $input.first().json;
let msg = it.error ? (it.error.description || it.error.message || JSON.stringify(it.error)) : detalle(it);
const m = /^\d{3} - (.*)$/s.exec(String(msg));
if (m) { try { let b = JSON.parse(m[1]); if (typeof b === 'string') b = JSON.parse(b); msg = typeof b.detail === 'string' ? b.detail : JSON.stringify(b); } catch (e) { msg = m[1]; } }
const id = $('POST buscar/:id').first().json.params.id;
return html(incrustar(P, { titulo: 'No se ha podido buscar en el ERP', error: String(msg).slice(0, 500),
  enlace: '/webhook/albaranes/revision/' + id, enlace_texto: 'Volver al reconocimiento' }, { '__BASE__': '/webhook/albaranes/' }), 409);""", (1000, 1520))
    f.unir(w7, b1); f.unir(b1, b2); f.unir(b2, b3, 0); f.unir(b2, b5, 1); f.unir(b3, b4)
    f.unir(b4, b6); f.unir(b5, b6); f.unir(b6, b7); f.unir(b7, resp); f.unir(b8, resp)
    for n in (b1, b3, b4, b5):
        f.unir(n, b8, 1)

    # Eliminar (la API solo borra los que están en error)
    w6 = webhook(f, "POST eliminar/:id", "POST", "eliminar/:id", (0, 1080))
    l7 = http(f, "Eliminar", "DELETE", f"={API}/incidencias/{{{{ $json.params.id }}}}", (220, 1080), completa=True)
    c7 = code(f, "Respuesta eliminar", JS_COMUN + "const P = " + json.dumps(web("resultado.html")) + r""";
const r = $input.first().json;
const id = $('POST eliminar/:id').first().json.params.id;
const datos = r.statusCode === 200
  ? { titulo: 'Reconocimiento eliminado', mensaje: 'Se ha eliminado el reconocimiento #' + id + ' y sus fotos.',
      enlace: '/webhook/albaranes/revision', enlace_texto: 'Volver a la lista' }
  : { titulo: 'No se ha podido eliminar', error: detalle(r),
      enlace: '/webhook/albaranes/revision/' + id, enlace_texto: 'Volver al reconocimiento' };
return html(incrustar(P, datos, { '__BASE__': '/webhook/albaranes/' }), r.statusCode === 200 ? 200 : r.statusCode);""", (440, 1080))
    f.unir(w6, l7); f.unir(l7, c7); f.unir(c7, resp)

    # Resolver (JSON o formulario de la pantalla)
    w4 = webhook(f, "POST api/incidencia/:id/resolver", "POST", "api/incidencia/:id/resolver", (0, 640))
    c4 = code(f, "Normalizar entrada", r"""
const w = $input.first().json;
const b = w.body || {};
let lineas = b.lineas || [];
if (typeof lineas === 'string') { try { lineas = JSON.parse(lineas || '[]'); } catch (e) { lineas = []; } }
return [{ json: { id: Number(w.params.id), html: b.formato === 'html' || (w.query || {}).formato === 'html',
  peticion: { accion: b.accion, lineas, usuario: b.usuario || null, comentario: b.comentario || null } } }];""", (220, 640))
    l4 = http(f, "Resolver", "POST", f"={API}/incidencias/{{{{ $json.id }}}}/resolver", (440, 640),
              body="$json.peticion", completa=True)
    i4 = f.nodo("¿Rectificar?", "n8n-nodes-base.if", 2.2, {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                       "combinator": "and", "conditions": [{
                           "id": "rect", "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                           "leftValue": "={{ $json.statusCode === 200 && ['aprobada', 'corregida'].includes($json.body.estado) && ($json.body.tipo || 'propio') === 'propio' }}",
                           "rightValue": ""}]},
        "options": {}}, (660, 640))
    r4 = http(f, "Rectificar en el ERP", "POST", f"{API}/erp/rectificar", (880, 560),
              body="{ incidencia_id: $('Normalizar entrada').first().json.id }", completa=True, timeout=120000)
    c5 = code(f, "Respuesta resolver", JS_COMUN + "const P = " + json.dumps(web("resultado.html")) + r""";
const ent = $('Normalizar entrada').first().json;
const res = $('Resolver').first().json;
const rect = $('Rectificar en el ERP').isExecuted ? $('Rectificar en el ERP').first().json : null;
const ok = res.statusCode === 200 && (!rect || rect.statusCode === 200);
const out = {
  incidencia_id: ent.id, ok, estado: res.statusCode === 200 ? res.body.estado : null,
  marca: res.statusCode === 200 ? res.body.marca : null,
  resolucion: res.statusCode === 200 ? res.body.resolucion : null,
  rectificacion: rect && rect.statusCode === 200 ? rect.body : null,
  error: res.statusCode !== 200 ? detalle(res) : (rect && rect.statusCode !== 200 ? 'Rectificación: ' + detalle(rect) : null),
};
if (!ent.html) return json(out, ok ? 200 : (res.statusCode !== 200 ? res.statusCode : 502));
const rc = out.rectificacion || {};
const datos = {
  titulo: ok ? 'Revisión guardada' : 'No se ha podido completar', estado: out.estado, marca: out.marca, error: out.error,
  albaran: res.statusCode === 200 ? res.body.albaran_numero : null,
  pasos: rc.dry_run ? rc.pasos : rc.hechos, dry_run: rc.dry_run, avisos: rc.avisos || [],
  mensaje: out.estado === 'rechazada' ? 'Rechazada: no se cambia nada en el ERP.'
    : res.statusCode === 200 && res.body.tipo !== 'propio' ? 'Revisión guardada. Es un albarán de terceros: solo se compara, no se cambia nada en el ERP.' : null,
  enlace: '/webhook/albaranes/revision/' + ent.id, enlace_texto: 'Volver al reconocimiento',
};
return html(incrustar(P, datos, { '__BASE__': '/webhook/albaranes/' }), ok ? 200 : 409);""", (1100, 640))
    f.unir(w4, c4); f.unir(c4, l4); f.unir(l4, i4)
    f.unir(i4, r4, 0); f.unir(i4, c5, 1); f.unir(r4, c5); f.unir(c5, resp)
    return f.json()


if __name__ == "__main__":
    os.makedirs(os.path.join(RAIZ, "n8n", "workflows"), exist_ok=True)
    for nombre, wf in (("ingesta.json", ingesta()), ("revision.json", revision())):
        ruta = os.path.join(RAIZ, "n8n", "workflows", nombre)
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(wf, fh, ensure_ascii=False, indent=2)
        print(ruta, len(wf["nodes"]), "nodos")
