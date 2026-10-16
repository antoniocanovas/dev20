"""Capa ERP. `crear_erp()` elige el adaptador con ERP_BACKEND (hoy solo "odoo")."""
import os

from .base import Erp, ErpError, ErpNoEncontrado  # noqa: F401


def crear_erp() -> Erp:
    backend = os.getenv("ERP_BACKEND", "odoo")
    if backend == "odoo":
        from .odoo_json2 import OdooJson2
        return OdooJson2(os.getenv("ODOO_URL"), os.getenv("ODOO_DB"), os.getenv("ODOO_API_KEY"),
                         lang=os.getenv("ODOO_LANG", "es_ES"))
    # Aquí irá el adaptador AS400/DB2 (p. ej. "db2"), con la misma interfaz Erp.
    raise RuntimeError(f"ERP_BACKEND desconocido: {backend}")
