# Mercas Base

Módulo base para la gestión de mercados mayoristas de frutas y hortalizas en Odoo 19 Community.

## Funcionalidades

### Ventas — Vender y Entregar

El botón **Vender y Entregar** en el pedido de venta ejecuta en un solo clic:

1. Valida que todas las líneas de producto trazadas tengan lote asignado.
2. Comprueba el riesgo financiero del cliente (requiere `sale_financial_risk` / `account_financial_risk`). Si se supera el riesgo, muestra el aviso estándar de OCA; si el usuario acepta continuar, el flujo continúa automáticamente.
3. Confirma el pedido.
4. Valida el albarán de salida asignando la cantidad hecha igual a la demandada (sin pedir confirmación de retroactivos).

### Ventas — Aviso de edición concurrente

Cuando dos o más usuarios tienen abierto el mismo pedido de venta y uno de ellos crea, modifica o elimina una línea (`sale.order.line`), el resto recibe un aviso flotante en tiempo real ("Pedido actualizado — [Usuario] ha modificado las líneas de este pedido. Haz clic aquí para recargar") con un botón **Recargar** que refresca la vista para traer los datos actuales. El propio usuario que hizo el cambio no se avisa a sí mismo.

Implementación:
- **Backend**: `sale.order.line` sobrescribe `create`/`write`/`unlink`; tras la operación, publica una notificación por proveedor de pedido afectado vía `self.env["bus.bus"]._sendone(...)` al canal `mercas_sale_order_lines-<id del pedido>`, con `order_id`, `user_id` y `user_name` de quien hizo el cambio como payload (tipo `mercas_sale_order_lines_updated`).
- **Frontend**: `static/src/js/sale_order_lines_bus_notification.js` parchea `FormController` (solo para `resModel == "sale.order"`): se suscribe al canal del pedido abierto mientras la vista esté montada (y se desuscribe al cambiar de registro o cerrar), escucha el tipo de notificación, descarta los avisos del propio usuario y muestra el toast con el servicio nativo `notification`. El botón "Recargar" llama a `this.model.load()` para refrescar el registro desde el servidor.

Requiere el módulo `bus` (dependencia estándar de Odoo, añadida explícitamente).

### Ventas — Fecha del último cambio de cantidad

Cada línea de pedido de venta (que no sea sección/nota) guarda en `product_qty_datetime` (Datetime, oculto) la fecha y hora de la creación de la línea (con la cantidad inicial ya puesta) o, si es posterior, de la última vez que se modificó `product_uom_qty` — solo si el valor realmente cambia (escribir la misma cantidad no actualiza la fecha). Se informa también en la creación porque, al añadir una línea desde el formulario, el cliente web manda todo (producto y cantidad) en una sola llamada, sin un `write` posterior que lo dispare.

En la lista de líneas del formulario de pedido de venta se muestra como un icono "i" compacto, sin título de columna, con ancho fijo (`width="32px"`) justo antes del icono de papelera de cada línea. Al pinchar/tocar el icono se abre una ventana emergente (igual que el icono de stock previsto de `sale_stock`) con el texto "Cantidad actualizada el: `<fecha>`" — funciona igual con ratón que en pantallas táctiles. El icono no activa el modo edición de la línea al pincharlo (para que no salte el foco al campo Producto).

Implementación: widget de campo propio `mercas_product_qty_datetime_icon` (`static/src/js/product_qty_datetime_icon.js` + plantilla `static/src/xml/product_qty_datetime_icon.xml`).

### Ventas — Cajas por línea de pedido

Cada línea de pedido tiene los campos **Cajas** (`box_qty`) y **Caja** (`box_product_id`), ocultos si el producto de la línea ya está marcado como caja/envase (`product_id.is_box`) — una línea de caja no necesita indicar en qué caja va empaquetada. Al confirmar el pedido:

- Se inserta la sección **PRODUCTOS** antes de las líneas de producto.
- Se inserta la sección **Envases** al final.
- Por cada línea con `box_qty > 0` se crea automáticamente una línea de caja vinculada (`box_sale_line_id`) usando el producto indicado en `box_product_id` de la línea (que se inicializa desde la plantilla del producto y puede modificarse manualmente antes de confirmar).
- Si después de confirmar se modifica `box_qty`, `box_product_id` o el producto de una línea, la línea de caja se actualiza o elimina en consecuencia.

### Ventas — Ubicación por cliente

Al confirmar un pedido de venta se verifica si el cliente tiene una sub-ubicación propia bajo el **Almacén clientes** configurado en la empresa. Si no existe, se crea automáticamente con el nombre del partner y se asigna como `property_stock_customer` del cliente (campo dependiente de empresa).

### Compras — Comprar y Recibir

El botón **Comprar y Recibir** en el pedido de compra:

