"""API interna (red de Easypanel) para el flujo n8n "Docling - Convertir y anonimizar".

Los PDF no viajan dentro de los datos de la ejecución de n8n: el formulario sube el fichero aquí
(multipart), se trocea a disco y este servicio le pasa cada tramo a docling (POST
/trozos/{id}/{n}/docling), devolviendo a n8n solo el task_id. No se usa `kind: http` de docling
porque rechaza las URL de la red interna ("URL is not allowed", protección SSRF). Motivo (12/11): con el PDF y
los tramos en base64 (~40 MB) en la ejecución, cada nodo Code tardaba más en pasarle los datos al
runner y hacia el tramo 7 de 9 n8n cortaba con "Task request timed out" (dos veces seguidas).
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request
import shutil
import time
import uuid

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from anonimizar import CATEGORIAS, POR_DEFECTO, Anonimizador
from trocear import trocear

app = FastAPI(title="anonimizador")
motor = Anonimizador()  # carga spaCy una vez al arrancar

DIR_TROZOS = os.environ.get("DIR_TROZOS", "/tmp/trozos")
CADUCIDAD_S = 6 * 3600  # tramos huérfanos (ejecución fallida): se borran a las 6 h
DOCLING = os.environ.get("DOCLING_URL", "http://ia-support_docling:5001")
ID_VALIDO = re.compile(r"^[0-9a-f]{32}$")


class Peticion(BaseModel):
    texto: str
    terminos: list[str] = []
    categorias: list[str] | None = None


def _purgar_caducados():
    if not os.path.isdir(DIR_TROZOS):
        return
    limite = time.time() - CADUCIDAD_S
    for d in os.listdir(DIR_TROZOS):
        ruta = os.path.join(DIR_TROZOS, d)
        if os.path.getmtime(ruta) < limite:
            shutil.rmtree(ruta, ignore_errors=True)


def _dir(id_):
    if not ID_VALIDO.match(id_):
        raise HTTPException(404, "No existe")
    return os.path.join(DIR_TROZOS, id_)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/categorias")
def categorias():
    return {"categorias": list(CATEGORIAS), "por_defecto": POR_DEFECTO}


@app.post("/trocear")
def trocear_pdf(pdf: UploadFile = File(...), paginas_por_tramo: int = Query(25, ge=1, le=500)):
    """Trocea en PDFs independientes (cada página solo con las imágenes que dibuja, ver trocear.py),
    los guarda en disco y devuelve sus URL para docling."""
    _purgar_caducados()
    try:
        total, tramos = trocear(pdf.file.read(), paginas_por_tramo)
    except Exception as e:
        raise HTTPException(422, f"No se puede leer el PDF: {e}")
    id_ = uuid.uuid4().hex
    os.makedirs(_dir(id_), exist_ok=True)
    salida = []
    for n, t in enumerate(tramos, 1):
        with open(os.path.join(_dir(id_), f"{n}.pdf"), "wb") as fh:
            fh.write(t["pdf"])
        salida.append({"tramo": n, "page_start": t["page_start"], "page_end": t["page_end"],
                       "bytes": len(t["pdf"])})
    return {"id": id_, "paginas": total, "tramos": salida}


@app.get("/trozos/{id_}/{n}.pdf")
def trozo(id_: str, n: int):
    ruta = os.path.join(_dir(id_), f"{n}.pdf")
    if not os.path.isfile(ruta):
        raise HTTPException(404, "No existe")
    return FileResponse(ruta, media_type="application/pdf", filename=f"tramo{n}.pdf")


@app.post("/trozos/{id_}/{n}/docling")
def enviar_a_docling(id_: str, n: int, opciones: dict, sincrono: bool = False):
    """Envía el tramo a docling con las `opciones` de conversión que pasa n8n y devuelve su respuesta
    tal cual: {task_id, ...} en asíncrono; el documento convertido si `sincrono` (sondeo de OCR)."""
    ruta = os.path.join(_dir(id_), f"{n}.pdf")
    if not os.path.isfile(ruta):
        raise HTTPException(404, "No existe")
    with open(ruta, "rb") as fh:
        cuerpo = json.dumps({"sources": [{"kind": "file", "filename": f"tramo{n}.pdf",
                                          "base64_string": base64.b64encode(fh.read()).decode()}],
                             "options": opciones}).encode()
    url = f"{DOCLING}/v1/convert/source" + ("" if sincrono else "/async")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, data=cuerpo, headers={"Content-Type": "application/json"}), timeout=900) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"docling {e.code}: {e.read()[:500].decode(errors='replace')}")
    except Exception as e:
        raise HTTPException(502, f"docling: {e}")


@app.delete("/trozos/{id_}")
def borrar_trozos(id_: str):
    shutil.rmtree(_dir(id_), ignore_errors=True)
    return {"ok": True}


@app.post("/anonimizar")
def anonimizar(p: Peticion):
    t0 = time.time()
    r = motor.anonimizar(p.texto, p.terminos, p.categorias)
    r["segundos"] = round(time.time() - t0, 1)
    return r
