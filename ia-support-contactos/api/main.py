"""API REST de contactos y tarifas (y consulta de albaranes) sobre Odoo 20, por SQL directo.

Se salta el ORM de Odoo, así que replica lo que haría Odoo al escribir:
campos calculados almacenados (complete_name, commercial_partner_id,
commercial_company_name, email_normalized), la tarifa como campo comercial
que comparten la empresa y sus direcciones, y auditoría (write_date/uid).
El historial de cambios y el deshacer viven en el esquema propio "api".
"""
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date
from enum import Enum
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
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
# Idioma en que se leen y crean los nombres traducibles (tarifas, productos)
ODOO_LANG = os.environ.get("ODOO_LANG", "es_ES")
if not re.fullmatch(r"[a-z]{2,3}_[A-Z]{2}", ODOO_LANG):
    raise RuntimeError(f"ODOO_LANG no válido: {ODOO_LANG}")

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS api;
CREATE TABLE IF NOT EXISTS api.contactos_log (
  id         BIGSERIAL PRIMARY KEY,
  partner_id INT NOT NULL,
  accion     VARCHAR(10) NOT NULL,   -- ALTA | MODIF | BAJA | UNDO | ASIGNAR | DUPLICAR | CREAR
  antes      JSONB,
  despues    JSONB,
  sesion     VARCHAR(60),            -- id de sesión del chat
  usuario    VARCHAR(60),
  revertido  BOOLEAN NOT NULL DEFAULT FALSE,
  ts         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS contactos_log_sesion_idx ON api.contactos_log (sesion, id DESC);
-- v1.1: el log también guarda cambios de tarifas y de sus precios
ALTER TABLE api.contactos_log ADD COLUMN IF NOT EXISTS entidad VARCHAR(10) NOT NULL DEFAULT 'contacto';  -- contacto | tarifa | precio
ALTER TABLE api.contactos_log ADD COLUMN IF NOT EXISTS objeto_id INT;   -- tarifa creada o regla de precio afectada
ALTER TABLE api.contactos_log ALTER COLUMN partner_id DROP NOT NULL;
"""

# Columnas de res_partner que gestiona la API: son la "foto" que se guarda
# en antes/despues y lo que se restaura al deshacer.
CAMPOS = ("name", "ref", "vat", "type", "is_company", "parent_id", "phone", "email", "active")


class Tipo(str, Enum):
    FACTURA = "FACTURA"
    ALBARAN = "ALBARAN"
    CADENA = "CADENA"


# Columnas obligatorias de res_partner que añaden otros módulos, con su valor
# por defecto en Odoo. Solo se usan si la columna existe (p. ej. con Facturación).
DEFECTOS_PARTNER = {
    "autopost_bills": "ask",   # account
}

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
    description="Mantenimiento de contactos sobre res_partner y de sus tarifas, con historial y deshacer.",
    version="1.3.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def quitar_parametros_vacios(request: Request, call_next):
    """`?tipo=&desde=` equivale a no mandarlos: así las herramientas del chat pueden dejar filtros vacíos."""
    qs = request.scope.get("query_string", b"")
    if qs:
        request.scope["query_string"] = b"&".join(p for p in qs.split(b"&") if p and not p.endswith(b"="))
    return await call_next(request)


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


class AsignarTarifa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tarifa_id: Optional[int] = Field(..., description="Tarifa a asignar; null quita la asignada y vuelve a la por defecto")
    sesion: Optional[str] = Field(None, max_length=60)
    usuario: Optional[str] = Field(None, max_length=60)


class NuevaTarifa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(..., min_length=1, max_length=128)
    contacto_id: Optional[int] = Field(None, description="Si se indica, se asigna la tarifa nueva a su empresa")
    sesion: Optional[str] = Field(None, max_length=60)
    usuario: Optional[str] = Field(None, max_length=60)

    @field_validator("nombre")
    @classmethod
    def recortar(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("no puede estar vacío")
        return v


class DuplicarTarifa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Optional[str] = Field(None, min_length=1, max_length=128, description="Por defecto: '<tarifa> - <cliente>'")
    sesion: Optional[str] = Field(None, max_length=60)
    usuario: Optional[str] = Field(None, max_length=60)

    @field_validator("nombre")
    @classmethod
    def recortar(cls, v):
        return v.strip() if isinstance(v, str) else v


class PrecioTarifa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producto_id: int = Field(..., description="id del producto (plantilla), de GET /productos")
    precio: float = Field(..., ge=0)
    cantidad_minima: float = Field(0, ge=0)
    sesion: Optional[str] = Field(None, max_length=60)
    usuario: Optional[str] = Field(None, max_length=60)


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

    if commercial_id != partner_id and hay_tarifas(cur):
        # La tarifa es un campo comercial: la dirección lleva la de su empresa, como en Odoo
        cur.execute(
            """UPDATE res_partner p SET specific_property_product_pricelist = c.specific_property_product_pricelist
                 FROM res_partner c WHERE c.id = %s AND p.id = %s""",
            (commercial_id, partner_id),
        )


def registrar(cur, partner_id, accion, antes, despues, sesion, usuario,
              entidad="contacto", objeto_id=None) -> int:
    return cur.execute(
        """INSERT INTO api.contactos_log (partner_id, accion, antes, despues, sesion, usuario, entidad, objeto_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (partner_id, accion, Jsonb(antes) if antes else None, Jsonb(despues) if despues else None,
         sesion, usuario, entidad, objeto_id),
    ).fetchone()["id"]


def respuesta(cur, partner_id, log_id) -> dict:
    return {**a_api(leer(cur, partner_id)), "log_id": log_id}


# ---------------------------------------------------------------------------
# Tarifas: acceso a datos
# ---------------------------------------------------------------------------
# En Odoo 20 la tarifa asignada al cliente es specific_property_product_pricelist,
# un jsonb por compañía ({"1": id_tarifa}) en la empresa (commercial_partner_id)
# que Odoo copia a todas sus direcciones. Si no hay tarifa asignada, Odoo usa la
# del grupo de países del cliente o la tarifa por defecto de la compañía.

CLAVE_COMPANIA = str(ODOO_COMPANY_ID)
DOMINIO_TARIFA = "pl.active AND (pl.company_id = %(cia)s OR pl.company_id IS NULL)"

APLICA_A = {"0_product_variant": "VARIANTE", "1_product": "PRODUCTO",
            "2_product_category": "CATEGORIA", "3_global": "TODOS"}
TIPO_PRECIO = {"fixed": "PRECIO_FIJO", "discount": "DESCUENTO", "markup": "RECARGO"}
BASE_PRECIO = {"list_price": "PRECIO_VENTA", "standard_price": "COSTE", "pricelist": "OTRA_TARIFA"}


def tr(columna: str) -> str:
    """Valor de un campo traducible (jsonb) en ODOO_LANG, o en inglés si no está traducido."""
    return f"coalesce({columna}->>'{ODOO_LANG}', {columna}->>'en_US')"


def hay_tarifas(cur) -> bool:
    return bool(cur.execute("SELECT to_regclass('public.product_pricelist') AS t").fetchone()["t"])


def comprobar_tarifas(cur):
    if not hay_tarifas(cur):
        raise ApiError(503, "Las tarifas no están disponibles: hay que instalar Ventas en Odoo")


def tarifas_activadas(cur) -> bool:
    """Ajustes → Ventas → Tarifas. Sin ella Odoo no aplica ninguna tarifa (como _is_feature_enabled)."""
    return cur.execute(
        """WITH RECURSIVE g(id) AS (
               SELECT gid FROM res_groups_users_rel WHERE uid = 1
               UNION SELECT r.hid FROM res_groups_implied_rel r JOIN g ON r.gid = g.id)
           SELECT EXISTS (SELECT 1 FROM g JOIN ir_model_data d ON d.res_id = g.id AND d.model = 'res.groups'
                           WHERE d.module = 'product' AND d.name = 'group_product_pricelist') AS ok"""
    ).fetchone()["ok"]


def cliente_tarifa(cur, partner_id: int, bloquear=False) -> dict:
    """El contacto, su empresa (donde vive la tarifa) y la tarifa asignada a esta."""
    row = cur.execute(
        """SELECT p.id, p.complete_name, c.id AS comercial_id, c.complete_name AS comercial_nombre,
                  c.country_id, (c.specific_property_product_pricelist->>%s)::int AS asignada_id
             FROM res_partner p JOIN res_partner c ON c.id = coalesce(p.commercial_partner_id, p.id)
            WHERE p.id = %s""" + (" FOR UPDATE OF c" if bloquear else ""),
        (CLAVE_COMPANIA, partner_id),
    ).fetchone()
    if not row:
        raise ApiError(404, f"El contacto {partner_id} no existe")
    return row


def tarifa_por_defecto(cur, country_id) -> Optional[int]:
    """La que Odoo aplica sin tarifa asignada (_get_country_pricelist_multi)."""
    p = {"cia": ODOO_COMPANY_ID, "pais": country_id}
    if country_id:
        row = cur.execute(
            f"""SELECT pl.id FROM product_pricelist pl
                  JOIN res_country_group_pricelist_rel r ON r.pricelist_id = pl.id
                  JOIN res_country_res_country_group_rel cg ON cg.res_country_group_id = r.res_country_group_id
                 WHERE {DOMINIO_TARIFA} AND cg.res_country_id = %(pais)s
                 ORDER BY pl.sequence, pl.id LIMIT 1""", p).fetchone()
        if row:
            return row["id"]
    row = cur.execute(
        f"""SELECT pl.id FROM product_pricelist pl
             WHERE {DOMINIO_TARIFA}
               AND NOT EXISTS (SELECT 1 FROM res_country_group_pricelist_rel r WHERE r.pricelist_id = pl.id)
             ORDER BY pl.sequence, pl.id LIMIT 1""", p).fetchone()
    if row:
        return row["id"]
    for clave in (f"res.partner.property_product_pricelist_{ODOO_COMPANY_ID}", "res.partner.property_product_pricelist"):
        row = cur.execute(
            """SELECT pl.id FROM ir_config_parameter icp JOIN product_pricelist pl ON pl.id::text = icp.value
                WHERE icp.key = %s""", (clave,)).fetchone()
        if row:
            return row["id"]
    row = cur.execute(f"SELECT pl.id FROM product_pricelist pl WHERE {DOMINIO_TARIFA} ORDER BY pl.sequence, pl.id LIMIT 1",
                      p).fetchone()
    return row["id"] if row else None


def tarifa_efectiva(cur, cliente: dict):
    """(id de la tarifa que se aplica, origen): origen = asignada | por_defecto | ninguna."""
    if cliente["asignada_id"]:
        activa = cur.execute("SELECT active FROM product_pricelist WHERE id = %s",
                             (cliente["asignada_id"],)).fetchone()
        if activa and activa["active"]:
            return cliente["asignada_id"], "asignada"
    defecto = tarifa_por_defecto(cur, cliente["country_id"])
    return (defecto, "por_defecto") if defecto else (None, "ninguna")


def leer_tarifa(cur, tarifa_id: int, bloquear=False) -> dict:
    row = cur.execute(
        f"""SELECT pl.id, {tr('pl.name')} AS nombre, pl.active, pl.company_id, pl.currency_id, cur.name AS moneda,
                   (SELECT count(*) FROM product_pricelist_item i WHERE i.pricelist_id = pl.id) AS num_precios,
                   (SELECT count(*) FROM res_partner c
                     WHERE c.active AND c.id = c.commercial_partner_id
                       AND c.specific_property_product_pricelist->>%s = pl.id::text) AS clientes
              FROM product_pricelist pl JOIN res_currency cur ON cur.id = pl.currency_id
             WHERE pl.id = %s""" + (" FOR UPDATE OF pl" if bloquear else ""),
        (CLAVE_COMPANIA, tarifa_id),
    ).fetchone()
    if not row:
        raise ApiError(404, f"La tarifa {tarifa_id} no existe")
    return row


def tarifa_api(cur, row) -> dict:
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "moneda": row["moneda"],
        "activa": row["active"],
        "num_precios": row["num_precios"],
        # empresas que la tienen asignada: un cambio de precios les afecta a todas
        "clientes_asignados": row["clientes"],
        "es_tarifa_por_defecto": row["id"] == tarifa_por_defecto(cur, None),
    }