1. Confirma el pedido (con auto-creación de lotes si está activada).
2. Valida el albarán de entrada asignando cantidad hecha igual a la demandada.
3. Genera la factura de proveedor, le asigna la fecha de hoy y la valida.
4. Abre directamente la factura generada.

La factura no se genera automáticamente para pedidos de devolución de envases (ver más abajo), donde ya se crea y valida dentro del propio flujo de confirmación.

### Compras — Cajas por línea de pedido

Igual que en ventas, cada línea de pedido de compra (que no sea de devolución de envases) tiene los campos **Cajas** (`box_qty`) y **Caja** (`box_product_id`, inicializado desde la plantilla del producto). Al confirmar el pedido:

- Se inserta la sección **PRODUCTOS** antes de las líneas de producto y la sección **Envases** al final.
- Por cada línea con `box_qty > 0` se crea una línea de caja vinculada (`box_purchase_line_id`) con el producto de `box_product_id`, de forma que el envase se incluye en el albarán de entrada generado al confirmar.
- Cambios posteriores en `box_qty`, `box_product_id` o el producto de la línea actualizan o eliminan la línea de caja correspondiente.

### Compras — Ubicación por proveedor

Al confirmar un pedido de compra (que no sea de devolución de envases) se verifica si el proveedor tiene una sub-ubicación propia bajo el **Almacén proveedores** configurado en la empresa. Si no existe, se crea automáticamente con el nombre del partner y se asigna como `property_stock_supplier` del proveedor (campo dependiente de empresa).

### Compras — Auto-creación de lotes

Cuando la opción **Purchase lot auto** está activa en la empresa, al confirmar cualquier pedido de compra se crea automáticamente un lote nuevo (usando la secuencia del producto) para cada línea trazada que no tenga lote asignado. El proveedor del pedido se asigna automáticamente al lote. Requiere el módulo OCA `purchase_lot`.

### Compras — Origen del producto

Las líneas de pedido de compra disponen de los campos **País origen** y **Provincia origen**. Su visibilidad en la vista de pedido se controla mediante los toggles **Columna país origen** y **Columna provincia origen** de la parametrización de empresa.

Cuando una línea tiene lote asignado, cualquier cambio en el país o provincia de origen se propaga automáticamente al lote correspondiente (`stock.lot`).

### Compras y Ventas — Imprimir etiquetas de caja

El botón **Imprimir etiquetas** (visible en pedidos de compra confirmados y en pedidos de venta confirmados) abre un asistente (`mercas.label.print.wizard`) que propone, para cada línea del pedido, una etiqueta por cada caja:

- Solo propone líneas con producto **almacenable o consumible** (`product_id.type == 'consu'`) que **no** esté marcado como caja/envase (`product.is_box`) — así no se proponen etiquetas para el propio envase.
- La cantidad propuesta por línea es su campo **Cajas** (`box_qty`), ya calculado/introducido al confirmar el pedido.
- La cantidad es **editable** antes de imprimir: sirve tanto para imprimir de más como para reponer solo las etiquetas que se han roto (poniendo, p. ej., 3 en vez de las 10 propuestas).
- El botón se puede pulsar tantas veces como haga falta (reimprimir), cada vez vuelve a proponer las cantidades desde cero.

Reutiliza el mecanismo estándar de etiquetas de producto de Odoo (`product.label.layout` / los informes `product.report_product_template_label_*`): el asistente arma su propio `quantity_by_product` (cantidad por producto, no uniforme como en el asistente nativo) y llama directamente al informe, así que las etiquetas impresas son las mismas plantillas y formatos que ya conoce cualquier usuario de Odoo (Dymo, 2x7, 4x7, 4x12, con o sin precio).

### Compras — Facturación firme

Cada línea de pedido de compra tiene el campo **Facturación firme** (`mercas_firm_negotiation`), que por defecto toma el valor configurado en el mismo campo del proveedor (**Facturación firme por defecto** en la ficha de contacto) y se puede cambiar a mano por línea. Al asignar lote a la línea (o al crearse automáticamente, ver más abajo), ese valor se traslada al lote — ver *Lotes de stock* para cómo afecta a la facturación al proveedor.

### Compras — Devolución de envases

**Detección por contenido, no por tipo de pedido**: un pedido de compra se considera devolución de envases (`mercas_is_box_return`, calculado y almacenado) cuando tiene al menos una línea de producto y **todas** sus líneas de producto están marcadas como caja/envase (`product.is_box`). No hace falta ningún wizard ni campo de tipo: un pedido de compra creado a mano con solo productos de caja se detecta igual.

El botón **Devolución cajas** en el pedido de venta abre un nuevo pedido de compra pre-relleno para el mismo cliente (solo un atajo cómodo; el usuario añade las líneas de caja a devolver).

Una vez el pedido de compra está confirmado y es de devolución de envases, aparece el botón **Recibir y facturar** — acción explícita, no automática al confirmar (así un pedido que resulte tener solo productos de caja por cualquier otro motivo nunca dispara esto por accidente):

