"""Incidencias en una base de datos Postgres propia (no la del ERP)."""
import json

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

ESQUEMA = """
CREATE TABLE IF NOT EXISTS incidencia (
    id              serial PRIMARY KEY,
    sha256          text NOT NULL UNIQUE,      -- idempotencia: misma foto = misma incidencia
    creada          timestamptz NOT NULL DEFAULT now(),
    actualizada     timestamptz NOT NULL DEFAULT now(),
    estado          text NOT NULL DEFAULT 'recibida',
    nombre_fichero  text,
    foto            bytea NOT NULL,            -- normalizada (orientación EXIF aplicada, JPEG)
    foto_ancho      int,
    foto_alto       int,
    foto_original   bytea,
    foto_original_mime text,
    albaran_numero  text,
    albaran_id      int,
    origen_numero   text,                      -- codigo_barras | vision
    lectura_codigo  jsonb,
    erp             jsonb,                     -- foto del albarán en el ERP al leerlo
    lectura         jsonb,                     -- respuesta del modelo
    decision        jsonb,                     -- reglas aplicadas por n8n
    resolucion      jsonb,                     -- decisión humana
    rectificacion   jsonb,                     -- plan o resultado en el ERP
    error           text,
    eventos         jsonb NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS incidencia_estado_idx ON incidencia (estado, creada DESC);
CREATE INDEX IF NOT EXISTS incidencia_albaran_idx ON incidencia (albaran_numero);
"""

ESTADOS = {"recibida", "procesando", "verificado", "pendiente_revision", "error",
           "aprobada", "corregida", "rechazada", "rectificada"}
JSONB = {"lectura_codigo", "erp", "lectura", "decision", "resolucion", "rectificacion"}
EDITABLES = JSONB | {"estado", "albaran_numero", "albaran_id", "origen_numero", "error"}
SIN_FOTOS = ("id, sha256, creada, actualizada, estado, nombre_fichero, foto_ancho, foto_alto, "
             "albaran_numero, albaran_id, origen_numero, lectura_codigo, erp, lectura, decision, "
             "resolucion, rectificacion, error, eventos")


class Store:
    def __init__(self, dsn):
        self.pool = ConnectionPool(dsn, min_size=1, max_size=5, kwargs={"row_factory": dict_row},
                                   open=True)
        with self.pool.connection() as c:
            c.execute(ESQUEMA)

    def crear(self, sha, nombre, foto, ancho, alto, original, mime, reprocesar=False):
        """Devuelve (fila, nueva). Si la foto ya existe no crea otra; con reprocesar la reinicia."""
        with self.pool.connection() as c:
            fila = c.execute(
                f"""INSERT INTO incidencia (sha256, nombre_fichero, foto, foto_ancho, foto_alto,
                        foto_original, foto_original_mime, eventos)
                    VALUES (%s,%s,%s,%s,%s,%s,%s, jsonb_build_array(jsonb_build_object(
                        'fecha', now(), 'evento', 'recibida')))
                    ON CONFLICT (sha256) DO NOTHING RETURNING {SIN_FOTOS}""",
                (sha, nombre, foto, ancho, alto, original, mime)).fetchone()
            if fila:
                return fila, True
            fila = c.execute(f"SELECT {SIN_FOTOS} FROM incidencia WHERE sha256=%s", (sha,)).fetchone()
            if reprocesar and fila["estado"] not in ("aprobada", "corregida", "rectificada"):
                fila = c.execute(
                    f"""UPDATE incidencia SET estado='recibida', albaran_numero=NULL, albaran_id=NULL,
                            origen_numero=NULL, lectura_codigo=NULL, erp=NULL, lectura=NULL,
                            decision=NULL, resolucion=NULL, rectificacion=NULL, error=NULL,
                            actualizada=now(),
                            eventos = eventos || jsonb_build_array(jsonb_build_object(
                                'fecha', now(), 'evento', 'reprocesar'))
                        WHERE id=%s RETURNING {SIN_FOTOS}""", (fila["id"],)).fetchone()
                return fila, True
            return fila, False

    def obtener(self, id_, con_foto=False):
        cols = SIN_FOTOS + (", foto" if con_foto else "")
        with self.pool.connection() as c:
            return c.execute(f"SELECT {cols} FROM incidencia WHERE id=%s", (id_,)).fetchone()

    def foto(self, id_, original=False):
        col = "coalesce(foto_original, foto) AS datos, coalesce(foto_original_mime, 'image/jpeg') AS mime" \
            if original else "foto AS datos, 'image/jpeg' AS mime"
        with self.pool.connection() as c:
            return c.execute(f"SELECT {col}, nombre_fichero FROM incidencia WHERE id=%s", (id_,)).fetchone()

    def listar(self, estado=None, limite=50):
        sql = f"SELECT {SIN_FOTOS} FROM incidencia"
        args = []
        if estado:
            sql += " WHERE estado = ANY(%s)"
            args.append(estado.split(","))
        sql += " ORDER BY creada DESC LIMIT %s"
        args.append(limite)
        with self.pool.connection() as c:
            return c.execute(sql, args).fetchall()

    def actualizar(self, id_, cambios: dict, evento: str | None = None, estado_esperado=None):
        cambios = {k: v for k, v in cambios.items() if k in EDITABLES}
        sets, args = [], []
        for k, v in cambios.items():
            sets.append(f"{k}=%s")
            args.append(Jsonb(v) if k in JSONB and v is not None else v)
        ev = {"evento": evento or "actualizada", **({"estado": cambios["estado"]} if "estado" in cambios else {})}
        sets.append("eventos = eventos || jsonb_build_array(%s::jsonb || jsonb_build_object('fecha', now()))")
        args.append(json.dumps(ev))
        sets.append("actualizada=now()")
        sql = f"UPDATE incidencia SET {', '.join(sets)} WHERE id=%s"
        args.append(id_)
        if estado_esperado:
            sql += " AND estado = ANY(%s)"
            args.append(list(estado_esperado))
        with self.pool.connection() as c:
            return c.execute(sql + f" RETURNING {SIN_FOTOS}", args).fetchone()
