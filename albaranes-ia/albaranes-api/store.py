"""Incidencias en una base de datos Postgres propia (no la del ERP).

Un albarán puede tener varias fotos (páginas): van en `incidencia_pagina`. Las columnas
foto* de `incidencia` son de antes de las páginas; al arrancar se copian a la página 1 y
ya no se escriben.

`tipo` es la operación: propio (nuestro albarán impreso), entrada (albarán de un proveedor
en la recepción) o entrega (albarán que hace el cliente al recibir). En los de terceros,
`referencias` guarda los albaranes nuestros que ha escrito el usuario (si no, se usan los que
lee la IA)."""
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
    foto            bytea,                     -- antiguo: ahora en incidencia_pagina
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
ALTER TABLE incidencia ALTER COLUMN foto DROP NOT NULL;
ALTER TABLE incidencia ADD COLUMN IF NOT EXISTS tipo text NOT NULL DEFAULT 'propio';
ALTER TABLE incidencia ADD COLUMN IF NOT EXISTS referencias text;
CREATE TABLE IF NOT EXISTS incidencia_pagina (
    incidencia_id   int NOT NULL REFERENCES incidencia (id) ON DELETE CASCADE,
    pagina          int NOT NULL,              -- 1, 2… en el orden en que se subieron
    sha256          text NOT NULL,
    nombre_fichero  text,
    foto            bytea NOT NULL,            -- normalizada (orientación EXIF aplicada, JPEG)
    foto_ancho      int,
    foto_alto       int,
    foto_original   bytea,
    foto_original_mime text,
    PRIMARY KEY (incidencia_id, pagina)
);
INSERT INTO incidencia_pagina (incidencia_id, pagina, sha256, nombre_fichero, foto, foto_ancho, foto_alto,
                               foto_original, foto_original_mime)
