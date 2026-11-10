// Código del nodo "Normalizar surtido" del flujo chat-ia-clientes-ayc.json (se copia
// dentro del JSON con build_workflow.py). Convierte la respuesta de
// surtidos/listarProductos en { tabla, avisos, marcas, grupos, total, hay_mas, productos }.
//
// Un surtido es la lista cerrada de lo que se puede vender al cliente. Cada línea es
// {codigoMarca, descripcionMarca, codigoGrupo, descripcionGrupo, codigoArticulo, descripcion,
// fechaDesde, fechaFin} (fechaFin 31/12/2500 = sin fin; las descripciones faltan si el código
// va vacío). Según lo que venga relleno (09/11/2026):
//   - codigoArticulo numérico → artículo (marca y grupo son los del artículo, informativos);
//   - sin artículo, con marca y sin grupo → TODA la marca ("marcas");
//   - sin artículo, con marca y grupo → todo ese grupo de la marca ("grupos");
//   - código no numérico (SOLOENDOSO, FINDESERVI, CSACLIENTE...) → marca del ERP ("avisos").
// La API NO expande marcas ni grupos en artículos.
const LIMITE = 60;
const e = $('Consulta').first().json;
const tb = $('Tabla').first().json;
const r = $input.first().json;
const t = (v) => String(v ?? '').trim();
const mensajeApi = (err) => (String(err?.message || '').match(/"(?:mensaje|message)"\s*:\s*"([^"]*)"/) || [])[1];

if (tb.error) {
  return [{ json: { error: tb.error } }];
}
if (r.error) {
  return [{ json: { error: mensajeApi(r.error) || 'La API de surtidos no responde o ha dado un error. Prueba de nuevo en unos segundos.' } }];
}
let lista;
try {
  lista = JSON.parse(r.data);
} catch (err) {
  return [{ json: { error: 'La API de surtidos ha devuelto una respuesta no válida.' } }];
}
if (!Array.isArray(lista)) {
  return [{ json: { error: lista.mensaje || 'La API de surtidos ha dado un error.' } }];
}

const hoy = $now.setZone('Europe/Madrid').toFormat('yyyy-MM-dd');
const iso = (f) => t(f).split('/').reverse().join('-');
const plano = (s) => t(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
const VACIAS = new Set(['DE', 'DEL', 'LA', 'EL', 'LOS', 'LAS', 'CON', 'Y', 'EN', 'AL', 'A', 'UN', 'UNA', 'PARA', 'POR']);
// Palabras del artículo a buscar, sin las vacías ("poker de vainilla" → POKER, VAINILLA).
const palabras = plano(e.articulo).split(/[\s,.;]+/).filter((w) => w && !VACIAS.has(w));
const aciertos = (texto) => palabras.filter((w) => plano(texto).includes(w)).length;
const esArticulo = (c) => /^\d+$/.test(c);

const sp = (v) => t(v).replace(/\s{2,}/g, ' ');
const lineas = lista.map((p) => {
  const hasta = t(p.fechaFin);
  const l = {
    articulo: t(p.codigoArticulo),
    descripcion: sp(p.descripcion),
    codigo_marca: t(p.codigoMarca),
    marca: sp(p.descripcionMarca) || t(p.codigoMarca),
    codigo_grupo: t(p.codigoGrupo),
    grupo: sp(p.descripcionGrupo) || t(p.codigoGrupo),
    desde: t(p.fechaDesde),
    hasta: hasta && !hasta.endsWith('/2500') ? hasta : '',
  };
  l.vigente = (!l.desde || iso(l.desde) <= hoy) && (!hasta || hoy <= iso(hasta));
  return l;
});
const fechas = (l) => ({ desde: l.desde, hasta: l.hasta, vigente: l.vigente });
const avisos = lineas.filter((l) => l.articulo && !esArticulo(l.articulo)).map((l) => `${l.articulo}: ${l.descripcion}`);
// Marcas completas y grupos de marca: son pocas líneas y van siempre, sin filtrar, para que el agente
// pueda decir si un artículo que no aparece suelto entra por su marca o su grupo.
const sinArticulo = lineas.filter((l) => !l.articulo && l.codigo_marca);
const marcas = sinArticulo.filter((l) => !l.codigo_grupo)
  .map((l) => ({ codigo_marca: l.codigo_marca, marca: l.marca, ...fechas(l) }));
const grupos = sinArticulo.filter((l) => l.codigo_grupo)
  .map((l) => ({ codigo_marca: l.codigo_marca, marca: l.marca, codigo_grupo: l.codigo_grupo, grupo: l.grupo, ...fechas(l) }));
const articulos = lineas.filter((l) => esArticulo(l.articulo)).map((l) => ({
  articulo: l.articulo, descripcion: l.descripcion, marca: l.marca, grupo: l.grupo, ...fechas(l),
}));
// El filtro busca en código, descripción, marca y grupo ("dulcesol" encuentra los artículos DSOL de la marca).
const texto = (l) => `${l.articulo} ${l.descripcion} ${l.marca} ${l.grupo}`;
const productos = articulos
  .filter((l) => aciertos(texto(l)) === palabras.length)
  .sort((a, b) => a.marca.localeCompare(b.marca, 'es') || a.descripcion.localeCompare(b.descripcion, 'es')
    || iso(a.desde).localeCompare(iso(b.desde)));
// Resumen de artículos por marca, para surtidos grandes (el agente solo recibe LIMITE artículos).
const porMarca = {};
articulos.forEach((l) => { porMarca[l.marca || 'SIN MARCA'] = (porMarca[l.marca || 'SIN MARCA'] || 0) + 1; });

// Si con todas las palabras no sale nada, los que tienen más palabras en común (como mucho 10),
// para que el agente no conteste "no está" solo porque la descripción lo escribe distinto.
function parecidos(todos, hallados) {
  if (hallados.length || palabras.length < 2) return [];
  return todos.map((l) => [aciertos(texto(l)), l]).filter(([n]) => n > 0)
    .sort((a, b) => b[0] - a[0]).slice(0, 10).map(([, l]) => l);
}

return [{
  json: {
    tipo: 'surtido',
    codigo_cliente: t(e.codigo_cliente),
    tabla: tb.tabla,
    articulo: t(e.articulo),
    avisos: [...new Set(avisos)],
    marcas,
    grupos,
    total_tabla: articulos.length,
    articulos_por_marca: porMarca,
    total: productos.length,
    hay_mas: productos.length > LIMITE,
    productos: productos.slice(0, LIMITE),
    parecidos: parecidos(articulos, productos),
  },
}];