def comprobar_asignable(cur, tarifa_id: int) -> dict:
    tarifa = leer_tarifa(cur, tarifa_id)
    if not tarifa["active"]:
        raise ApiError(400, f"La tarifa {tarifa_id} está archivada")
    if tarifa["company_id"] not in (None, ODOO_COMPANY_ID):
        raise ApiError(400, f"La tarifa {tarifa_id} es de otra compañía")
    return tarifa


def asignar_tarifa(cur, comercial_id: int, tarifa_id: Optional[int]):
    """Asigna la tarifa a la empresa y a todas sus direcciones (campo comercial en Odoo)."""
    cur.execute(
        """UPDATE res_partner
              SET specific_property_product_pricelist = nullif(
                      CASE WHEN %(tarifa)s::int IS NULL
                           THEN coalesce(specific_property_product_pricelist, '{}'::jsonb) - %(clave)s
                           ELSE coalesce(specific_property_product_pricelist, '{}'::jsonb)
                                || jsonb_build_object(%(clave)s, %(tarifa)s::int) END,
                      '{}'::jsonb),
                  write_date = now() AT TIME ZONE 'UTC', write_uid = %(uid)s
            WHERE id = %(id)s OR commercial_partner_id = %(id)s""",
        {"tarifa": tarifa_id, "clave": CLAVE_COMPANIA, "id": comercial_id, "uid": ODOO_UID},
    )


