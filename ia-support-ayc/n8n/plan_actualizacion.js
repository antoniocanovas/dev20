// Código del nodo "Plan actualización" del flujo chat-ia-clientes-ayc.json (build_workflow.py lo copia en el JSON,
// precedido de comun.js).
// Con las líneas actuales del producto en la tabla (listarProductos), decide si es un alta o una modificación,
// prepara el cuerpo del POST .../actualizar y:
//   - sin confirmación (o si no coincide): devuelve la vista previa con codigo_confirmacion;
//   - con la confirmación de esa misma vista previa: { ejecutar: true, ... }.
// Si falta un dato (qué línea, qué cliente factura) devuelve { tipo: 'pregunta', mensaje }.
const p = $('Preparar actualización').first().json;
const pregunta = (mensaje, extra = {}) => [{ json: { tipo: 'pregunta', mensaje, ...extra } }];

const { datos: lista, error } = leerApi($input.first().json, p.que, true);
if (error) return fallo(error);

const surtido = p.base === 'surtidos';
const sinCeros = (c) => t(c).replace(/^0+(?=.)/, '');
const hoy = $now.setZone('Europe/Madrid').toFormat('dd/MM/yyyy');
const SIN_FIN = '31/12/2500';
const pr = p.producto;

// Líneas de este mismo producto: del artículo (sin tener en cuenta ceros a la izquierda), o de la marca o el grupo
// sin artículo. listarProductos no devuelve las caducadas.
const delProducto = (l) => (pr.codigoArticulo
  ? sinCeros(l.codigoArticulo) === sinCeros(pr.codigoArticulo)
  : !t(l.codigoArticulo) && t(l.codigoMarca) === pr.codigoMarca && t(l.codigoGrupo) === pr.codigoGrupo);
let lineas = lista.filter(delProducto);

// Surtido: cada línea es de un cliente factura. Si se indica, solo cuentan las suyas.
let cf = p.cliente_factura;
if (surtido && cf) lineas = lineas.filter((l) => t(l.clienteFactura) === cf);
if (surtido && !cf && lineas.length) {
  const cfs = [...new Set(lineas.map((l) => t(l.clienteFactura)))];
  if (cfs.length > 1) {
    return pregunta(`Este producto está en el surtido con varios clientes factura: ${cfs.map((c) => `${nombreCf(c)} (${c})`).join(', ')}. ¿Cuál quieres cambiar?`,
      { opciones: cfs.map((c) => ({ codigo: c, nombre: nombreCf(c) })) });
  }
  cf = cfs[0];
}

// ¿Qué línea se modifica? Con fecha_desde, la que empieza ese día; sin ella, la única que haya.
const verLinea = (l) => ({ desde: t(l.fechaDesde), hasta: t(l.fechaFin) === SIN_FIN ? 'sin fin' : t(l.fechaFin), ...(p.campo ? { [p.campo]: l[p.campo] } : {}) });
let linea = null;
if (p.fecha_desde) {
  linea = lineas.find((l) => t(l.fechaDesde) === p.fecha_desde) || null;
} else if (lineas.length > 1) {
  return pregunta(`Este producto tiene ${lineas.length} líneas en la tabla ${p.tabla.codigo}. ¿Cuál quieres cambiar? Indica su fecha desde.`,
    { lineas: lineas.map(verLinea) });
} else {
  linea = lineas[0] || null;
}
const esAlta = !linea;

// Surtido, alta sin cliente factura: el de las otras líneas de la misma marca en la tabla; si no hay, el genérico.
// De un artículo nuevo no se sabe la marca antes de guardar (no hay API de artículos): se pregunta.
if (surtido && esAlta && !cf) {
  if (pr.codigoArticulo) {
    return pregunta('¿Con qué cliente factura se añade al surtido? El genérico (0000000001) vale haga quien haga el endoso; '
      + 'uno concreto (p. ej. VICKY FOODS 4400000173, para Dulcesol, Hermanos Juan, BePlus o Burger King) solo cuando el endoso lo hace él.',
    { opciones: [{ codigo: GENERICO, nombre: 'Genérico' }, { codigo: '4400000173', nombre: NOMBRES_CF['4400000173'] }] });
  }
  const cfs = [...new Set(lista.filter((l) => t(l.codigoMarca) === pr.codigoMarca).map((l) => t(l.clienteFactura)))];
  if (cfs.length > 1) {
    return pregunta(`La marca ${pr.codigoMarca} tiene líneas con varios clientes factura en la tabla ${p.tabla.codigo}: `
      + `${cfs.map((c) => `${nombreCf(c)} (${c})`).join(', ')}. ¿Con cuál se añade?`, { opciones: cfs.map((c) => ({ codigo: c, nombre: nombreCf(c) })) });
  }
  cf = cfs[0] || GENERICO;
}

