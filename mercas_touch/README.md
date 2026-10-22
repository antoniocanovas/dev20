# Mostrador táctil de Mercas (`mercas_touch`)

Pantalla de mostrador para mercados mayoristas de fruta, pensada para tablet o pantalla táctil. Reúne en una aplicación las tareas del puesto, cada una con su tecla de función:

- **F1 · Venta:** presupuestos en borrador que se van completando (cliente, producto, lote, kg, cajas y precio) y se venden y entregan en un paso.
- **F2 · Compra:** compras en borrador que se van completando y se compran y reciben en un paso, con lote nuevo (o el que se indique), origen y facturación firme.
- **F3 · Cajas:** cajas que devuelve un cliente, o que devolvemos a un proveedor.
- **F4 · Lotes:** stock de cada lote (recibido, vendido, desechado, en almacén), desechos y liquidación al proveedor.
- **F5 · Cobros:** cobra las facturas pendientes de un cliente.
- **F6 · Etiqueta dañada:** reimprime etiquetas de un lote, escaneando la etiqueta o escribiendo su lote.

La aplicación se llama *Mostrador* y aparece en la pantalla de inicio de Odoo. Su dirección es `/odoo/mercas-touch`.

Depende de `mercas_base` (y con él de los módulos de lotes de OCA) y de `barcodes`. Funciona en Odoo 20 Community y Enterprise.

## Criterio

Sigue el mismo criterio que *Despiece cárnico* (`meat_cutting`) y *Ruta de venta* (`sale_route_offline`):

- **Tarjetas grandes y teclado numérico en pantalla**, sin formularios ni listas del backend.
- **Se guarda mientras se trabaja.** La venta y la compra en curso se guardan como borrador (presupuesto o petición de presupuesto) con cada cambio, en segundo plano. Se puede dejar una a medias, pasar a otra y retomarla después, en el mismo puesto, en otro o desde el backend, sin perder nada.
- **Una llamada por operación.** Cada botón final (*Vender y entregar*, *Comprar y recibir*, *Recibir y abonar*, *Cobrar*…) es un único método del servidor que valida lo que recibe y ejecuta el flujo de `mercas_base`. La pantalla no depende de onchanges ni manipula el DOM del backend.
- **Sin duplicados.** Cada operación lleva un identificador (`mercas_touch_uuid`). Si se pulsa dos veces o se reintenta tras un corte, el servidor devuelve el documento ya creado.
- **Solo con conexión.** El stock de los lotes tiene que ser el real en ese momento. Cuando otro puesto vende o desecha, la pantalla recibe un aviso por el bus y actualiza los lotes que muestra.

## Uso

### Inicio

Un botón por modo, con su tecla de función. Arriba, la **cuadrícula de puntos** vuelve a Odoo y el botón de descarga **instala Odoo como aplicación** en la tablet (se abre en esta pantalla con una pulsación larga sobre el icono).

Dentro de cada modo, la flecha (o **Esc**) vuelve atrás, y los botones F1-F6 de la cabecera cambian de modo. Las teclas F1-F6 tienen prioridad sobre las de `mercas_keys` mientras la pantalla está abierta.

### F1 · Venta

1. **Presupuesto.** Al entrar se ven todos los presupuestos en borrador, el último modificado primero, con su cliente, líneas, importe y comercial, y un buscador. Se toca uno para seguir con él, o **Nuevo presupuesto**.
2. **Cliente** (en un presupuesto nuevo). Se busca por nombre, referencia, NIF o teléfono. La cabecera muestra su deuda (vencida en rojo), si supera el riesgo y las cajas que tiene nuestras. Si supera su crédito, el ticket lo avisa con el crédito usado y el concedido, por ejemplo «(50,00 € / 30,00 €)»; si el riesgo se supera por otro límite y el cliente no tiene límite de crédito, el aviso sale sin importes. El presupuesto se crea al añadir la primera línea.
3. **Producto.** En tarjetas por categoría, o buscando. También se puede **escanear la etiqueta de una caja**: el código es el nombre del lote, y abre directamente ese lote.
4. **Lote.** Los productos con lote muestran sus lotes con stock como tarjetas, el más antiguo primero: disponible, proveedor, fecha, origen y si es de facturación firme. Los lotes ya facturados al proveedor no se venden, igual que en el pedido.
5. **Línea.** Si el producto tiene atributos que se eligen en cada venta (los que nunca crean variantes, como la **calidad** y el **calibre** de la mercancía a granel, ver `mercas_base`), arriba aparece una fila de botones por atributo: se toca el valor, y tocándolo otra vez se quita. No son obligatorios. Después, kg, precio y cajas (con el tipo de caja del producto por defecto), con el teclado numérico, el del dispositivo o una báscula que escriba como teclado. Opcionalmente, un texto que va bajo el producto en el pedido. No deja vender más de lo que queda en el lote, contando las líneas ya añadidas.
6. **Ticket.** A la derecha, las líneas, las cajas y el total orientativo (sin impuestos). Las líneas muestran su calidad y calibre. Tocando una línea se modifica entera, también la calidad y el calibre: la descripción del pedido se actualiza y se conserva el texto de la línea. Arriba se ve si el presupuesto está guardado. Cada cambio se guarda en él: la flecha atrás vuelve a la lista de presupuestos sin perder nada, y la papelera cancela el presupuesto (pide confirmación).
   - **Cambio rápido de precios:** el precio de cada línea es un botón. Al tocarlo se abre un editor solo de precio, con el teclado numérico. La primera tecla sustituye el precio, como en un TPV, y el subtotal se ve al momento. *Siguiente* y *Anterior* pasan de una línea a otra; con teclado, **Intro** o **↓** va a la siguiente, **Mayús+Intro** o **↑** a la anterior y **Esc** termina. Pasada la última línea, el editor se cierra.
