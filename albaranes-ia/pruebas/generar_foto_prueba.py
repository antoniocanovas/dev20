"""Genera una "foto" sintética de un albarán de Odoo modificado a mano.

Sirve para probar el circuito sin imprimir: renderiza el PDF del informe, escribe
tachones y cantidades con una fuente manuscrita sobre la columna "Entregado"
(o "Quantity") y simula una foto (perspectiva, giro, sombra y ruido).

Uso:
  python generar_foto_prueba.py albaran.pdf salida.jpg \
      --cambio "Gabinete grande=barra:10" --cambio "Caja de almacenamiento=encima:20" \
      --cambio "Alfombrilla=garabato"

Tipos de cambio: barra:N (tacha con "/" y escribe N al lado), encima:N (tacha con
rayas y escribe N encima), garabato (tachón sin número legible).
Requiere pymupdf, pillow, numpy y opencv-python-headless.
"""
import argparse
import random

import cv2
import fitz  # pymupdf
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FUENTES = [
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Noteworthy.ttc",
    "/System/Library/Fonts/MarkerFelt.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
]
TINTA = (25, 45, 140)  # bolígrafo azul


def fuente(tam):
    for f in FUENTES:
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def renderizar(pdf, dpi=200):
    doc = fitz.open(pdf)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return page, img, dpi / 72.0


def celda_cantidad(page, texto, escala):
    """Caja (en píxeles) del último número de la fila del producto `texto`."""
    hits = page.search_for(texto)
    if not hits:
        raise SystemExit(f"No encuentro '{texto}' en el PDF")
    fila = hits[0]
    palabras = [w for w in page.get_text("words")
                if abs((w[1] + w[3]) / 2 - (fila.y0 + fila.y1) / 2) < 6 and w[0] > page.rect.width * 0.6]
    palabras.sort(key=lambda w: w[0])
    if not palabras:
        raise SystemExit(f"No encuentro la cantidad de '{texto}'")
    x0, y0, x1, y1 = palabras[-1][:4]
    return [v * escala for v in (x0, y0, x1, y1)], palabras[-1][4]


def aplicar(img, page, escala, cambios):
    d = ImageDraw.Draw(img)
    for c in cambios:
        nombre, _, accion = c.partition("=")
        tipo, _, valor = accion.partition(":")
        (x0, y0, x1, y1), impreso = celda_cantidad(page, nombre, escala)
        h = y1 - y0
        ancho = max(3, int(h * 0.12))
        if tipo == "barra":
            d.line([(x0 - h * 0.2, y1 + h * 0.2), (x1 + h * 0.2, y0 - h * 0.2)], fill=TINTA, width=ancho)
            f = fuente(int(h * 1.9))
            d.text((x0 - h * 2.8, y0 - h * 0.6), valor, font=f, fill=TINTA)
        elif tipo == "encima":
            for k in (-0.15, 0.15):
                d.line([(x0 - 4, (y0 + y1) / 2 + k * h), (x1 + 4, (y0 + y1) / 2 + k * h + 2)],
                       fill=TINTA, width=ancho)
            f = fuente(int(h * 1.7))
            d.text((x0 - h * 0.3, y0 - h * 1.9), valor, font=f, fill=TINTA)
        elif tipo == "garabato":
            rnd = random.Random(7)
            pts = [(x0 - 6 + rnd.random() * (x1 - x0 + 12), y0 - 4 + rnd.random() * (h + 8))
                   for _ in range(18)]
            d.line(pts, fill=TINTA, width=ancho, joint="curve")
        else:
            raise SystemExit(f"Tipo de cambio desconocido: {tipo}")
        print(f"{nombre}: impreso {impreso} -> {tipo} {valor}")
    return img


def simular_foto(img, giro=-3.0, semilla=1):
    rnd = np.random.default_rng(semilla)
    a = np.array(img)
    h, w = a.shape[:2]
    # Fondo de mesa y perspectiva
    pad = int(w * 0.08)
    lienzo = np.full((h + 2 * pad, w + 2 * pad, 3), (120, 105, 90), np.uint8)
    lienzo[pad:pad + h, pad:pad + w] = a
    H, W = lienzo.shape[:2]
    src = np.float32([[pad, pad], [pad + w, pad], [pad + w, pad + h], [pad, pad + h]])
    j = lambda s: rnd.uniform(-s, s) * w
    dst = np.float32([[pad + j(0.02), pad + j(0.02)], [pad + w + j(0.03), pad + j(0.01)],
                      [pad + w + j(0.01), pad + h + j(0.02)], [pad + j(0.03), pad + h + j(0.01)]])
    lienzo = cv2.warpPerspective(lienzo, cv2.getPerspectiveTransform(src, dst), (W, H),
                                 borderValue=(120, 105, 90))
    m = cv2.getRotationMatrix2D((W / 2, H / 2), giro, 1.0)
    lienzo = cv2.warpAffine(lienzo, m, (W, H), borderValue=(120, 105, 90))
    # Sombra suave y ruido de sensor
    gx = np.linspace(0.78, 1.04, W)[None, :, None]
    gy = np.linspace(1.0, 0.9, H)[:, None, None]
    lienzo = np.clip(lienzo * gx * gy + rnd.normal(0, 4, lienzo.shape), 0, 255).astype(np.uint8)
    lienzo = cv2.GaussianBlur(lienzo, (3, 3), 0.8)
    return Image.fromarray(lienzo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("salida")
    ap.add_argument("--cambio", action="append", default=[])
    ap.add_argument("--giro", type=float, default=-3.0)
    ap.add_argument("--sin-foto", action="store_true", help="no simular la foto")
    a = ap.parse_args()
    page, img, escala = renderizar(a.pdf)
    img = aplicar(img, page, escala, a.cambio)
    if not a.sin_foto:
        img = simular_foto(img, a.giro)
    img.save(a.salida, quality=88)
    print("Guardada", a.salida, img.size)


if __name__ == "__main__":
    main()
