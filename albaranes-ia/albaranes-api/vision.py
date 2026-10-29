"""Lectura del albarán con un modelo de visión (y emparejado de los de terceros).

El servicio construye la petición (prompt, esquema, imagen y modelo) y la interpreta;
la clave del proveedor no tiene por qué estar aquí: n8n envía la petición con su
credencial. Variables:
- VISION_PROVIDER: openrouter (por defecto) o anthropic (por defecto si hay ANTHROPIC_API_KEY)
- VISION_MODEL: por defecto anthropic/claude-sonnet-5.5 (OpenRouter) o claude-sonnet-5-5 (Anthropic)
- VISION_MODEL_NUMERO: modelo del primer intento de leer el número de albarán (solo la primera foto,
  reducida a NUMERO_LADO_MAX px, 800 por defecto). Por defecto Haiku 5.5. El segundo intento, si el
  primero no lo lee, va con VISION_MODEL y todas las fotos a tamaño normal.
- ANTHROPIC_API_KEY / OPENROUTER_API_KEY: opcionales, solo para la llamada directa (`llamar`).

La respuesta se obliga a JSON estricto con salida estructurada (JSON Schema).
"""
import base64
import io
import json
import os
import time

import httpx
from PIL import Image

PROMPT_SISTEMA = """Eres un revisor de albaranes de entrega de una empresa de distribución.
Recibes la FOTO de un albarán impreso por el ERP (o VARIAS, una por página, numeradas en orden: "Página 1",
"Página 2"…) y, como contexto, las líneas que tiene ese albarán en el ERP.
El comercial a veces modifica a mano el albarán impreso: tacha la cantidad (con una "/", con rayas o con un garabato)
y escribe otra al lado o encima, o escribe directamente sobre el número.

Formato del albarán (Odoo estándar): tabla con columnas "Producto" ([REFERENCIA] Nombre), "Pedido" y "Entregado"
(en el informe de operaciones solo hay "Producto" y "Cantidad"). La cantidad que importa es la de la columna
"Entregado" (o "Cantidad"). Si el cambio manuscrito está en la columna "Pedido", aplícalo igualmente como cantidad final
y explícalo en "motivo".

Para cada línea del ERP devuelve una sola entrada con su move_id (aunque haya varias páginas), y añade además
(con move_id null) cualquier línea escrita a mano que no esté en el ERP.
- pagina: número de la página (foto) donde está la fila, empezando en 1. Si la fila aparece en más de una página,
  la página donde está la cantidad que cuenta. Si no se ve en ninguna, la página donde debería estar.
- impreso: número impreso en la columna Entregado/Cantidad tal como lo ves (null si no se ve).
- tachado: true si el número impreso está tachado, rayado, sobrescrito o cubierto por un garabato.
- manuscrito: número escrito a mano para esa línea (null si no hay o es ilegible). No lo inventes.
- cantidad_final: manuscrito si existe y es legible; impreso si no está tachado y no hay manuscrito;
  null si está tachado y no se puede leer ningún número nuevo.
- confianza: de 0 a 1, lo seguro que estás de cantidad_final (1 = número impreso limpio sin marcas).
- dudoso: true si hay cualquier ambigüedad (trazo confuso, 1/7, 3/8, 5/6, número que puede ser de otra fila,
  mancha, foto borrosa o cortada en esa zona).
- motivo: frase corta en español explicando qué ves (p. ej. "12 tachado con /, escrito 10 a la izquierda").
- bbox: caja de TODA la fila (desde el producto hasta la cantidad, incluidas las anotaciones a mano) en coordenadas
  normalizadas de la imagen de su página: [x_min, y_min, x_max, y_max], de 0 a 1, origen arriba a la izquierda.
Ten en cuenta que la foto puede estar girada o en perspectiva: sigue cada fila por su inclinación y no mezcles
cantidades de filas vecinas. Lee también el número de albarán impreso (p. ej. "WH/OUT/00040") y, en "paginas",
el número que se ve en cada foto (null si en esa foto no aparece): sirve para detectar fotos de otro albarán.
Si las fotos se solapan (la misma parte del albarán en dos fotos), no dupliques líneas.
Responde solo con el JSON pedido."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "numero_albaran": {"type": ["string", "null"], "description": "Número de albarán impreso"},
        "lineas": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "move_id": {"type": ["integer", "null"]},
                "pagina": {"type": "integer", "description": "Página (foto) donde está la fila, desde 1"},
                "articulo": {"type": "string", "description": "Referencia y nombre tal como se leen"},
                "impreso": {"type": ["number", "null"]},
                "tachado": {"type": "boolean"},
                "manuscrito": {"type": ["number", "null"]},
                "cantidad_final": {"type": ["number", "null"]},
                "confianza": {"type": "number"},
                "dudoso": {"type": "boolean"},
                "motivo": {"type": "string"},
                "bbox": {"type": "array", "items": {"type": "number"},
                         "description": "[x_min, y_min, x_max, y_max] normalizadas 0-1"},
            },
            "required": ["move_id", "pagina", "articulo", "impreso", "tachado", "manuscrito", "cantidad_final",
                         "confianza", "dudoso", "motivo", "bbox"],
            "additionalProperties": False,
        }},
        "paginas": {"type": "array", "items": {
            "type": "object",
            "properties": {"pagina": {"type": "integer"},
                           "numero_albaran": {"type": ["string", "null"],
                                              "description": "Número de albarán impreso en esa foto"}},
            "required": ["pagina", "numero_albaran"],
            "additionalProperties": False,
        }},
        "observaciones": {"type": "string", "description": "Otras anotaciones a mano (firma, notas...)"},
        "calidad_imagen": {"type": "string", "enum": ["buena", "regular", "mala"],
                           "description": "La de la peor foto"},
    },
    "required": ["numero_albaran", "lineas", "paginas", "observaciones", "calidad_imagen"],
    "additionalProperties": False,
}

PROMPT_NUMERO = """Lees el número de albarán impreso en la foto de un albarán (p. ej. "WH/OUT/00040").
Devuelve el número tal como está impreso, o null si no se lee con seguridad. No lo inventes ni lo completes.
Responde solo con el JSON pedido."""
NUMERO_LADO_MAX = int(os.getenv("NUMERO_LADO_MAX", "800"))

ESQUEMA_NUMERO = {
    "type": "object",
    "properties": {"numero_albaran": {"type": ["string", "null"]}, "confianza": {"type": "number"}},
    "required": ["numero_albaran", "confianza"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- terceros
# Albarán de otra empresa: lo leemos sin contexto del ERP (sus códigos no son los nuestros) y
# después se empareja con nuestras líneas en una llamada de solo texto (PROMPT_EMPAREJAR).
# Ojo: el proveedor admite como mucho 16 campos que pueden ser null en un esquema.
OPERACIONES = {
    "entrada": "Es el albarán de un PROVEEDOR que nos entrega mercancía (lo recibimos en el almacén). "
               "Puede estar valorado (con precios, descuentos e importes) o no.",
    "entrega": "Es el albarán que ha hecho un CLIENTE al recibir nuestra mercancía, con sus propios códigos y "
               "descripciones: nos pagará según esas cantidades y artículos. Puede estar valorado o no.",
}
PROMPT_TERCEROS = """Eres un administrativo que transcribe albaranes de otras empresas para compararlos con nuestro ERP.
Recibes la FOTO de un albarán (o VARIAS, una por página, numeradas en orden: "Página 1", "Página 2"…).
{operacion}

