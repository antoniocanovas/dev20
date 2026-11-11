// Código del nodo "Preparar actualización" del flujo chat-ia-clientes-ayc.json (build_workflow.py lo copia en el JSON,
// precedido de comun.js y numero_es.js). Valida lo que pide el agente para dar de alta o modificar una línea de precios
// especiales, descuentos o surtido. La tabla la decide antes el nodo Tabla (la que da el usuario o la del cliente).
// Devuelve { base, campo, tabla, producto, valor, fecha_desde, fecha_fin, cliente_factura, ... } o { error }.
const e = $('Consulta').first().json;
const tipo = TIPOS[e.accion];
const tb = $('Tabla').first().json;
if (tb.error) return fallo(tb.error);
const tabla = tb.tabla;
if (!/^\d+$/.test(tabla.codigo) || Number(tabla.codigo) <= 0) return fallo(`Número de tabla no válido: ${tabla.codigo}.`);
// 999 y 998 son "sin precios especiales / descuentos / surtido" y las comparten decenas de miles de clientes.
if (['998', '999'].includes(String(Number(tabla.codigo)))) {
  return fallo(`La tabla ${Number(tabla.codigo)} es la de los clientes sin ${tipo.que} y la comparten miles de clientes: `
    + 'no se modifica. Si el cliente necesita condiciones propias, hay que asignarle otra tabla en el ERP.');
}

// Producto: artículo, o marca completa, o grupo (de una marca).
const producto = {
  codigoArticulo: t(e.articulo).toUpperCase(),
  codigoMarca: t(e.codigo_marca).toUpperCase(),
  codigoGrupo: t(e.codigo_grupo).toUpperCase(),
};
if (!producto.codigoArticulo && !producto.codigoMarca && !producto.codigoGrupo) {
  return fallo('Falta el código del artículo (o la marca o el grupo, si la línea es de marca completa o de grupo).');
}
if (producto.codigoArticulo && !/^[A-Z0-9]{1,10}$/.test(producto.codigoArticulo)) {
  return fallo(`"${e.articulo}" no es un código de artículo. Busca antes el artículo para saber su código (p. ej. 14403).`);
}
if (producto.codigoArticulo) {
  producto.codigoMarca = '';
  producto.codigoGrupo = '';
}
if (producto.codigoMarca.length > 6 || producto.codigoGrupo.length > 6) return fallo('Los códigos de marca y de grupo tienen como mucho 6 caracteres.');

// Valor: obligatorio en precios y descuentos (la API guardaría 0 si faltara). aNumero viene de numero_es.js.
let valor = null;
if (tipo.campo) {
  const nombre = tipo.campo === 'precio' ? 'Precio' : 'Descuento';
  if (!t(e.valor)) return fallo(`Falta el ${tipo.campo} nuevo.`);
  const n = aNumero(e.valor);
  if (n.error) return fallo(`${nombre}: ${n.error}`);
  valor = n.valor;
  if (tipo.campo === 'precio' && valor < 0) return fallo('El precio no puede ser negativo.');
  if (tipo.campo === 'descuento' && (valor < 0 || valor > 100)) return fallo('El descuento tiene que estar entre 0 y 100 %.');
}

// Fechas dd/mm/aaaa (vacías = por defecto: alta desde hoy y sin fin; modificación, las que tenga).
function fecha(v, nombre) {
  const s = t(v);
  if (!s) return { valor: '' };
  const m = s.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  const d = m && new Date(Date.UTC(+m[3], +m[2] - 1, +m[1]));
  if (!m || d.getUTCDate() !== +m[1] || d.getUTCMonth() !== +m[2] - 1) return { error: `${nombre} no válida (${s}). Usa dd/mm/aaaa.` };
  return { valor: `${m[1].padStart(2, '0')}/${m[2].padStart(2, '0')}/${m[3]}` };
}
const desde = fecha(e.fecha_desde, 'Fecha desde');
const hasta = fecha(e.fecha_fin, 'Fecha fin');
if (desde.error || hasta.error) return fallo(desde.error || hasta.error);
if (desde.valor && hasta.valor && iso(hasta.valor) < iso(desde.valor)) return fallo('La fecha fin no puede ser anterior a la fecha desde.');

const clienteFactura = tipo.base === 'surtidos' ? t(e.cliente_factura) : '';
if (clienteFactura && !/^\d{10}$/.test(clienteFactura)) return fallo(`Cliente factura no válido: ${clienteFactura} (son 10 cifras, p. ej. 4400000173).`);

return [{
  json: {
    accion: e.accion,
    base: tipo.base,
    que: tipo.que,
    campo: tipo.campo,
    codigo_cliente: t(e.codigo_cliente),
    tabla,
    producto,
    valor,
    fecha_desde: desde.valor,
    fecha_fin: hasta.valor,
    cliente_factura: clienteFactura,
    confirmacion: t(e.confirmacion),
  },
}];
