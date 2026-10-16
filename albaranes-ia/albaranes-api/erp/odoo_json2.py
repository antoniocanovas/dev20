"""Adaptador Odoo 20 por la API externa JSON-2 (POST /json/2/<modelo>/<método>).

Autenticación con API key de un usuario de integración (Authorization: bearer).
Solo se llaman métodos públicos y estándar; no hace falta ningún módulo propio.

Rectificación (ver README, apartado E):
- Albarán sin validar: se ponen las cantidades hechas finales y se valida sin
  pedido pendiente (sin backorder).
- Albarán validado:
  * menos cantidad -> devolución estándar (`action_return`) solo de la diferencia,
    que Odoo descuenta de lo entregado en el pedido de venta;
  * más cantidad -> se sube la cantidad de la línea del pedido, Odoo genera un
    albarán con la diferencia y se valida;
  * si el pedido ya tenía factura publicada, el asistente estándar "Crear factura"
    (método "según lo entregado") genera en borrador la factura rectificativa
    (abono) o la factura complementaria. Se deja en borrador para que
    Administración la revise y la publique.
"""
import base64

import httpx

from .base import Erp, ErpError, ErpNoEncontrado


class OdooJson2(Erp):
    nombre = "odoo"

    def __init__(self, url, db, api_key, lang="es_ES", timeout=30):
        if not (url and api_key):
            raise RuntimeError("Faltan ODOO_URL u ODOO_API_KEY")
        self.lang = lang
        headers = {"Authorization": f"bearer {api_key}", "Content-Type": "application/json"}
        if db:
            headers["X-Odoo-Database"] = db
        self.http = httpx.Client(base_url=url.rstrip("/") + "/json/2", headers=headers, timeout=timeout)

    # -- llamada genérica --------------------------------------------------
    def _call(self, modelo, metodo, ids=None, context=None, **kw):
        body = dict(kw)
        if ids is not None:
            body["ids"] = list(ids)
        body["context"] = {"lang": self.lang, **(context or {})}
        try:
            r = self.http.post(f"/{modelo}/{metodo}", json=body)
        except httpx.HTTPError as e:
            raise ErpError(f"Odoo no responde: {e}")
        if r.status_code >= 400:
            try:
                msg = r.json().get("message") or r.text
            except ValueError:
                msg = r.text
            raise ErpError(f"Odoo {modelo}.{metodo}: {msg[:500]}", 502 if r.status_code >= 500 else 400)
        return r.json()

    def _sr(self, modelo, domain, fields, **kw):
        return self._call(modelo, "search_read", domain=domain, fields=fields, **kw)

    def _read(self, modelo, ids, fields):
        return self._call(modelo, "read", ids=ids, fields=fields) if ids else []

    # -- lectura -----------------------------------------------------------
    CAMPOS_PICKING = ["name", "state", "partner_id", "origin", "sale_id", "scheduled_date",
                      "date_done", "picking_type_code", "return_ids"]

    def obtener_albaran(self, numero):
        numero = (numero or "").strip()
        picks = self._sr("stock.picking", [["name", "=", numero]], self.CAMPOS_PICKING, limit=2)
        if not picks and numero.isdigit():
            # Solo los dígitos (p. ej. "00040"): se acepta si identifica un único albarán de salida
            picks = self._sr("stock.picking", [["name", "=like", f"%/{numero}"],
                                               ["picking_type_code", "=", "outgoing"]],
                             self.CAMPOS_PICKING, limit=2)
            if len(picks) > 1:
                raise ErpNoEncontrado(f"El número {numero} coincide con varios albaranes")
        if not picks:
            raise ErpNoEncontrado(f"No existe el albarán {numero}")
        return self._normalizar(picks[0])

    def obtener_albaran_por_id(self, albaran_id):
        picks = self._read("stock.picking", [albaran_id], self.CAMPOS_PICKING)
        if not picks:
            raise ErpNoEncontrado(f"No existe el albarán {albaran_id}")
        return self._normalizar(picks[0])

    def _normalizar(self, p):
        moves = self._sr("stock.move", [["picking_id", "=", p["id"]], ["state", "!=", "cancel"]],
                         ["product_id", "product_uom_qty", "quantity", "uom_id", "state", "sale_line_id"],
                         order="sequence, id")
        prods = {x["id"]: x for x in self._read("product.product",
                                                 sorted({m["product_id"][0] for m in moves}),
                                                 ["default_code", "name", "invoice_policy"])}
        pedido, facturas = None, []
        if p.get("sale_id"):
            so = self._read("sale.order", [p["sale_id"][0]], ["name", "invoice_ids", "invoice_status"])[0]
            pedido = {"id": so["id"], "numero": so["name"], "estado_facturacion": so["invoice_status"]}
            facturas = [{"id": f["id"], "numero": f["name"], "estado": f["state"], "tipo": f["move_type"],
                         "pago": f["payment_state"]}
                        for f in self._read("account.move", so["invoice_ids"],
                                            ["name", "state", "move_type", "payment_state"])]
        fecha = p["date_done"] or p["scheduled_date"]
        return {
            "erp": self.nombre,
            "id": p["id"],
            "numero": p["name"],
            "estado": p["state"],
            "hecho": p["state"] == "done",
            "tipo": p["picking_type_code"],
            "cliente": {"id": p["partner_id"][0], "nombre": p["partner_id"][1]} if p["partner_id"] else None,
            "pedido": pedido,
            "origen": p["origin"] or None,
            "fecha": fecha[:10] if fecha else None,
            "devoluciones": p.get("return_ids") or [],
            "lineas": [{
                "id": m["id"],
                "referencia": prods[m["product_id"][0]]["default_code"] or None,
                "producto": prods[m["product_id"][0]]["name"],
                "cantidad_pedida": m["product_uom_qty"],
                "cantidad": m["quantity"],
                "unidad": m["uom_id"][1] if m["uom_id"] else None,
                "politica_facturacion": prods[m["product_id"][0]]["invoice_policy"],
                "linea_venta_id": m["sale_line_id"][0] if m["sale_line_id"] else None,
            } for m in moves],
            "facturas": facturas,
        }

    # -- historial ---------------------------------------------------------
    def anadir_nota(self, albaran_id, html, adjuntos=()):
        att_ids = []
        for nombre, datos, mime in adjuntos:
            att_ids.append(self._call("ir.attachment", "create", vals_list=[{
                # Odoo 20 ignora "datas": el contenido va en "raw" (en base64 por JSON)
                "name": nombre, "raw": base64.b64encode(datos).decode(), "mimetype": mime,
                "res_model": "stock.picking", "res_id": albaran_id}])[0])
        msg = self._call("stock.picking", "message_post", ids=[albaran_id], body=html,
                         body_is_html=True, message_type="comment",
                         subtype_xmlid="mail.mt_note", attachment_ids=att_ids)
        return {"mensaje_id": msg[0] if isinstance(msg, list) else msg, "adjuntos": att_ids}

    # -- rectificación -----------------------------------------------------
    def _clasificar(self, albaran, cambios):
        lineas = {l["id"]: l for l in albaran["lineas"]}
        menos, mas = [], []
        for c in cambios:
            l = lineas.get(c["linea_id"])
            if not l:
                raise ErpError(f"La línea {c['linea_id']} no es del albarán {albaran['numero']}", 409)
            dif = round(c["cantidad_final"] - l["cantidad"], 4)
            if dif < 0:
                menos.append((l, -dif))
            elif dif > 0:
                mas.append((l, dif))
        return lineas, menos, mas

    def _facturas_publicadas(self, albaran):
        return [f for f in albaran["facturas"] if f["estado"] == "posted" and f["tipo"] == "out_invoice"]

    def planificar_rectificacion(self, albaran, cambios):
        lineas, menos, mas = self._clasificar(albaran, cambios)
        nombre = lambda l: f"[{l['referencia']}] {l['producto']}" if l["referencia"] else l["producto"]
        pasos, avisos = [], []
        if not (menos or mas):
            return {"caso": "sin_cambios", "pasos": [], "avisos": ["Las cantidades ya coinciden con el ERP"]}
        if not albaran["hecho"]:
            finales = {c["linea_id"]: c["cantidad_final"] for c in cambios}
            for l in albaran["lineas"]:
                q = finales.get(l["id"], l["cantidad"])
                pasos.append(f"Cantidad hecha de {nombre(l)}: {l['cantidad']:g} → {q:g}")
            pasos.append(f"Validar {albaran['numero']} sin crear pedido pendiente (backorder)")
            return {"caso": "albaran_sin_validar", "pasos": pasos, "avisos": avisos}
        if menos:
            pasos.append(f"Crear devolución de {albaran['numero']} con: " + ", ".join(
                f"{nombre(l)} {d:g} {l['unidad'] or ''}".strip() for l, d in menos))
            pasos.append("Validar la devolución (vuelve al stock y descuenta lo entregado en el pedido)")
            for l, d in menos:
                if l["politica_facturacion"] == "order":
                    pasos.append(f"Bajar {d:g} la cantidad pedida de {nombre(l)} en el pedido "
                                 "(se factura por pedido, no por entrega)")
        if mas:
            if not albaran["pedido"]:
                raise ErpError("Hay más cantidad que la del albarán y no tiene pedido de venta: "
                               "no se puede rectificar automáticamente", 409)
            for l, d in mas:
                if not l["linea_venta_id"]:
                    raise ErpError(f"La línea {nombre(l)} no tiene línea de pedido", 409)
                pasos.append(f"Subir {d:g} la cantidad de {nombre(l)} en {albaran['pedido']['numero']}")
            pasos.append("Validar el albarán nuevo que genera Odoo con esa diferencia")
        publicadas = self._facturas_publicadas(albaran)
        if publicadas:
            pasos.append("Crear en borrador, desde el pedido, " + (
                "la factura rectificativa (abono)" if menos and not mas else
                "la factura complementaria" if mas and not menos else
                "las facturas de ajuste") + " por la diferencia (asistente estándar «Crear factura», "
                "según lo entregado), para revisarla y publicarla en Administración")
            avisos.append("Factura ya publicada: " + ", ".join(f["numero"] for f in publicadas))
        elif albaran["facturas"]:
            avisos.append("El pedido tiene factura en borrador: revísala, Odoo no la recalcula sola")
        else:
            avisos.append("Sin factura todavía: cuando se facture saldrá con las cantidades corregidas")
        return {"caso": "albaran_validado", "pasos": pasos, "avisos": avisos}

    def _validar(self, picking_id):
        res = self._call("stock.picking", "button_validate", ids=[picking_id],
                         context={"skip_backorder": True, "picking_ids_not_to_backorder": [picking_id]})
        if isinstance(res, dict) and res.get("res_model"):
            raise ErpError(f"Odoo pide confirmación al validar ({res['res_model']}); revisa el albarán", 409)

    def aplicar_rectificacion(self, albaran, cambios):
        plan = self.planificar_rectificacion(albaran, cambios)
        hechos, docs = [], {}
        if plan["caso"] == "sin_cambios":
            return {**plan, "hechos": hechos, "documentos": docs}
        lineas, menos, mas = self._clasificar(albaran, cambios)

        if not albaran["hecho"]:
            finales = {c["linea_id"]: c["cantidad_final"] for c in cambios}
            for l in albaran["lineas"]:
                self._call("stock.move", "write", ids=[l["id"]],
                           vals={"quantity": finales.get(l["id"], l["cantidad"]), "picked": True})
            self._validar(albaran["id"])
            hechos.append(f"Validado {albaran['numero']} con las cantidades finales")
            return {**plan, "hechos": hechos, "documentos": docs}

        facturas_antes = {f["id"] for f in albaran["facturas"]}
        if menos:
            act = self._call("stock.picking", "action_return", ids=[albaran["id"]])
            dev_id = act["res_id"]
            dif = {l["id"]: d for l, d in menos}
            for m in self._sr("stock.move", [["picking_id", "=", dev_id]], ["origin_returned_move_id"]):
                orig = m["origin_returned_move_id"] and m["origin_returned_move_id"][0]
                if orig in dif:
                    self._call("stock.move", "write", ids=[m["id"]], vals={"product_uom_qty": dif[orig]})
                else:
                    self._call("stock.move", "unlink", ids=[m["id"]])
            self._call("stock.picking", "action_confirm", ids=[dev_id])
            self._call("stock.picking", "action_assign", ids=[dev_id])
            for m in self._sr("stock.move", [["picking_id", "=", dev_id]], ["product_uom_qty"]):
                self._call("stock.move", "write", ids=[m["id"]],
                           vals={"quantity": m["product_uom_qty"], "picked": True})
            self._validar(dev_id)
            dev = self._read("stock.picking", [dev_id], ["name"])[0]
            docs["devolucion"] = {"id": dev_id, "numero": dev["name"]}
            hechos.append(f"Devolución {dev['name']} validada")
            for l, d in menos:
                if l["politica_facturacion"] == "order" and l["linea_venta_id"]:
                    sol = self._read("sale.order.line", [l["linea_venta_id"]], ["product_uom_qty"])[0]
                    self._call("sale.order.line", "write", ids=[sol["id"]],
                               vals={"product_uom_qty": max(0, sol["product_uom_qty"] - d)})
                    hechos.append(f"Pedido: {l['producto']} baja {d:g}")

        if mas:
            nuevos = []
            for l, d in mas:
                sol = self._read("sale.order.line", [l["linea_venta_id"]], ["product_uom_qty"])[0]
                self._call("sale.order.line", "write", ids=[sol["id"]],
                           vals={"product_uom_qty": sol["product_uom_qty"] + d})
                hechos.append(f"Pedido: {l['producto']} sube {d:g}")
                for m in self._sr("stock.move", [["sale_line_id", "=", sol["id"]],
                                                 ["state", "not in", ["done", "cancel"]],
                                                 ["picking_code", "=", "outgoing"]],
                                  ["picking_id", "product_uom_qty"]):
                    self._call("stock.move", "write", ids=[m["id"]],
                               vals={"quantity": m["product_uom_qty"], "picked": True})
                    if m["picking_id"] and m["picking_id"][0] not in nuevos:
                        nuevos.append(m["picking_id"][0])
            for pid in nuevos:
                self._validar(pid)
            docs["albaranes_complementarios"] = [
                {"id": x["id"], "numero": x["name"]} for x in self._read("stock.picking", nuevos, ["name"])]
            hechos.append("Validados: " + ", ".join(x["numero"] for x in docs["albaranes_complementarios"]))

        if self._facturas_publicadas(albaran):
            so_id = albaran["pedido"]["id"]
            wiz = self._call("sale.advance.payment.inv", "create",
                             vals_list=[{"advance_payment_method": "delivered",
                                         "sale_order_ids": [[6, 0, [so_id]]]}],
                             context={"active_model": "sale.order", "active_ids": [so_id], "active_id": so_id})
            self._call("sale.advance.payment.inv", "create_invoices", ids=wiz,
                       context={"active_model": "sale.order", "active_ids": [so_id], "active_id": so_id})
            so = self._read("sale.order", [so_id], ["invoice_ids"])[0]
            nuevas = [i for i in so["invoice_ids"] if i not in facturas_antes]
            docs["facturas_borrador"] = [
                {"id": f["id"], "numero": f["name"] or "(borrador)", "tipo": f["move_type"],
                 "importe": f["amount_total"]}
                for f in self._read("account.move", nuevas, ["name", "move_type", "amount_total"])]
            hechos.append("Facturas en borrador: " + (", ".join(
                f"{'abono' if f['tipo'] == 'out_refund' else 'factura'} {f['importe']:g}"
                for f in docs["facturas_borrador"]) or "ninguna (nada que facturar)"))
        return {**plan, "hechos": hechos, "documentos": docs}