def respuesta_tarifa(cur, partner_id: int, **extra) -> dict:
    cliente = cliente_tarifa(cur, partner_id)
    tarifa_id, origen = tarifa_efectiva(cur, cliente)
    res = {
        "cliente_id": cliente["id"],
        "cliente": cliente["complete_name"],
        "empresa_id": cliente["comercial_id"],
        "empresa": cliente["comercial_nombre"],
        "origen": origen,
        "tarifa": tarifa_api(cur, leer_tarifa(cur, tarifa_id)) if tarifa_id else None,
        "tarifas_activadas": tarifas_activadas(cur),
    }
    if not res["tarifas_activadas"]:
        res["aviso"] = "Las tarifas están desactivadas en Odoo (Ajustes → Ventas → Tarifas): no se aplican en los pedidos"
    return res | extra


SELECT_PRECIO = f"""
SELECT i.id, i.pricelist_id, i.applied_on, i.compute_price, i.base, i.base_pricelist_id,
       i.fixed_price, i.price_discount, i.min_quantity, i.date_start, i.date_end,
       t.id AS producto_id, i.product_id AS variante_id, {tr('t.name')} AS producto,
       coalesce(pp.default_code, t.default_code) AS codigo, t.list_price, {tr('cat.name')} AS categoria
  FROM product_pricelist_item i
  LEFT JOIN product_product pp ON pp.id = i.product_id
  LEFT JOIN product_template t ON t.id = coalesce(i.product_tmpl_id, pp.product_tmpl_id)
  LEFT JOIN product_category cat ON cat.id = i.categ_id
"""


def precio_api(row) -> dict:
    return {
        "precio_id": row["id"],
        "tarifa_id": row["pricelist_id"],
        "aplica_a": APLICA_A.get(row["applied_on"], row["applied_on"]),
        "producto_id": row["producto_id"],
        "variante_id": row["variante_id"],
        "producto": row["producto"],
        "codigo": row["codigo"],
        "categoria": row["categoria"],
        "cantidad_minima": float(row["min_quantity"] or 0),
        "tipo": TIPO_PRECIO.get(row["compute_price"], row["compute_price"]),
        "precio": float(row["fixed_price"] or 0) if row["compute_price"] == "fixed" else None,
        "descuento": float(row["price_discount"] or 0) if row["compute_price"] == "discount" else None,
        "recargo": -float(row["price_discount"] or 0) if row["compute_price"] == "markup" else None,
        "sobre": BASE_PRECIO.get(row["base"], row["base"]) if row["compute_price"] != "fixed" else None,
        "precio_venta": float(row["list_price"]) if row["list_price"] is not None else None,
        "desde": row["date_start"].isoformat() if row["date_start"] else None,
        "hasta": row["date_end"].isoformat() if row["date_end"] else None,
    }


def foto_precio(cur, precio_id: int) -> Optional[dict]:
    """La fila completa de la regla: se guarda en el log y se restaura al deshacer."""
    row = cur.execute("SELECT to_jsonb(i) AS f FROM product_pricelist_item i WHERE id = %s", (precio_id,)).fetchone()
    return row["f"] if row else None


def columnas(cur, tabla: str, excluir=()) -> list:
    rows = cur.execute(
        """SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""", (tabla,)).fetchall()
    return [r["column_name"] for r in rows if r["column_name"] not in excluir]


