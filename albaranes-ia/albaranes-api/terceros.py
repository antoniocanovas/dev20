"""Albaranes de terceros: de un proveedor en la recepción (entrada) o el que hace el cliente al
recibir nuestra mercancía (entrega).

1. La IA transcribe su albarán sin contexto (vision.py, tipo "terceros") y lee las referencias
   a nuestros albaranes escritas a mano.
2. Se buscan en el ERP las referencias: las que escribe el usuario o, si no, las leídas.
3. Sus líneas se emparejan con las nuestras: por EAN o código idéntico y el resto con la IA
   (tipo "emparejar", solo texto). Lo dudoso va a revisión.
4. Se comparan cantidades y, si el albarán está valorado, precios.

No se escribe nada en el ERP: solo se lee.
"""
import re

from erp import ErpNoEncontrado

TIPO_ERP = {"entrada": "incoming", "entrega": "outgoing"}
UMBRAL_EMPAREJAR = 0.8
TOLERANCIA_PRECIO = 0.005  # relativa al precio neto del ERP (con un mínimo de 1 céntimo)


def separar(texto) -> list[str]:
    """Referencias escritas por una persona: separadas por espacios, comas o punto y coma."""
    vistas = []
    for r in re.split(r"[\s,;]+", (texto or "").strip().upper()):
        if r and r not in vistas:
            vistas.append(r)
    return vistas


def detectadas(lectura) -> str:
    """Texto con las referencias que ha leído la IA (sin espacios dentro de cada una)."""
    return " ".join(re.sub(r"\s+", "", r.get("texto") or "") for r in (lectura or {}).get("referencias_erp") or [])


def buscar(erp, referencias, operacion):
    """(albaranes, no_encontradas, avisos) de las referencias en el ERP, sin repetir albaranes."""
    tipo = TIPO_ERP[operacion]
    albaranes, no_encontradas, avisos = [], [], []
    for r in referencias:
        try:
            encontrados = erp.buscar_albaranes(r, tipo)
        except ErpNoEncontrado as e:
            no_encontradas.append({"referencia": r, "motivo": e.mensaje})
            continue
        for a in encontrados:
            if any(x["id"] == a["id"] for x in albaranes):
                continue
            a["referencia"] = r
            albaranes.append(a)
            if a.get("tipo") and a["tipo"] != tipo:
                avisos.append(f"{a['numero']} no es un albarán de {'entrada' if tipo == 'incoming' else 'salida'}")
    empresas = {(a.get("cliente") or {}).get("nombre") for a in albaranes}
    if len(empresas) > 1:
        avisos.append("Los albaranes son de empresas distintas: " + ", ".join(sorted(e or "?" for e in empresas)))
    return albaranes, no_encontradas, avisos


def nuestras(albaranes):
    return [{**l, "albaran": a["numero"], "albaran_id": a["id"]} for a in albaranes for l in a["lineas"]]


def _norm(c):
    return re.sub(r"[^0-9A-Z]", "", str(c or "").upper())


def preemparejar(lectura, albaranes) -> dict:
    """{indice: emparejamiento} de las líneas suyas con el mismo EAN o código que una nuestra."""
    por_ean = {_norm(l["ean"]): l for l in nuestras(albaranes) if l.get("ean")}
    por_codigo = {_norm(l["referencia"]): l for l in nuestras(albaranes) if l.get("referencia")}
    res = {}
    for i, s in enumerate((lectura or {}).get("lineas") or []):
        if s.get("ean") and _norm(s["ean"]) in por_ean:
            res[i] = {"linea_id": por_ean[_norm(s["ean"])]["id"], "confianza": 1.0, "motivo": "mismo EAN", "por": "ean"}
        elif s.get("codigo") and _norm(s["codigo"]) in por_codigo:
            res[i] = {"linea_id": por_codigo[_norm(s["codigo"])]["id"], "confianza": 1.0,
                      "motivo": "mismo código", "por": "codigo"}
    return res


def datos_emparejar(lectura, albaranes, pre) -> dict | None:
    """Lo que se manda a la IA para emparejar (None si no queda nada por emparejar)."""
    suyas = [{"indice": i, "codigo": s.get("codigo"), "ean": s.get("ean"), "descripcion": s.get("descripcion"),
              "unidad": s.get("unidad"), "cantidad": s.get("cantidad_final"), "precio": s.get("precio")}
             for i, s in enumerate((lectura or {}).get("lineas") or []) if i not in pre]
    mias = [{"linea_id": l["id"], "albaran": l["albaran"], "referencia": l["referencia"], "producto": l["producto"],
             "ean": l.get("ean"), "cantidad": l["cantidad"] or l["cantidad_pedida"], "unidad": l["unidad"],
             "precio": l.get("precio")} for l in nuestras(albaranes)]
    if not suyas or not mias:
        return None
    return {"emisor": (lectura or {}).get("emisor"),
            "nuestros_albaranes": [{"numero": a["numero"], "empresa": (a.get("cliente") or {}).get("nombre")}
                                   for a in albaranes],
            "suyas": suyas, "nuestras": mias}


def _neto(precio, descuento):
    return None if precio is None else precio * (1 - (descuento or 0) / 100)


