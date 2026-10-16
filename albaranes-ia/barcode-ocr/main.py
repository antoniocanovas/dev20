"""barcode-ocr: lee el código de barras de la foto de un albarán.

POST /decode (multipart, campo "foto") -> {"codigo": "WH/OUT/00041" | null, ...}

Si no encuentra ningún código devuelve codigo=null (HTTP 200): n8n usará entonces
el número impreso, leído por el modelo de visión.
"""
import io
import re
import time

import cv2
import numpy as np
import zxingcpp
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, ImageOps

try:  # fotos HEIC de iPhone
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

app = FastAPI(title="barcode-ocr", version="1.0.0")

MAX_BYTES = 25 * 1024 * 1024
# Formatos lineales habituales en documentos; Odoo imprime Code128.
FORMATOS = (zxingcpp.BarcodeFormat.Code128 | zxingcpp.BarcodeFormat.Code39
            | zxingcpp.BarcodeFormat.Code93 | zxingcpp.BarcodeFormat.EAN13
            | zxingcpp.BarcodeFormat.ITF | zxingcpp.BarcodeFormat.QRCode
            | zxingcpp.BarcodeFormat.DataMatrix)


def _cargar(datos: bytes) -> np.ndarray:
    """Imagen en escala de grises, con la orientación EXIF aplicada."""
    try:
        img = Image.open(io.BytesIO(datos))
        img = ImageOps.exif_transpose(img)
        return np.array(img.convert("L"))
    except Exception as e:
        raise HTTPException(422, f"No es una imagen válida: {e}")


def _escalar(gris: np.ndarray, lado_max: int) -> np.ndarray:
    h, w = gris.shape
    f = lado_max / max(h, w)
    if abs(f - 1) < 0.05:
        return gris
    interp = cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC
    return cv2.resize(gris, (int(w * f), int(h * f)), interpolation=interp)


def _variantes(gris: np.ndarray):
    """Preprocesados en orden de coste; zxing ya prueba rotaciones e inversión."""
    for lado in (2000, 3000, 1400):
        base = _escalar(gris, lado)
        yield f"gris@{lado}", base
        yield f"clahe@{lado}", cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(base)
        yield f"otsu@{lado}", cv2.threshold(cv2.GaussianBlur(base, (3, 3), 0), 0, 255,
                                            cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        yield f"adapt@{lado}", cv2.adaptiveThreshold(base, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                                     cv2.THRESH_BINARY, 31, 10)
    # Rotación fina por si la foto está torcida (zxing solo prueba múltiplos de 90º)
    base = _escalar(gris, 2000)
    h, w = base.shape
    for ang in (-8, -4, 4, 8):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        yield f"rot{ang}", cv2.warpAffine(base, m, (w, h), borderValue=255)


@app.get("/health")
def health():
    return {"ok": True, "zxing": zxingcpp.__version__ if hasattr(zxingcpp, "__version__") else None}


@app.post("/decode")
async def decode(foto: UploadFile = File(...), patron: str | None = None):
    """Devuelve el primer código legible. `patron` (regex) prioriza los que encajan,
    p. ej. `^WH/OUT/` para quedarse con el número de albarán si hay varios códigos."""
    datos = await foto.read()
    if not datos:
        raise HTTPException(422, "Imagen vacía")
    if len(datos) > MAX_BYTES:
        raise HTTPException(413, "Imagen demasiado grande (máx. 25 MB)")
    t0 = time.monotonic()
    gris = _cargar(datos)
    rx = re.compile(patron) if patron else None
    intentos = []
    candidatos = {}
    for nombre, img in _variantes(gris):
        intentos.append(nombre)
        for r in zxingcpp.read_barcodes(img, formats=FORMATOS, try_rotate=True, try_downscale=True):
            if r.valid and r.text:
                candidatos.setdefault(r.text, {"codigo": r.text, "formato": r.format.name,
                                               "variante": nombre})
        buenos = [c for c in candidatos.values() if not rx or rx.search(c["codigo"])]
        if buenos:
            return {**buenos[0], "candidatos": list(candidatos.values()), "intentos": len(intentos),
                    "ms": int((time.monotonic() - t0) * 1000), "tamano": list(gris.shape[::-1])}
    return {"codigo": None, "formato": None, "variante": None, "candidatos": list(candidatos.values()),
            "intentos": len(intentos), "ms": int((time.monotonic() - t0) * 1000),
            "tamano": list(gris.shape[::-1])}