1. Se verifica la ubicación de stock del cliente (igual que en ventas).
2. Se reciben las cajas desde la ubicación física del cliente (no desde el proveedor virtual).
3. Se genera y valida automáticamente la factura de proveedor (nota de crédito al cliente por el depósito).
4. Se abre la factura para revisión.

El botón **Purchase & Receive** (atajo de "confirmar y procesar todo") también ejecuta este flujo automáticamente si el pedido es de devolución de envases, ya que es en sí mismo una acción explícita de "hazlo todo ahora".

### Compras — Entrega de cajas a proveedor

Simétrico al anterior: un pedido de venta se considera entrega de cajas (`mercas_is_box_delivery`, calculado y almacenado) si viene vinculado a una compra de origen vía `box_delivery_purchase_id` **o** si tiene al menos una línea de producto y todas están marcadas como caja/envase — así un pedido de venta creado a mano también se detecta correctamente.

El botón **Entrega cajas** en el pedido de compra confirmado abre un nuevo pedido de venta pre-relleno para el mismo proveedor (atajo cómodo, con `box_delivery_purchase_id` ya vinculado).

Una vez el pedido de venta está confirmado y es de entrega de cajas, aparece el botón **Recibir y facturar** — igualmente una acción explícita, no automática al confirmar:

1. Se verifica/crea la ubicación de stock propia del proveedor (igual que en compras).
2. Se entregan las cajas a la ubicación física del proveedor (en vez de a la ubicación virtual de clientes).
3. Se genera y valida automáticamente la factura de cliente correspondiente al proveedor.

El botón **Sold & Sent** también ejecuta este flujo automáticamente si el pedido es de entrega de cajas, por el mismo motivo que en compras.

### Contabilidad — Compensación de facturas

El botón **Compensar** en facturas de proveedor (`in_invoice`) en estado publicado y pendiente de pago:

1. Crea un asiento de compensación en el **Diario de compensación** configurado en la empresa:
   - Debe a la cuenta a pagar de la factura de proveedor (salda la deuda con el proveedor).
   - Haber a la cuenta a cobrar del mismo partner (genera un crédito pendiente en sus facturas de cliente).
2. Valida y concilia el asiento con la línea a pagar de la factura de proveedor.
3. El crédito resultante aparece como **crédito pendiente** en las facturas de cliente del mismo partner y puede aplicarse directamente desde ellas.

### Maestros — Producto: caja/envase

En la ficha de producto (`product.template`) hay dos campos junto a la cantidad disponible:

- **Es caja/envase** (`is_box`, booleano): marca el producto como caja/envase. Es el campo que usan todos los filtros y detecciones relacionadas con cajas del módulo (devolución/entrega de envases, exclusión en la impresión de etiquetas, cálculo de cajas por contacto) — global, no por compañía.
- **Caja** (`box_product_id`): producto de envase por defecto a usar al vender/comprar *este* producto (p. ej., "Caja1" para Manzana). Solo admite productos marcados como caja/envase (dominio `is_box = True`), y se oculta si el propio producto ya está marcado como caja (una caja no necesita su propia caja). Si se crea un producto nuevo directamente desde este campo (crear y editar / creación rápida), la vista pasa `context="{'default_is_box': True}"` para que el producto recién creado nazca ya marcado como caja/envase — si no, no cumpliría el propio dominio (`is_box = True`) que exige el campo y no volvería a aparecer al buscarlo.

### Maestros — País y Provincia de origen

Los modelos `res.country` y `res.country.state` disponen del campo booleano **Origen Mercas** (`mercas_origin`), visible en sus vistas de formulario y lista. Permite marcar los países y provincias habituales de origen de la mercancía para su uso futuro como filtro (controlado por **Filtro origen** en la empresa).

### Lotes de stock (`stock.lot`)

El módulo extiende el lote de stock con las siguientes capacidades:

#### Campos de trazabilidad

| Campo | Descripción |
|---|---|
| **Proveedor** (`partner_id`) | Partner proveedor del lote. Se asigna automáticamente al confirmar el pedido de compra y puede editarse manualmente. |
| **País origen** / **Provincia origen** | Origen geográfico del producto. Se propagan desde las líneas de compra. |

Un lote solo puede tener líneas de compra de un único proveedor (`_check_single_purchase_partner`, por trazabilidad alimentaria): si se intenta vincular a un lote líneas de pedidos de compra de proveedores distintos, salta una validación que lo impide.

#### Dos regímenes de facturación a proveedor

El acuerdo de pago de un lote lo decide el campo booleano **Facturación firme** (`mercas_firm_negotiation`) del propio lote — no el tipo de pedido de compra:

- **Liquidación por venta** (`mercas_firm_negotiation = False`, valor por defecto): se paga al proveedor en función de lo que realmente se ha vendido. Admite **anticipos**: mientras queda stock, puede facturarse una estimación sobre lo vendido + desechado hasta ese momento; al agotarse el stock (`completed`) se da por completamente facturado el lote, descontando los anticipos ya emitidos — el proveedor asume la diferencia por desechos u otros ajustes.
- **Facturación firme** (`mercas_firm_negotiation = True`): se paga al proveedor la totalidad de lo recibido, con independencia de lo vendido. Admite **facturación parcial**: cada factura cubre solo el saldo pendiente (`Kg recibidos - Kg facturados`), y el lote no requiere tener el stock agotado para ser facturable.

**Control del campo `mercas_firm_negotiation`:**
- Solo lo puede cambiar un usuario del grupo **Contabilidad/Gestor de contabilidad** (`account.group_account_manager`); cualquier otro usuario recibe un error.
- No se puede cambiar en absoluto una vez el lote tiene facturación **en firme** posteada (línea marcada `mercas_is_firm_line` en una factura/abono ya posteado) — el paso de liquidación por venta a firme sigue permitido en todo momento anterior (ver más abajo), pero una vez facturado en firme, el lote queda fijado a ese régimen para siempre.
- Registra cualquier cambio en el chatter del lote (`tracking=True`).
- Su valor inicial se propaga desde la línea de pedido de compra de origen (**Facturación firme**, que a su vez toma por defecto el valor del proveedor).

El campo booleano **Facturado** (`invoiced`) sustituye al antiguo M2O a una única factura — el detalle de facturas y abonos de proveedor asociados al lote está en la pestaña **F.Proveedor**. Es editable manualmente: si el usuario lo cambia a mano, el sistema deja de recalcularlo automáticamente para ese lote (para reabrirlo al cálculo automático, hay que editarlo de nuevo tras la próxima factura/abono real). Comportamiento automático, en ambos casos recalculado **al postear** una factura o abono de proveedor con líneas de este lote (nunca al crearla en borrador):

- **Facturación firme**: se recalcula `Kg facturados (neto)` = Σ cantidad de líneas marcadas `mercas_is_firm_line` en facturas posteadas − lo mismo en abonos posteados, y `invoiced` pasa a `True` en cuanto `Kg facturados (neto) ≥ Kg recibidos` (puede requerir varias facturas parciales).
- **Liquidación por venta**: se recalcula `Importe facturado (neto)` de la misma forma (en importe, no en kg, y sobre todas las líneas, no solo las de suministro firme), y `invoiced` pasa a `True` solo cuando, además, el lote está `completed` (sin stock) y ese neto cubre el importe bruto de liquidación final. Un anticipo con stock pendiente nunca marca `invoiced = True` por sí solo.
- En ambos regímenes, un abono que reduzca el neto por debajo del objetivo puede volver a poner `invoiced` en `False`.

#### Anticipos en liquidación por venta

Un lote en liquidación por venta con stock disponible puede facturarse antes de agotarse (`invoiceable = True` aunque `completed = False`), usando una estimación. El importe es siempre el de lo realmente vendido neto de margen — el desecho no se paga nunca, con o sin anticipo. Cómo se reparte ese importe fijo entre cantidad/precio de línea depende del ajuste de empresa **Modo de liquidación** (`liquidation_mode`, pestaña Mercas > Contabilidad):

- **Precio medio (una línea)**, por defecto: la cantidad de la línea (vendido + desechado) reparte el importe fijo en un precio/kg menor, sin que el desecho aparezca por separado — igual que hace la liquidación final con `purchase_kg`.
  ```
  importe_bruto  = Importe vendido × (1 - Margen%)            (fijo, no depende del desecho)
  resuelto_kg    = Kg vendidos + Kg desechados                (solo para mostrar cantidad/precio en la línea)
  precio_kg      = importe_bruto / resuelto_kg
  ```
- **Precio medio + desecho aparte**: el importe fijo se reparte solo entre lo vendido (`Kg vendidos`, sin diluir por el desecho), y si hay algo desechado se añade una **segunda línea a precio 0** con esa cantidad — deja explícito en la propia factura que el desecho no se paga, en vez de solo bajar el precio/kg de forma no evidente.

Si está `completed`, se usa en su lugar el importe final (`supplier_amount`); la cantidad de la línea principal es `purchase_kg` en modo "Precio medio" o `Kg vendidos` en modo "desecho aparte" (con su línea a 0 igual que en el anticipo).

Al generar la factura (parcial o la liquidación final), la línea principal (más la de desecho, si aplica) usa ese importe bruto y, si el lote ya tiene facturas o abonos anteriores posteados, se añade **una línea de descuento por cada uno** ("(-) Anticipo ya facturado: FACT/... del DD/MM/YYYY"), igual que hace el estándar de Odoo con los anticipos de venta — así el importe neto de la nueva factura es siempre el bruto actual menos lo ya facturado, y el histórico completo de anticipos queda visible en el propio documento.