Una persona de nuestra empresa puede haber escrito a mano en el documento (normalmente arriba) el número de
NUESTRO albarán o pedido en el ERP, por ejemplo {formato}. Devuélvelo en referencias_erp: puede haber varios.
No lo confundas con el número del propio documento, ni con el pedido o los códigos impresos del tercero.
Si no hay ninguno, referencias_erp vacío.

Transcribe cada línea de artículo del documento:
- pagina: página (foto) donde está, desde 1. codigo: su código de artículo impreso (null si no hay);
  ean: código EAN/GTIN de 8-14 cifras si aparece (null si no); descripcion: tal como se lee; unidad: la que
  indique (vacío si no indica ninguna).
- impreso: cantidad impresa (null si no hay). tachado: true si la cantidad impresa está tachada, rayada o sobrescrita.
- manuscrito: cantidad escrita a mano para esa línea (null si no hay o es ilegible). No la inventes.
- cantidad_final: manuscrito si es legible; impreso si no está tachado; null si está tachado y no se lee otra.
- precio (unitario), descuento (%) e importe de la línea, si el albarán está valorado (null si no aparecen).
- confianza (0 a 1) de cantidad_final; dudoso: true ante cualquier ambigüedad; motivo: frase corta en español.
- bbox: caja de toda la fila en coordenadas normalizadas de su página [x_min, y_min, x_max, y_max], de 0 a 1.
Incluye también como líneas los portes, embalajes u otros cargos con cantidad o importe; no incluyas totales,
impuestos ni observaciones. Si las fotos se solapan, no dupliques líneas.
valorado: true si el documento trae precios o importes. Responde solo con el JSON pedido."""

_FILA_TERCEROS = {
    "type": "object",
    "properties": {
        "pagina": {"type": "integer"},
        "codigo": {"type": ["string", "null"]},
        "ean": {"type": ["string", "null"]},
        "descripcion": {"type": "string"},
        "unidad": {"type": "string", "description": "Vacío si no se indica"},
        "impreso": {"type": ["number", "null"]},
        "tachado": {"type": "boolean"},
        "manuscrito": {"type": ["number", "null"]},
        "cantidad_final": {"type": ["number", "null"]},
        "precio": {"type": ["number", "null"]},
        "descuento": {"type": ["number", "null"]},
        "importe": {"type": ["number", "null"]},
        "confianza": {"type": "number"},
        "dudoso": {"type": "boolean"},
        "motivo": {"type": "string"},
        "bbox": {"type": "array", "items": {"type": "number"}},
    },
    "required": ["pagina", "codigo", "ean", "descripcion", "unidad", "impreso", "tachado", "manuscrito",
                 "cantidad_final", "precio", "descuento", "importe", "confianza", "dudoso", "motivo", "bbox"],
    "additionalProperties": False,
}
_EMPRESA = {"type": "object", "properties": {"nombre": {"type": ["string", "null"]}, "cif": {"type": ["string", "null"]}},
            "required": ["nombre", "cif"], "additionalProperties": False}
ESQUEMA_TERCEROS = {
    "type": "object",
    "properties": {
        "emisor": _EMPRESA,
        "numero_documento": {"type": ["string", "null"], "description": "Número del albarán del tercero"},
        "fecha": {"type": ["string", "null"], "description": "Fecha del documento, AAAA-MM-DD"},
        "valorado": {"type": "boolean"},
        "referencias_erp": {"type": "array", "items": {
            "type": "object",
            "properties": {"texto": {"type": "string"}, "manuscrita": {"type": "boolean"},
                           "pagina": {"type": "integer"}, "confianza": {"type": "number"}},
            "required": ["texto", "manuscrita", "pagina", "confianza"], "additionalProperties": False}},
        "lineas": {"type": "array", "items": _FILA_TERCEROS},
        "totales": {"type": "object",
                    "properties": {"base": {"type": ["number", "null"]}, "total": {"type": ["number", "null"]}},
                    "required": ["base", "total"], "additionalProperties": False},
        "observaciones": {"type": "string"},
        "calidad_imagen": {"type": "string", "enum": ["buena", "regular", "mala"]},
    },
    "required": ["emisor", "numero_documento", "fecha", "valorado", "referencias_erp", "lineas",
                 "totales", "observaciones", "calidad_imagen"],
    "additionalProperties": False,
}

PROMPT_EMPAREJAR = """Emparejas las líneas del albarán de otra empresa con las líneas de nuestros albaranes en el ERP.
Sus códigos de artículo no son los nuestros: compara por descripción (marca, modelo, medida, formato), por EAN
si lo hay y, solo para desempatar, por cantidad y precio. Nuestros productos pueden estar en otro idioma.
Para cada línea suya (por su "indice") devuelve el linea_id de la nuestra que es el mismo artículo, o null si no
corresponde a ninguna. Una línea nuestra puede corresponder a varias suyas; no fuerces emparejamientos.
confianza: de 0 a 1, lo seguro que estás de que es el mismo artículo; que la cantidad o el precio sean distintos
no la rebaja (esas diferencias son justo lo que buscamos). motivo: frase corta en español.
mismo_tercero: true si el emisor del documento es la misma empresa que la de nuestros albaranes, false si
claramente no, null si no se puede saber. Responde solo con el JSON pedido."""

ESQUEMA_EMPAREJAR = {
    "type": "object",
    "properties": {
        "emparejamientos": {"type": "array", "items": {
            "type": "object",
            "properties": {"indice": {"type": "integer"}, "linea_id": {"type": ["integer", "null"]},
                           "confianza": {"type": "number"}, "motivo": {"type": "string"}},
            "required": ["indice", "linea_id", "confianza", "motivo"], "additionalProperties": False}},
        "mismo_tercero": {"type": ["boolean", "null"]},
        "comentario": {"type": "string"},
    },
    "required": ["emparejamientos", "mismo_tercero", "comentario"],
    "additionalProperties": False,
}
FORMATO_REFERENCIA = os.getenv("FORMATO_REFERENCIA", '"WH/IN/00016", "WH/OUT/00040", "P00014", "S00026" o solo los dígitos')


class VisionError(Exception):
    pass


def _proveedor():
    forzado = os.getenv("VISION_PROVIDER")
    if forzado:
        return forzado
    return "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "openrouter"


def modelo(ligero=False):
    """(proveedor, modelo). ligero: el del primer intento de leer el número (VISION_MODEL_NUMERO)."""
    p = _proveedor()
    if ligero:
        return p, os.getenv("VISION_MODEL_NUMERO") or (
            "claude-haiku-5-5" if p == "anthropic" else "anthropic/claude-haiku-5.5")
    return p, os.getenv("VISION_MODEL") or (
        "claude-sonnet-5-5" if p == "anthropic" else "anthropic/claude-sonnet-5.5")


def imagen_para_modelo(jpeg: bytes, lado_max=1568) -> bytes:
    """El modelo reduce internamente a ~1568 px; se manda ya reducida (mismo encuadre)."""
    img = Image.open(io.BytesIO(jpeg))
    if max(img.size) > lado_max:
        img.thumbnail((lado_max, lado_max), Image.LANCZOS)
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def _contenido(tipo, albaran, operacion=None, emparejar=None):
    """(sistema, texto, nombre del esquema, esquema, max_tokens) de cada tipo de petición."""
    if tipo == "numero":
        return PROMPT_NUMERO, "Si hay varias fotos, el número de la primera en que se lea.", \
            "registrar_numero", ESQUEMA_NUMERO, 300
    if tipo == "terceros":
        sistema = PROMPT_TERCEROS.format(operacion=OPERACIONES[operacion], formato=FORMATO_REFERENCIA)
        return sistema, "Transcribe el albarán.", "registrar_albaran_terceros", ESQUEMA_TERCEROS, 6000
    if tipo == "emparejar":
        return PROMPT_EMPAREJAR, json.dumps(emparejar, ensure_ascii=False), "registrar_emparejamiento", \
            ESQUEMA_EMPAREJAR, 600 + 120 * len(emparejar["suyas"])
    contexto = {
        "numero": albaran["numero"],
        "lineas_erp": [{"move_id": l["id"], "referencia": l["referencia"], "producto": l["producto"],
                        "pedido": l["cantidad_pedida"], "entregado": l["cantidad"], "unidad": l["unidad"]}
                       for l in albaran["lineas"]],
    }
    return PROMPT_SISTEMA, ("Líneas del ERP para este albarán (usa su move_id; el producto puede ir impreso en otro idioma):\n"
                            + json.dumps(contexto, ensure_ascii=False)), "registrar_lectura", ESQUEMA, 4000


def construir_peticion(tipo: str, jpegs: list[bytes], albaran: dict | None = None, operacion: str | None = None,
                       emparejar: dict | None = None, intento: int = 2) -> dict:
    """Petición HTTP lista para enviar al proveedor (sin la clave: la pone quien llama,
    p. ej. n8n con su credencial). jpegs: una foto por página, en orden (ninguna en "emparejar").
    tipo: lectura (nuestro albarán, con sus líneas del ERP), numero, terceros (albarán de otra
    empresa, con `operacion` entrada/entrega) o emparejar (sus líneas con las nuestras).
    intento=1 en "numero": solo la primera foto, reducida a NUMERO_LADO_MAX y con el modelo ligero."""
    ligero = tipo == "numero" and intento == 1
    proveedor, mod = modelo(ligero)
    sistema, texto, herramienta, esquema, max_tokens = _contenido(tipo, albaran, operacion, emparejar)
    if ligero:
        jpegs = jpegs[:1]
    lado = NUMERO_LADO_MAX if ligero else 1568
    b64s = [base64.b64encode(imagen_para_modelo(j, lado)).decode() for j in jpegs]
    if len(b64s) > 1:
        texto = f"Son {len(b64s)} fotos del mismo albarán, en orden de página.\n" + texto
        max_tokens += 1000 * (len(b64s) - 1) if tipo in ("lectura", "terceros") else 0
    # Con varias fotos cada imagen va precedida de su "Página N" para que el modelo las numere.
    etiqueta = (lambda n: [{"type": "text", "text": f"Página {n}"}]) if len(b64s) > 1 else (lambda n: [])
    if proveedor == "anthropic":
        return {"proveedor": proveedor, "modelo": mod, "url": "https://api.anthropic.com/v1/messages",
                "cabeceras": {"anthropic-version": "2023-06-01"},
                "body": {
                    "model": mod, "max_tokens": max_tokens, "system": sistema,
                    "output_config": {"format": {"type": "json_schema", "schema": esquema}},
                    "messages": [{"role": "user", "content": [
                        x for n, b64 in enumerate(b64s, 1) for x in etiqueta(n) + [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}]
                    ] + [{"type": "text", "text": texto}]}]}}
    return {"proveedor": proveedor, "modelo": mod, "url": "https://openrouter.ai/api/v1/chat/completions",
            "cabeceras": {"X-Title": "albaranes-ia"},
            "body": {
                "model": mod, "max_tokens": max_tokens, "temperature": 0,
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": herramienta, "strict": True, "schema": esquema}},
                "messages": [{"role": "system", "content": sistema},
                             {"role": "user", "content": [
                                 x for n, b64 in enumerate(b64s, 1) for x in etiqueta(n) + [
                                     {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
                             ] + [{"type": "text", "text": texto}]}]}}


def interpretar(tipo: str, proveedor: str, d: dict) -> dict:
    """Extrae el JSON de la herramienta de la respuesta del proveedor y lo sanea."""
    if not isinstance(d, dict):
        raise VisionError(f"Respuesta del modelo no válida: {str(d)[:300]}")
    if d.get("error"):
        raise VisionError(f"{proveedor}: {str(d['error'])[:400]}")
    if proveedor == "anthropic":
        texto = "".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text")
        uso = d.get("usage", {})
        tokens = {"entrada": uso.get("input_tokens"), "salida": uso.get("output_tokens")}
    else:
        msg = (d.get("choices") or [{}])[0].get("message") or {}
        texto = msg.get("content") or ""
        if isinstance(texto, list):
            texto = "".join(x.get("text", "") for x in texto if isinstance(x, dict))
        uso = d.get("usage", {})
        tokens = {"entrada": uso.get("prompt_tokens"), "salida": uso.get("completion_tokens"),
                  "coste": uso.get("cost")}
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`").removeprefix("json").strip()
    try:
        datos = json.loads(texto) if texto else None
    except ValueError as e:
        raise VisionError(f"JSON del modelo no válido: {e}: {texto[:200]}")
    if datos is None:
        raise VisionError("El modelo no devolvió ninguna lectura")
    if tipo == "emparejar":
        for e in datos.get("emparejamientos", []):
            e["confianza"] = min(1.0, max(0.0, float(e.get("confianza") or 0)))
    elif tipo != "numero":
        for l in datos.get("lineas", []):
            b = l.get("bbox") or []
            l["bbox"] = [min(1.0, max(0.0, float(v))) for v in b] if len(b) == 4 else None
            l["confianza"] = min(1.0, max(0.0, float(l.get("confianza") or 0)))
            l["pagina"] = int(l.get("pagina") or 1)
    datos["meta"] = {"proveedor": proveedor, "modelo": d.get("model"), "tokens": tokens}
    return datos


def llamar(tipo: str, jpegs: list[bytes], albaran: dict | None = None, operacion: str | None = None,
           emparejar: dict | None = None) -> dict:
    """Llamada directa desde el servicio (necesita la clave en su entorno). n8n no la usa:
    pide la petición con construir_peticion y la envía con su credencial."""
    pet = construir_peticion(tipo, jpegs, albaran, operacion, emparejar)
    if pet["proveedor"] == "anthropic":
        clave = {"x-api-key": os.getenv("ANTHROPIC_API_KEY", "")}
    else:
        clave = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}"}
    if not list(clave.values())[0].replace("Bearer ", ""):
        raise VisionError("El servicio no tiene clave propia: la llamada la hace n8n con su credencial")
    t0 = time.monotonic()
    r = httpx.post(pet["url"], json=pet["body"], headers={**pet["cabeceras"], **clave},
                   timeout=float(os.getenv("VISION_TIMEOUT", "120")))
    if r.status_code >= 400:
        raise VisionError(f"{pet['proveedor']} {r.status_code}: {r.text[:400]}")
    datos = interpretar(tipo, pet["proveedor"], r.json())
    datos["meta"]["ms"] = int((time.monotonic() - t0) * 1000)
    return datos
