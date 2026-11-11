// Código del nodo "Normalizar" del flujo chat-ia-clientes-ayc.json (build_workflow.py lo copia en el JSON, precedido
// de comun.js). Convierte la respuesta de consultarClientes en { total, requiere_eleccion, hay_mas, resultados }.
const LIMITE = 10;
const dato = t($('Consulta').first().json.dato).toUpperCase();

if (!dato) return fallo('Falta el dato a buscar (nombre, CIF/NIF o código de cliente).');
const { datos: lista, error } = leerApi($input.first().json, 'clientes', true);
if (error) return fallo(error);

// nombreClienteCadena solo viene si el cliente es de una cadena (~4 %) y nombreClienteFactura
// casi siempre es igual al nombre: se dejan vacíos si faltan o coinciden con el nombre.
const distinto = (v, nombre) => (t(v) && t(v) !== nombre ? t(v) : '');
const clientes = lista.map((c) => ({
  codigo: t(c.codigoCliente),
  nombre: t(c.nombreCliente),
  cadena: distinto(c.nombreClienteCadena, t(c.nombreCliente)),
  nombre_factura: distinto(c.nombreClienteFactura, t(c.nombreCliente)),
  cif: t(c.cif),
  direccion: t(c.direccion),
  codigo_postal: t(c.codigoPostal),
  poblacion: t(c.poblacion),
  provincia: t(c.provincia),
}));

// Primero las coincidencias exactas de código o CIF, después por nombre.
const exacto = (c) => (c.codigo === dato || c.cif === dato ? 0 : 1);
clientes.sort((a, b) => exacto(a) - exacto(b) || a.nombre.localeCompare(b.nombre, 'es'));

return [{
  json: {
    dato,
    total: clientes.length,
    requiere_eleccion: clientes.length > 1,
    hay_mas: clientes.length > LIMITE,
    resultados: clientes.slice(0, LIMITE),
  },
}];