**Precio/kg proveedor editable**: además de fijar el margen (que recalcula el precio/kg), también se puede editar directamente el **Precio/kg proveedor** (en el lote y en el asistente de liquidación) — recalcula el margen equivalente (`mercas_margin` sigue siendo el único campo realmente persistido). Si el lote todavía no tiene nada vendido (`Importe vendido = 0`), no hay base sobre la que calcular un margen a partir de un precio: el cambio se ignora en silencio y el campo vuelve a mostrar su valor calculado (0).

Editar **cualquiera** de los dos campos (Margen o Precio/kg) recalcula los otros dos (margen, precio/kg e importe proveedor) al momento, en pantalla, sin esperar a guardar — en el lote, vía el `compute`/`onchange` del propio campo; en el asistente de liquidación, la línea (`stock.lot.invoice.wizard.line`) recalcula explícitamente los tres valores en sí misma en vez de depender del `related` a `stock.lot` y de vuelta, para que el importe también se actualice en el acto.

**Detalle de ventas en factura** (ajuste de empresa, desactivado por defecto): si está activo, la línea principal de venta de la factura incluye además, en su descripción, un desglose **acumulado** (todas las ventas del lote hasta la fecha, no solo las nuevas desde la última factura) con una línea de texto por cada movimiento de venta validado: `DD/MM/YYYY => Pedido => Cantidad UdM => Precio unitario símbolo_moneda` (p. ej. `05/08/2026 => S00012 => 100.00 kg => 3.50 €`; precio de venta al cliente de ese pedido, neto de descuento — no el precio/proveedor liquidado; UdM y moneda son las propias de la línea de venta, no las de la empresa). Es solo texto informativo: no crea líneas contables nuevas ni afecta al importe o cantidad facturados, así que no hace falta ningún control de "esta venta ya apareció en una factura anterior". No aplica a lotes en facturación firme (ahí no hay margen sobre ventas que desglosar).

Con el mismo ajuste activo, la línea de desecho del modo "Precio medio + desecho aparte" (ver arriba) también incluye su propio desglose acumulado, uno por cada regularización de desecho del lote (mismo criterio que `Kg desechados`: desechos formales y ajustes de inventario negativos en positivo, ajustes positivos en negativo): `DD/MM/YYYY => Cantidad UdM` (p. ej. `06/08/2026 => 10.00 kg`).

#### Paso de liquidación por venta a facturación firme

Un lote que ya tiene anticipos o liquidaciones por venta facturados puede pasar a facturación firme (lo cambia un Gestor de contabilidad en el campo del lote). La **primera** factura en firme de ese lote:

1. Incluye la línea de suministro habitual (`Kg recibidos - Kg facturados en firme` × precio de compra, sin tocar el precio unitario).
2. Si queda algún importe de liquidación por venta sin reconciliar (`Importe facturado (neto)` de líneas que no son de suministro firme), añade una única línea de descuento "(-) Anticipos pendientes de descontar" por ese importe.

Como esa línea de descuento también cuenta como "no es de suministro firme", el importe pendiente de reconciliar queda a cero justo después de postear esa factura — las siguientes facturas en firme de ese lote (si hace falta más de una, por recepciones parciales) ya no vuelven a comprobar ni añadir esa línea. El camino inverso (de facturación firme a liquidación por venta) no está permitido en cuanto hay facturación en firme posteada, así que nunca hace falta la reconciliación simétrica.

#### El asistente de liquidación: tres botones

- **Liquidar**: acción masiva, sin selección. Incluye lotes en facturación firme con saldo pendiente y lotes en liquidación por venta ya `completed`. Dejan fuera los anticipos.
- **Facturar adelanto**: solo sobre lotes **seleccionados** en liquidación por venta (completados o no). Rechaza con error si hay algún lote seleccionado en facturación firme.
- **Factura firme**: solo sobre lotes **seleccionados** con facturación firme activada. Rechaza con error si hay algún lote seleccionado que no la tenga activada.

Los anticipos y las facturas firme son siempre una selección explícita del usuario — nunca se generan por descuido desde "Liquidar".

La columna **Seleccionado** de la lista solo es editable en los lotes `invoiceable`: en liquidación por venta, cuando se ha vendido o desechado parte del material (hay importe bruto pendiente de facturar); en facturación firme, cuando el lote tiene kg recibidos pendientes de facturar. En el resto de lotes queda de solo lectura.

#### Pestaña General — Cantidades y Liquidación

