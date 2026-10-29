"""Genera "fotos" sintéticas de albaranes de terceros (proveedor o cliente) para las pruebas.

Dibuja el albarán de otra empresa con sus códigos, escribe a mano arriba la referencia de
nuestro albarán y los cambios de cantidad, y simula la foto (simular_foto de
generar_foto_prueba.py).

Uso:
  python generar_albaran_terceros.py <modelo> salida.jpg
Modelos: proveedor_valorado, proveedor_sin_referencia, proveedor_ean, cliente_entrega.
Requiere pymupdf, pillow, numpy y opencv-python-headless.
"""
import argparse

from PIL import Image, ImageDraw, ImageFont

from generar_foto_prueba import TINTA, fuente, simular_foto

IMPRENTA = ["/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

MODELOS = {
    # WH/IN/00016 (P00014): Gabinete 6 a 780, Caja 30 a 14, Cubo 10 a 10 -5 %, Alfombrilla 20 a 0,90
    "proveedor_valorado": {
        "emisor": ["SUMINISTROS LEVANTE, S.L.", "CIF B30111223", "Polígono Oeste, calle 7 · 30169 Murcia"],
        "titulo": "ALBARÁN DE ENTREGA", "numero": "AL-2026-0457", "fecha": "21/10/2026",
        "destino": ["Cliente: PRUEBA IA, S.A.", "Su pedido: P00014"],
        "referencia": "WH/IN/00016",
        "columnas": ["Código", "Descripción", "Cant.", "Precio", "Dto.", "Importe"],
        "lineas": [
            ["SL-4410", "Armario metálico grande 2 puertas", 6, 780.00, 0, None],
            ["SL-1022", "Caja almacenaje 40 L con tapa", 30, 14.50, 0, None],
            ["SL-3305", "Cubo con pedal 20 L inox", 10, 10.00, 5, None],
            ["SL-0871", "Alfombrilla escritorio 60x40", 20, 0.90, 0, None],
            ["PORTES", "Portes y embalaje", 1, 25.00, 0, None],
        ],
        "cambios": {0: 5},  # fila -> cantidad escrita a mano (tachando la impresa)
        "valorado": True,
    },
    # WH/IN/00017 (P00015): Silla 8, Caja 12. Sin referencia escrita y sin precios.
    "proveedor_sin_referencia": {
        "emisor": ["SUMINISTROS LEVANTE, S.L.", "CIF B30111223", "Polígono Oeste, calle 7 · 30169 Murcia"],
        "titulo": "ALBARÁN DE ENTREGA", "numero": "AL-2026-0461", "fecha": "22/10/2026",
        "destino": ["Cliente: PRUEBA IA, S.A.", "Su pedido: P00015"],
        "referencia": None,
        "columnas": ["Código", "Descripción", "Cantidad", "Bultos"],
        "lineas": [["SL-5120", "Silla de oficina ergonómica negra", 8, 2], ["SL-1022", "Caja almacenaje 40 L con tapa", 12, 1]],
        "cambios": {},
        "valorado": False,
    },
    # WH/IN/00016 (P00014) con EAN impreso: el armario (E-COM07) y el cubo (E-COM10) tienen ese
    # código de barras en el ERP y una descripción que no se parece a la nuestra; caja y alfombrilla, sin EAN.
    "proveedor_ean": {
        "emisor": ["SUMINISTROS LEVANTE, S.L.", "CIF B30111223", "Polígono Oeste, calle 7 · 30169 Murcia"],
        "titulo": "ALBARÁN DE ENTREGA", "numero": "AL-2026-0470", "fecha": "26/10/2026",
        "destino": ["Cliente: PRUEBA IA, S.A.", "Su pedido: P00014"],
        "referencia": "WH/IN/00016",
        "columnas": ["Código", "EAN", "Descripción", "Cant."],
        "anchos": [130, 230, 470, 150],
        "lineas": [
            ["SL-4410", "8412345000072", "Mod. G2-180 gris RAL 7035", 6],
            ["SL-1022", "", "Caja almacenaje 40 L con tapa", 30],
            ["SL-3305", "8412345000102", "Ref. P-20 acero cepillado", 10],
            ["SL-0871", "", "Alfombrilla escritorio 60x40", 20],
        ],
        "cambios": {2: 9},
        "col_cantidad": 3,
        "valorado": False,
    },
    # WH/OUT/00040 (S00026): Gabinete 12, Silla 5, Caja 24, Alfombrilla 3, Cubo 8
    "cliente_entrega": {
        "emisor": ["SUPERMERCADOS PRUEBA IA", "Central de compras · Recepción de mercancía", "Avda. de la Industria 12 · 30100 Murcia"],
        "titulo": "ALBARÁN DE RECEPCIÓN", "numero": "REC-88213", "fecha": "17/10/2026",
        "destino": ["Proveedor: PRUEBA IA, S.A.", "Muelle 3 · Recibido por: J. López"],
        "referencia": "00040",
        "columnas": ["Art.", "Descripción", "Recibido", "Rechazado"],
        "lineas": [
            ["100234", "ARMARIO GRANDE OFICINA", 12, 0],
            ["100877", "SILLA OFICINA", 5, 0],
            ["100512", "CAJA ALMACENAJE", 24, 0],
            ["100513", "ALFOMBRILLA ESCRITORIO", 3, 0],
            ["100690", "PAPELERA PEDAL", 8, 0],
        ],
        "cambios": {0: 10},
        "valorado": False,
    },
}


def imprenta(tam, negrita=False):
    for f in IMPRENTA:
        try:
            return ImageFont.truetype(f, tam, index=1 if negrita and f.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def num(v, dec=2):
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def dibujar(m):
    W, H = 1240, 1754  # A4 a 150 ppp
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    x0, y = 90, 90
    d.text((x0, y), m["emisor"][0], font=imprenta(34, True), fill="black")
    for i, t in enumerate(m["emisor"][1:]):
        d.text((x0, y + 48 + i * 28), t, font=imprenta(22), fill=(60, 60, 60))
    d.rectangle([760, 90, 1150, 230], outline="black", width=2)
    d.text((780, 104), m["titulo"], font=imprenta(26, True), fill="black")
    d.text((780, 150), "Nº " + m["numero"], font=imprenta(24), fill="black")
    d.text((780, 186), "Fecha: " + m["fecha"], font=imprenta(24), fill="black")
    for i, t in enumerate(m["destino"]):
        d.text((x0, 270 + i * 30), t, font=imprenta(24), fill="black")
    # Referencia de nuestro albarán escrita a mano, arriba
    if m["referencia"]:
        d.text((560, 268), m["referencia"], font=fuente(52), fill=TINTA)
        d.line([(552, 336), (900, 330)], fill=TINTA, width=4)
    # Tabla
    cols = m["columnas"]
    anchos = m.get("anchos") or ([150, 470, 120, 130, 90, 160] if m["valorado"] else [150, 560, 160, 160])
    xs = [x0]
    for a in anchos:
        xs.append(xs[-1] + a)
    y = 390
    d.rectangle([x0, y, xs[-1], y + 46], fill=(225, 228, 232))
    for c, x in zip(cols, xs):
        d.text((x + 10, y + 10), c, font=imprenta(22, True), fill="black")
    y += 46
    filas, base = [], 0.0
    for i, l in enumerate(m["lineas"]):
        if m["valorado"]:
            cod, des, cant, precio, dto, _ = l
            importe = cant * precio * (1 - dto / 100)
            base += importe
            celdas = [cod, des, num(cant, 0), num(precio), f"{dto:g}%" if dto else "", num(importe)]
        else:
            celdas = [str(x) for x in l]
        for j, (c, x) in enumerate(zip(celdas, xs)):
            derecha = j >= m.get("col_cantidad", 2)
            f = imprenta(24)
            tx = xs[j + 1] - 12 - d.textlength(c, font=f) if derecha else x + 10
            d.text((tx, y + 14), c, font=f, fill="black")
        filas.append((y, y + 56))
        d.line([(x0, y + 56), (xs[-1], y + 56)], fill=(190, 190, 190), width=1)
        y += 56
    d.rectangle([x0, 390, xs[-1], y], outline="black", width=2)
    if m["valorado"]:
        iva = base * 0.21
        for k, (t, v) in enumerate((("Base imponible", base), ("IVA 21%", iva), ("TOTAL", base + iva))):
            d.text((760, y + 30 + k * 36), t, font=imprenta(24, k == 2), fill="black")
            d.text((1150 - d.textlength(num(v), font=imprenta(24, k == 2)), y + 30 + k * 36), num(v),
                   font=imprenta(24, k == 2), fill="black")
    d.text((x0, H - 260), "Recibí conforme:", font=imprenta(22), fill=(60, 60, 60))
    d.line([(x0 + 20, H - 150), (x0 + 220, H - 190), (x0 + 300, H - 160)], fill=TINTA, width=3)  # firma
    # Cambios a mano: se tacha la cantidad impresa con una "/" y se escribe la nueva al lado
    for i, nueva in m["cambios"].items():
        ya, yb = filas[i]
        c = m.get("col_cantidad", 2)
        xa, xb = xs[c] + 40, xs[c + 1] - 8
        d.line([(xa, yb - 6), (xb, ya + 6)], fill=TINTA, width=5)
        d.text((xs[c] - 30, ya - 6), str(nueva), font=fuente(50), fill=TINTA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modelo", choices=sorted(MODELOS))
    ap.add_argument("salida")
    ap.add_argument("--giro", type=float, default=-2.0)
    ap.add_argument("--sin-foto", action="store_true", help="no simular la foto")
    a = ap.parse_args()
    img = dibujar(MODELOS[a.modelo])
    if not a.sin_foto:
        img = simular_foto(img, a.giro)
    img.save(a.salida, quality=88)
    print("Guardada", a.salida, img.size)


if __name__ == "__main__":
    main()
