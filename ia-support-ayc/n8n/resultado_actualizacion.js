// Código del nodo "Resultado actualización" del flujo chat-ia-clientes-ayc.json (build_workflow.py lo copia en el JSON,
// precedido de comun.js).
// Lee la respuesta del POST .../actualizar y devuelve { respuesta, fila }: respuesta es lo que recibe el agente y fila,
// la línea del registro de cambios (Data Table "Cambios ERP AYC").
const plan = $('Plan actualización').first().json;
const r = $input.first().json;

let ok = false;
let mensaje = '';
let lineas = [];
if (r.error) {
  mensaje = mensajeApi(r.error) || t(r.error.message) || 'La API no ha respondido.';
} else {
  try {
    const d = JSON.parse(r.data);
    if (Array.isArray(d.lineas)) {
      ok = true;
      lineas = d.lineas;
      mensaje = `${d.insertados || 0} alta(s), ${d.actualizados || 0} modificación(es)`;
    } else {
      mensaje = d.mensaje || 'Respuesta inesperada de la API.';
    }
  } catch (err) {
    mensaje = 'La API ha devuelto una respuesta no válida.';
  }
}

const s = plan.resumen;
const l = lineas[0] || {};
const producto = s.producto.articulo ? `artículo ${s.producto.articulo}`
  : s.producto.grupo ? `grupo ${s.producto.grupo}${s.producto.marca ? ` de ${s.producto.marca}` : ''}` : `marca ${s.producto.marca}`;

return [{
  json: {
    respuesta: {
      tipo: 'resultado',
      guardado: ok,
      mensaje,
      operacion: ok ? l.operacion : s.operacion,
      tabla: s.tabla,
      producto: s.producto,
      valor_anterior: s.valor_anterior,
      valor_nuevo: s.valor_nuevo,
      desde: ok ? t(l.fechaDesde) : s.desde,
      hasta: ok ? (t(l.fechaFin) === '31/12/2500' ? 'sin fin' : t(l.fechaFin)) : s.hasta,
      cliente_factura: s.cliente_factura,
    },
    fila: {
      fecha: $now.toISO(),
      usuario: 'revision',
      tipo: s.que,
      codigo_tabla: Number(s.tabla.codigo),
      codigo_cliente: plan.codigo_cliente || '',
      cliente_factura: s.cliente_factura ? s.cliente_factura.codigo : '',
      producto,
      operacion: ok ? t(l.operacion) : s.operacion,
      valor_anterior: s.valor_anterior,
      valor_nuevo: s.valor_nuevo,
      fecha_desde: ok ? t(l.fechaDesde) : s.desde,
      fecha_fin: ok ? t(l.fechaFin) : s.hasta,
      resultado: ok ? 'ok' : 'error',
      mensaje,
      peticion: JSON.stringify(plan.body),
    },
  },
}];