| Campo | Descripción |
|---|---|
| **Kg comprados** | Suma de kg de las líneas de compra confirmadas (cantidad documentada/pedida). |
| **Kg recibidos** | *(solo facturación firme)* Kg recibidos físicamente (`stock.move.line` validados desde ubicación de proveedor a interna). |
| **Kg vendidos** | Suma de kg entregados en albaranes de venta (`stock.move.line` completados). |
| **Kg desechados** | Desechos formales más ajustes de inventario negativos, menos ajustes positivos (neto). |
| **Kg en almacén** | Campo estándar `product_qty` de Odoo (stock disponible). |
| **Importe vendido** | *(solo liquidación por venta)* Calculado desde los movimientos de salida: `qty × precio_unitario × (1 - descuento%)`. |
| **Margen (%)** | *(solo liquidación por venta)* Margen aplicable al lote: del partner si está informado, o el general de la empresa. Se asigna al crear el lote y puede modificarse manualmente (requiere grupo Gestor de Ventas). |
| **Importe proveedor** | *(solo liquidación por venta)* `Importe vendido × (1 - Margen%)` |
| **Precio/kg proveedor** | *(solo liquidación por venta)* `Importe proveedor / Kg comprados`. Editable: cambiarlo a mano recalcula el Margen (%) equivalente — ver *Anticipos en liquidación por venta*. |
| **Margen importe** | *(solo liquidación por venta)* `Importe vendido - Importe proveedor` |
| **Importe facturado (neto)** | *(solo liquidación por venta)* Facturas de proveedor posteadas menos abonos posteados que referencian este lote. |
| **Kg facturados (neto)** | *(solo facturación firme)* Kg de líneas marcadas `mercas_is_firm_line` en facturas de proveedor posteadas menos en abonos posteados. |
| **Facturado** | Ver arriba. Editable manualmente. |
| **Facturación firme** | Ver *Dos regímenes de facturación a proveedor*. Editable solo por Gestor de contabilidad y solo antes de tener facturación en firme. |

#### Campo Completado y Facturable

El campo booleano **Completado** (`completed`, almacenado) se activa automáticamente cuando `product_qty ≤ 0`.

El campo booleano **Facturable** (`invoiceable`, almacenado) unifica el criterio de entrada a la facturación de proveedor para ambos regímenes: `False` si ya está `invoiced`; si no, hay importe bruto de liquidación pendiente sobre lo vendido/desechado en liquidación por venta (con o sin stock — ver *Anticipos*), o `Kg recibidos > Kg facturados` en facturación firme.

#### Pestañas de trazabilidad

El formulario incluye pestañas con las líneas de compra, venta, facturas de proveedor, facturas de cliente y desechos asociados al lote, cada una con cantidad y subtotal totalizados al pie de la lista.

#### Facturación de lotes a proveedor

El asistente (**Mercas > Liquidaciones**, ver *El asistente de liquidación: tres botones*) y el botón **Facturar lote** en el formulario individual llaman a `action_create_supplier_invoices`, que trata ambos regímenes en una misma pasada según el `mercas_firm_negotiation` de cada lote. No hay acción de facturación masiva desde la vista lista de lotes.

1. Filtra los lotes: `invoiceable = True` y con proveedor asignado.
2. Agrupa por proveedor y crea **una factura por proveedor** (puede mezclar lotes de ambos regímenes en el mismo documento). Por cada lote:
   - **Facturación firme**: una línea con cantidad = saldo pendiente (`Kg recibidos - Kg facturados en firme`) y precio = el de la línea de compra de origen (marcada `mercas_is_firm_line`), más, si es la primera factura en firme del lote y queda algo de liquidación por venta sin reconciliar, una línea de descuento (ver *Paso de liquidación por venta a facturación firme*).
   - **Liquidación por venta**: una línea con el importe bruto de liquidación (final si `completed`, estimado por anticipo si no — ver *Anticipos*), más una línea a precio 0 por el desecho si el **Modo de liquidación** de la empresa es "Precio medio + desecho aparte" y el lote tiene algo desechado, más, si hay facturas/abonos previos posteados de este lote, una línea de descuento por cada uno.
   - Todas las líneas de un lote llevan descripción compuesta por el nombre del producto y, en segunda línea, `DD/MM/YYYY | Ref.pedido | Ref.proveedor | Núm.lote` (las de descuento llevan su propia referencia).
3. Actualiza el coste (`purchase_price`) en las líneas de venta relacionadas de los lotes de liquidación por venta ya **completados** (no en anticipos, para no propagar un coste todavía estimado), si el módulo `sale_margin` está instalado.
4. Confirma la factura automáticamente si **Confirmar factura proveedor automáticamente** está activo en la empresa — en cuyo caso `invoiced` se recalcula de inmediato (ver arriba); si no, se recalculará cuando alguien la postee manualmente.

El asistente de liquidación (**Mercas > Liquidaciones**) muestra, además de las columnas de venta/margen, la facturación firme, kg recibidos/facturados y el importe a facturar de cada lote (calculado según su régimen), y permite marcar **Mostrar todos** para ver también lotes aún no facturables.

#### Vista lista y búsqueda de lotes

