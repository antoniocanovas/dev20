// Código del nodo "Tabla" del flujo chat-ia-clientes-ayc.json (se copia dentro del
// JSON con build_workflow.py). Decide qué tabla de precios especiales, de descuentos o
// de surtido listar: la que da el usuario o la que devuelve "consultar" para el cliente.
const e = $('Consulta').first().json;
const r = $input.first().json;
const t = (v) => String(v ?? '').trim();
const que = { descuentos: 'descuentos', surtidos: 'surtidos' }[e.accion] || 'precios especiales';
// Los 4xx llegan como texto en error.message: '404 - {"mensaje":"No hay datos comerciales (CLP) ..."}'.
const mensajeApi = (err) => (String(err?.message || '').match(/"(?:mensaje|message)"\s*:\s*"([^"]*)"/) || [])[1];

if (t(e.codigo_tabla)) {
  return [{ json: { tabla: { codigo: t(e.codigo_tabla) } } }];
}
if (!t(e.codigo_cliente)) {
  return [{ json: { error: 'Falta el código de cliente (o el código de tabla).' } }];
}
if (r.error) {
  return [{ json: { error: mensajeApi(r.error) || `La API de ${que} no responde o ha dado un error. Prueba de nuevo en unos segundos.` } }];
}
let d;
try {
  d = JSON.parse(r.data);
} catch (err) {
  return [{ json: { error: `La API de ${que} ha devuelto una respuesta no válida.` } }];
}
if (d.codigoTabla === undefined) {
  return [{ json: { error: d.mensaje || `La API de ${que} ha dado un error.` } }];
}
return [{
  json: { tabla: { codigo: t(d.codigoTabla), descripcion: t(d.descripcion), num_clientes: d.numeroClientes } },
}];
