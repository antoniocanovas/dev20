// Código del nodo "Normalizar surtido" del flujo chat-ia-clientes-ayc.json (se copia
// dentro del JSON con build_workflow.py, precedido de comun.js). Convierte la respuesta de
// surtidos/listarProductos en { tabla, avisos, clientes_factura, marcas, grupos, total, hay_mas, productos }.
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
//
// Cada línea es además de un cliente factura (clienteFactura, 11/11/2026): el subdistribuidor que hace el endoso
// (p. ej. Vicky Foods 4400000173). 0000000001 = genérico: vale sea quien sea el que factura (nombres en comun.js,
// NOMBRES_CF). Con la entrada cliente_factura solo se devuelven las líneas de ese cliente factura.
const LIMITE = 60;
const e = $('Consulta').first().json;
const tb = $('Tabla').first().json;

if (tb.error) return fallo(tb.error);
const { datos: lista, error } = leerApi($input.first().json, 'surtidos', true);
if (error) return fallo(error);

const hoy = hoyIso();
const { palabras, aciertos } = buscador(e.articulo);
const esArticulo = (c) => /^\d+$/.test(c);

const todas = lista.map((p) => {
  const hasta = t(p.fechaFin);
  const l = {
    codigo_cf: t(p.clienteFactura),
    articulo: t(p.codigoArticulo),
    descripcion: sp(p.descripcion),
    codigo_marca: t(p.codigoMarca),
    marca: sp(p.descripcionMarca) || t(p.codigoMarca),
    codigo_grupo: t(p.codigoGrupo),
    grupo: sp(p.descripcionGrupo) || t(p.codigoGrupo),
    desde: t(p.fechaDesde),
    hasta: hasta && !hasta.endsWith('/2500') ? hasta : '',
  };
  l.cliente_factura = nombreCf(l.codigo_cf);
  l.vigente = (!l.desde || iso(l.desde) <= hoy) && (!hasta || hoy <= iso(hasta));
  return l;
});
const cfFiltro = t(e.cliente_factura);
const lineas = cfFiltro ? todas.filter((l) => l.codigo_cf === cfFiltro) : todas;
const fechas = (l) => ({ cliente_factura: l.cliente_factura, desde: l.desde, hasta: l.hasta, vigente: l.vigente });
// Los avisos (SOLOENDOSO...) son de la tabla: se miran en todas las líneas.
const avisos = todas.filter((l) => l.articulo && !esArticulo(l.articulo)).map((l) => `${l.articulo}: ${l.descripcion}`);
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
// Primero los clientes factura concretos y al final el genérico.
const ordenCf = (n) => (n === 'Genérico' ? 'ZZZ' : n);
// El filtro busca en código, descripción, marca y grupo ("dulcesol" encuentra los artículos DSOL de la marca).
const texto = (l) => `${l.articulo} ${l.descripcion} ${l.marca} ${l.grupo}`;
const productos = articulos
  .filter((l) => aciertos(texto(l)) === palabras.length)
  .sort((a, b) => ordenCf(a.cliente_factura).localeCompare(ordenCf(b.cliente_factura), 'es')
    || a.marca.localeCompare(b.marca, 'es') || a.descripcion.localeCompare(b.descripcion, 'es')
    || iso(a.desde).localeCompare(iso(b.desde)));
// Resumen por cliente factura: código, nombre, nº de marcas completas, de grupos y de artículos, y artículos
// por marca (para surtidos grandes: el agente solo recibe LIMITE artículos).
const resumen = {};
lineas.filter((l) => l.codigo_marca || esArticulo(l.articulo)).forEach((l) => {
  const r = resumen[l.codigo_cf] ||= { codigo: l.codigo_cf, nombre: l.cliente_factura, marcas: 0, grupos: 0, articulos: 0, articulos_por_marca: {} };
  if (esArticulo(l.articulo)) {
    r.articulos += 1;
    const m = l.marca || 'SIN MARCA';
    r.articulos_por_marca[m] = (r.articulos_por_marca[m] || 0) + 1;
  } else if (!l.articulo) {
    r[l.codigo_grupo ? 'grupos' : 'marcas'] += 1;
  }
});
const clientesFactura = Object.values(resumen).sort((a, b) => ordenCf(a.nombre).localeCompare(ordenCf(b.nombre), 'es'));

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
    cliente_factura: cfFiltro ? { codigo: cfFiltro, nombre: nombreCf(cfFiltro), lineas_de_otros: todas.length - lineas.length } : null,
    avisos: [...new Set(avisos)],
    clientes_factura: clientesFactura,
    marcas,
    grupos,
    total_tabla: articulos.length,
    total: productos.length,
    hay_mas: productos.length > LIMITE,
    productos: productos.slice(0, LIMITE),
    parecidos: parecidos(articulos, productos),
  },
}];
