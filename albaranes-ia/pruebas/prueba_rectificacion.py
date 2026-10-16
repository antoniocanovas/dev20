"""Prueba la rectificación REAL (DRY_RUN=false) del adaptador ERP, sin pasar por n8n.

Usa los albaranes desechables que crea `RECTIFICACION=1 odoo shell < scripts/datos_prueba.py`
(WH/OUT/00042 validado y facturado, WH/OUT/00043 sin validar). Se ejecuta dentro del
contenedor de albaranes-api, que ya tiene la configuración del ERP:

  docker exec -i <albaranes-api> python - < pruebas/prueba_rectificacion.py
"""
import json
import os
import sys

sys.path.insert(0, "/app")
for linea in open(os.getenv("ENV_FILE", "/run/config/albaranes-ia.env")):
    k, _, v = linea.strip().partition("=")
    if k and not k.startswith("#"):
        os.environ.setdefault(k, v)
from erp import crear_erp  # noqa: E402

erp = crear_erp()


def prueba(numero, finales):
    alb = erp.obtener_albaran(numero)
    if alb.get("devoluciones"):
        print(f"{numero}: ya tiene devoluciones, se omite (recrea los datos de prueba)")
        return
    por_ref = {l["referencia"]: l for l in alb["lineas"]}
    cambios = [{"linea_id": por_ref[r]["id"], "cantidad_actual": por_ref[r]["cantidad"], "cantidad_final": q}
               for r, q in finales.items()]
    print(f"\n== {numero} ({'validado' if alb['hecho'] else 'sin validar'})")
    res = erp.aplicar_rectificacion(alb, cambios)
    for h in res["hechos"]:
        print("  hecho:", h)
    print("  documentos:", json.dumps(res["documentos"], ensure_ascii=False))
    despues = erp.obtener_albaran_por_id(alb["id"])
    print("  estado después:", despues["estado"], [(l["referencia"], l["cantidad"]) for l in despues["lineas"]])
    if despues["pedido"]:
        print("  facturas:", [(f["numero"], f["tipo"], f["estado"]) for f in despues["facturas"]])


prueba("WH/OUT/00042", {"E-COM07": 10, "FURN_7777": 7, "FURN_0002": 2})
prueba("WH/OUT/00043", {"E-COM07": 11})
