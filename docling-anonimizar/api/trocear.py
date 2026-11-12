"""Trocea un PDF en tramos de páginas para docling.

Cada tramo es un PDF independiente (no un page_range sobre el original) y cada página
conserva solo las imágenes que dibuja. Motivo, medido el 2026-11-12 con un PDF de
LibreOffice de 224 páginas: todas las páginas compartían un diccionario de recursos con
las 228 imágenes del documento (dibujando 0 o 1 cada una), y docling, aun con
page_range de 5 páginas, llegaba a 4,8 GB y lo mataba el OOM killer.
"""
import io
import re

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

DO = re.compile(rb"/([^\s/\[\]()<>{}%]+)\s*Do\b")


def _podar_xobjects(pagina):
    res = pagina.get("/Resources")
    if res is None:
        return
    res = res.get_object()
    xo = res.get("/XObject")
    if xo is None:
        return
    contenido = pagina.get_contents()
    usados = set(DO.findall(contenido.get_data() if contenido is not None else b""))  # ojo: un stream vacío de claves es falsy
    xo = xo.get_object()
    nuevo = DictionaryObject({NameObject(k): v for k, v in res.items()})
    nuevo[NameObject("/XObject")] = DictionaryObject(
        {NameObject(k): v for k, v in xo.items() if k[1:].encode("latin-1") in usados})
    pagina[NameObject("/Resources")] = nuevo


def trocear(pdf: bytes, paginas_por_tramo: int):
    r = PdfReader(io.BytesIO(pdf))
    total = len(r.pages)
    tramos = []
    for ini in range(0, total, paginas_por_tramo):
        fin = min(ini + paginas_por_tramo, total)
        w = PdfWriter()
        for i in range(ini, fin):
            p = r.pages[i]
            _podar_xobjects(p)
            w.add_page(p)
        b = io.BytesIO()
        w.write(b)
        tramos.append({"page_start": ini + 1, "page_end": fin, "pdf": b.getvalue()})
    return total, tramos