def comparar(lectura, albaranes, pre, emparejado, umbral, operacion):
    """Decisión: una línea por cada línea nuestra, con las suyas que le corresponden, y extras
    (las suyas sin pareja). cantidad_final propuesta = la del documento del tercero."""
    lectura = lectura or {}
    suyas = lectura.get("lineas") or []
    ids = {l["id"] for l in nuestras(albaranes)}
    pares = dict(pre)
    for e in (emparejado or {}).get("emparejamientos") or []:
        i = e.get("indice")
        if isinstance(i, int) and 0 <= i < len(suyas) and i not in pares and e.get("linea_id") in ids:
            pares[i] = {"linea_id": e["linea_id"], "confianza": e["confianza"], "motivo": e.get("motivo"), "por": "ia"}
    valorado = bool(lectura.get("valorado"))
    lineas = []
    for l in nuestras(albaranes):
        suyas_l = [(i, s) for i, s in enumerate(suyas) if (pares.get(i) or {}).get("linea_id") == l["id"]]
        esperada = l["cantidad"] or l["cantidad_pedida"]
        motivos = []
        cantidades = [s.get("cantidad_final") for _, s in suyas_l]
        cantidad_doc = sum(cantidades) if cantidades and None not in cantidades else None
        precio_doc = next((s.get("precio") for _, s in suyas_l if s.get("precio") is not None), None)
        descuento_doc = next((s.get("descuento") for _, s in suyas_l if s.get("precio") is not None), None)
        if not suyas_l:
            motivos.append("no_en_documento")
            final = 0
        else:
            final = cantidad_doc
            if None in cantidades:
                motivos.append("tachon_ilegible" if any(s.get("tachado") for _, s in suyas_l) else "no_leida")
            if any(s.get("confianza", 0) < umbral for _, s in suyas_l):
                motivos.append("baja_confianza")
            if any(s.get("dudoso") for _, s in suyas_l):
                motivos.append("dudosa")
            if any(s.get("tachado") or s.get("manuscrito") is not None for _, s in suyas_l):
                motivos.append("modificada")
            if any(pares[i]["confianza"] < UMBRAL_EMPAREJAR for i, _ in suyas_l):
                motivos.append("emparejamiento_dudoso")
            if cantidad_doc is not None and cantidad_doc != esperada:
                motivos.append("cantidad_distinta")
            neto_erp, neto_doc = _neto(l.get("precio"), l.get("descuento")), _neto(precio_doc, descuento_doc)
            if valorado and neto_erp is not None and neto_doc is not None and \
                    abs(neto_doc - neto_erp) > max(0.01, TOLERANCIA_PRECIO * abs(neto_erp)):
                motivos.append("precio_distinto")
        primera = suyas_l[0][1] if suyas_l else {}
        confs = [s.get("confianza") for _, s in suyas_l if s.get("confianza") is not None]
        lineas.append({
            "linea_id": l["id"], "albaran": l["albaran"], "referencia": l["referencia"], "producto": l["producto"],
            "unidad": l["unidad"], "pedida": l["cantidad_pedida"], "erp": esperada,
            "precio_erp": l.get("precio"), "descuento_erp": l.get("descuento"),
            "documento": [{"indice": i, "codigo": s.get("codigo"), "descripcion": s.get("descripcion"),
                           "cantidad": s.get("cantidad_final"), "impreso": s.get("impreso"), "tachado": s.get("tachado"),
                           "manuscrito": s.get("manuscrito"), "precio": s.get("precio"), "descuento": s.get("descuento"),
                           "importe": s.get("importe"), "emparejado_por": pares[i]["por"],
                           "confianza_emparejamiento": pares[i]["confianza"], "motivo_emparejamiento": pares[i]["motivo"]}
                          for i, s in suyas_l],
            "cantidad_doc": cantidad_doc, "precio_doc": precio_doc, "descuento_doc": descuento_doc,
            "impreso": primera.get("impreso"), "tachado": bool(primera.get("tachado")),
            "manuscrito": primera.get("manuscrito"), "cantidad_final": final,
            "confianza": min(confs) if confs else None, "dudoso": any(s.get("dudoso") for _, s in suyas_l) or not suyas_l,
            "motivo_ia": "; ".join(s.get("motivo") or "" for _, s in suyas_l) or None,
            "bbox": primera.get("bbox"), "pagina": primera.get("pagina") if suyas_l else None,
            "estado": "pendiente_revision" if motivos else "verificado", "motivos": motivos,
        })
    extras = [{"indice": i, "articulo": " ".join(x for x in (s.get("codigo"), s.get("descripcion")) if x),
               "codigo": s.get("codigo"), "descripcion": s.get("descripcion"), "cantidad_final": s.get("cantidad_final"),
               "precio": s.get("precio"), "bbox": s.get("bbox"), "pagina": s.get("pagina"), "motivo": s.get("motivo")}
              for i, s in enumerate(suyas) if i not in pares]
    return lineas, extras, valorado


def avisos_documento(lectura, albaranes, emparejado):
    lectura, avisos = lectura or {}, []
    if emparejado and emparejado.get("mismo_tercero") is False and albaranes:
        emisor = (lectura.get("emisor") or {}).get("nombre") or "el emisor"
        avisos.append(f"El documento es de {emisor} y nuestro albarán de "
                      f"{(albaranes[0].get('cliente') or {}).get('nombre') or 'otra empresa'}")
    importes = [s.get("importe") for s in lectura.get("lineas") or []]
    base = (lectura.get("totales") or {}).get("base")
    if lectura.get("valorado") and base is not None and importes and None not in importes \
            and abs(sum(importes) - base) > 0.02:
        avisos.append(f"La suma de las líneas del documento ({sum(importes):.2f}) no cuadra con su base ({base:.2f})")
    if lectura.get("calidad_imagen") == "mala":
        avisos.append("Calidad de imagen mala: conviene repetir la foto")
    return avisos
