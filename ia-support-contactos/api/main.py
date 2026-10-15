"""API REST de contactos sobre res_partner de Odoo 20, por SQL directo.

Se salta el ORM de Odoo, así que replica lo que haría Odoo al escribir:
campos calculados almacenados (complete_name, commercial_partner_id,
commercial_company_name, email_normalized) y auditoría (write_date/uid).
El historial de cambios y el deshacer viven en el esquema propio "api".
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict, Field, field_validator

import nif as nif_util

_logger = logging.getLogger("contactos-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DSN = "host={} port={} dbname={} user={} password={}".format(
    os.environ.get("DB_HOST", "ia-support_surtidos-db"),
    os.environ.get("DB_PORT", "5432"),
    os.environ.get("DB_NAME", "odoo"),
    os.environ.get("DB_USER", "odoo"),
    os.environ.get("DB_PASSWORD", ""),
)
ODOO_UID = 1          # usuario que figura en create_uid / write_uid
ODOO_COMPANY_ID = 1   # compañía de los contactos creados por la API
MAX_RESULTADOS = 10

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS api;
CREATE TABLE IF NOT EXISTS api.contactos_log (
  id         BIGSERIAL PRIMARY KEY,
  partner_id INT NOT NULL,
  accion     VARCHAR(10) NOT NULL,   -- ALTA | MODIF | BAJA | UNDO
  antes      JSONB,
  despues    JSONB,
  sesion     VARCHAR(60),            -- id de sesión del chat
  usuario    VARCHAR(60),
  revertido  BOOLEAN NOT NULL DEFAULT FALSE,
  ts         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS contactos_log_sesion_idx ON api.contactos_log (sesion, id DESC);
"""

# Columnas de res_partner que gestiona la API: son la "foto" que se guarda
# en antes/despues y lo que se restaura al deshacer.
CAMPOS = ("name", "ref", "vat", "type", "is_company", "parent_id", "phone", "email", "active")


class Tipo(str, Enum):
    FACTURA = "FACTURA"
    ALBARAN = "ALBARAN"
    CADENA = "CADENA"


TIPO_A_ODOO = {
    Tipo.FACTURA: {"type": "invoice", "is_company": False},
    Tipo.ALBARAN: {"type": "delivery", "is_company": False},
    Tipo.CADENA: {"type": "contact", "is_company": True},
}

pool: Optional[ConnectionPool] = None


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

def esperar_odoo():
    """Bloquea hasta que la BD responde y Odoo ha creado res_partner."""
    import psycopg
    while True:
        try:
            with psycopg.connect(DSN, connect_timeout=5) as conn:
                if conn.execute("SELECT to_regclass('public.res_partner')").fetchone()[0]:
                    conn.execute(SCHEMA_SQL)
                    return
                _logger.info("res_partner aún no existe; esperando a que Odoo inicialice la BD")
        except psycopg.OperationalError as e:
            _logger.info("BD no disponible todavía: %s", str(e).strip().splitlines()[0])
        time.sleep(3)


@asynccontextmanager
async def lifespan(app):
    global pool
    esperar_odoo()
    # check_connection: descarta conexiones muertas (p. ej. tras reiniciar surtidos-db)
    pool = ConnectionPool(DSN, min_size=1, max_size=5, kwargs={"row_factory": dict_row},
                          check=ConnectionPool.check_connection, open=True)
    _logger.info("Conectada a la BD; esquema api listo")
    yield
    pool.close()


app = FastAPI(
    title="API de contactos (Odoo 20 por SQL)",
    description="Mantenimiento de contactos sobre res_partner con historial y deshacer.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Errores: siempre {"error": "..."}, nunca trazas
# ---------------------------------------------------------------------------

class ApiError(HTTPException):
    pass


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    mensajes = []
    for err in exc.errors():
        campo = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
        mensajes.append(f"{campo}: {err.get('msg')}" if campo else err.get("msg"))
    return JSONResponse(status_code=422, content={"error": "; ".join(mensajes)})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    _logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})


# ---------------------------------------------------------------------------
# Modelos de entrada
# ---------------------------------------------------------------------------

class Auditoria(BaseModel):
    sesion: Optional[str] = Field(None, max_length=60)
    usuario: Optional[str] = Field(None, max_length=60)


class ContactoBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: Optional[str] = Field(None, min_length=1, max_length=64)
    nif: Optional[str] = Field(None, max_length=32)
    nombre: Optional[str] = Field(None, min_length=1, max_length=256)
    tipo: Optional[Tipo] = None
    cadena_id: Optional[int] = None
    telefono: Optional[str] = Field(None, max_length=32)
    email: Optional[str] = Field(None, max_length=240)
    sesion: Optional[str] = Field(None, max_length=60)
    usuario: Optional[str] = Field(None, max_length=60)

    @field_validator("nif")
    @classmethod
    def validar_nif(cls, v):
        if v is None:
            return v
        if not nif_util.es_valido(v):
            raise ValueError("NIF/NIE/CIF no válido")
        return nif_util.normalizar(v)

    @field_validator("codigo", "nombre", "telefono", "email")
    @classmethod
    def recortar(cls, v):
        return v.strip() if isinstance(v, str) else v


class ContactoAlta(ContactoBase):
    nombre: str = Field(..., min_length=1, max_length=256)
    tipo: Tipo


class ContactoModif(ContactoBase):
    activo: Optional[bool] = None


# ---------------------------------------------------------------------------
# Acceso a datos
# ---------------------------------------------------------------------------

SELECT_CONTACTO = """
SELECT p.id, p.ref, p.vat, p.name, p.complete_name, p.type, p.is_company,
       p.parent_id, par.name AS parent_name, p.phone, p.email, p.active, p.write_date
  FROM res_partner p
  LEFT JOIN res_partner par ON par.id = p.parent_id
"""


def tipo_api(row) -> str:
    if row["is_company"]:
        return Tipo.CADENA.value
    # FACTURA/ALBARAN para las direcciones; el resto se devuelve con el tipo estándar de Odoo
    return {"invoice": Tipo.FACTURA.value, "delivery": Tipo.ALBARAN.value}.get(row["type"], row["type"])


def a_api(row) -> dict:
    return {
        "id": row["id"],
        "codigo": row["ref"],
        "nif": row["vat"],
        "nombre": row["name"],
        "nombre_completo": row["complete_name"],
        "tipo": tipo_api(row),
        "cadena_id": row["parent_id"],
        "cadena_nombre": row["parent_name"],
        "telefono": row["phone"],
        "email": row["email"],
        "activo": row["active"],
        "modificado": row["write_date"].isoformat() if row["write_date"] else None,
    }


def leer(cur, partner_id: int, bloquear=False) -> dict:
    sql = SELECT_CONTACTO + " WHERE p.id = %s" + (" FOR UPDATE OF p" if bloquear else "")
    row = cur.execute(sql, (partner_id,)).fetchone()
    if not row:
        raise ApiError(404, f"El contacto {partner_id} no existe")
    return row


def foto(cur, partner_id: int) -> dict:
    row = cur.execute(f"SELECT {', '.join(CAMPOS)} FROM res_partner WHERE id = %s", (partner_id,)).fetchone()
    return dict(row) if row else None


def campos_odoo(datos: BaseModel) -> dict:
    """Traduce los campos enviados (solo esos) al vocabulario de res_partner."""
    enviados = datos.model_dump(exclude_unset=True, exclude={"sesion", "usuario"})
    mapeo = {"codigo": "ref", "nif": "vat", "nombre": "name", "cadena_id": "parent_id",
             "telefono": "phone", "email": "email", "activo": "active"}
    vals = {mapeo[k]: v for k, v in enviados.items() if k in mapeo}
    if "tipo" in enviados:
        if enviados["tipo"] is None:
            raise ApiError(422, "tipo: no puede ser nulo")
        vals.update(TIPO_A_ODOO[Tipo(enviados["tipo"])])
    if "name" in vals and not vals["name"]:
        raise ApiError(422, "nombre: no puede estar vacío")
    return vals


def validar(cur, partner_id: Optional[int], estado: dict):
    """Reglas de negocio sobre el estado final del contacto."""
    if estado.get("ref"):
        dup = cur.execute(
            "SELECT id FROM res_partner WHERE active AND lower(ref) = lower(%s) AND id IS DISTINCT FROM %s LIMIT 1",
            (estado["ref"], partner_id),
        ).fetchone()
        if dup:
            raise ApiError(409, f"El código {estado['ref']} ya lo usa el contacto {dup['id']}")
    if estado.get("parent_id"):
        if estado.get("is_company"):
            raise ApiError(400, "Una CADENA no puede pertenecer a otra cadena (quita cadena_id)")
        if estado["parent_id"] == partner_id:
            raise ApiError(400, "Un contacto no puede ser su propia cadena")
        padre = cur.execute("SELECT is_company, active FROM res_partner WHERE id = %s",
                            (estado["parent_id"],)).fetchone()
        if not padre:
            raise ApiError(400, f"La cadena {estado['parent_id']} no existe")
        if not padre["is_company"] or not padre["active"]:
            raise ApiError(400, f"El contacto {estado['parent_id']} no es una cadena activa")