7. **Vender y entregar.** Guarda las últimas líneas en el presupuesto y ejecuta *Vender y Entregar* de `mercas_base`: confirma y valida el albarán. Después se puede imprimir el **albarán** o las **etiquetas de caja**, o abrir el pedido.
8. **Facturar y cobrar.** *Facturar* crea y publica la factura del pedido, que se puede imprimir. *Cobrar* abre el cobro del cliente con esa factura ya marcada y su importe pendiente propuesto: se elige el diario y se cobra, total o parcialmente.

Si el cliente supera su riesgo (con `sale_financial_risk` y sin permitir confirmar por encima del riesgo), el pedido queda en presupuesto y se abre el aviso estándar de OCA, donde un gestor de riesgo puede continuar.

### Presupuestos y compras confirmados

La lista inicial de ventas y de compras tiene tres filtros:

- **En curso** (por defecto): los borradores que se están preparando.
- **Para facturar:** los pedidos confirmados que aún no están facturados del todo.
- **Todos:** cualquier pedido salvo los cancelados, con su estado y su estado de facturación.

Al tocar un pedido confirmado se abre su **resumen**: estado, estado de facturación, líneas (producto, lote, calidad y calibre, cantidad, precio e importe) y la última factura. Desde ahí:

- En una **venta:** imprimir el albarán y las etiquetas, **Facturar**, imprimir la factura y **Cobrar**.
- En una **compra:** imprimir las etiquetas y **Crear factura de proveedor**, que crea la factura estándar del pedido en borrador y la abre en un diálogo para revisarla y confirmarla. Si los lotes de esa compra se facturan por liquidación (F4), no se debe crear también la factura desde el pedido.

*Volver a la lista* (o la flecha atrás) vuelve a la lista con el mismo filtro.

### F2 · Compra

Igual que la venta: al entrar se ven las **compras en borrador** para seguir con una, o **Nueva compra**, que pregunta el proveedor. La compra se guarda como petición de presupuesto con cada cambio, así que se puede pasar a otra compra sin cerrar la primera.

Por línea: kg, precio, cajas, país y provincia de origen (si están activados en la compañía). Sin el *Filtro origen* de la compañía se ofrecen todos los países y las provincias del país elegido; con el filtro, solo los países y provincias marcados como *Origen Mercas*, **facturación firme** (por defecto la del proveedor) y el **lote**: si se deja vacío, se crea uno nuevo. Mientras la compra está en borrador, el lote pedido se guarda solo por su nombre (*Lote a recibir*), sin crear todavía el lote. *Comprar y recibir* confirma, recibe y crea los lotes, y muestra los lotes creados para imprimir sus **etiquetas de caja**.

### F3 · Cajas

Se elige el contacto y el sentido:

- **El cliente devuelve cajas:** se registra con el flujo de devolución de envases de `mercas_base`, que recibe las cajas y abona la fianza.
- **Devolvemos cajas al proveedor:** con el flujo de entrega de envases, que entrega las cajas y factura.

Cada tipo de caja muestra cuántas tiene el cliente (o cuántas tenemos del proveedor) y se ajusta con +/−.

### F4 · Lotes

Los lotes pendientes de facturar al proveedor, el último recibido primero, con buscador (o escaneando una etiqueta). Cada tarjeta muestra una barra de vendido, desechado y en almacén, y los kg de cada cosa.

