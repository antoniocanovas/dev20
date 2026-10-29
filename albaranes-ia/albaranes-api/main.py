"""albaranes-api: incidencias de albaranes modificados a mano.

- Incidencias: foto, lectura de la IA, decisión, revisión humana (BD propia).
- Visión: lee el albarán con un modelo multimodal (vision.py).
- ERP: única puerta al ERP (paquete erp/, hoy Odoo 20 por JSON-2).
- Terceros: albaranes de proveedores y clientes comparados con los nuestros (terceros.py).

Lo orquestan los flujos de n8n "Albaranes IA - Ingesta" y "Albaranes IA - Revisión".
"""
import base64
import hashlib
import html
import io
import os
from datetime import date, datetime, timezone


def _cargar_env_file(ruta=os.getenv("ENV_FILE", "/run/config/albaranes-ia.env")):
    """Secretos en un fichero montado (no en el panel). No pisa variables ya definidas."""
    if os.path.isfile(ruta):
        for linea in open(ruta, encoding="utf-8"):
            k, sep, v = linea.strip().partition("=")
            if sep and k and not k.startswith("#"):
                os.environ.setdefault(k, v)


_cargar_env_file()

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request  # noqa: E402
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

import terceros
import vision
from erp import ErpError, crear_erp
from store import ESTADOS, TIPOS, Store  # noqa: E402

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

VERSION = "1.0.0"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() not in ("false", "0", "no")
UMBRAL = float(os.getenv("CONFIANZA_UMBRAL", "0.85"))
VARIACION_SOSPECHOSA = float(os.getenv("VARIACION_SOSPECHOSA", "0.5"))
URL_REVISION = os.getenv("URL_REVISION", "")  # p. ej. https://n8n.../webhook/revision
API_TOKEN = os.getenv("API_TOKEN")
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGINAS = 10  # fotos por albarán (n8n reenvía como mucho este número de ficheros)

app = FastAPI(title="albaranes-api", version=VERSION)
store = Store(os.environ["STORE_DSN"])
erp = crear_erp()


def auth(x_api_token: str | None = Header(None)):
    if API_TOKEN and x_api_token != API_TOKEN:
        raise HTTPException(401, "Token incorrecto")


@app.exception_handler(ErpError)
async def erp_error(_, e: ErpError):
    return JSONResponse({"detail": e.mensaje, "origen": "erp"}, status_code=e.estado_http)


@app.exception_handler(vision.VisionError)
async def vision_error(_, e):
    return JSONResponse({"detail": str(e), "origen": "vision"}, status_code=502)


def _inc(id_, con_fotos=False):
    inc = store.obtener(id_, con_fotos)
    if not inc:
        raise HTTPException(404, f"No existe el reconocimiento {id_}")
    return inc


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/config", dependencies=[Depends(auth)])
def config():
    prov, mod = vision.modelo()
    return {"dry_run": DRY_RUN, "umbral": UMBRAL, "variacion_sospechosa": VARIACION_SOSPECHOSA,
            "erp": erp.nombre, "vision": {"proveedor": prov, "modelo": mod, "modelo_numero": vision.modelo(True)[1],
                                          "numero_lado_max": vision.NUMERO_LADO_MAX}, "url_revision": URL_REVISION}