def escribir(cur, partner_id: int, vals: dict, heredar_nif=False):
    """Escribe vals en res_partner y recalcula los campos almacenados que Odoo calcularía.

    heredar_nif: al asignar cadena sin NIF propio, copia el de la empresa (como Odoo).
    """
    estado = foto(cur, partner_id)
    estado.update(vals)

    commercial_id, ccn, padre_nombre, lang = partner_id, None, None, None
    if estado["parent_id"]:
        padre = cur.execute(
            """SELECT par.name, par.lang, par.commercial_partner_id, cp.name AS cp_name, cp.is_company AS cp_company
                 FROM res_partner par JOIN res_partner cp ON cp.id = par.commercial_partner_id
                WHERE par.id = %s""", (estado["parent_id"],)).fetchone()
        commercial_id, padre_nombre, lang = padre["commercial_partner_id"], padre["name"], padre["lang"]
        ccn = padre["cp_name"] if padre["cp_company"] else None
        if heredar_nif and not estado["vat"]:
            cur.execute("SELECT vat FROM res_partner WHERE id = %s", (commercial_id,))
            estado["vat"] = cur.fetchone()["vat"]
    elif estado["is_company"]:
        ccn = estado["name"]

    complete = estado["name"] or ""
    if estado["parent_id"] and not estado["is_company"]:
        complete = f"{ccn or padre_nombre}, {complete}"

    cur.execute(
        f"""UPDATE res_partner SET {', '.join(f'{c} = %({c})s' for c in CAMPOS)},
                   complete_name = %(complete)s, commercial_partner_id = %(commercial_id)s,
                   commercial_company_name = %(ccn)s, email_normalized = %(email_norm)s,
                   lang = coalesce(%(lang)s::varchar, lang, 'en_US'),
                   write_date = now() AT TIME ZONE 'UTC', write_uid = %(uid)s
             WHERE id = %(id)s""",
        {**estado, "complete": complete.strip(), "commercial_id": commercial_id, "ccn": ccn,
         "email_norm": (estado["email"] or "").strip().lower() or None,
         "lang": lang, "uid": ODOO_UID, "id": partner_id},
    )

    if estado["is_company"] or vals.get("is_company") is False:
        # Como hace Odoo: los hijos heredan el nombre comercial de la empresa
        cur.execute(
            """UPDATE res_partner c
                  SET commercial_partner_id = CASE WHEN c.is_company THEN c.id ELSE %(id)s END,
                      commercial_company_name = %(ccn)s::varchar,
                      complete_name = CASE WHEN c.is_company THEN c.name
                                           ELSE coalesce(%(ccn)s::varchar, %(name)s::varchar) || ', ' || coalesce(c.name, '') END
                WHERE c.parent_id = %(id)s""",
            {"id": partner_id, "ccn": ccn, "name": estado["name"]},
        )


