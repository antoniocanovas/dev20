"""Lectura del albarán con un modelo de visión.

El servicio construye la petición (prompt, esquema, imagen y modelo) y la interpreta;
la clave del proveedor no tiene por qué estar aquí: n8n envía la petición con su
credencial. Variables:
- VISION_PROVIDER: openrouter (por defecto) o anthropic (por defecto si hay ANTHROPIC_API_KEY)
- VISION_MODEL: por defecto anthropic/claude-sonnet-5.5 (OpenRouter) o claude-sonnet-5-5 (Anthropic)
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
Recibes la FOTO de un albarán impreso por el ERP y, como contexto, las líneas que tiene ese albarán en el ERP.
El comercial a veces modifica a mano el albarán impreso: tacha la cantidad (con una "/", con rayas o con un garabato)
y escribe otra al lado o encima, o escribe directamente sobre el número.

Formato del albarán (Odoo estándar): tabla con columnas "Producto" ([REFERENCIA] Nombre), "Pedido" y "Entregado"
(en el informe de operaciones solo hay "Producto" y "Cantidad"). La cantidad que importa es la de la columna
"Entregado" (o "Cantidad"). Si el cambio manuscrito está en la columna "Pedido", aplícalo igualmente como cantidad final
y explícalo en "motivo".

Para cada línea del ERP devuelve una entrada con su move_id, y añade además (con move_id null) cualquier línea
escrita a mano que no esté en el ERP.
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
  normalizadas de la imagen recibida: [x_min, y_min, x_max, y_max], de 0 a 1, origen arriba a la izquierda.
Ten en cuenta que la foto puede estar girada o en perspectiva: sigue cada fila por su inclinación y no mezcles
cantidades de filas vecinas. Lee también el número de albarán impreso (p. ej. "WH/OUT/00040").
Responde solo con el JSON pedido."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "numero_albaran": {"type": ["string", "null"], "description": "Número de albarán impreso"},
        "lineas": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "move_id": {"type": ["integer", "null"]},
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
            "required": ["move_id", "articulo", "impreso", "tachado", "manuscrito", "cantidad_final",
                         "confianza", "dudoso", "motivo", "bbox"],
            "additionalProperties": False,
        }},
        "observaciones": {"type": "string", "description": "Otras anotaciones a mano (firma, notas...)"},
        "calidad_imagen": {"type": "string", "enum": ["buena", "regular", "mala"]},
    },
    "required": ["numero_albaran", "lineas", "observaciones", "calidad_imagen"],
    "additionalProperties": False,
}

ESQUEMA_NUMERO = {
    "type": "object",
    "properties": {"numero_albaran": {"type": ["string", "null"]}, "confianza": {"type": "number"}},
    "required": ["numero_albaran", "confianza"],
    "additionalProperties": False,
}


class VisionError(Exception):
    pass


def _proveedor():
    forzado = os.getenv("VISION_PROVIDER")
    if forzado:
        return forzado
    return "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "openrouter"


def modelo():
    p = _proveedor()
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


def _contenido(tipo, albaran):
    if tipo == "numero":
        return ("Solo necesito el número de albarán impreso en el documento (p. ej. WH/OUT/00040). "
                "Devuelve null si no se lee."), "registrar_numero", ESQUEMA_NUMERO, 300
    contexto = {
        "numero": albaran["numero"],
        "lineas_erp": [{"move_id": l["id"], "referencia": l["referencia"], "producto": l["producto"],
                        "pedido": l["cantidad_pedida"], "entregado": l["cantidad"], "unidad": l["unidad"]}
                       for l in albaran["lineas"]],
    }
    return ("Líneas del ERP para este albarán (usa su move_id; el producto puede ir impreso en otro idioma):\n"
            + json.dumps(contexto, ensure_ascii=False)), "registrar_lectura", ESQUEMA, 4000


def construir_peticion(tipo: str, jpeg: bytes, albaran: dict | None = None) -> dict:
    """Petición HTTP lista para enviar al proveedor (sin la clave: la pone quien llama,
    p. ej. n8n con su credencial)."""
    proveedor, mod = modelo()
    texto, herramienta, esquema, max_tokens = _contenido(tipo, albaran)
    b64 = base64.b64encode(imagen_para_modelo(jpeg)).decode()
    if proveedor == "anthropic":
        return {"proveedor": proveedor, "modelo": mod, "url": "https://api.anthropic.com/v1/messages",
                "cabeceras": {"anthropic-version": "2023-06-01"},
                "body": {
                    "model": mod, "max_tokens": max_tokens, "system": PROMPT_SISTEMA,
                    "output_config": {"format": {"type": "json_schema", "schema": esquema}},
                    "messages": [{"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                        {"type": "text", "text": texto}]}]}}
    return {"proveedor": proveedor, "modelo": mod, "url": "https://openrouter.ai/api/v1/chat/completions",
            "cabeceras": {"X-Title": "albaranes-ia"},
            "body": {
                "model": mod, "max_tokens": max_tokens, "temperature": 0,
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": herramienta, "strict": True, "schema": esquema}},
                "messages": [{"role": "system", "content": PROMPT_SISTEMA},
                             {"role": "user", "content": [
                                 {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                 {"type": "text", "text": texto}]}]}}


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
    if tipo != "numero":
        for l in datos.get("lineas", []):
            b = l.get("bbox") or []
            l["bbox"] = [min(1.0, max(0.0, float(v))) for v in b] if len(b) == 4 else None
            l["confianza"] = min(1.0, max(0.0, float(l.get("confianza") or 0)))
    datos["meta"] = {"proveedor": proveedor, "modelo": d.get("model"), "tokens": tokens}
    return datos


def llamar(tipo: str, jpeg: bytes, albaran: dict | None = None) -> dict:
    """Llamada directa desde el servicio (necesita la clave en su entorno). n8n no la usa:
    pide la petición con construir_peticion y la envía con su credencial."""
    pet = construir_peticion(tipo, jpeg, albaran)
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