def restaurar_precio(cur, foto_: dict):
    """Vuelve a dejar la regla como en la foto (la crea de nuevo, con el mismo id, si se quitó)."""
    if cur.execute("SELECT 1 FROM product_pricelist_item WHERE id = %s", (foto_["id"],)).fetchone():
        cols = columnas(cur, "product_pricelist_item", excluir=("id",))
        cur.execute(
            f"""UPDATE product_pricelist_item
                   SET ({', '.join(cols)}) = (SELECT {', '.join(cols)}
                                                FROM jsonb_populate_record(NULL::product_pricelist_item, %s))
                 WHERE id = %s""", (Jsonb(foto_), foto_["id"]))
    else:
        cur.execute("INSERT INTO product_pricelist_item SELECT * FROM jsonb_populate_record(NULL::product_pricelist_item, %s)",
                    (Jsonb(foto_),))
    cur.execute("UPDATE product_pricelist_item SET write_date = now() AT TIME ZONE 'UTC', write_uid = %s WHERE id = %s",
                (ODOO_UID, foto_["id"]))


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
        # Valores por defecto de Odoo para columnas obligatorias que añaden otros módulos
        defectos = {c: v for c, v in DEFECTOS_PARTNER.items() if c in columnas(cur, "res_partner")}
        cur.execute(
            f"""INSERT INTO res_partner (id, name, complete_name, type, active, company_id, color, lang,
                                         partner_share, commercial_partner_id,
                                         create_date, write_date, create_uid, write_uid
                                         {''.join(', ' + c for c in defectos)})
                VALUES (%(id)s, %(name)s, %(name)s, %(type)s, true, %(company)s, 0, 'en_US',
                        true, %(id)s, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', %(uid)s, %(uid)s
                        {''.join(f', %({c})s' for c in defectos)})""",
            {"id": partner_id, "name": estado["name"], "type": estado["type"],
             "company": ODOO_COMPANY_ID, "uid": ODOO_UID, **defectos},
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

        sesion = auditoria.sesion or entrada["sesion"]
        usuario = auditoria.usuario or entrada["usuario"]
        deshacer_entidad = {"tarifa": deshacer_tarifa, "precio": deshacer_precio}.get(entrada["entidad"],
                                                                                      deshacer_contacto)
        resultado = deshacer_entidad(cur, entrada, sesion, usuario)
        cur.execute("UPDATE api.contactos_log SET revertido = true WHERE id = %s", (log_id,))
        return {**resultado, "deshecho_log_id": log_id}


def deshacer_contacto(cur, entrada, sesion, usuario) -> dict:
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
    nuevo_log = registrar(cur, partner_id, "UNDO", actual, foto(cur, partner_id), sesion, usuario)
    return respuesta(cur, partner_id, nuevo_log)


def deshacer_tarifa(cur, entrada, sesion, usuario) -> dict:
    """ASIGNAR vuelve a la tarifa que tenía el cliente; CREAR y DUPLICAR además archivan
    la tarifa creada si ninguna empresa la tiene asignada."""
    comprobar_tarifas(cur)
    creada = entrada["despues"].get("tarifa_creada")
    cliente = None
    if entrada["partner_id"]:
        cliente = cliente_tarifa(cur, entrada["partner_id"], bloquear=True)
        if cliente["asignada_id"] != entrada["despues"]["tarifa_id"]:
            raise ApiError(409, f"La tarifa de {cliente['comercial_nombre']} ha cambiado después; no se puede deshacer")
        anterior = entrada["antes"]["tarifa_id"]
        if anterior and not cur.execute("SELECT 1 FROM product_pricelist WHERE id = %s", (anterior,)).fetchone():
            raise ApiError(409, f"La tarifa {anterior} ya no existe; no se puede volver a ella")
        asignar_tarifa(cur, cliente["comercial_id"], anterior)
    extra = {}
    if creada:
        leer_tarifa(cur, creada, bloquear=True)
        en_uso = cur.execute(
            "SELECT 1 FROM res_partner WHERE specific_property_product_pricelist->>%s = %s::text LIMIT 1",
            (CLAVE_COMPANIA, creada)).fetchone()
        if not en_uso:
            cur.execute("""UPDATE product_pricelist SET active = false, write_date = now() AT TIME ZONE 'UTC',
                                  write_uid = %s WHERE id = %s""", (ODOO_UID, creada))
        extra["tarifa_archivada"] = not en_uso
    if not cliente:
        nuevo_log = registrar(cur, None, "UNDO", entrada["despues"], None, sesion, usuario,
                              entidad="tarifa", objeto_id=creada)
        return {"tarifa": tarifa_api(cur, leer_tarifa(cur, creada)), "log_id": nuevo_log, **extra}
    nuevo_log = registrar(cur, cliente["comercial_id"], "UNDO", {"tarifa_id": cliente["asignada_id"]},
                          {"tarifa_id": entrada["antes"]["tarifa_id"]}, sesion, usuario,
                          entidad="tarifa", objeto_id=creada or entrada["antes"]["tarifa_id"])
    return respuesta_tarifa(cur, cliente["comercial_id"], log_id=nuevo_log, **extra)


def deshacer_precio(cur, entrada, sesion, usuario) -> dict:
    """ALTA quita el precio; MODIF devuelve el anterior; BAJA lo vuelve a poner."""
    comprobar_tarifas(cur)
    precio_id = entrada["objeto_id"]
    objetivo = entrada["antes"]
    tarifa_id = (objetivo or entrada["despues"])["pricelist_id"]
    if not cur.execute("SELECT 1 FROM product_pricelist WHERE id = %s FOR UPDATE", (tarifa_id,)).fetchone():
        raise ApiError(409, f"La tarifa {tarifa_id} ya no existe; no se puede deshacer")
    actual = foto_precio(cur, precio_id)
    if actual != entrada["despues"]:
        raise ApiError(409, "Ese precio ha cambiado después; no se puede deshacer")
    if objetivo:
        restaurar_precio(cur, objetivo)
    else:
        cur.execute("DELETE FROM product_pricelist_item WHERE id = %s", (precio_id,))
    nuevo_log = registrar(cur, None, "UNDO", actual, foto_precio(cur, precio_id), sesion, usuario,
                          entidad="precio", objeto_id=precio_id)
    fila = cur.execute(SELECT_PRECIO + " WHERE i.id = %s", (precio_id,)).fetchone()
    return {"precio": precio_api(fila) if fila else None, "log_id": nuevo_log,
            "tarifa": tarifa_api(cur, leer_tarifa(cur, tarifa_id))}


@app.get("/log", tags=["historial"])
def historial(sesion: Optional[str] = Query(None, max_length=60),
              limite: int = Query(50, ge=1, le=500)):
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT id AS log_id, entidad, partner_id, objeto_id, accion, antes, despues, sesion, usuario, revertido, ts
                 FROM api.contactos_log WHERE (%(s)s::text IS NULL OR sesion = %(s)s)
                ORDER BY id DESC LIMIT %(l)s""",
            {"s": sesion, "l": limite},
        ).fetchall()
    for r in rows:
        r["ts"] = r["ts"].isoformat()
    return {"total": len(rows), "cambios": rows}


# ---------------------------------------------------------------------------
# Endpoints de tarifas
# ---------------------------------------------------------------------------

@app.get("/contactos/{partner_id}/tarifa", tags=["tarifas"])
def tarifa_cliente(partner_id: int):
    with pool.connection() as conn:
        cur = conn.cursor()
        comprobar_tarifas(cur)
        return respuesta_tarifa(cur, partner_id)


@app.put("/contactos/{partner_id}/tarifa", tags=["tarifas"])
def asignar(partner_id: int, datos: AsignarTarifa):
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        comprobar_tarifas(cur)
        cliente = cliente_tarifa(cur, partner_id, bloquear=True)
        if datos.tarifa_id is not None:
            comprobar_asignable(cur, datos.tarifa_id)
        if datos.tarifa_id == cliente["asignada_id"]:
            raise ApiError(409, "El cliente ya tiene esa tarifa asignada" if datos.tarifa_id
                           else "El cliente no tiene tarifa asignada; ya usa la tarifa por defecto")
        asignar_tarifa(cur, cliente["comercial_id"], datos.tarifa_id)
        log_id = registrar(cur, cliente["comercial_id"], "ASIGNAR", {"tarifa_id": cliente["asignada_id"]},
                           {"tarifa_id": datos.tarifa_id}, datos.sesion, datos.usuario,
                           entidad="tarifa", objeto_id=datos.tarifa_id)
        return respuesta_tarifa(cur, partner_id, log_id=log_id)


@app.post("/contactos/{partner_id}/tarifa/duplicar", status_code=201, tags=["tarifas"])
def duplicar(partner_id: int, datos: Optional[DuplicarTarifa] = Body(None)):
    datos = datos or DuplicarTarifa()
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        comprobar_tarifas(cur)
        cliente = cliente_tarifa(cur, partner_id, bloquear=True)
        origen_id, _origen = tarifa_efectiva(cur, cliente)
        if not origen_id:
            raise ApiError(409, "El cliente no tiene ninguna tarifa que duplicar")
        origen = leer_tarifa(cur, origen_id)
        nombre = datos.nombre or f"{origen['nombre']} - {cliente['comercial_nombre']}"
        # Cabecera: sin grupos de países y al final de la secuencia, para que la copia
        # no pase a ser la tarifa por defecto de nadie
        nueva_id = cur.execute(
            """INSERT INTO product_pricelist (name, sequence, currency_id, company_id, active,
                                              create_uid, write_uid, create_date, write_date)
               SELECT jsonb_build_object('en_US', %(nombre)s::text) || jsonb_build_object(%(lang)s::text, %(nombre)s::text),
                      (SELECT coalesce(max(sequence), 0) + 1 FROM product_pricelist), currency_id, company_id, true,
                      %(uid)s, %(uid)s, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
                 FROM product_pricelist WHERE id = %(origen)s
               RETURNING id""",
            {"nombre": nombre, "lang": ODOO_LANG, "uid": ODOO_UID, "origen": origen_id},
        ).fetchone()["id"]
        # Reglas: las mismas que copia Odoo (las de productos archivados no)
        cols = columnas(cur, "product_pricelist_item",
                        excluir=("id", "pricelist_id", "create_uid", "create_date", "write_uid", "write_date"))
        cur.execute(
            f"""INSERT INTO product_pricelist_item (pricelist_id, create_uid, write_uid, create_date, write_date,
                                                    {', '.join(cols)})
                SELECT %(nueva)s, %(uid)s, %(uid)s, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC',
                       {', '.join('i.' + c for c in cols)}
                  FROM product_pricelist_item i
                  LEFT JOIN product_template t ON t.id = i.product_tmpl_id
                  LEFT JOIN product_product pp ON pp.id = i.product_id
                 WHERE i.pricelist_id = %(origen)s AND (t.id IS NULL OR t.active) AND (pp.id IS NULL OR pp.active)
                 ORDER BY i.id""",
            {"nueva": nueva_id, "origen": origen_id, "uid": ODOO_UID},
        )
        asignar_tarifa(cur, cliente["comercial_id"], nueva_id)
        log_id = registrar(cur, cliente["comercial_id"], "DUPLICAR", {"tarifa_id": cliente["asignada_id"]},
                           {"tarifa_id": nueva_id, "tarifa_creada": nueva_id, "copia_de": origen_id},
                           datos.sesion, datos.usuario, entidad="tarifa", objeto_id=nueva_id)
        return respuesta_tarifa(cur, partner_id, log_id=log_id,
                                copia_de={"id": origen_id, "nombre": origen["nombre"]})


@app.post("/tarifas", status_code=201, tags=["tarifas"])
def crear_tarifa(datos: NuevaTarifa):
    """Tarifa nueva sin precios (los productos van a su precio de venta), en la moneda de la compañía."""
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        comprobar_tarifas(cur)
        cliente = cliente_tarifa(cur, datos.contacto_id, bloquear=True) if datos.contacto_id else None
        dup = cur.execute(
            f"""SELECT pl.id FROM product_pricelist pl
                 WHERE {DOMINIO_TARIFA} AND lower({tr('pl.name')}) = lower(%(nombre)s) LIMIT 1""",
            {"cia": ODOO_COMPANY_ID, "nombre": datos.nombre}).fetchone()
        if dup:
            raise ApiError(409, f"Ya hay una tarifa activa llamada {datos.nombre} (id {dup['id']})")
        # Sin grupos de países y al final de la secuencia: nunca pasa a ser la tarifa por defecto
        nueva_id = cur.execute(
            """INSERT INTO product_pricelist (name, sequence, currency_id, company_id, active,
                                              create_uid, write_uid, create_date, write_date)
               SELECT jsonb_build_object('en_US', %(nombre)s::text) || jsonb_build_object(%(lang)s::text, %(nombre)s::text),
                      (SELECT coalesce(max(sequence), 0) + 1 FROM product_pricelist), c.currency_id, c.id, true,
                      %(uid)s, %(uid)s, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
                 FROM res_company c WHERE c.id = %(cia)s
               RETURNING id""",
            {"nombre": datos.nombre, "lang": ODOO_LANG, "uid": ODOO_UID, "cia": ODOO_COMPANY_ID},
        ).fetchone()["id"]
        if not cliente:
            log_id = registrar(cur, None, "CREAR", None, {"tarifa_creada": nueva_id}, datos.sesion, datos.usuario,
                               entidad="tarifa", objeto_id=nueva_id)
            return {"tarifa": tarifa_api(cur, leer_tarifa(cur, nueva_id)), "log_id": log_id}
        asignar_tarifa(cur, cliente["comercial_id"], nueva_id)
        log_id = registrar(cur, cliente["comercial_id"], "CREAR", {"tarifa_id": cliente["asignada_id"]},
                           {"tarifa_id": nueva_id, "tarifa_creada": nueva_id}, datos.sesion, datos.usuario,
                           entidad="tarifa", objeto_id=nueva_id)
        return respuesta_tarifa(cur, datos.contacto_id, log_id=log_id)


@app.get("/tarifas", tags=["tarifas"])
def buscar_tarifas(q: Optional[str] = Query(None, description="Parte del nombre; vacío = todas"),
                   incluir_archivadas: bool = Query(False)):
    with pool.connection() as conn:
        cur = conn.cursor()
        comprobar_tarifas(cur)
        rows = cur.execute(
            f"""SELECT pl.id FROM product_pricelist pl
                 WHERE (pl.active OR %(arch)s) AND (pl.company_id = %(cia)s OR pl.company_id IS NULL)
                   AND (%(q)s::text IS NULL OR {tr('pl.name')} ILIKE %(q)s)
                 ORDER BY pl.sequence, pl.id LIMIT 20""",
            {"arch": incluir_archivadas, "cia": ODOO_COMPANY_ID, "q": f"%{q.strip()}%" if q and q.strip() else None},
        ).fetchall()
        resultados = [tarifa_api(cur, leer_tarifa(cur, r["id"])) for r in rows]
    return {"total": len(resultados), "resultados": resultados}


@app.get("/tarifas/{tarifa_id}", tags=["tarifas"])
def contenido_tarifa(tarifa_id: int,
                     q: Optional[str] = Query(None, description="Filtra los precios por producto, código o categoría"),
                     limite: int = Query(100, ge=1, le=1000)):
    with pool.connection() as conn:
        cur = conn.cursor()
        comprobar_tarifas(cur)
        tarifa = tarifa_api(cur, leer_tarifa(cur, tarifa_id))
        filtro = f"%{q.strip()}%" if q and q.strip() else None
        rows = cur.execute(
            SELECT_PRECIO + f"""
             WHERE i.pricelist_id = %(id)s AND (t.id IS NULL OR t.active) AND (pp.id IS NULL OR pp.active)
               AND (%(q)s::text IS NULL OR {tr('t.name')} ILIKE %(q)s
                    OR coalesce(pp.default_code, t.default_code) ILIKE %(q)s OR {tr('cat.name')} ILIKE %(q)s)
             ORDER BY i.applied_on, producto, i.min_quantity, i.id
             LIMIT %(lim)s""",
            {"id": tarifa_id, "q": filtro, "lim": limite + 1},
        ).fetchall()
    return {**tarifa, "precios": [precio_api(r) for r in rows[:limite]], "hay_mas": len(rows) > limite}


@app.post("/tarifas/{tarifa_id}/precios", status_code=201, tags=["tarifas"])
def poner_precio(tarifa_id: int, datos: PrecioTarifa, response: Response):
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        comprobar_tarifas(cur)
        tarifa = leer_tarifa(cur, tarifa_id, bloquear=True)
        if not tarifa["active"]:
            raise ApiError(400, f"La tarifa {tarifa_id} está archivada")
        producto = cur.execute(f"SELECT id, {tr('name')} AS nombre, active, company_id FROM product_template WHERE id = %s",
                               (datos.producto_id,)).fetchone()
        if not producto:
            raise ApiError(404, f"El producto {datos.producto_id} no existe")
        if not producto["active"]:
            raise ApiError(400, f"El producto {producto['nombre']} está archivado")
        if producto["company_id"] and tarifa["company_id"] and producto["company_id"] != tarifa["company_id"]:
            raise ApiError(400, f"El producto {producto['nombre']} es de otra compañía")

        # Un precio por producto y cantidad mínima: si ya hay regla (sin fechas), se cambia
        existente = cur.execute(
            """SELECT id FROM product_pricelist_item
                WHERE pricelist_id = %s AND applied_on = '1_product' AND product_tmpl_id = %s
                  AND product_id IS NULL AND coalesce(min_quantity, 0) = %s::numeric
                  AND date_start IS NULL AND date_end IS NULL
                ORDER BY id DESC LIMIT 1 FOR UPDATE""",
            (tarifa_id, datos.producto_id, datos.cantidad_minima),
        ).fetchone()
        if existente:
            precio_id, antes = existente["id"], foto_precio(cur, existente["id"])
            if antes["compute_price"] == "fixed" and float(antes["fixed_price"] or 0) == datos.precio:
                raise ApiError(409, f"{producto['nombre']} ya tiene ese precio en la tarifa")
            cur.execute(
                """UPDATE product_pricelist_item
                      SET compute_price = 'fixed', base = 'list_price', fixed_price = %s, price_discount = 0,
                          write_date = now() AT TIME ZONE 'UTC', write_uid = %s
                    WHERE id = %s""", (datos.precio, ODOO_UID, precio_id))
            accion = "MODIF"
            response.status_code = 200
        else:
            antes, accion = None, "ALTA"
            precio_id = cur.execute(
                """INSERT INTO product_pricelist_item (
                       pricelist_id, company_id, currency_id, applied_on, product_tmpl_id, base, compute_price,
                       fixed_price, min_quantity, price_discount, price_round, price_surcharge,
                       price_min_margin, price_max_margin, create_uid, write_uid, create_date, write_date)
                   VALUES (%(tarifa)s, %(cia)s, %(moneda)s, '1_product', %(producto)s, 'list_price', 'fixed',
                           %(precio)s, %(cantidad)s, 0, 0, 0, 0, 0, %(uid)s, %(uid)s,
                           now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
                   RETURNING id""",
                {"tarifa": tarifa_id, "cia": tarifa["company_id"], "moneda": tarifa["currency_id"],
                 "producto": datos.producto_id, "precio": datos.precio, "cantidad": datos.cantidad_minima,
                 "uid": ODOO_UID},
            ).fetchone()["id"]
        log_id = registrar(cur, None, accion, antes, foto_precio(cur, precio_id), datos.sesion, datos.usuario,
                           entidad="precio", objeto_id=precio_id)
        fila = cur.execute(SELECT_PRECIO + " WHERE i.id = %s", (precio_id,)).fetchone()
        return {**precio_api(fila), "accion": accion, "log_id": log_id,
                "tarifa": tarifa_api(cur, leer_tarifa(cur, tarifa_id))}


@app.delete("/tarifas/{tarifa_id}/precios/{precio_id}", tags=["tarifas"])
def quitar_precio(tarifa_id: int, precio_id: int,
                  sesion: Optional[str] = Query(None, max_length=60),
                  usuario: Optional[str] = Query(None, max_length=60)):
    with pool.connection() as conn, conn.transaction():
        cur = conn.cursor()
        comprobar_tarifas(cur)
        leer_tarifa(cur, tarifa_id, bloquear=True)
        fila = cur.execute(SELECT_PRECIO + " WHERE i.id = %s AND i.pricelist_id = %s",
                           (precio_id, tarifa_id)).fetchone()
        if not fila:
            raise ApiError(404, f"La tarifa {tarifa_id} no tiene el precio {precio_id}")
        antes = foto_precio(cur, precio_id)
        cur.execute("DELETE FROM product_pricelist_item WHERE id = %s", (precio_id,))
        log_id = registrar(cur, None, "BAJA", antes, None, sesion, usuario, entidad="precio", objeto_id=precio_id)
        return {"quitado": precio_api(fila), "log_id": log_id, "tarifa": tarifa_api(cur, leer_tarifa(cur, tarifa_id))}


@app.get("/productos", tags=["productos"])
def buscar_productos(q: str = Query(..., min_length=1, description="Nombre, referencia interna o código de barras")):
    patron = f"%{q.strip()}%"
    with pool.connection() as conn:
        cur = conn.cursor()
        comprobar_tarifas(cur)
        rows = cur.execute(
            f"""SELECT t.id, {tr('t.name')} AS nombre, t.default_code, t.list_price, t.sale_ok, {tr('u.name')} AS unidad
                  FROM product_template t LEFT JOIN uom_uom u ON u.id = t.uom_id
                 WHERE t.active AND (t.company_id IS NULL OR t.company_id = %(cia)s)
                   AND ({tr('t.name')} ILIKE %(p)s OR t.default_code ILIKE %(p)s
                        OR EXISTS (SELECT 1 FROM product_product pp
                                    WHERE pp.product_tmpl_id = t.id AND pp.active
                                      AND (pp.default_code ILIKE %(p)s OR pp.barcode = %(q)s)))
                 ORDER BY t.sale_ok DESC, nombre, t.id
                 LIMIT %(lim)s""",
            {"cia": ODOO_COMPANY_ID, "p": patron, "q": q.strip(), "lim": MAX_RESULTADOS},
        ).fetchall()
    resultados = [{"id": r["id"], "nombre": r["nombre"], "codigo": r["default_code"],
                   "precio_venta": float(r["list_price"] or 0), "unidad": r["unidad"], "se_vende": r["sale_ok"]}
                  for r in rows]
    return {"total": len(resultados), "requiere_eleccion": len(resultados) > 1, "resultados": resultados}


# ---------------------------------------------------------------------------
# Albaranes (stock.picking) y sus líneas (stock.move): solo consulta
# ---------------------------------------------------------------------------

TIPO_ALBARAN = {"outgoing": "ENTREGA", "incoming": "RECEPCION", "internal": "INTERNO"}
ESTADO_ALBARAN = {"draft": "BORRADOR", "waiting": "ESPERANDO_OTRA_OPERACION", "confirmed": "ESPERANDO",
                  "assigned": "PREPARADO", "done": "HECHO", "cancel": "CANCELADO"}
ESTADO_LINEA = {**ESTADO_ALBARAN, "partially_available": "PARCIALMENTE_DISPONIBLE"}


class TipoAlbaran(str, Enum):
    ENTREGA = "ENTREGA"
    RECEPCION = "RECEPCION"
    INTERNO = "INTERNO"


class EstadoAlbaran(str, Enum):
    PENDIENTE = "PENDIENTE"   # ni hecho ni cancelado
    BORRADOR = "BORRADOR"
    ESPERANDO = "ESPERANDO"   # incluye ESPERANDO_OTRA_OPERACION
    PREPARADO = "PREPARADO"
    HECHO = "HECHO"
    CANCELADO = "CANCELADO"


ESTADO_A_ODOO = {
    EstadoAlbaran.PENDIENTE: ("draft", "waiting", "confirmed", "assigned"),
    EstadoAlbaran.BORRADOR: ("draft",),
    EstadoAlbaran.ESPERANDO: ("waiting", "confirmed"),
    EstadoAlbaran.PREPARADO: ("assigned",),
    EstadoAlbaran.HECHO: ("done",),
    EstadoAlbaran.CANCELADO: ("cancel",),
}


def comprobar_albaranes(cur):
    if "sale_id" not in columnas(cur, "stock_picking"):
        # stock_picking.sale_id lo añade sale_stock (Inventario + Ventas)
        raise ApiError(503, "Los albaranes no están disponibles: hay que instalar Inventario en Odoo")


def fecha_iso(valor):
    return valor.isoformat() if valor else None


def filtros_albaran(cur, contacto_id, tipo, estado, desde, hasta) -> tuple:
    """Condiciones comunes sobre stock_picking p (con rp = contacto y pt = tipo de operación)."""
    if contacto_id is not None:
        leer(cur, contacto_id)
    cond = ["p.company_id = %(cia)s"]
    params = {"cia": ODOO_COMPANY_ID, "contacto": contacto_id, "desde": desde, "hasta": hasta}
    if contacto_id is not None:
        # Una empresa incluye todas sus direcciones; una dirección, solo ella y sus contactos
        cond.append("(rp.id = %(contacto)s OR rp.parent_id = %(contacto)s OR rp.commercial_partner_id = %(contacto)s)")
    if tipo:
        cond.append("pt.code = %(tipo)s")
        params["tipo"] = {v: k for k, v in TIPO_ALBARAN.items()}[tipo.value]
    if estado:
        cond.append("p.state = ANY(%(estados)s)")
        params["estados"] = list(ESTADO_A_ODOO[estado])
    # Fecha del albarán: la de realización si está hecho, si no la prevista (UTC)
    if desde:
        cond.append("coalesce(p.date_done, p.scheduled_date) >= %(desde)s")
    if hasta:
        cond.append("coalesce(p.date_done, p.scheduled_date) < %(hasta)s::date + 1")
    return cond, params


SELECT_ALBARAN = f"""
SELECT p.id, p.name, p.state, p.origin, p.scheduled_date, p.date_done, p.date_deadline, p.note,
       pt.code AS tipo_code, {tr('pt.name')} AS tipo_operacion,
       rp.id AS contacto_id, rp.complete_name AS contacto,
       so.id AS pedido_venta_id, so.name AS pedido_venta,
       lo.complete_name AS ubicacion_origen, ld.complete_name AS ubicacion_destino,
       (SELECT count(*) FROM stock_move m WHERE m.picking_id = p.id) AS num_lineas
  FROM stock_picking p
  JOIN stock_picking_type pt ON pt.id = p.picking_type_id
  LEFT JOIN res_partner rp ON rp.id = p.partner_id
  LEFT JOIN sale_order so ON so.id = p.sale_id
  LEFT JOIN stock_location lo ON lo.id = p.location_id
  LEFT JOIN stock_location ld ON ld.id = p.location_dest_id
"""


def albaran_api(row) -> dict:
    return {
        "id": row["id"],
        "numero": row["name"],
        "tipo": TIPO_ALBARAN.get(row["tipo_code"], row["tipo_code"]),
        "tipo_operacion": row["tipo_operacion"],
        "estado": ESTADO_ALBARAN.get(row["state"], row["state"]),
        "contacto_id": row["contacto_id"],
        "contacto": row["contacto"],
        "origen": row["origin"],
        "pedido_venta_id": row["pedido_venta_id"],
        "pedido_venta": row["pedido_venta"],
        "fecha_prevista": fecha_iso(row["scheduled_date"]),
        "fecha_limite": fecha_iso(row["date_deadline"]),
        "fecha_hecho": fecha_iso(row["date_done"]),
        "ubicacion_origen": row["ubicacion_origen"],
        "ubicacion_destino": row["ubicacion_destino"],
        "num_lineas": row["num_lineas"],
    }


SELECT_LINEA = f"""
SELECT m.id, m.picking_id, m.state, m.product_uom_qty, m.quantity, m.description_picking_manual,
       t.id AS producto_id, pp.id AS variante_id, {tr('t.name')} AS producto,
       coalesce(pp.default_code, t.default_code) AS codigo, {tr('u.name')} AS unidad,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('lote', coalesce(l.name, ml.lot_name), 'cantidad', ml.quantity)
                                  ORDER BY ml.id), '[]'::jsonb)
          FROM stock_move_line ml LEFT JOIN stock_lot l ON l.id = ml.lot_id
         WHERE ml.move_id = m.id AND (ml.lot_id IS NOT NULL OR ml.lot_name IS NOT NULL)) AS lotes
  FROM stock_move m
  JOIN product_product pp ON pp.id = m.product_id
  JOIN product_template t ON t.id = pp.product_tmpl_id
  LEFT JOIN uom_uom u ON u.id = m.uom_id