SELECT id, 1, sha256, nombre_fichero, foto, foto_ancho, foto_alto, foto_original, foto_original_mime
FROM incidencia i WHERE foto IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM incidencia_pagina p WHERE p.incidencia_id = i.id);
"""

TIPOS = {"propio", "entrada", "entrega"}
ESTADOS = {"recibida", "procesando", "verificado", "pendiente_revision", "error",
           "aprobada", "corregida", "rechazada", "rectificada"}
JSONB = {"lectura_codigo", "erp", "lectura", "decision", "resolucion", "rectificacion"}
EDITABLES = JSONB | {"estado", "albaran_numero", "albaran_id", "origen_numero", "error", "tipo", "referencias"}
SIN_FOTOS = ("id, sha256, creada, actualizada, estado, tipo, referencias, nombre_fichero, "
             "albaran_numero, albaran_id, origen_numero, lectura_codigo, erp, lectura, decision, "
             "resolucion, rectificacion, error, eventos")
# Páginas sin las fotos: [{pagina, nombre_fichero, ancho, alto}]
PAGINAS = ("(SELECT coalesce(jsonb_agg(jsonb_build_object('pagina', p.pagina, 'nombre_fichero', p.nombre_fichero, "
           "'ancho', p.foto_ancho, 'alto', p.foto_alto) ORDER BY p.pagina), '[]') "
           "FROM incidencia_pagina p WHERE p.incidencia_id = incidencia.id) AS paginas")


class Store:
    def __init__(self, dsn):
        self.pool = ConnectionPool(dsn, min_size=1, max_size=5, kwargs={"row_factory": dict_row},
                                   open=True)
        with self.pool.connection() as c:
            c.execute(ESQUEMA)

    def crear(self, sha, nombre, paginas, reprocesar=False, tipo="propio", referencias=None):
        """Devuelve (fila, nueva). Si las fotos ya existen no crea otra; con reprocesar, o si
        llegan con otro tipo de operación, la reinicia (salvo que ya esté resuelta).
        paginas: [{sha256, nombre_fichero, foto, ancho, alto, original, mime}] en orden."""
        with self.pool.connection() as c:
            fila = c.execute(
                f"""INSERT INTO incidencia (sha256, nombre_fichero, tipo, referencias, eventos)
                    VALUES (%s,%s,%s,%s, jsonb_build_array(jsonb_build_object(
                        'fecha', now(), 'evento', 'recibida', 'paginas', %s::int, 'tipo', %s::text)))
                    ON CONFLICT (sha256) DO NOTHING RETURNING {SIN_FOTOS}""",
                (sha, nombre, tipo, referencias, len(paginas), tipo)).fetchone()
            if fila:
                for n, p in enumerate(paginas, 1):
                    c.execute("""INSERT INTO incidencia_pagina (incidencia_id, pagina, sha256, nombre_fichero, foto,
                                     foto_ancho, foto_alto, foto_original, foto_original_mime)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                              (fila["id"], n, p["sha256"], p["nombre_fichero"], p["foto"], p["ancho"], p["alto"],
                               p["original"], p["mime"]))
                return fila, True
            fila = c.execute(f"SELECT {SIN_FOTOS} FROM incidencia WHERE sha256=%s", (sha,)).fetchone()
            if (reprocesar or tipo != fila["tipo"]) and fila["estado"] not in ("aprobada", "corregida", "rectificada"):
                fila = c.execute(
                    f"""UPDATE incidencia SET estado='recibida', albaran_numero=NULL, albaran_id=NULL,
                            origen_numero=NULL, lectura_codigo=NULL, erp=NULL, lectura=NULL,
                            decision=NULL, resolucion=NULL, rectificacion=NULL, error=NULL,
                            tipo=%s, referencias=coalesce(%s, referencias), actualizada=now(),
                            eventos = eventos || jsonb_build_array(jsonb_build_object(
                                'fecha', now(), 'evento', 'reprocesar', 'tipo', %s::text))
                        WHERE id=%s RETURNING {SIN_FOTOS}""", (tipo, referencias, tipo, fila["id"])).fetchone()
                return fila, True
            return fila, False

    def obtener(self, id_, con_fotos=False):
        """Con con_fotos, cada página lleva además `foto` (bytes normalizados)."""
        with self.pool.connection() as c:
            fila = c.execute(f"SELECT {SIN_FOTOS}, {PAGINAS} FROM incidencia WHERE id=%s", (id_,)).fetchone()
            if fila and con_fotos:
                fotos = {p["pagina"]: p["foto"] for p in c.execute(
                    "SELECT pagina, foto FROM incidencia_pagina WHERE incidencia_id=%s", (id_,))}
                for p in fila["paginas"]:
                    p["foto"] = bytes(fotos[p["pagina"]])
            return fila

    def foto(self, id_, original=False, pagina=1):
        col = "coalesce(foto_original, foto) AS datos, coalesce(foto_original_mime, 'image/jpeg') AS mime" \
            if original else "foto AS datos, 'image/jpeg' AS mime"
        with self.pool.connection() as c:
            return c.execute(f"SELECT {col}, nombre_fichero, pagina FROM incidencia_pagina "
                             "WHERE incidencia_id=%s AND pagina=%s", (id_, pagina)).fetchone()

    def fotos(self, id_, original=False):
        """Todas las páginas en orden (lista vacía si no existe)."""
        col = "coalesce(foto_original, foto) AS datos, coalesce(foto_original_mime, 'image/jpeg') AS mime" \
            if original else "foto AS datos, 'image/jpeg' AS mime"
        with self.pool.connection() as c:
            return c.execute(f"SELECT {col}, nombre_fichero, pagina FROM incidencia_pagina "
                             "WHERE incidencia_id=%s ORDER BY pagina", (id_,)).fetchall()

    def eliminar(self, id_, estado_esperado):
        with self.pool.connection() as c:
            return c.execute("DELETE FROM incidencia WHERE id=%s AND estado = ANY(%s) RETURNING id",
                             (id_, list(estado_esperado))).fetchone()

    def listar(self, estado=None, limite=50, albaran=None, excluir=None, desde=None, hasta=None, tipo=None):
        sql = f"SELECT {SIN_FOTOS}, {PAGINAS} FROM incidencia WHERE true"
        args = []
        if tipo:
            sql += " AND tipo = ANY(%s)"
            args.append(tipo.split(","))
        if estado:
            sql += " AND estado = ANY(%s)"
            args.append(estado.split(","))
        if albaran:
            sql += " AND albaran_numero = %s"
            args.append(albaran)
        if excluir:
            sql += " AND id <> %s"
            args.append(excluir)
        # Fechas de recepción en hora de Madrid; `hasta` incluye el día entero.
        if desde:
            sql += " AND creada >= (%s::date)::timestamp AT TIME ZONE 'Europe/Madrid'"
            args.append(desde)
        if hasta:
            sql += " AND creada < (%s::date + 1)::timestamp AT TIME ZONE 'Europe/Madrid'"
            args.append(hasta)
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
