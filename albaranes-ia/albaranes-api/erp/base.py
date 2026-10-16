"""Contrato de la capa ERP.

Todo el acceso al ERP pasa por esta interfaz. En pruebas la implementa Odoo 20
(`odoo_json2.py`); en producción se sustituirá por un adaptador AS400/DB2 que
devuelva los mismos diccionarios. Nada fuera de `erp/` conoce modelos de Odoo.

Albarán normalizado (lo que devuelve `obtener_albaran`):
{
  "erp": "odoo",
  "id": 49,                       # identificador interno del albarán en el ERP
  "numero": "WH/OUT/00040",       # lo que va impreso y en el código de barras
  "estado": "done",               # estado propio del ERP (informativo)
  "hecho": true,                  # true si ya está validado / servido
  "cliente": {"id": 70, "nombre": "..."},
  "pedido": {"id": 26, "numero": "S00026"} | null,
  "fecha": "2026-10-16",
  "lineas": [{
      "id": 97,                   # identificador de la línea en el ERP
      "referencia": "E-COM07",
      "producto": "Gabinete grande",
      "cantidad_pedida": 12.0,    # columna "Pedido"
      "cantidad": 12.0,           # columna "Entregado": la que se compara con la foto
      "unidad": "Unidades"
  }],
  "facturas": [{"id": 10, "numero": "INV/2026/00010", "estado": "posted", "tipo": "out_invoice"}]
}

Cambio a rectificar: {"linea_id": 97, "cantidad_actual": 12, "cantidad_final": 10}
Plan de rectificación: {"caso": "...", "pasos": ["texto", ...], "avisos": [...]}
"""
from abc import ABC, abstractmethod


class ErpError(Exception):
    def __init__(self, mensaje, estado_http=502):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado_http = estado_http


class ErpNoEncontrado(ErpError):
    def __init__(self, mensaje):
        super().__init__(mensaje, 404)


class Erp(ABC):
    nombre = "erp"

    @abstractmethod
    def obtener_albaran(self, numero: str) -> dict:
        """Albarán normalizado por su número impreso. Lanza ErpNoEncontrado."""

    @abstractmethod
    def obtener_albaran_por_id(self, albaran_id: int) -> dict:
        """Albarán normalizado por su id interno. Lanza ErpNoEncontrado."""

    @abstractmethod
    def anadir_nota(self, albaran_id: int, html: str, adjuntos: list[tuple[str, bytes, str]] = ()) -> dict:
        """Nota interna en el historial del albarán, con adjuntos (nombre, datos, mime)."""

    @abstractmethod
    def planificar_rectificacion(self, albaran: dict, cambios: list[dict]) -> dict:
        """Qué haría para dejar las cantidades finales, sin escribir nada."""

    @abstractmethod
    def aplicar_rectificacion(self, albaran: dict, cambios: list[dict]) -> dict:
        """Aplica el plan. Devuelve {"pasos": [...], "documentos": {...}, "avisos": [...]}."""
