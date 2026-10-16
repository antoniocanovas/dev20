"""albaranes-api: incidencias de albaranes modificados a mano.

- Incidencias: foto, lectura de la IA, decisión, revisión humana (BD propia).
- Visión: lee el albarán con un modelo multimodal (vision.py).
- ERP: única puerta al ERP (paquete erp/, hoy Odoo 20 por JSON-2).

Lo orquestan los flujos de n8n "Albaranes IA - Ingesta" y "Albaranes IA - Revisión".
"""
import base64
import hashlib
import html
import io
import os
from datetime import datetime, timezone


def _cargar_env_file(ruta=os.getenv("ENV_FILE", "/run/config/albaranes-ia.env")):
    """Secretos en un fichero montado (no en el panel). No pisa variables ya definidas."""
    if os.path.isfile(ruta):
        for linea in open(ruta, encoding="utf-8"):
            k, sep, v = linea.strip().partition("=")
            if sep and k and not k.startswith("#"):
                os.environ.setdefault(k, v)


_cargar_env_file()

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

import vision
from erp import ErpError, crear_erp
from store import ESTADOS, Store  # noqa: E402

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


def _inc(id_, con_foto=False):
    inc = store.obtener(id_, con_foto)
    if not inc:
        raise HTTPException(404, f"No existe la incidencia {id_}")
    return inc


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/config", dependencies=[Depends(auth)])
def config():
    prov, mod = vision.modelo()
    return {"dry_run": DRY_RUN, "umbral": UMBRAL, "variacion_sospechosa": VARIACION_SOSPECHOSA,
            "erp": erp.nombre, "vision": {"proveedor": prov, "modelo": mod}, "url_revision": URL_REVISION}


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


@app.post("/incidencias", dependencies=[Depends(auth)])
async def crear_incidencia(foto: UploadFile = File(...), reprocesar: bool = Form(False)):
    """Guarda la foto. Idempotente por SHA-256: la misma foto devuelve la misma incidencia
    con `duplicada: true` (salvo `reprocesar`, que la vuelve a dejar en 'recibida')."""
    datos = await foto.read()
    if not datos:
        raise HTTPException(422, "Foto vacía")
    if len(datos) > MAX_BYTES:
        raise HTTPException(413, "Foto demasiado grande (máx. 25 MB)")
    sha = hashlib.sha256(datos).hexdigest()
    norm, (w, h) = _normalizar_foto(datos)
    fila, nueva = store.crear(sha, foto.filename, norm, w, h, datos, foto.content_type, reprocesar)
    return {**fila, "duplicada": not nueva}


@app.get("/incidencias", dependencies=[Depends(auth)])
def listar(estado: str | None = None, limite: int = Query(50, le=500)):
    """Resumen. `estado` admite varios separados por comas."""
    res = []
    for i in store.listar(estado, limite):
        lineas = (i["decision"] or {}).get("lineas") or []
        res.append({k: i[k] for k in ("id", "creada", "actualizada", "estado", "albaran_numero",
                                       "albaran_id", "error")}
                   | {"cliente": ((i["erp"] or {}).get("cliente") or {}).get("nombre"),
                      "lineas": len(lineas),
                      "revisar": sum(1 for l in lineas if l.get("estado") != "verificado")})
    return {"total": len(res), "resultados": res}


@app.get("/incidencias/{id_}", dependencies=[Depends(auth)])
def ficha(id_: int, imagen: bool = False):
    """Incidencia completa; con `imagen=true` incluye la foto como data URL."""
    inc = _inc(id_, con_foto=imagen)
    if imagen:
        inc["imagen"] = "data:image/jpeg;base64," + base64.b64encode(inc.pop("foto")).decode()
    inc["dry_run"] = DRY_RUN
    return inc