"""


def linea_api(row) -> dict:
    return {
        "linea_id": row["id"],
        "producto_id": row["producto_id"],
        "variante_id": row["variante_id"],
        "producto": row["producto"],
        "codigo": row["codigo"],
        "descripcion": row["description_picking_manual"]
                       if row["description_picking_manual"] not in (None, "", row["producto"]) else None,
        "cantidad": float(row["product_uom_qty"] or 0),          # pedida
        "cantidad_hecha": float(row["quantity"] or 0),           # preparada o entregada
        "unidad": row["unidad"],
        "estado": ESTADO_LINEA.get(row["state"], row["state"]),
        "lotes": [{"lote": lt["lote"], "cantidad": float(lt["cantidad"] or 0)} for lt in row["lotes"]],
    }


@app.get("/albaranes", tags=["albaranes"])
def buscar_albaranes(
        q: Optional[str] = Query(None, description="Número de albarán, origen o pedido de venta (parcial)"),
        contacto_id: Optional[int] = Query(None, description="Cliente o proveedor; una empresa incluye sus direcciones"),
        producto_id: Optional[int] = Query(None, description="Solo albaranes con este producto (id de GET /productos)"),
        tipo: Optional[TipoAlbaran] = Query(None),
        estado: Optional[EstadoAlbaran] = Query(None),
        desde: Optional[date] = Query(None, description="Fecha (hecho o prevista) desde, AAAA-MM-DD"),
        hasta: Optional[date] = Query(None, description="Fecha (hecho o prevista) hasta, incluida"),
        limite: int = Query(20, ge=1, le=100)):
    with pool.connection() as conn:
        cur = conn.cursor()
        comprobar_albaranes(cur)
        cond, params = filtros_albaran(cur, contacto_id, tipo, estado, desde, hasta)
        if q and q.strip():
            cond.append("(p.name ILIKE %(q)s OR p.origin ILIKE %(q)s OR so.name ILIKE %(q)s)")
            params["q"] = f"%{q.strip()}%"
        if producto_id is not None:
            cond.append("""EXISTS (SELECT 1 FROM stock_move m JOIN product_product pp ON pp.id = m.product_id
                                    WHERE m.picking_id = p.id AND pp.product_tmpl_id = %(producto)s)""")
            params["producto"] = producto_id
        params["lim"] = limite + 1
        rows = cur.execute(
            SELECT_ALBARAN + " WHERE " + " AND ".join(cond)
            + " ORDER BY coalesce(p.date_done, p.scheduled_date) DESC NULLS LAST, p.id DESC LIMIT %(lim)s",
            params).fetchall()
    return {"total": min(len(rows), limite), "hay_mas": len(rows) > limite,
            "resultados": [albaran_api(r) for r in rows[:limite]]}


@app.get("/albaranes/{albaran_id}", tags=["albaranes"])
def ficha_albaran(albaran_id: int):
    with pool.connection() as conn:
        cur = conn.cursor()
        comprobar_albaranes(cur)
        row = cur.execute(SELECT_ALBARAN + " WHERE p.id = %s", (albaran_id,)).fetchone()
        if not row:
            raise ApiError(404, f"El albarán {albaran_id} no existe")
        lineas = cur.execute(SELECT_LINEA + " WHERE m.picking_id = %s ORDER BY m.sequence, m.id",
                             (albaran_id,)).fetchall()
    nota = re.sub(r"<[^>]+>", " ", row["note"] or "")
    return {**albaran_api(row), "nota": re.sub(r"\s+", " ", nota).strip() or None,
            "lineas": [linea_api(r) for r in lineas]}


@app.get("/lineas-albaran", tags=["albaranes"])
def buscar_lineas_albaran(
        producto_id: Optional[int] = Query(None, description="id de GET /productos"),
        contacto_id: Optional[int] = Query(None, description="Cliente o proveedor; una empresa incluye sus direcciones"),
        tipo: Optional[TipoAlbaran] = Query(None),
        estado: Optional[EstadoAlbaran] = Query(None),
        desde: Optional[date] = Query(None, description="Fecha del albarán (hecho o prevista) desde, AAAA-MM-DD"),
        hasta: Optional[date] = Query(None, description="Fecha del albarán hasta, incluida"),
        limite: int = Query(50, ge=1, le=500)):
    if producto_id is None and contacto_id is None:
        raise ApiError(400, "Indica producto_id o contacto_id")
    with pool.connection() as conn:
        cur = conn.cursor()
        comprobar_albaranes(cur)
        cond, params = filtros_albaran(cur, contacto_id, tipo, estado, desde, hasta)
        if producto_id is not None:
            cond.append("t.id = %(producto)s")
            params["producto"] = producto_id
        desde_sql = """
              FROM stock_move m
              JOIN stock_picking p ON p.id = m.picking_id
              JOIN stock_picking_type pt ON pt.id = p.picking_type_id
              LEFT JOIN res_partner rp ON rp.id = p.partner_id
              JOIN product_product pp ON pp.id = m.product_id
              JOIN product_template t ON t.id = pp.product_tmpl_id
              LEFT JOIN uom_uom u ON u.id = m.uom_id
             WHERE """ + " AND ".join(cond)
        # Totales de todas las líneas que cumplen el filtro (no solo de las mostradas)
        totales = cur.execute(
            f"""SELECT pt.code AS tipo_code, t.id AS producto_id, {tr('t.name')} AS producto, {tr('u.name')} AS unidad,
                       count(*) AS lineas, sum(m.product_uom_qty) AS cantidad, sum(m.quantity) AS cantidad_hecha
                {desde_sql} AND m.state <> 'cancel'
                GROUP BY pt.code, t.id, producto, unidad ORDER BY pt.code, producto, unidad""", params).fetchall()
        params["lim"] = limite + 1
        ids = cur.execute(
            f"""SELECT m.id {desde_sql}
                ORDER BY coalesce(p.date_done, p.scheduled_date) DESC NULLS LAST, p.id DESC, m.sequence, m.id
                LIMIT %(lim)s""", params).fetchall()
        lineas = []
        if ids:
            orden = [r["id"] for r in ids[:limite]]
            filas = {r["id"]: r for r in cur.execute(SELECT_LINEA + " WHERE m.id = ANY(%s)", (orden,)).fetchall()}
            albs = {r["id"]: r for r in cur.execute(
                SELECT_ALBARAN + " WHERE p.id = ANY(%s)",
                (list({filas[i]["picking_id"] for i in orden}),)).fetchall()}
            for i in orden:
                a = albs[filas[i]["picking_id"]]
                lineas.append({**linea_api(filas[i]),
                               "albaran_id": a["id"], "albaran": a["name"],
                               "tipo": TIPO_ALBARAN.get(a["tipo_code"], a["tipo_code"]),
                               "estado_albaran": ESTADO_ALBARAN.get(a["state"], a["state"]),
                               "contacto_id": a["contacto_id"], "contacto": a["contacto"],
                               "fecha": fecha_iso(a["date_done"] or a["scheduled_date"])})
    return {
        # Por tipo (entregas y recepciones no se suman) y producto; sin las líneas canceladas
        "totales": [{"tipo": TIPO_ALBARAN.get(r["tipo_code"], r["tipo_code"]), "producto_id": r["producto_id"], "producto": r["producto"], "unidad": r["unidad"],
                     "lineas": r["lineas"], "cantidad": float(r["cantidad"] or 0),
                     "cantidad_hecha": float(r["cantidad_hecha"] or 0)} for r in totales],
        "total_lineas": sum(r["lineas"] for r in totales),
        "hay_mas": len(ids) > limite,
        "lineas": lineas,
    }