# ---------------------------------------------------------------- incidencias
def _normalizar_foto(datos: bytes):
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos)))
    except Exception as e:
        raise HTTPException(422, f"No es una imagen válida: {e}")
    img = img.convert("RGB")
    if max(img.size) > 2400:
        img.thumbnail((2400, 2400), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue(), img.size


def _orden_campo(nombre):
    """foto, foto0, foto1… foto10 (n8n numera así los ficheros del webhook) en orden numérico."""
    cifras = nombre.lstrip("abcdefghijklmnopqrstuvwxyz_")
    return int(cifras) if cifras.isdigit() else -1


@app.post("/incidencias", dependencies=[Depends(auth)])
async def crear_incidencia(request: Request):
    """Guarda las fotos de un albarán (una por página), en multipart: cualquier campo de
    fichero cuyo nombre empiece por "foto" (foto, foto0, foto_1… o varias veces foto), en
    orden. `reprocesar` (true/false) y `paginas` (las que se esperan, para detectar que se
    ha perdido alguna) son opcionales. `tipo`: propio (por defecto), entrada o entrega; en los
    de terceros, `referencias` son nuestros albaranes si ya se saben (separados por espacios o comas).
    Idempotente por SHA-256: las mismas fotos en el mismo orden devuelven la misma incidencia
    con `duplicada: true` (salvo `reprocesar`, que la vuelve a dejar en 'recibida')."""
    form = await request.form()
    ficheros = [(k, i, v) for i, (k, v) in enumerate(form.multi_items())
                if isinstance(v, UploadFile) and k.lower().startswith("foto")]
    ficheros.sort(key=lambda x: (_orden_campo(x[0].lower()), x[1]))
    if not ficheros:
        raise HTTPException(422, "No se ha recibido ninguna foto")
    if len(ficheros) > MAX_PAGINAS:
        raise HTTPException(422, f"Demasiadas fotos: como mucho {MAX_PAGINAS} por albarán")
    esperadas = str(form.get("paginas") or "").strip()
    if esperadas.isdigit() and int(esperadas) != len(ficheros):
        raise HTTPException(422, f"Se esperaban {esperadas} fotos y han llegado {len(ficheros)}"
                                 + (f" (máximo {MAX_PAGINAS})" if int(esperadas) > MAX_PAGINAS else ""))
    paginas = []
    for n, (_, _, f) in enumerate(ficheros, 1):
        datos = await f.read()
        if not datos:
            raise HTTPException(422, f"La foto {n} está vacía")
        if len(datos) > MAX_BYTES:
            raise HTTPException(413, f"La foto {n} es demasiado grande (máx. 25 MB)")
        norm, (w, h) = _normalizar_foto(datos)
        paginas.append({"sha256": hashlib.sha256(datos).hexdigest(), "nombre_fichero": f.filename, "foto": norm,
                        "ancho": w, "alto": h, "original": datos, "mime": f.content_type})
    # Con una sola foto la huella es la de la foto (igual que antes de las páginas).
    sha = paginas[0]["sha256"] if len(paginas) == 1 else \
        hashlib.sha256("\n".join(p["sha256"] for p in paginas).encode()).hexdigest()
    reprocesar = str(form.get("reprocesar") or "").lower() in ("true", "1", "si", "sí", "on")
    tipo = str(form.get("tipo") or "propio").strip().lower()
    if tipo not in TIPOS:
        raise HTTPException(422, f"Tipo de albarán no válido: {tipo} (propio, entrada o entrega)")
    referencias = " ".join(terceros.separar(str(form.get("referencias") or ""))) or None if tipo != "propio" else None
    nombre = paginas[0]["nombre_fichero"] + (f" (+{len(paginas) - 1})" if len(paginas) > 1 else "") \
        if paginas[0]["nombre_fichero"] else None
    fila, nueva = store.crear(sha, nombre, paginas, reprocesar, tipo, referencias)
    return {**fila, "paginas": len(paginas) if nueva else len(store.obtener(fila["id"])["paginas"]),
            "duplicada": not nueva}


def _marca(inc):
    """'modificado' u 'original': lo aprobado si ya está resuelto; si no, lo que detectó la IA.
    'error' si no se pudo leer."""
    if inc["estado"] == "error":
        return "error"
    res, dec = inc.get("resolucion") or {}, inc.get("decision") or {}
    if inc["estado"] in ("aprobada", "corregida", "rectificada") and res.get("lineas"):
        return "modificado" if any(l["final"] != l["erp"] for l in res["lineas"]) else "original"
    if not dec:
        return None
    if dec.get("marca"):
        return dec["marca"]
    cambiada = any(l.get("cantidad_final") is not None and l["cantidad_final"] != l.get("erp")
                   for l in dec.get("lineas") or [])
    return "modificado" if cambiada or dec.get("extras") else "original"


def _lineas_erp(inc):
    """Líneas de nuestros albaranes: el del reconocimiento o, en terceros, los de sus referencias."""
    e = inc.get("erp") or {}
    if "albaranes" in e:
        return terceros.nuestras(e["albaranes"])
    return e.get("lineas", [])


def _cliente(i):
    e = i.get("erp") or {}
    a = (e.get("albaranes") or [e])[0] if e else {}
    return (a.get("cliente") or {}).get("nombre") or ((i.get("lectura") or {}).get("emisor") or {}).get("nombre")


def _con_marca(fila):
    return fila and {**fila, "marca": _marca(fila)}


@app.get("/incidencias", dependencies=[Depends(auth)])
def listar(estado: str | None = None, limite: int = Query(50, le=500), albaran: str | None = None,
           excluir: int | None = None, desde: str | None = None, hasta: str | None = None,
           tipo: str | None = None):
    """Resumen. `estado` admite varios separados por comas; `albaran` filtra por número
    (`excluir` quita un id, para buscar reconocimientos previos del mismo albarán);
    `desde`/`hasta` (AAAA-MM-DD, vacío = sin límite) por fecha de recepción; `tipo` por operación
    (propio, entrada, entrega; varios separados por comas)."""
    try:
        desde, hasta = (date.fromisoformat(x) if x else None for x in (desde, hasta))
    except ValueError:
        raise HTTPException(422, "Fecha no válida: usa AAAA-MM-DD")
    res = []
    for i in store.listar(estado, limite, albaran, excluir, desde, hasta, tipo):
        r = i["resolucion"] or {}
        lineas = (i["decision"] or {}).get("lineas") or []
        res.append({k: i[k] for k in ("id", "creada", "actualizada", "estado", "tipo", "albaran_numero",
                                       "albaran_id", "error")}
                   | {"marca": _marca(i), "cliente": _cliente(i),
                      "documento": (i["lectura"] or {}).get("numero_documento"),
                      "lineas": len(lineas), "paginas": len(i["paginas"]),
                      "revisar": sum(1 for l in lineas if l.get("estado") != "verificado"),
                      "cambios": r.get("cambios"), "revisado_por": r.get("usuario"),
                      "revisado": r.get("fecha"), "comentario": r.get("comentario")})
    return {"total": len(res), "resultados": res}


@app.get("/incidencias/{id_}", dependencies=[Depends(auth)])
def ficha(id_: int, imagen: bool = False):
    """Reconocimiento completo; con `imagen=true` cada página de `paginas` incluye su foto
    como data URL (`imagen`)."""
    inc = _inc(id_, con_fotos=imagen)
    for p in inc["paginas"] if imagen else ():
        p["imagen"] = "data:image/jpeg;base64," + base64.b64encode(p.pop("foto")).decode()
    inc["dry_run"] = DRY_RUN
    inc["marca"] = _marca(inc)
    return inc


@app.delete("/incidencias/{id_}", dependencies=[Depends(auth)])
def eliminar(id_: int):
    """Borra un reconocimiento con sus fotos. Solo los que están en error: el resto se rechaza en la revisión."""
    inc = _inc(id_)
    if not store.eliminar(id_, ("error",)):
        raise HTTPException(409, f"El reconocimiento está en estado '{inc['estado']}': solo se eliminan los que tienen error")
    return {"id": id_, "eliminado": True}


@app.get("/incidencias/{id_}/imagen", dependencies=[Depends(auth)])
def imagen(id_: int, original: bool = False, pagina: int = 1):
    f = store.foto(id_, original, pagina)
    if not f:
        raise HTTPException(404, f"No existe la foto {pagina} del reconocimiento {id_}")
    return Response(bytes(f["datos"]), media_type=f["mime"])


class Cambios(BaseModel):
    estado: str | None = None
    albaran_numero: str | None = None
    albaran_id: int | None = None
    origen_numero: str | None = None
    lectura_codigo: dict | None = None
    erp: dict | None = None
    lectura: dict | None = None
    decision: dict | None = None
    error: str | None = None
    evento: str | None = None


@app.patch("/incidencias/{id_}", dependencies=[Depends(auth)])
def actualizar(id_: int, c: Cambios):
    _inc(id_)
    datos = c.model_dump(exclude_unset=True)
    evento = datos.pop("evento", None)
    if "estado" in datos and datos["estado"] not in ESTADOS:
        raise HTTPException(422, f"Estado no válido: {datos['estado']}")
    return _con_marca(store.actualizar(id_, datos, evento))


class LineaFinal(BaseModel):
    linea_id: int
    cantidad_final: float = Field(ge=0)


class Resolucion(BaseModel):
    accion: str = Field(pattern="^(aprobar|corregir|rechazar)$")
    lineas: list[LineaFinal] = []
    usuario: str | None = None
    comentario: str | None = None


@app.post("/incidencias/{id_}/resolver", dependencies=[Depends(auth)])
def resolver(id_: int, r: Resolucion):
    """Decisión humana. aprobar = cantidades de la IA; corregir = las enviadas (las que falten,
    las de la IA); rechazar = no se toca el ERP."""
    inc = _inc(id_)
    if inc["estado"] not in ("pendiente_revision", "verificado"):
        raise HTTPException(409, f"El reconocimiento está en estado '{inc['estado']}' y no se puede resolver")
    ahora = datetime.now(timezone.utc).isoformat()
    base = {"accion": r.accion, "usuario": r.usuario, "comentario": r.comentario, "fecha": ahora}
    if r.accion == "rechazar":
        return _con_marca(store.actualizar(id_, {"estado": "rechazada", "resolucion": base}, "resolver",
                                ("pendiente_revision", "verificado")))
    dec = {l["linea_id"]: l for l in (inc["decision"] or {}).get("lineas", []) if l.get("linea_id")}
    enviadas = {l.linea_id: l.cantidad_final for l in r.lineas} if r.accion == "corregir" else {}
    lineas = []
    for l in _lineas_erp(inc):
        ia = (dec.get(l["id"]) or {}).get("cantidad_final")
        final = enviadas.get(l["id"], ia)
        if final is None:
            raise HTTPException(422, f"Falta la cantidad final de {l['producto']}")
        lineas.append({"linea_id": l["id"], "producto": l["producto"], "referencia": l["referencia"],
                       "erp": l["cantidad"], "ia": ia, "final": final})
    sobrantes = set(enviadas) - {l["linea_id"] for l in lineas}
    if sobrantes:
        raise HTTPException(422, f"Líneas que no son del albarán: {sorted(sobrantes)}")
    base |= {"lineas": lineas, "cambios": sum(1 for l in lineas if l["final"] != l["erp"])}
    estado = "aprobada" if r.accion == "aprobar" else "corregida"
    fila = store.actualizar(id_, {"estado": estado, "resolucion": base}, "resolver",
                            ("pendiente_revision", "verificado"))
    if not fila:
        raise HTTPException(409, "El reconocimiento ha cambiado de estado; recarga la página")
    return _con_marca(fila)


# ---------------------------------------------------------------- visión
class PeticionVision(BaseModel):
    incidencia_id: int
    tipo: str = Field("lectura", pattern="^(lectura|numero|terceros)$")
    albaran: dict | None = None
    intento: int = Field(2, ge=1, le=2)  # numero: 1 = primera foto, pequeña y modelo ligero; 2 = como la lectura


def _operacion(p: PeticionVision):
    """Entrada o entrega, para la lectura de un albarán de terceros."""
    if p.tipo != "terceros":
        return None
    tipo = _inc(p.incidencia_id)["tipo"]
    if tipo not in terceros.TIPO_ERP:
        raise HTTPException(409, "El reconocimiento es de un albarán propio, no de terceros")
    return tipo


def _fotos_para_vision(p: PeticionVision):
    if p.tipo == "lectura" and not p.albaran:
        raise HTTPException(422, "Falta el albarán del ERP")
    fotos = store.fotos(p.incidencia_id)
    if not fotos:
        raise HTTPException(404, "No existe el reconocimiento")
    return [bytes(f["datos"]) for f in fotos]


@app.post("/vision/peticion", dependencies=[Depends(auth)])
def vision_peticion(p: PeticionVision):
    """Petición lista para el proveedor de visión, sin clave: n8n la envía con su credencial.
    tipo=numero lee solo el número de albarán (cuando no hay código de barras), en dos intentos."""
    return vision.construir_peticion(p.tipo, _fotos_para_vision(p), p.albaran, _operacion(p), intento=p.intento)


class RespuestaVision(BaseModel):
    tipo: str = Field("lectura", pattern="^(lectura|numero|terceros|emparejar)$")
    proveedor: str
    respuesta: dict


@app.post("/vision/interpretar", dependencies=[Depends(auth)])
def vision_interpretar(r: RespuestaVision):
    """JSON estricto de la lectura a partir de la respuesta del proveedor, más las reglas
    (umbral) para que n8n decida."""
    return {"lectura": vision.interpretar(r.tipo, r.proveedor, r.respuesta),
            "reglas": {"umbral": UMBRAL, "variacion_sospechosa": VARIACION_SOSPECHOSA},
            "url_revision": URL_REVISION}


@app.post("/vision/leer", dependencies=[Depends(auth)])
def vision_leer(p: PeticionVision):
    """Llamada directa al proveedor (solo si el servicio tiene ANTHROPIC_API_KEY u OPENROUTER_API_KEY)."""
    return {"lectura": vision.llamar(p.tipo, _fotos_para_vision(p), p.albaran, _operacion(p)),
            "reglas": {"umbral": UMBRAL, "variacion_sospechosa": VARIACION_SOSPECHOSA},
            "url_revision": URL_REVISION}


# ---------------------------------------------------------------- terceros
class Busqueda(BaseModel):
    referencias: str | None = None  # None: las guardadas o, si no hay, las que ha leído la IA


def _inc_terceros(id_):
    inc = _inc(id_)
    if inc["tipo"] not in terceros.TIPO_ERP:
        raise HTTPException(409, "El reconocimiento es de un albarán propio, no de terceros")
    if not inc["lectura"]:
        raise HTTPException(409, "Todavía no se ha leído el albarán")
    if inc["estado"] in ("aprobada", "corregida", "rectificada", "rechazada"):
        raise HTTPException(409, f"El reconocimiento ya está resuelto ('{inc['estado']}')")
    return inc


@app.post("/terceros/{id_}/emparejar", dependencies=[Depends(auth)])
def terceros_emparejar(id_: int, b: Busqueda):
    """Busca en el ERP nuestros albaranes (las referencias enviadas, las guardadas o las que ha
    leído la IA) y prepara la petición a la IA para emparejar las líneas que no coinciden por
    EAN o código (`peticion`, null si no hace falta). Solo lee el ERP."""
    inc = _inc_terceros(id_)
    if b.referencias is not None:
        texto, origen = b.referencias, "manual"
    elif inc["referencias"]:
        texto, origen = inc["referencias"], "manual"
    else:
        texto, origen = terceros.detectadas(inc["lectura"]), "vision"
    refs = terceros.separar(texto)
    if not refs and origen == "manual":  # campo vaciado: se vuelve a las que ha leído la IA
        texto, origen = terceros.detectadas(inc["lectura"]), "vision"
        refs = terceros.separar(texto)
    albaranes, no_encontradas, avisos = terceros.buscar(erp, refs, inc["tipo"])
    pre = terceros.preemparejar(inc["lectura"], albaranes)
    datos = terceros.datos_emparejar(inc["lectura"], albaranes, pre)
    return {"incidencia_id": id_, "operacion": inc["tipo"], "referencias": refs, "origen": origen,
            "manual": " ".join(refs) if origen == "manual" and b.referencias is not None else None,
            "albaranes": albaranes, "no_encontradas": no_encontradas, "avisos": avisos,
            "pre": {str(k): v for k, v in pre.items()},
            "peticion": vision.construir_peticion("emparejar", [], emparejar=datos) if datos else None}


class Comparacion(BaseModel):
    busqueda: dict                  # respuesta de /terceros/{id}/emparejar
    proveedor: str | None = None    # y la de la IA, si hubo que emparejar
    respuesta: dict | None = None


@app.post("/terceros/{id_}/comparar", dependencies=[Depends(auth)])
def terceros_comparar(id_: int, c: Comparacion):
    """Compara su albarán con los nuestros y guarda la decisión (por revisar o verificado)."""
    inc = _inc_terceros(id_)
    b = c.busqueda
    emparejado = vision.interpretar("emparejar", c.proveedor, c.respuesta) if c.respuesta else None
    pre = {int(k): v for k, v in (b.get("pre") or {}).items()}
    albaranes = b.get("albaranes") or []
    lineas, extras, valorado = terceros.comparar(inc["lectura"], albaranes, pre, emparejado, UMBRAL, inc["tipo"])
    avisos = list(b.get("avisos") or [])
    if not b.get("referencias"):
        avisos.insert(0, "No se ha encontrado escrito nuestro albarán: escríbelo en «Nuestro albarán» y pulsa "
                         "«Buscar en el ERP»")
    for n in b.get("no_encontradas") or []:
        avisos.append(f"{n['referencia']}: {n['motivo']}")
    avisos += terceros.avisos_documento(inc["lectura"], albaranes, emparejado)
    if extras:
        avisos.append(f"{len(extras)} línea(s) del documento sin pareja en nuestros albaranes")
    # Otros reconocimientos del mismo tipo con estos albaranes (solos o juntos): solo es un aviso
    numeros = {a["numero"] for a in albaranes} | ({", ".join(a["numero"] for a in albaranes)} if albaranes else set())
    previos = sorted({r["id"]: {"id": r["id"], "estado": r["estado"], "creada": r["creada"].isoformat()}
                      for n in numeros for r in store.listar(albaran=n, excluir=id_, tipo=inc["tipo"])}.values(),
                     key=lambda r: r["id"])
    if previos:
        avisos.append("Este albarán ya se había reconocido antes: " + ", ".join(
            f"#{p['id']} del {p['creada'][8:10]}/{p['creada'][5:7]}/{p['creada'][:4]}" for p in previos))
    estado = "verificado" if albaranes and lineas and not extras and not avisos and         all(l["estado"] == "verificado" for l in lineas) else "pendiente_revision"
    marca = "modificado" if extras or any(l["motivos"] for l in lineas) else "original"
    meta = (emparejado or {}).get("meta")
    decision = {"estado": estado, "marca": marca, "umbral": UMBRAL, "umbral_emparejar": terceros.UMBRAL_EMPAREJAR,
                "valorado": valorado, "lineas": lineas, "extras": extras, "avisos": avisos, "previos": previos,
                "mismo_tercero": (emparejado or {}).get("mismo_tercero"),
                "comentario_emparejamiento": (emparejado or {}).get("comentario"), "emparejamiento": meta,
                "revision_url": f"{URL_REVISION}/{id_}"}
    cambios = {"estado": estado, "albaran_numero": ", ".join(a["numero"] for a in albaranes) or None,
               "albaran_id": albaranes[0]["id"] if albaranes else None, "origen_numero": b.get("origen"),
               "erp": {"operacion": inc["tipo"], "referencias": b.get("referencias") or [], "albaranes": albaranes,
                       "no_encontradas": b.get("no_encontradas") or []},
               "decision": decision}
    if b.get("manual") is not None or b.get("origen") == "vision":
        cambios["referencias"] = b.get("manual")
    fila = store.actualizar(id_, cambios, "comparar")
    return {**_con_marca(fila), "decision": decision}


# ---------------------------------------------------------------- ERP
@app.get("/erp/albaran", dependencies=[Depends(auth)])
def erp_albaran(numero: str | None = None, id: int | None = None):
    """Albarán normalizado por número impreso (o por id interno)."""
    if id:
        return erp.obtener_albaran_por_id(id)
    if not numero:
        raise HTTPException(422, "No se ha identificado el número de albarán: no hay código de barras "
                                 "legible ni número impreso visible en la foto")
    return erp.obtener_albaran(numero)


class Nota(BaseModel):
    html: str
    adjuntar_foto_de: int | None = None  # id de incidencia cuyas fotos se adjuntan


@app.post("/erp/albaranes/{albaran_id}/nota", dependencies=[Depends(auth)])
def erp_nota(albaran_id: int, n: Nota):
    adjuntos = _adjuntos(n.adjuntar_foto_de, original=True) if n.adjuntar_foto_de else []
    return erp.anadir_nota(albaran_id, n.html, adjuntos)


def _adjuntos(id_, original=False):
    """Fotos del reconocimiento como adjuntos (nombre, bytes, mime); "-p2"… si hay varias."""
    fotos = store.fotos(id_, original)
    res = []
    for f in fotos:
        ext = "jpg" if "jpeg" in f["mime"] else (f["mime"].split("/")[-1] or "jpg")
        pag = f"-p{f['pagina']}" if len(fotos) > 1 else ""
        res.append((f"albaran-foto-reconocimiento-{id_}{pag}.{ext}", bytes(f["datos"]), f["mime"]))
    return res


class PeticionRectificar(BaseModel):
    incidencia_id: int


@app.post("/erp/rectificar", dependencies=[Depends(auth)])
def erp_rectificar(p: PeticionRectificar):
    """Lleva al ERP las cantidades finales de una incidencia aprobada o corregida.
    Con DRY_RUN=true (por defecto) solo registra el plan."""
    inc = _inc(p.incidencia_id)
    if inc["tipo"] != "propio":
        raise HTTPException(409, "Los albaranes de terceros solo se comparan: no se rectifica nada en el ERP")
    if inc["estado"] not in ("aprobada", "corregida"):
        raise HTTPException(409, f"El reconocimiento está en estado '{inc['estado']}': solo se rectifican "
                                 "los aprobados o corregidos")
    res = inc["resolucion"] or {}
    actual = erp.obtener_albaran_por_id(inc["albaran_id"])
    leido = {l["id"]: l["cantidad"] for l in (inc["erp"] or {}).get("lineas", [])}
    finales = {l["linea_id"]: l["final"] for l in res.get("lineas", [])}
    for l in actual["lineas"]:
        if l["id"] in leido and l["cantidad"] != leido[l["id"]] and l["cantidad"] != finales.get(l["id"]):
            raise HTTPException(409, f"El albarán ha cambiado en el ERP desde la lectura ({l['producto']}: "
                                     f"{leido[l['id']]:g} → {l['cantidad']:g}); vuelve a procesar la foto")
    if actual["hecho"] != (inc["erp"] or {}).get("hecho"):
        raise HTTPException(409, "El albarán ha cambiado de estado en el ERP desde la lectura")
    cambios = [{"linea_id": i, "cantidad_actual": next(l["cantidad"] for l in actual["lineas"] if l["id"] == i),
                "cantidad_final": q} for i, q in finales.items()
               if any(l["id"] == i and l["cantidad"] != q for l in actual["lineas"])]
    ahora = datetime.now(timezone.utc).isoformat()
    if DRY_RUN:
        plan = erp.planificar_rectificacion(actual, cambios)
        rect = {"dry_run": True, "fecha": ahora, "cambios": cambios, **plan}
        store.actualizar(inc["id"], {"rectificacion": rect}, "rectificar_dry_run")
        return rect
    try:
        hecho = erp.aplicar_rectificacion(actual, cambios)
    except ErpError as e:
        store.actualizar(inc["id"], {"rectificacion": {"dry_run": False, "fecha": ahora, "cambios": cambios,
                                                       "error": e.mensaje}}, "rectificar_error")
        raise
    rect = {"dry_run": False, "fecha": ahora, "cambios": cambios, **hecho}
    lis = "".join(f"<li>{html.escape(x)}</li>" for x in hecho.get("hechos", []))
    fotos = _adjuntos(inc["id"])
    nota = (f"<p><b>Albarán rectificado</b> desde el reconocimiento #{inc['id']} "
            f"({html.escape(res.get('accion', ''))} por {html.escape(res.get('usuario') or 'revisión')}).</p>"
            f"<ul>{lis}</ul>" + (f"<p>{html.escape(res['comentario'])}</p>" if res.get("comentario") else "")
            + ("<p>Se adjuntan las fotos del albarán firmado.</p>" if len(fotos) > 1
               else "<p>Se adjunta la foto del albarán firmado.</p>"))
    try:
        rect["nota"] = erp.anadir_nota(actual["id"], nota, fotos)
    except ErpError as e:
        rect["avisos"] = rect.get("avisos", []) + [f"No se pudo añadir la nota: {e.mensaje}"]
    store.actualizar(inc["id"], {"estado": "rectificada", "rectificacion": rect}, "rectificar")
    return rect