- **Desechar:** cantidad con el teclado numérico; se desecha de la ubicación con más stock del lote.
- **Etiquetas:** reimprime las etiquetas de caja del lote, o de todos los marcados, con el asistente de `mercas_base` (ver *F6 · Etiqueta dañada*).
- **Liquidar**, **Facturar adelanto** y **Factura firme**, sobre los lotes marcados, con las mismas reglas que el asistente de liquidación de `mercas_base`. Al terminar se abre la factura.

### F5 · Cobros

Facturas pendientes del cliente (las vencidas en rojo). Al marcarlas se propone su importe, que se puede cambiar para un cobro parcial. Se elige el diario (banco o caja) y, opcionalmente, un concepto. El cobro se publica y se concilia con las facturas marcadas; sin facturas queda como anticipo del cliente.

### F6 · Etiqueta dañada

Para reponer las etiquetas de una caja cuya etiqueta se ha estropeado. El campo de búsqueda está listo al entrar:

- **Escanear la etiqueta:** el código es el nombre del lote, y abre directamente sus etiquetas.
- **Escribirlo**, si la etiqueta no se puede leer: el lote impreso, o parte de él, el producto o el proveedor, e **Intro** o *Buscar*. Si un lote se llama exactamente así (sin distinguir mayúsculas), se abren sus etiquetas; si no, se muestran los lotes que coinciden, y se toca el que sea. Sin escribir nada se ven los últimos recibidos.

Salen todos los lotes, también los ya facturados al proveedor. Las etiquetas se imprimen con el asistente de `mercas_base`, que propone tantas como cajas se compraron del lote: se puede cambiar el número (por ejemplo, 1 para la caja dañada) y el formato.

## Permisos

Se aplican los permisos normales del usuario: la pantalla no salta ninguna regla. Para usar todos los modos, el usuario del mostrador necesita ventas, compras, inventario (con lotes) y facturación. La deuda, el riesgo y las cajas del cliente se leen como información aunque el usuario no vea todas las facturas.

## Notas técnicas

- **Servidor:** el modelo abstracto `mercas.touch` (`get_screen_data`, `search_partners`, `get_partner_info`, `get_product_lots`, `find_by_barcode`, `get_lots`, `get_drafts`, `get_draft`, `save_draft`, `cancel_draft`, `get_order_summary`, `invoice_sale`, `invoice_purchase`, `sell`, `purchase`, `move_boxes`, `scrap_lot`, `invoice_lots`, `register_payment`, `get_print_action`, `search_label_lots`, `get_lot_label_action`).
- **Calidad y calibre:** cada producto de `get_screen_data` trae sus `attributes` (los que nunca crean variantes y tienen más de un valor), y las líneas de venta de `save_draft`/`sell` llevan `attribute_value_ids`, que el servidor comprueba (valores del producto, uno por atributo) y guarda en `product_no_variant_attribute_value_ids`.
- **Pantalla:** acción cliente Owl 3 `mercas_touch.screen` con un componente `TouchNumpad` para el teclado numérico. El teclado solo emite la tecla pulsada; la pantalla la aplica al campo que se está editando.
- **Escáner:** usa el plugin de `barcodes`; un código escaneado mientras se escribe en un campo va al campo.
- **Aviso de lotes:** el servidor envía `mercas_touch/lots_changed` a los usuarios internos cuando vende, compra o desecha.

## Tests

- **Python:** filtros *En curso*, *Para facturar* y *Todos*, resumen de un pedido confirmado y factura de proveedor desde la compra; facturar una venta (una sola vez) e imprimir la factura; presupuestos y compras en borrador (crear, actualizar línea a línea, conservar secciones, retomar los del backend, cancelar, vender y comprar desde el borrador, lote de compra por nombre); venta con lote, cajas, precio y texto; venta a granel con calidad y calibre, cambiados después conservando el texto, y valores no válidos; compra con lote nuevo o con nombre y origen; idempotencia; validación de las líneas; lotes con stock y lotes ya facturados; escáner; devolución y entrega de cajas; desechos; liquidación; cobros con y sin facturas; impresión; etiqueta dañada (búsqueda del lote escaneado o escrito y reimpresión); riesgo superado (si está `sale_financial_risk`).
- **Tours en el navegador:** facturar desde *Para facturar* una venta y una compra ya cerradas; venta completa con el teclado numérico, facturada y cobrada desde la propia venta, retomar un presupuesto del backend y dejarlo a medias, pasar de una compra en borrador a otra y volver, cambio rápido de precios línea a línea, compra con lote nuevo, impresión de sus etiquetas y desecho, y cobro parcial.

```bash
odoo-bin -c odoo20.conf -d <bd> -i mercas_touch --test-tags /mercas_touch --stop-after-init
```

Los tours necesitan Chrome y el paquete de Python `websocket-client`.
