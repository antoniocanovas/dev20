# Propuesta: impresión y correo en mercas_touch

Estado: **pendiente de decidir**, sin desarrollar. Recomendaciones del 23/10/2026 para retomar después.

## Situación actual

Tras *Vender y entregar* (F1), la pantalla de resultado ofrece botones para el **albarán**, las **etiquetas de caja** y, después de facturar, la **factura**. Tras *Comprar y recibir* (F2), solo las etiquetas. No se imprime ni se envía nada automáticamente (`get_print_action` en `models/mercas_touch.py`).

## Recomendación

- **Correo:** automático y en segundo plano, según la configuración del cliente y de la compañía.
- **Impresión:** manual por defecto, a un toque. Automática solo en los puestos con impresión silenciosa.
- **Etiquetas tras comprar:** abrir siempre el asistente.

### Impresión: manual, a un toque

- **Odoo no imprime en silencio por sí mismo.** Un informe abre el PDF y el navegador muestra su diálogo de impresión. "Automático" sin preparar la impresión solo significa que el diálogo aparece solo, y más pestañas abiertas.
- **Hay que imprimir en dos impresoras:** albaranes y facturas en la predeterminada (A4) y etiquetas en la de etiquetas. Por eso Chrome con `--kiosk-printing` **no sirve**: imprime siempre en una sola impresora (la predeterminada o la última usada en ese perfil) y no distingue un albarán de una etiqueta. La IoT Box es solo Enterprise. La solución son los módulos OCA de envío a impresora (ver *Envío directo a impresora*).
- **Con eso preparado, que sea configurable por puesto,** guardado en el navegador y no por compañía. Por ejemplo: "tras vender, imprimir el albarán automáticamente" (sí/no). Cada puesto tiene impresoras distintas (A4 o etiquetas) y costumbres distintas.
- **No todas las ventas necesitan papel,** por ejemplo un cliente habitual que recibe la factura por correo. Conviene una preferencia por cliente: albarán en papel, sí o no.

| Documento | Cuándo | Recomendación |
|---|---|---|
| Albarán | Tras *Vender y entregar* | Automático en los puestos con impresión silenciosa; botón a un toque en el resto |
| Etiquetas de caja | Tras *Comprar y recibir* | Abrir automáticamente el asistente de etiquetas: siempre se necesitan |
| Factura | Tras *Facturar* | Manual, o por correo (ver abajo) |
| Pedido de compra | — | No imprimirlo: el proveedor trae su propio albarán |

### Envío directo a impresora: OCA `report-print-send`

Cada informe tiene que salir por su impresora. Para v19 está resuelto en OCA, en `19report-print-send` (ya clonado, rama 19.0):

| Módulo | Qué hace |
|---|---|
| `base_report_to_printer` | Base: cada informe puede ir "a impresora", por informe, por usuario o por ambos. Odoo deja de abrir el PDF y lo envía directamente a la impresora, sin diálogo. |
| `base_report_to_label_printer` | Se marcan los informes de etiquetas como tales y cada usuario tiene su impresora de etiquetas. Es justo la separación A4 / etiquetas. |
| `base_report_to_printer_cups` | El servidor de Odoo envía el trabajo a CUPS. |
| `base_report_to_printer_qztray` | El navegador del puesto envía el trabajo a sus impresoras locales a través de QZ Tray. |
| `base_report_to_printer_websocket` | Odoo envía el PDF por su propio websocket a un pequeño agente en el puesto, que lo imprime. |

**El backend depende de dónde esté el servidor de Odoo:**

- **Servidor en la misma red que las impresoras** (puesto con servidor local): CUPS. Es lo más sencillo y robusto: no hay que instalar nada en los puestos y vale también desde una tableta.
- **Servidor en la nube e impresoras en el puesto:** el servidor no llega a las impresoras, así que QZ Tray en el PC del mostrador.
  - Hay que instalar QZ Tray en cada puesto, y no funciona desde una tableta.
  - Para que no pida confirmación en cada impresión hay que firmar las peticiones con un certificado. Revisar antes sus condiciones de licencia.

**Qué supone para mercas_touch:**

- Configuración:
  - Marcar los informes de etiquetas como *etiqueta*.
  - Dejar el albarán y la factura en la impresora predeterminada.
  - Asignar a cada usuario de puesto sus impresoras.
- Código: muy poco. Hoy `get_print_action` devuelve la acción del informe; con estos módulos, Odoo decide si lo envía a la impresora. Como mucho, mostrar en pantalla "Enviado a la impresora" en lugar del visor de PDF.
- La impresión automática de esta propuesta pasa a ser fácil: tras vender se pide el albarán y sale por la impresora sin tocar la pantalla.

**Pega en v20:** no hay `20report-print-send` clonado y puede que OCA aún no lo haya migrado. Si se va por aquí, v20 necesitará su propia migración o esperar.

### Correo: automático, en segundo plano, con lo estándar

El vendedor no debería tener que decidir si se envía algo ni esperar al servidor de correo.

- **Albarán:** Inventario › Ajustes › *Confirmación por correo*. Envía un correo al validar una entrega de salida. Es estándar, sin código.
- **Factura:** al facturar desde touch, enviarla según el *método de envío de facturas* del cliente (`invoice_sending_method`, estándar desde v18): por correo si lo tiene, nada si no. Requiere un cambio pequeño en mercas_touch: llamar al proceso de envío estándar después de publicar la factura.
- **Confirmación del pedido:** normalmente no hace falta en el mostrador, porque vender y entregar van juntos. Se descarta.
- **Compras:** no enviar correo al proveedor; la compra se hace en el momento.
- **Aviso en pantalla:** el resultado debe mostrar "Factura enviada a x@y", o un aviso si el cliente no tiene correo, para que nadie tenga que comprobar si salió.

## Pendiente de decidir antes de desarrollar

1. ¿El servidor de Odoo estará en el propio puesto o en la nube? Decide entre CUPS y QZ Tray.
2. ¿Preferencia "albarán en papel" por cliente, o basta la configuración por puesto?
3. ¿Activar la confirmación por correo de los albaranes en la compañía?

## Alcance del desarrollo (cuando se decida)

- Instalar y configurar `base_report_to_printer`, `base_report_to_label_printer` y el backend elegido (CUPS o QZ Tray).
- Opciones por puesto (almacenadas en el navegador): imprimir el albarán tras vender, abrir las etiquetas tras comprar.
- Mensaje "Enviado a la impresora" en la pantalla de resultado cuando el informe va directo a impresora.
- Envío de la factura en segundo plano al facturar, según `invoice_sending_method`, con el resultado en pantalla.
- Hacerlo en las dos versiones: dev19 (Odoo 19) y dev20 (Odoo 20).
