// Código del nodo "Tabla" del flujo chat-ia-clientes-ayc.json (build_workflow.py lo copia en el JSON, precedido de
// comun.js). Decide la tabla de precios especiales, de descuentos o de surtido, tanto para consultar como para
// actualizar: la que da el usuario o la que devuelve "consultar" para el cliente (API tabla).
// Devuelve { tabla: { codigo, descripcion, num_clientes } } o { error }.
const e = $('Consulta').first().json;
const tipo = TIPOS[e.accion];

if (!tipo) return fallo(`Acción desconocida: ${e.accion}.`);
if (t(e.codigo_tabla)) return [{ json: { tabla: { codigo: t(e.codigo_tabla) } } }];
if (!t(e.codigo_cliente)) return fallo('Falta el código de cliente (o el número de tabla).');

const { datos: d, error } = leerApi($input.first().json, tipo.que);
if (error) return fallo(error);
if (d?.codigoTabla === undefined) return fallo(d?.mensaje || `La API de ${tipo.que} ha dado un error.`);
return [{ json: { tabla: { codigo: t(d.codigoTabla), descripcion: t(d.descripcion), num_clientes: d.numeroClientes } } }];
