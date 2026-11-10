// Código del nodo "Normalizar condiciones" del flujo chat-ia-clientes-ayc.json (se
// copia dentro del JSON con build_workflow.py). Convierte la respuesta de
// listarProductos (precios especiales o descuentos) en { tabla, total, hay_mas, productos }.
const LIMITE = 60;
const e = $('Consulta').first().json;
const tb = $('Tabla').first().json;
const r = $input.first().json;
const t = (v) => String(v ?? '').trim();
const descuentos = e.accion === 'descuentos';
const que = descuentos ? 'descuentos' : 'precios especiales';
const mensajeApi = (err) => (String(err?.message || '').match(/"(?:mensaje|message)"\s*:\s*"([^"]*)"/) || [])[1];

if (tb.error) {
  return [{ json: { error: tb.error } }];
}
if (r.error) {
  return [{ json: { error: mensajeApi(r.error) || `La API de ${que} no responde o ha dado un error. Prueba de nuevo en unos segundos.` } }];
}
let lista;
try {
  lista = JSON.parse(r.data);
} catch (err) {
  return [{ json: { error: `La API de ${que} ha devuelto una respuesta no válida.` } }];
}
if (!Array.isArray(lista)) {
  return [{ json: { error: lista.mensaje || `La API de ${que} ha dado un error.` } }];
}

// La API no devuelve líneas caducadas, pero sí futuras, y a veces el mismo artículo
// con dos periodos (p. ej. uno desde 2024 y otro que empieza hoy): se dejan todas.
const hoy = $now.setZone('Europe/Madrid').toFormat('yyyy-MM-dd');
const iso = (f) => t(f).split('/').reverse().join('-');
const plano = (s) => t(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
const VACIAS = new Set(['DE', 'DEL', 'LA', 'EL', 'LOS', 'LAS', 'CON', 'Y', 'EN', 'AL', 'A', 'UN', 'UNA', 'PARA', 'POR']);
// Palabras del artículo a buscar, sin las vacías ("poker de vainilla" → POKER, VAINILLA).
const palabras = plano(e.articulo).split(/[\s,.;]+/).filter((w) => w && !VACIAS.has(w));
const aciertos = (texto) => palabras.filter((w) => plano(texto).includes(w)).length;

const productos = lista
  .map((p) => ({
    articulo: t(p.codigoArticulo),
    descripcion: t(p.descripcion).replace(/\s{2,}/g, ' '),
    ...(descuentos ? { descuento: p.descuento } : { precio: p.precio }),
    desde: t(p.fechaDesde),
    hasta: t(p.fechaFin),
    vigente: iso(p.fechaDesde) <= hoy && hoy <= iso(p.fechaFin),
  }))
  .filter((p) => aciertos(`${p.articulo} ${p.descripcion}`) === palabras.length)
  .sort((a, b) => a.descripcion.localeCompare(b.descripcion, 'es') || iso(a.desde).localeCompare(iso(b.desde)));

return [{
  json: {
    tipo: que,
    codigo_cliente: t(e.codigo_cliente),
    tabla: tb.tabla,
    articulo: t(e.articulo),
    total_tabla: lista.length,
    total: productos.length,
    hay_mas: productos.length > LIMITE,
    productos: productos.slice(0, LIMITE),
  },
}];
