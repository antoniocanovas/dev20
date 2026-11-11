// Conversión de números escritos por el usuario (formato español) al número que espera la API de AYC
// (JSON con punto decimal). Se copia dentro de los nodos Code que preparan precios o descuentos para
// .../actualizar (build_workflow.py). La API no acepta texto: "1,25" entre comillas lo guardaría como 125.
//
//   aNumero('1,25')      → { valor: 1.25 }
//   aNumero('1.250,5 €') → { valor: 1250.5 }
//   aNumero('6,5 %')     → { valor: 6.5 }
//   aNumero('1.25')      → { valor: 1.25 }      (punto decimal, por si lo escriben así)
//   aNumero('1.250')     → { error: '...' }     (¿mil doscientos cincuenta o uno con veinticinco? se pregunta)
//   aNumero(1.25)        → { valor: 1.25 }      (si ya es número, se deja)
function aNumero(entrada) {
  if (typeof entrada === 'number') {
    return Number.isFinite(entrada) ? { valor: entrada } : { error: `"${entrada}" no es un número.` };
  }
  const original = String(entrada ?? '').trim();
  const s = original.replace(/[\s €%]/g, '').replace(/^\+/, '');
  if (!s) return { error: 'Falta el número.' };
  if (!/^-?[\d.,]+$/.test(s) || !/\d/.test(s)) return { error: `"${original}" no es un número.` };

  const comas = (s.match(/,/g) || []).length;
  const puntos = (s.match(/\./g) || []).length;
  let normal;
  if (comas && puntos) {
    // Los dos: el último que aparece es el decimal y el otro separa miles (grupos de 3 cifras).
    const dec = s.lastIndexOf(',') > s.lastIndexOf('.') ? ',' : '.';
    const miles = dec === ',' ? '.' : ',';
    const [entera, decimales, ...resto] = s.split(dec);
    if (resto.length || decimales.includes(miles) || !/^-?\d{1,3}([.,]\d{3})*$/.test(entera)) {
      return { error: `"${original}" no es un número válido.` };
    }
    normal = `${entera.split(miles).join('')}.${decimales}`;
  } else if (comas) {
    // Solo comas: una es el decimal (formato español). Varias = separador de miles ("1,250,000"): no se adivina.
    if (comas > 1) return { error: `"${original}" no es un número válido. Escribe los decimales con coma (p. ej. 1,25).` };
    normal = s.replace(',', '.');
  } else if (puntos) {
    if (puntos > 1) {
      // "1.250.000": puntos de miles.
      if (!/^-?\d{1,3}(\.\d{3})+$/.test(s)) return { error: `"${original}" no es un número válido.` };
      normal = s.split('.').join('');
    } else if (/^-?\d{1,3}\.\d{3}$/.test(s)) {
      // Un punto y 3 cifras detrás: en español es separador de miles, pero puede ser un decimal mal escrito.
      return { error: `"${original}" es ambiguo: ¿${s.replace('.', '')} o ${s.replace('.', ',')}? Escribe los decimales con coma.` };
    } else {
      normal = s; // punto decimal ("1.25", "6.5")
    }
  } else {
    normal = s;
  }

  normal = normal.replace(/^(-?)\./, '$10.'); // ",5" → 0.5
  const valor = Number(normal);
  return Number.isFinite(valor) && /^-?\d+(\.\d+)?$/.test(normal)
    ? { valor }
    : { error: `"${original}" no es un número válido.` };
}

if (typeof module !== 'undefined') module.exports = { aNumero };