- Columnas adicionales: **Proveedor**, **Tipo de compra** (informativo, oculta por defecto), **Facturación firme**, **Completado**, **Facturable** y **Facturado** (todas opcionales salvo las tres últimas).
- Filtros: **No facturados**, **Facturables** (cubre ambos regímenes), **Completado**, **Facturación firme**.
- Agrupación por **Proveedor**.
- Búsqueda por **Proveedor** como primera opción en la barra de búsqueda.

#### Corregir lote de una línea de venta, servida o pendiente

Si al vender se asigna por error el lote equivocado, el botón **Corregir lote** (icono junto al campo *Lote* en las líneas de pedido de venta, y también en la pestaña **Ventas** del formulario del lote) abre un asistente (`stock.lot.change.wizard`) que corrige, de una vez. Funciona **tanto si el albarán ya está validado como si todavía está pendiente de servir** (basta con que la línea de albarán ya tenga un lote asignado en la reserva, algo que ocurre automáticamente al confirmar el pedido gracias a `sale_order_lot_selection`): el icono aparece en cuanto hay un lote que corregir, no hace falta esperar a la entrega. Corregir antes de servir reasigna también la reserva de existencias (Odoo libera la cantidad reservada del lote antiguo y reserva la del nuevo automáticamente).

1. El lote de cada línea de albarán ligada a esa línea de venta (`stock.move.line.lot_id`), validada o pendiente — es lo que realmente recalcula `Kg vendidos`/`Importe vendido` (y por tanto la liquidación) de los dos lotes implicados una vez servida. Una línea de venta puede tener varias entregas (parciales/backorders); el asistente las lista todas y cada una se corrige por separado.
2. El campo **Lote** de la propia línea de venta.
3. El lote en la línea de la factura de cliente correspondiente, **solo si sigue en borrador** (no afecta importes, así que no hay problema en tocarla; si ya está contabilizada, no se toca).
4. `stock.move.restrict_lot_id` del movimiento de cada línea de albarán corregida, **solo si el módulo OCA `stock_restrict_lot` está instalado** (comprobación por `_fields`, sin dependencia dura).

El asistente no necesita tocar `stock.quant` a mano: escribir `lot_id` sobre una línea de albarán ya es suficiente en los dos casos, porque es comportamiento **nativo** de `stock.move.line.write()` (no código de `mercas_base`).

- Si la línea **ya está validada** (`done`), Odoo deshace el efecto físico del lote antiguo en origen y destino y aplica el del nuevo automáticamente — así que las existencias físicas por lote quedan también corregidas.
- Si la línea **todavía está pendiente de servir**, Odoo resincroniza la cantidad *reservada* del lote antiguo al nuevo (libera la reserva del uno, reserva el otro): no hay stock físico que mover todavía.

Deja constancia del cambio en el chatter de los dos lotes implicados (origen y destino).

**No permitido si la liquidación por venta ya está facturada por completo**: si el lote de origen o el de destino están en régimen de liquidación por venta (`mercas_firm_negotiation = False`) y tienen `invoiced = True`, el asistente rechaza el cambio — corregir a estas alturas descuadraría una liquidación ya cerrada; hace falta una corrección contable manual aparte. Un anticipo facturado (`net_invoiced_amount`/`net_invoiced_kg` > 0 sin `invoiced = True`) **no bloquea**, porque la liquidación final todavía no está fijada. Los lotes en **facturación firme** tampoco bloquean aunque estén `invoiced = True`, porque ese importe es responsabilidad nuestra frente al proveedor y no depende de a qué venta se atribuya el lote.

Solo visible/ejecutable para el grupo **Mercas: Corregir lotes** (`mercas_base.group_correct_lots`); es un grupo aparte del de Contabilidad, pensado para quien gestione la trazabilidad (p. ej. un responsable de almacén), no necesariamente con acceso a Ventas o Contabilidad — la escritura del lote de la línea de venta y de la factura de cliente en borrador se hace internamente con permisos elevados para no obligar a dar esos accesos aparte.

### Contactos — Resumen de cajas

Cuando un contacto ya tiene ubicación de stock propia como cliente y/o como proveedor (ver *Ventas — Ubicación por cliente* y *Compras — Ubicación por proveedor*), su ficha muestra un smart button **Cajas** con la cantidad total de envases presentes en esas ubicaciones. Solo se tienen en cuenta:

- Las ubicaciones dedicadas del contacto (`property_stock_customer` / `property_stock_supplier`); si alguna de ellas todavía es la ubicación genérica configurada en la empresa (es decir, el contacto nunca ha comprado o vendido nada), se ignora.
- Los productos marcados como caja/envase (`product.is_box`).

El botón permanece oculto solo si el contacto no tiene ubicación dedicada o no hay ningún producto marcado como caja/envase (`mercas_has_box_location`); se muestra igualmente aunque las existencias actuales sean cero. Al pulsarlo se abre un listado de `stock.quant` agrupado por producto y ubicación.

Junto a él hay siempre dos botones más, sin depender de que el contacto tenga ya ubicación propia:

- **Entregar cajas** (`action_mercas_open_box_delivery`): abre un pedido de venta nuevo con este contacto como cliente — mismo destino final que el botón **Entrega cajas** de un pedido de compra, pero sin partir de una compra concreta.
- **Devolver cajas** (`action_mercas_open_box_return`): abre un pedido de compra nuevo con este contacto como proveedor — mismo destino final que el botón **Devolución cajas** de un pedido de venta, pero sin partir de una venta concreta.

Ambos exigen que exista al menos un producto marcado como caja/envase (mismo guard que los botones de compra/venta); el pedido se crea vacío y el usuario añade las líneas de caja a mano.

## Parametrización (Empresa > pestaña Mercas)

### Almacén
| Campo | Descripción |
|---|---|
| **Almacén clientes** | Ubicación padre bajo la que se crean las sub-ubicaciones por cliente. Por defecto: `stock.stock_location_customers`. |
| **Almacén proveedores** | Ubicación padre bajo la que se crean las sub-ubicaciones por proveedor. Por defecto: `stock.stock_location_suppliers`. |

### Compras
| Campo | Descripción |
|---|---|
| **Purchase lot auto** | Activa la creación automática de lotes al confirmar pedidos de compra. |
| **Columna país origen** | Muestra la columna de país de origen en las líneas de pedido de compra. |
| **Columna provincia origen** | Muestra la columna de provincia de origen en las líneas de pedido de compra. |
| **Filtro origen** | Restringe la selección de país/provincia a los marcados como Origen Mercas. |

### Contabilidad
| Campo | Descripción |
|---|---|
| **Diario de compensación** | Diario de tipo "Operaciones varias" para los asientos de compensación. |
| **Margen Mercas (%)** | Margen general aplicado a los lotes cuando el partner no tiene margen propio. |
| **Confirmar factura proveedor automáticamente** | Si está activo, las facturas de liquidación de lotes se confirman al generarse. |
| **Modo de liquidación** | "Precio medio (una línea)" o "Precio medio + desecho aparte". Solo afecta a lotes en liquidación por venta (no a facturación firme) — ver *Anticipos en liquidación por venta*. |
| **Detalle de ventas en factura** | Si está activo, añade a la descripción de la línea de venta un desglose acumulado (fecha, pedido, cantidad, precio) de cada venta del lote, y a la línea de desecho (modo "desecho aparte") un desglose acumulado (fecha, cantidad) de cada regularización. Solo texto informativo — ver *Anticipos en liquidación por venta*. |

## Menú Mercas

El módulo crea un menú raíz **Mercas** con accesos directos a las pantallas estándar más usadas y a las específicas del módulo, en este orden: **Ventas · Compras · Contactos · Productos · Lotes · Facturas · Liquidaciones**.

| Menú | Contenido |
|---|---|
| **Ventas** / **Compras** | Pedidos de venta / de compra (acciones estándar de Odoo). |
| **Contactos** | Contactos (acción estándar). |
| **Productos** | Plantillas de producto (acción estándar). Incluye el filtro **Cajas** en la vista de búsqueda (`is_box = True`) para localizar los productos marcados como caja/envase. |
| **Lotes** | Lista de lotes de stock, filtrada por defecto a los no facturados. |
| **Facturas** | **Facturas de cliente**, **Facturas rectificativas**, **Facturas de proveedor** y **Reembolsos** — mismas etiquetas que usa el estándar de Odoo para estas acciones. |
| **Liquidaciones** | Asistente de facturación de lotes a proveedor. Visible solo para el grupo **Contabilidad/Gestor de contabilidad** (`account.group_account_manager`). |

## Instalación

El `post_init_hook` activa automáticamente, como si un usuario marcase las casillas en *Inventario > Configuración > Ajustes*, las opciones: ubicaciones de almacenamiento, números de serie y lote, variantes de producto, unidades de medida y embalajes, y firma en las órdenes de entrega. No requiere configuración manual adicional tras instalar el módulo.

## Dependencias

### Odoo
- `purchase`
- `stock`
- `account`
- `sale_stock`
- `contacts`
- `bus` — aviso en tiempo real de edición concurrente en pedidos de venta
- `product` — asistente de impresión de etiquetas (reutiliza `product.label.layout`)

### OCA
- `purchase_lot` — campo `lot_id` en líneas de pedido de compra
- `sale_order_lot_selection` — selección de lote en líneas de venta

### OCA opcionales
- `sale_financial_risk` — control de riesgo financiero en ventas
- `account_financial_risk` — cálculo de riesgo financiero por partner
- `stock_restrict_lot` — si está instalado, el asistente de corrección de lote también actualiza `stock.move.restrict_lot_id` al corregir

### Odoo opcionales
- `sale_margin` — actualización del precio de coste en líneas de venta al generar facturas de lote

## Compatibilidad

Odoo **19.0 Community**
