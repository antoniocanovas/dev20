"""Anonimización de texto sin IA generativa.

- Términos que pide el usuario: búsqueda literal, sin distinguir mayúsculas ni tildes.
- Datos estructurados (teléfono, email, DNI/NIE/CIF, IBAN, tarjeta, dirección, URL, IP):
  patrones de Presidio y propios, con validación de dígito de control donde existe.
- Nombres, lugares y organizaciones: el reconocedor de entidades de spaCy
  (modelo estadístico pequeño que corre en el propio servidor; no es un LLM y no
  sale nada del contenedor).

Cada valor distinto recibe una etiqueta estable ([PERSONA_1], [TELEFONO_2]...) y se
sustituye en TODO el documento, también donde el detector no lo vio la primera vez.
"""
import os
import re
import unicodedata

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    CreditCardRecognizer, EmailRecognizer, EsNieRecognizer, EsNifRecognizer, EsPassportRecognizer,
    IbanRecognizer, IpRecognizer, PhoneRecognizer, SpacyRecognizer, UrlRecognizer,
)

IDIOMA = "es"
MODELO_SPACY = "es_core_news_md"
TROZO = 50_000  # caracteres por llamada al analizador (spaCy va mejor con textos acotados)

# Categoría del formulario -> (entidades de Presidio, etiqueta del reemplazo)
CATEGORIAS = {
    "personas": (["PERSON"], "PERSONA"),
    "telefonos": (["PHONE_NUMBER"], "TELEFONO"),
    "emails": (["EMAIL_ADDRESS"], "EMAIL"),
    "documentos": (["ES_NIF", "ES_NIE", "ES_CIF", "ES_PASSPORT"], "DOCUMENTO"),
    "bancarios": (["IBAN_CODE", "CREDIT_CARD"], "CUENTA"),
    "direcciones": (["DIRECCION"], "DIRECCION"),
    "lugares": (["LOCATION"], "LUGAR"),
    "organizaciones": (["ORGANIZATION"], "ORGANIZACION"),
    "web": (["URL", "IP_ADDRESS"], "WEB"),
}
POR_DEFECTO = ["personas", "telefonos", "emails", "documentos", "bancarios", "direcciones"]

# Prioridad al resolver solapes: lo que pide el usuario, luego lo validado por patrón, y lo
# estadístico (spaCy) al final.
PRIORIDAD = {"TERMINO": 0, "PERSON": 3, "LOCATION": 3, "ORGANIZATION": 3}
UMBRAL = 0.4
CONECTORES = {"de", "del", "la", "las", "los", "y", "i", "van", "von", "da", "dos"}


class EsCifRecognizer(PatternRecognizer):
    """CIF de empresa: letra + 7 dígitos + control (dígito o letra), con validación."""
    LETRAS = "JABCDEFGHI"

    def __init__(self):
        super().__init__(supported_entity="ES_CIF", supported_language=IDIOMA,
                         patterns=[Pattern("cif", r"\b[ABCDEFGHJNPQRSUVW]-?\d{7}-?[0-9A-J]\b", 0.5)],
                         context=["cif", "nif", "empresa", "sociedad"])

    def validate_result(self, texto):
        t = texto.replace("-", "").upper()
        d = t[1:8]
        par = sum(int(x) for x in d[1::2])
        impar = sum(sum(divmod(int(x) * 2, 10)) for x in d[0::2])
        c = (10 - (par + impar) % 10) % 10
        return t[8] in (str(c), self.LETRAS[c])


class DireccionRecognizer(PatternRecognizer):
    """Dirección postal: tipo de vía + nombre + número opcional."""
    VIA = (r"(?i:C/|Calle|Avda\.?|Av\.|Avenida|Plaza|Pza\.?|Pl\.|Paseo|Pº|"
           r"Ctra\.?|Carretera|Camino|Ronda|Travesía|Urbanización|Urb\.|Polígono|Pol\.)")

    def __init__(self):
        patron = (self.VIA + r" +[A-ZÁÉÍÓÚÑa-záéíóúñü0-9ºª.' -]{2,60}?(?:,?\s*(?:n[º°o.]?\s*)?\d{1,4}[A-Za-z]?\b)"
                  # código postal y localidad detrás, si los hay: "..., 30001 Murcia"
                  r"(?:,?\s*\d{5}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)?)?")
        super().__init__(supported_entity="DIRECCION", supported_language=IDIOMA,
                         patterns=[Pattern("via_numero", patron, 0.6)], global_regex_flags=re.MULTILINE)


