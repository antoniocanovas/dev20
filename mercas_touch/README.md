# Mostrador táctil de Mercas (`mercas_touch`)

Pantalla de mostrador para mercados mayoristas de fruta, pensada para tablet o pantalla táctil. Reúne en una aplicación las tareas del puesto, cada una con su tecla de función:

- **F1 · Venta:** vende y entrega en un paso: cliente, producto, lote, kg, cajas y precio.
- **F2 · Compra:** compra y recibe en un paso, con lote nuevo (o el que se indique), origen y facturación firme.
- **F3 · Cajas:** cajas que devuelve un cliente, o que devolvemos a un proveedor.
- **F4 · Lotes:** stock de cada lote (recibido, vendido, desechado, en almacén), desechos y liquidación al proveedor.
- **F5 · Cobros:** cobra las facturas pendientes de un cliente.

La aplicación se llama *Mostrador* y aparece en la pantalla de inicio de Odoo. Su dirección es `/odoo/mercas-touch`.

Depende de `mercas_base` (y con él de los módulos de lotes de OCA) y de `barcodes`. Funciona en Odoo 20 Community y Enterprise.

## Criterio

Sigue el mismo criterio que *Despiece cárnico* (`meat_cutting`) y *Ruta de venta* (`sale_route_offline`):

- **Tarjetas grandes y teclado numérico en pantalla**, sin formularios ni listas del backend.
- **Una llamada por operación.** Cada botón final (*Vender y entregar*, *Comprar y recibir*, *Recibir y abonar*, *Cobrar*…) es un único método del servidor que valida lo que recibe y ejecuta el flujo de `mercas_base`. La pantalla no depende de onchanges ni manipula el DOM del backend.
- **Sin duplicados.** Cada operación lleva un identificador (`mercas_touch_uuid`). Si se pulsa dos veces o se reintenta tras un corte, el servidor devuelve el documento ya creado.
- **Solo con conexión.** El stock de los lotes tiene que ser el real en ese momento. Cuando otro puesto vende o desecha, la pantalla recibe un aviso por el bus y actualiza los lotes que muestra.

## Uso

### Inicio

Un botón por modo, con su tecla de función. Arriba, la **cuadrícula de puntos** vuelve a Odoo y el botón de descarga **instala Odoo como aplicación** en la tablet (se abre en esta pantalla con una pulsación larga sobre el icono).

Dentro de cada modo, la flecha (o **Esc**) vuelve atrás, y los botones F1-F5 de la cabecera cambian de modo. Las teclas F1-F5 tienen prioridad sobre las de `mercas_keys` mientras la pantalla está abierta.

### F1 · Venta

1. **Cliente.** Se busca por nombre, referencia, NIF o teléfono. La cabecera muestra su deuda (vencida en rojo), si supera el riesgo y las cajas que tiene nuestras.
2. **Producto.** En tarjetas por categoría, o buscando. También se puede **escanear la etiqueta de una caja**: el código es el nombre del lote, y abre directamente ese lote.
3. **Lote.** Los productos con lote muestran sus lotes con stock como tarjetas, el más antiguo primero: disponible, proveedor, fecha, origen y si es de facturación firme. Los lotes ya facturados al proveedor no se venden, igual que en el pedido.
4. **Línea.** Kg, precio y cajas (con el tipo de caja del producto por defecto), con el teclado numérico, el del dispositivo o una báscula que escriba como teclado. Opcionalmente, un texto que va bajo el producto en el pedido. No deja vender más de lo que queda en el lote, contando las líneas ya añadidas.
5. **Ticket.** A la derecha, las líneas, las cajas y el total orientativo (sin impuestos). Tocando una línea se modifica.
6. **Vender y entregar.** Crea el pedido con sus lotes y cajas y ejecuta *Vender y Entregar* de `mercas_base`: confirma y valida el albarán. Después se puede imprimir el **albarán** o las **etiquetas de caja**, o abrir el pedido.

Si el cliente supera su riesgo (con `sale_financial_risk` y sin permitir confirmar por encima del riesgo), el pedido queda en presupuesto y se abre el aviso estándar de OCA, donde un gestor de riesgo puede continuar.

### F2 · Compra

Proveedor, producto y, por línea: kg, precio, cajas, país y provincia de origen (si están activados en la compañía, con el filtro *Origen Mercas*), **facturación firme** (por defecto la del proveedor) y el **lote**: si se deja vacío, se crea uno nuevo. *Comprar y recibir* confirma, recibe y crea los lotes, y muestra los lotes creados para imprimir sus **etiquetas de caja**.

### F3 · Cajas

Se elige el contacto y el sentido:

- **El cliente devuelve cajas:** se registra con el flujo de devolución de envases de `mercas_base`, que recibe las cajas y abona la fianza.
- **Devolvemos cajas al proveedor:** con el flujo de entrega de envases, que entrega las cajas y factura.

Cada tipo de caja muestra cuántas tiene el cliente (o cuántas tenemos del proveedor) y se ajusta con +/−.

### F4 · Lotes

Los lotes pendientes de facturar al proveedor, el último recibido primero, con buscador (o escaneando una etiqueta). Cada tarjeta muestra una barra de vendido, desechado y en almacén, y los kg de cada cosa.

- **Desechar:** cantidad con el teclado numérico; se desecha de la ubicación con más stock del lote.
- **Liquidar**, **Facturar adelanto** y **Factura firme**, sobre los lotes marcados, con las mismas reglas que el asistente de liquidación de `mercas_base`. Al terminar se abre la factura.

### F5 · Cobros

Facturas pendientes del cliente (las vencidas en rojo). Al marcarlas se propone su importe, que se puede cambiar para un cobro parcial. Se elige el diario (banco o caja) y, opcionalmente, un concepto. El cobro se publica y se concilia con las facturas marcadas; sin facturas queda como anticipo del cliente.

## Permisos

Se aplican los permisos normales del usuario: la pantalla no salta ninguna regla. Para usar todos los modos, el usuario del mostrador necesita ventas, compras, inventario (con lotes) y facturación. La deuda, el riesgo y las cajas del cliente se leen como información aunque el usuario no vea todas las facturas.

## Notas técnicas

- **Servidor:** el modelo abstracto `mercas.touch` (`get_screen_data`, `search_partners`, `get_partner_info`, `get_product_lots`, `find_by_barcode`, `get_lots`, `sell`, `purchase`, `move_boxes`, `scrap_lot`, `invoice_lots`, `register_payment`, `get_print_action`).
- **Pantalla:** acción cliente Owl 3 `mercas_touch.screen` con un componente `TouchNumpad` para el teclado numérico.
- **Escáner:** usa el plugin de `barcodes`; un código escaneado mientras se escribe en un campo va al campo.
- **Aviso de lotes:** el servidor envía `mercas_touch/lots_changed` a los usuarios internos cuando vende, compra o desecha.

## Tests

- **Python:** venta con lote, cajas, precio y texto; compra con lote nuevo o con nombre y origen; idempotencia; validación de las líneas; lotes con stock y lotes ya facturados; escáner; devolución y entrega de cajas; desechos; liquidación; cobros con y sin facturas; impresión; riesgo superado (si está `sale_financial_risk`).
- **Tours en el navegador:** venta completa con el teclado numérico, compra con lote nuevo y desecho, y cobro parcial.

```bash
odoo-bin -c odoo20.conf -d <bd> -i mercas_touch --test-tags /mercas_touch --stop-after-init
```

Los tours necesitan Chrome y el paquete de Python `websocket-client`.
