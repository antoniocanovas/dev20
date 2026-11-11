// Funciones comunes de los nodos Code del flujo chat-ia-clientes-ayc.json. build_workflow.py pone este fichero
// delante del código de cada nodo, así que lo que se define aquí no se puede volver a declarar en los otros .js.
const t = (v) => String(v ?? '').trim();
// Quita los espacios de relleno de las descripciones del ERP.
const sp = (v) => t(v).replace(/\s{2,}/g, ' ');
// dd/mm/aaaa → aaaa-mm-dd, para comparar fechas como texto.
const iso = (f) => t(f).split('/').reverse().join('-');
const hoyIso = () => $now.setZone('Europe/Madrid').toFormat('yyyy-MM-dd');
const fallo = (mensaje) => [{ json: { error: mensaje } }];

// Acciones de las herramientas de tablas: base de la URL de la API (/api/<base>/...), nombre para los mensajes y
// campo del valor (null en surtidos).
const TIPOS = {
  preciosEspeciales: { base: 'preciosEspeciales', que: 'precios especiales', campo: 'precio' },
  descuentos: { base: 'descuentos', que: 'descuentos', campo: 'descuento' },
  surtidos: { base: 'surtidos', que: 'surtido', campo: null },
};
TIPOS.actualizarPreciosEspeciales = TIPOS.preciosEspeciales;
TIPOS.actualizarDescuentos = TIPOS.descuentos;
TIPOS.actualizarSurtidos = TIPOS.surtidos;

// Cliente factura de las líneas de surtido. La API no da el nombre: los conocidos van aquí; el resto, por su código.
const GENERICO = '0000000001';
const NOMBRES_CF = { [GENERICO]: 'Genérico', '4400000173': 'VICKY FOODS PRODUCTS SLU' };
const nombreCf = (c) => NOMBRES_CF[c] || (c ? `Cliente factura ${c}` : 'Sin cliente factura');

// Mensaje de la API dentro de un error de n8n: '404 - {"mensaje":"No hay datos comerciales (CLP) ..."}'.
const mensajeApi = (err) => (String(err?.message || '').match(/"(?:mensaje|message)"\s*:\s*"([^"]*)"/) || [])[1];

// Lee la salida de un nodo HTTP de la API ({ data } en texto, o { error } si no ha respondido).
// Devuelve { datos } o { error } con un mensaje para el usuario. lista = true: se espera un array.
function leerApi(r, que, lista = false) {
  if (r.error) {
    return { error: mensajeApi(r.error) || `La API de ${que} no responde o ha dado un error. Prueba de nuevo en unos segundos.` };
  }
  let d;
  try {
    d = JSON.parse(r.data);
  } catch (err) {
    return { error: `La API de ${que} ha devuelto una respuesta no válida.` };
  }
  if (lista && !Array.isArray(d)) return { error: d?.mensaje || `La API de ${que} ha dado un error.` };
  return { datos: d };
}

// Búsqueda por palabras en las descripciones, sin tildes ni mayúsculas y sin palabras vacías
// ("poker de vainilla" → POKER, VAINILLA). aciertos(texto) = cuántas palabras de la búsqueda contiene el texto.
const plano = (s) => t(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
const VACIAS = new Set(['DE', 'DEL', 'LA', 'EL', 'LOS', 'LAS', 'CON', 'Y', 'EN', 'AL', 'A', 'UN', 'UNA', 'PARA', 'POR']);
function buscador(busqueda) {
  const palabras = plano(busqueda).split(/[\s,.;]+/).filter((w) => w && !VACIAS.has(w));
  return { palabras, aciertos: (texto) => { const p = plano(texto); return palabras.filter((w) => p.includes(w)).length; } };
}