@app.get("/incidencias/{id_}/imagen", dependencies=[Depends(auth)])
def imagen(id_: int, original: bool = False):
    f = store.foto(id_, original)
    if not f:
        raise HTTPException(404, f"No existe la incidencia {id_}")
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
    return store.actualizar(id_, datos, evento)


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
        raise HTTPException(409, f"La incidencia está en estado '{inc['estado']}' y no se puede resolver")
    ahora = datetime.now(timezone.utc).isoformat()
    base = {"accion": r.accion, "usuario": r.usuario, "comentario": r.comentario, "fecha": ahora}
    if r.accion == "rechazar":
        return store.actualizar(id_, {"estado": "rechazada", "resolucion": base}, "resolver",
                                ("pendiente_revision", "verificado"))
    dec = {l["linea_id"]: l for l in (inc["decision"] or {}).get("lineas", []) if l.get("linea_id")}
    enviadas = {l.linea_id: l.cantidad_final for l in r.lineas} if r.accion == "corregir" else {}
    lineas = []
    for l in (inc["erp"] or {}).get("lineas", []):
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
        raise HTTPException(409, "La incidencia ha cambiado de estado; recarga la página")
    return fila


# ---------------------------------------------------------------- visión
class PeticionVision(BaseModel):
    incidencia_id: int
    tipo: str = Field("lectura", pattern="^(lectura|numero)$")
    albaran: dict | None = None


def _foto_para_vision(p: PeticionVision):
    if p.tipo == "lectura" and not p.albaran:
        raise HTTPException(422, "Falta el albarán del ERP")
    f = store.foto(p.incidencia_id)
    if not f:
        raise HTTPException(404, "No existe la incidencia")
    return bytes(f["datos"])


@app.post("/vision/peticion", dependencies=[Depends(auth)])
def vision_peticion(p: PeticionVision):
    """Petición lista para el proveedor de visión, sin clave: n8n la envía con su credencial.
    tipo=numero lee solo el número de albarán (cuando no hay código de barras)."""
    return vision.construir_peticion(p.tipo, _foto_para_vision(p), p.albaran)


class RespuestaVision(BaseModel):
    tipo: str = Field("lectura", pattern="^(lectura|numero)$")
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
    return {"lectura": vision.llamar(p.tipo, _foto_para_vision(p), p.albaran),
            "reglas": {"umbral": UMBRAL, "variacion_sospechosa": VARIACION_SOSPECHOSA},
            "url_revision": URL_REVISION}


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
    adjuntar_foto_de: int | None = None  # id de incidencia cuya foto se adjunta


@app.post("/erp/albaranes/{albaran_id}/nota", dependencies=[Depends(auth)])
def erp_nota(albaran_id: int, n: Nota):
    adjuntos = []
    if n.adjuntar_foto_de:
        f = store.foto(n.adjuntar_foto_de, original=True)
        if f:
            ext = "jpg" if "jpeg" in f["mime"] else (f["mime"].split("/")[-1] or "jpg")
            adjuntos.append((f"albaran-foto-incidencia-{n.adjuntar_foto_de}.{ext}", bytes(f["datos"]), f["mime"]))
    return erp.anadir_nota(albaran_id, n.html, adjuntos)


class PeticionRectificar(BaseModel):
    incidencia_id: int


@app.post("/erp/rectificar", dependencies=[Depends(auth)])
def erp_rectificar(p: PeticionRectificar):
    """Lleva al ERP las cantidades finales de una incidencia aprobada o corregida.
    Con DRY_RUN=true (por defecto) solo registra el plan."""
    inc = _inc(p.incidencia_id)
    if inc["estado"] not in ("aprobada", "corregida"):
        raise HTTPException(409, f"La incidencia está en estado '{inc['estado']}': solo se rectifican "
                                 "las aprobadas o corregidas")
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
    nota = (f"<p><b>Albarán rectificado</b> desde la incidencia #{inc['id']} "
            f"({html.escape(res.get('accion', ''))} por {html.escape(res.get('usuario') or 'revisión')}).</p>"
            f"<ul>{lis}</ul>" + (f"<p>{html.escape(res['comentario'])}</p>" if res.get("comentario") else "")
            + "<p>Se adjunta la foto del albarán firmado.</p>")
    try:
        rect["nota"] = erp.anadir_nota(actual["id"], nota, [(
            f"albaran-foto-incidencia-{inc['id']}.jpg", bytes(store.foto(inc["id"])["datos"]), "image/jpeg")])
    except ErpError as e:
        rect["avisos"] = rect.get("avisos", []) + [f"No se pudo añadir la nota: {e.mensaje}"]
    store.actualizar(inc["id"], {"estado": "rectificada", "rectificacion": rect}, "rectificar")
    return rect