def registrar(cur, partner_id, accion, antes, despues, sesion, usuario) -> int:
    return cur.execute(
        """INSERT INTO api.contactos_log (partner_id, accion, antes, despues, sesion, usuario)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (partner_id, accion, Jsonb(antes) if antes else None, Jsonb(despues) if despues else None,
         sesion, usuario),
    ).fetchone()["id"]


def respuesta(cur, partner_id, log_id) -> dict:
    return {**a_api(leer(cur, partner_id)), "log_id": log_id}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["sistema"])
def health():
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1 FROM res_partner LIMIT 1")
        return {"ok": True}
    except Exception:
        return JSONResponse(status_code=503, content={"ok": False, "error": "Base de datos no disponible"})


@app.get("/contactos", tags=["contactos"])
def buscar(q: str = Query(..., min_length=1, description="NIF, código o nombre (parcial)"),
           incluir_bajas: bool = Query(False, description="Incluir contactos archivados")):
    patron = f"%{q.strip()}%"
    patron_nif = f"%{nif_util.normalizar(q)}%"
    with pool.connection() as conn:
        rows = conn.execute(
            SELECT_CONTACTO + """
             WHERE (p.active OR %s)
               AND (p.complete_name ILIKE %s OR p.name ILIKE %s OR p.ref ILIKE %s
                    OR replace(p.vat, ' ', '') ILIKE %s)
             ORDER BY p.is_company DESC NULLS LAST, p.complete_name, p.id
             LIMIT %s""",
            (incluir_bajas, patron, patron, patron, patron_nif, MAX_RESULTADOS),
        ).fetchall()
    return {"total": len(rows), "requiere_eleccion": len(rows) > 1, "resultados": [a_api(r) for r in rows]}


@app.get("/contactos/{partner_id}", tags=["contactos"])
def ficha(partner_id: int):
    with pool.connection() as conn:
        return a_api(leer(conn.cursor(), partner_id))


@app.post("/contactos", status_code=201, tags=["contactos"])
def alta(datos: ContactoAlta):
    vals = campos_odoo(datos)
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        estado = {c: None for c in CAMPOS} | {"active": True} | vals
        validar(cur, None, estado)
        partner_id = cur.execute("SELECT nextval('res_partner_id_seq') AS id").fetchone()["id"]
        cur.execute(
            """INSERT INTO res_partner (id, name, complete_name, type, active, company_id, color, lang,
                                        partner_share, commercial_partner_id,
                                        create_date, write_date, create_uid, write_uid)
               VALUES (%(id)s, %(name)s, %(name)s, %(type)s, true, %(company)s, 0, 'en_US',
                       true, %(id)s, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', %(uid)s, %(uid)s)""",
            {"id": partner_id, "name": estado["name"], "type": estado["type"],
             "company": ODOO_COMPANY_ID, "uid": ODOO_UID},
        )
        escribir(cur, partner_id, estado, heredar_nif=True)
        log_id = registrar(cur, partner_id, "ALTA", None, foto(cur, partner_id), datos.sesion, datos.usuario)
        return respuesta(cur, partner_id, log_id)


@app.patch("/contactos/{partner_id}", tags=["contactos"])
def modificar(partner_id: int, datos: ContactoModif):
    vals = campos_odoo(datos)
    if not vals:
        raise ApiError(400, "No se ha enviado ningún campo a modificar")
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        leer(cur, partner_id, bloquear=True)
        antes = foto(cur, partner_id)
        validar(cur, partner_id, antes | vals)
        escribir(cur, partner_id, vals, heredar_nif="parent_id" in vals and "vat" not in vals)
        despues = foto(cur, partner_id)
        log_id = registrar(cur, partner_id, "MODIF", antes, despues, datos.sesion, datos.usuario)
        return respuesta(cur, partner_id, log_id)


@app.delete("/contactos/{partner_id}", tags=["contactos"])
def baja(partner_id: int,
         sesion: Optional[str] = Query(None, max_length=60),
         usuario: Optional[str] = Query(None, max_length=60)):
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        leer(cur, partner_id, bloquear=True)
        antes = foto(cur, partner_id)
        if not antes["active"]:
            raise ApiError(409, f"El contacto {partner_id} ya está de baja")
        escribir(cur, partner_id, {"active": False})  # baja lógica: nunca DELETE
        log_id = registrar(cur, partner_id, "BAJA", antes, foto(cur, partner_id), sesion, usuario)
        return respuesta(cur, partner_id, log_id)


@app.post("/log/{log_id}/undo", tags=["historial"])
def deshacer(log_id: int, auditoria: Optional[Auditoria] = Body(None)):
    auditoria = auditoria or Auditoria()
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        entrada = cur.execute("SELECT * FROM api.contactos_log WHERE id = %s FOR UPDATE", (log_id,)).fetchone()
        if not entrada:
            raise ApiError(404, f"El cambio {log_id} no existe")
        if entrada["accion"] == "UNDO":
            raise ApiError(400, "Un deshacer no se puede deshacer; repite el cambio original")
        if entrada["revertido"]:
            raise ApiError(409, f"El cambio {log_id} ya estaba deshecho")

        partner_id = entrada["partner_id"]
        leer(cur, partner_id, bloquear=True)
        actual = foto(cur, partner_id)
        if actual != entrada["despues"]:
            raise ApiError(409, f"El contacto {partner_id} ha cambiado después de ese cambio; no se puede deshacer")

        # Deshacer un ALTA = baja lógica; el resto restaura la foto "antes"
        objetivo = entrada["antes"] or {**actual, "active": False}
        if objetivo["active"]:
            validar(cur, partner_id, objetivo)
        escribir(cur, partner_id, {c: objetivo[c] for c in CAMPOS})
        cur.execute("UPDATE api.contactos_log SET revertido = true WHERE id = %s", (log_id,))
        nuevo_log = registrar(cur, partner_id, "UNDO", actual, foto(cur, partner_id),
                              auditoria.sesion or entrada["sesion"], auditoria.usuario or entrada["usuario"])
        return {**respuesta(cur, partner_id, nuevo_log), "deshecho_log_id": log_id}


@app.get("/log", tags=["historial"])
def historial(sesion: Optional[str] = Query(None, max_length=60),
              limite: int = Query(50, ge=1, le=500)):
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT id AS log_id, partner_id, accion, antes, despues, sesion, usuario, revertido, ts
                 FROM api.contactos_log WHERE (%(s)s::text IS NULL OR sesion = %(s)s)
                ORDER BY id DESC LIMIT %(l)s""",
            {"s": sesion, "l": limite},
        ).fetchall()
    for r in rows:
        r["ts"] = r["ts"].isoformat()
    return {"total": len(rows), "cambios": rows}
