// Código del nodo "Normalizar condiciones" del flujo chat-ia-clientes-ayc.json (build_workflow.py lo copia en el
// JSON, precedido de comun.js). Convierte la respuesta de listarProductos (precios especiales o descuentos) en
// { tabla, generales, marcas, grupos, familias, total_tabla, total, hay_mas, productos }.
//
// Cada línea es {codigoMarca, descripcionMarca, codigoGrupo, descripcionGrupo, codigoPreFamilia, codigoFamilia,
// codigoArticulo, descripcion, precio|descuento, fechaDesde, fechaFin}. Los campos vacíos pueden faltar. Según lo que
// venga relleno (visto el 11/11/2026 en descuentos 14 y 55):
//   - con artículo → artículo (marca y grupo son los del artículo, informativos; prefamilia y familia, del ERP);
//   - sin artículo, con marca y sin grupo → toda la marca ("marcas");
//   - sin artículo, con marca y grupo → ese grupo de la marca ("grupos");
//   - sin artículo ni marca, con prefamilia o familia → "familias" (no se ha visto ninguna);
//   - sin nada → línea general de la tabla ("generales", p. ej. el 6 % de descuentos 14).
// La API no expande marcas, grupos ni familias en artículos.
const LIMITE = 60;
const e = $('Consulta').first().json;
const tb = $('Tabla').first().json;
const tipo = TIPOS[e.accion];

if (tb.error) return fallo(tb.error);
const { datos: lista, error } = leerApi($input.first().json, tipo.que, true);
if (error) return fallo(error);

// La API no devuelve líneas caducadas, pero sí futuras, y a veces el mismo artículo
// con dos periodos (p. ej. uno desde 2024 y otro que empieza hoy): se dejan todas.
const hoy = hoyIso();
const { palabras, aciertos } = buscador(e.articulo);

// 998 y 999 son las tablas de los clientes sin precios especiales o descuentos (o bloqueados). La 998 de descuentos
// trae una línea general al 0 %: no se enseña, para que el agente diga que el cliente no tiene.
const sinCondiciones = ['998', '999'].includes(String(Number(tb.tabla.codigo)));
const lineas = (sinCondiciones ? [] : lista).map((p) => {
  const hasta = t(p.fechaFin);
  const l = {
    articulo: t(p.codigoArticulo),
    descripcion: sp(p.descripcion),
    codigo_marca: t(p.codigoMarca),
    marca: sp(p.descripcionMarca) || t(p.codigoMarca),
    codigo_grupo: t(p.codigoGrupo),
    grupo: sp(p.descripcionGrupo) || t(p.codigoGrupo),
    prefamilia: t(p.codigoPreFamilia),
    familia: t(p.codigoFamilia),
    [tipo.campo]: p[tipo.campo],
    desde: t(p.fechaDesde),
    // 31/12/2500 = sin fin: hasta vacío.
    hasta: hasta && !hasta.endsWith('/2500') ? hasta : '',
  };
  l.vigente = (!l.desde || iso(l.desde) <= hoy) && (!l.hasta || hoy <= iso(l.hasta));
  return l;
});
const valor = (l) => ({ [tipo.campo]: l[tipo.campo], desde: l.desde, hasta: l.hasta, vigente: l.vigente });
const sinArticulo = lineas.filter((l) => !l.articulo);

// Marcas, grupos, familias y generales: son pocas líneas y van siempre, sin filtrar, para que el agente pueda decir
// si a un artículo le puede afectar una línea de su marca o su grupo.
const marcas = sinArticulo.filter((l) => l.codigo_marca && !l.codigo_grupo)
  .map((l) => ({ codigo_marca: l.codigo_marca, marca: l.marca, ...valor(l) }));
const grupos = sinArticulo.filter((l) => l.codigo_grupo)
  .map((l) => ({ codigo_marca: l.codigo_marca, marca: l.marca, codigo_grupo: l.codigo_grupo, grupo: l.grupo, ...valor(l) }));
const familias = sinArticulo.filter((l) => !l.codigo_marca && !l.codigo_grupo && (l.prefamilia || l.familia))
  .map((l) => ({ prefamilia: l.prefamilia, familia: l.familia, ...valor(l) }));
const generales = sinArticulo.filter((l) => !l.codigo_marca && !l.codigo_grupo && !l.prefamilia && !l.familia).map(valor);

// Artículos. El filtro busca en código, descripción, marca y grupo ("dulcesol" encuentra los artículos de la marca).
const articulos = lineas.filter((l) => l.articulo);
const texto = (l) => `${l.articulo} ${l.descripcion} ${l.marca} ${l.grupo}`;
const productos = articulos
  .filter((l) => aciertos(texto(l)) === palabras.length)
  .sort((a, b) => a.descripcion.localeCompare(b.descripcion, 'es') || iso(a.desde).localeCompare(iso(b.desde)))
  .map((l) => ({ articulo: l.articulo, descripcion: l.descripcion, marca: l.marca, grupo: l.grupo, ...valor(l) }));

return [{
  json: {
    tipo: tipo.que,
    codigo_cliente: t(e.codigo_cliente),
    tabla: tb.tabla,
    articulo: t(e.articulo),
    generales,
    marcas,
    grupos,
    familias,
    total_tabla: articulos.length,
    total: productos.length,
    hay_mas: productos.length > LIMITE,
    productos: productos.slice(0, LIMITE),
    // Al filtrar sin encontrar el artículo, el agente tendía a ofrecer "compruebo su grupo con el código": no se puede.
    ...(palabras.length && !productos.length && (marcas.length || grupos.length || familias.length)
      ? { nota: 'Ningún artículo con línea propia coincide. La API no da la marca ni el grupo de un artículo sin línea propia: '
        + 'no se puede comprobar, ni con su código, si entra en estas marcas o grupos. No lo ofrezcas; como mucho, pregunta al usuario si sabe su grupo.' }
      : {}),
  },
}];