class NombreConApellidoRecognizer(PatternRecognizer):
    """Nombre de pila conocido (nombres.txt) + 1-3 apellidos con mayúscula. Complementa a
    spaCy, que en tablas y listas sin contexto se deja nombres evidentes."""

    def __init__(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nombres.txt")
        nombres = sorted({l.strip() for l in open(ruta, encoding="utf-8") if l.strip() and not l.startswith("#")},
                         key=len, reverse=True)
        apellido = r"(?:(?:de|del|de la|de los|y) +)?[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+(?:-[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)?"
        nombre = "(?:" + "|".join(re.escape(n) for n in nombres) + ")"
        patron = rf"\b{nombre}(?: +{nombre})?(?: +{apellido}){{1,3}}\b"
        # Igual en mayúsculas, como suelen ir en contratos: "BLANCA RUIZ GARCÍA".
        nombre_m = "(?:" + "|".join(re.escape(n.upper()) for n in nombres) + ")"
        apellido_m = r"(?:(?:DE|DEL|DE LA|DE LOS) +)?[A-ZÁÉÍÓÚÑÜ]{2,}(?:-[A-ZÁÉÍÓÚÑÜ]{2,})?"
        patron_m = rf"\b{nombre_m}(?: +{nombre_m})?(?: +{apellido_m}){{1,3}}\b"
        # Sin IGNORECASE (Presidio lo pone por defecto): la mayúscula es lo que distingue
        # "Blanca Ruiz" de "blanca y negra".
        super().__init__(supported_entity="PERSON", supported_language=IDIOMA,
                         patterns=[Pattern("nombre_apellido", patron, 0.6), Pattern("nombre_apellido_mayus", patron_m, 0.6)],
                         global_regex_flags=re.MULTILINE)


TRATAMIENTO = re.compile(r"\s*(?:(?:Doña|Dña|Dª|Don|Srta|Sra|Sr|Dra|Dr|D)(?![a-zñ])\.?\s*)*")


def _sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _clave(tipo, valor):
    return tipo, re.sub(r"\s+", " ", _sin_tildes(valor).lower().strip(" .,;:"))


class Anonimizador:
    def __init__(self):
        nlp = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": IDIOMA, "model_name": MODELO_SPACY}],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": {"PER": "PERSON", "LOC": "LOCATION", "ORG": "ORGANIZATION"},
                "labels_to_ignore": ["MISC"],
            },
        }).create_engine()
        nlp.nlp[IDIOMA].max_length = TROZO * 2
        reg = RecognizerRegistry(supported_languages=[IDIOMA])
        for r in (
            SpacyRecognizer(supported_language=IDIOMA, supported_entities=["PERSON", "LOCATION", "ORGANIZATION"]),
            # Solo ES: los números con prefijo internacional (+33...) se reconocen igual, y con
            # regiones como US un código postal ("02110-1301") pasaba por teléfono.
            PhoneRecognizer(supported_language=IDIOMA, supported_regions=("ES",),
                            context=["teléfono", "telefono", "tel", "móvil", "movil", "fax", "llamar"]),
            EmailRecognizer(supported_language=IDIOMA),
            EsNifRecognizer(), EsNieRecognizer(), EsPassportRecognizer(), EsCifRecognizer(),
            IbanRecognizer(supported_language=IDIOMA), CreditCardRecognizer(supported_language=IDIOMA),
            DireccionRecognizer(),
            UrlRecognizer(supported_language=IDIOMA), IpRecognizer(supported_language=IDIOMA),
        ):
            reg.add_recognizer(r)
        self.motor = AnalyzerEngine(nlp_engine=nlp, registry=reg, supported_languages=[IDIOMA])
        # Fuera del registro a propósito: así lo que devuelve el motor como PERSON es solo de
        # spaCy (y se le aplican los filtros), y la lista se fusiona después.
        self.nombres = NombreConApellidoRecognizer()

    # ---- detección -------------------------------------------------------------------------
    def _trozos(self, texto):
        """Corta por saltos de línea en bloques de como mucho TROZO caracteres."""
        ini = 0
        while ini < len(texto):
            fin = min(ini + TROZO, len(texto))
            if fin < len(texto):
                corte = texto.rfind("\n", ini, fin)
                fin = corte + 1 if corte > ini else fin
            yield ini, texto[ini:fin]
            ini = fin

    @staticmethod
    def _persona_valida(valor, minusculas):
        """Filtra falsos positivos de spaCy, que en textos técnicos marca como persona
        palabras sueltas con mayúscula ("Estilo", "Mezclador", "Botones ENDING")."""
        palabras = [p for p in valor.split() if p.lower() not in CONECTORES]
        if not 2 <= len(palabras) <= 5 or re.search(r"[\d|#*_\[\]()/@]", valor):
            return False
        if not all(p[0].isupper() for p in palabras):
            return False
        mayus = [p.isupper() and len(p) > 1 for p in palabras]
        if any(mayus) and not all(mayus):
            return False  # mezcla "Tomas MAIN OUTPUT": rótulo, no nombre
        # Si todas sus palabras salen también en minúscula en el documento, son palabras comunes.
        return not all(_sin_tildes(p).lower() in minusculas for p in palabras)

    def _detectar(self, texto, entidades):
        hallados = []
        if not entidades:
            return hallados
        minusculas = {_sin_tildes(w) for w in re.findall(r"\b[a-záéíóúñü]{3,}\b", texto)}
        for desde, trozo in self._trozos(texto):
            if "PERSON" in entidades:
                hallados += [(desde + r.start, desde + r.end, "PERSON", trozo[r.start:r.end])
                             for r in self.nombres.analyze(trozo, ["PERSON"])]
            for r in self.motor.analyze(text=trozo, language=IDIOMA, entities=entidades, score_threshold=UMBRAL):
                if r.entity_type != "PERSON":
                    hallados.append((desde + r.start, desde + r.end, r.entity_type, trozo[r.start:r.end]))
                    continue
                # spaCy a veces se come la celda de al lado ("Ana Ruiz | Técnico"): cada trozo
                # entre separadores se valida por su cuenta, sin el tratamiento delante.
                trozos = list(re.finditer(r"[^|\n\t]+", trozo[r.start:r.end]))
                for m in trozos:
                    ini, fin = r.start + m.start(), r.start + m.end()
                    ini += len(TRATAMIENTO.match(trozo[ini:fin]).group(0))
                    while fin > ini and trozo[fin - 1] in " .,;:":
                        fin -= 1
                    if self._persona_valida(trozo[ini:fin], minusculas):
                        hallados.append((desde + ini, desde + fin, "PERSON", trozo[ini:fin]))
        return hallados

    @staticmethod
    def _buscar_literal(texto, valor):
        """Todas las apariciones de `valor` como palabra completa, sin mayúsculas ni tildes.
        La normalización conserva longitudes (solo quita diacríticos de letras sueltas)."""
        base = _sin_tildes(texto).lower()
        aguja = _sin_tildes(valor).lower().strip()
        if len(base) != len(texto) or not aguja:
            base, aguja = texto.lower(), valor.lower().strip()
        patron = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in aguja.split()) + r"(?!\w)"
        return [(m.start(), m.end()) for m in re.finditer(patron, base)]

    # ---- sustitución -----------------------------------------------------------------------
    def anonimizar(self, texto, terminos=(), categorias=None):
        categorias = POR_DEFECTO if categorias is None else [c for c in categorias if c in CATEGORIAS]
        etiqueta_de = {e: CATEGORIAS[c][1] for c in categorias for e in CATEGORIAS[c][0]}
        etiqueta_de["TERMINO"] = "ELIMINADO"

        candidatos = [(i, f, "TERMINO", texto[i:f]) for t in terminos if t.strip()
                      for i, f in self._buscar_literal(texto, t)]
        candidatos += self._detectar(texto, list(etiqueta_de.keys() - {"TERMINO"}))

        # Segunda pasada: cada valor detectado se busca literalmente en todo el texto.
        vistos = {}
        for _, _, tipo, valor in candidatos:
            vistos.setdefault(_clave(tipo, valor), (tipo, valor))
        for tipo, valor in vistos.values():
            if tipo != "TERMINO" and len(valor.strip()) >= 3:
                candidatos += [(i, f, tipo, texto[i:f]) for i, f in self._buscar_literal(texto, valor)]

        # Solapes: prioridad y, a igualdad, el tramo más largo.
        candidatos.sort(key=lambda c: (PRIORIDAD.get(c[2], 1), -(c[1] - c[0]), c[0]))
        ocupado, elegidos = [], []
        for c in candidatos:
            if not any(c[0] < f and i < c[1] for i, f in ocupado):
                ocupado.append((c[0], c[1]))
                elegidos.append(c)
        elegidos.sort()

        etiquetas, contador, resumen, partes, pos = {}, {}, {}, [], 0
        for i, f, tipo, valor in elegidos:
            k = _clave(tipo, valor)
            if k not in etiquetas:
                base = etiqueta_de[tipo]
                contador[base] = contador.get(base, 0) + 1
                etiquetas[k] = f"[{base}_{contador[base]}]" if tipo != "TERMINO" else "[ELIMINADO]"
            base = etiqueta_de[tipo]
            resumen[base] = resumen.get(base, 0) + 1
            partes += [texto[pos:i], etiquetas[k]]
            pos = f
        partes.append(texto[pos:])
        return {
            "texto": "".join(partes),
            "reemplazos": len(elegidos),
            "resumen": resumen,
            "valores_distintos": {b: n for b, n in contador.items()},
        }