// Fechas que quedarán y solape con las otras líneas del producto (la API también lo comprueba, con las caducadas).
const desde = p.fecha_desde || (esAlta ? hoy : t(linea.fechaDesde));
const hasta = p.fecha_fin || (esAlta ? SIN_FIN : t(linea.fechaFin) || SIN_FIN);
const otra = lineas.find((l) => l !== linea && iso(desde) <= iso(t(l.fechaFin) || SIN_FIN) && iso(t(l.fechaDesde)) <= iso(hasta));
if (otra) {
  return pregunta(`Se solaparía con la línea que va del ${t(otra.fechaDesde)} ${t(otra.fechaFin) === SIN_FIN ? 'sin fecha de fin' : `al ${t(otra.fechaFin)}`}. `
    + 'Para cambiar el valor a partir de una fecha, primero hay que cerrar la línea actual (fecha fin = el día anterior) y después dar de alta la nueva.',
  { linea_existente: verLinea(otra) });
}

// Sin cambios: mismo valor y mismas fechas.
if (!esAlta && (!p.campo || Number(linea[p.campo]) === p.valor)
  && desde === t(linea.fechaDesde) && hasta === (t(linea.fechaFin) || SIN_FIN)) {
  return [{ json: { tipo: 'sin_cambios', mensaje: 'La línea ya tiene ese valor y esas fechas: no hay nada que cambiar.', linea: verLinea(linea) } }];
}

// Cuerpo del POST: el código del artículo como en la línea existente; la API rellena lo demás.
const producto = {};
if (pr.codigoArticulo) producto.codigoArticulo = esAlta ? pr.codigoArticulo : t(linea.codigoArticulo);
else {
  if (pr.codigoMarca) producto.codigoMarca = pr.codigoMarca;
  if (pr.codigoGrupo) producto.codigoGrupo = pr.codigoGrupo;
}
if (p.campo) producto[p.campo] = p.valor;
if (p.fecha_desde || !esAlta) producto.fechaDesde = desde;
if (p.fecha_fin) producto.fechaFin = p.fecha_fin;
const body = { codigoTabla: Number(p.tabla.codigo), subEmpresa: 'AYC', productos: [producto] };
if (surtido) body.clienteFactura = cf;

// Código de confirmación: resumen (hash) del cuerpo. Solo se ejecuta si llega el mismo que se dio en la vista previa.
let h = 5381;
for (const c of JSON.stringify(body)) h = ((h * 33) ^ c.charCodeAt(0)) >>> 0;
const codigo = `C${h.toString(36).toUpperCase().padStart(7, '0').slice(-6)}`;

const fmt = (v) => {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  return p.campo === 'precio'
    ? `${n.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 4 })} €`
    : `${n.toLocaleString('es-ES', { maximumFractionDigits: 4 })} %`;
};
const resumen = {
  que: p.que,
  tabla: p.tabla,
  tabla_compartida: p.tabla.num_clientes === undefined ? null : p.tabla.num_clientes > 1,
  operacion: esAlta ? 'alta' : 'modificacion',
  producto: pr.codigoArticulo
    ? { articulo: producto.codigoArticulo, descripcion: linea ? sp(linea.descripcion) : '(se verá al guardar)', marca: linea ? sp(linea.descripcionMarca || linea.codigoMarca) : '' }
    : { marca: pr.codigoMarca, grupo: pr.codigoGrupo },
  valor_anterior: p.campo && linea ? fmt(linea[p.campo]) : '',
  valor_nuevo: p.campo ? fmt(p.valor) : '',
  fechas_anteriores: linea ? verLinea(linea) : null,
  desde,
  hasta: hasta === SIN_FIN ? 'sin fin' : hasta,
  cliente_factura: surtido ? { codigo: cf, nombre: nombreCf(cf) } : null,
};

if (p.confirmacion && p.confirmacion === codigo) {
  return [{ json: { ejecutar: true, base: p.base, body, resumen, codigo_cliente: p.codigo_cliente } }];
}
return [{
  json: {
    tipo: 'vista_previa',
    ...(p.confirmacion ? { aviso: 'El código de confirmación no corresponde a estos datos (han cambiado): hay que volver a confirmar.' } : {}),
    resumen,
    codigo_confirmacion: codigo,
  },
}];
