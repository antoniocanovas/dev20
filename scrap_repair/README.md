# Reparación de vehículos de compra/venta (`scrap_repair`)

Reparación (módulo *Reparaciones* de Odoo) de los vehículos comprados para repararlos y venderlos completos (*Para compra/venta*). Sus costes y, si el vehículo ya está vendido, también sus ingresos van a la **cuenta analítica del vehículo**.

Depende de `scrap_touch` y de `repair`. Ojo: `repair` instala también `sale_management` (Ventas), porque Odoo lo exige.

## Uso

En la pantalla táctil, en el resumen de un vehículo de compra/venta (desde *Entrada Compra/Venta → En venta* o desde *Vehículos*), hay un botón **Reparar** antes de *Volver a la lista*:

- Abre en un diálogo la **orden de reparación** del vehículo que aún no está hecha o, si no hay ninguna, crea una nueva. El botón muestra la referencia de la reparación abierta, para no duplicarlas.
- **Vehículo en stock** (lo reparamos para venderlo): la reparación no tiene cliente, el vehículo se repara en su ubicación y con su número de serie (la matrícula).
- **Vehículo ya vendido** (no está en stock y tiene una entrega hecha a un cliente): la reparación es de ese cliente, en su ubicación de cliente.
- Si no está en stock ni vendido (por ejemplo, por recibir) o no es de compra/venta, no se puede reparar: el botón no sale.

En la orden de reparación se añaden las **piezas** y los **servicios** (mano de obra...) como en Odoo, se confirma y se termina.

## Analítica

- **Piezas:** al terminar la reparación, su consumo (a su valor de stock) se imputa a la cuenta analítica del vehículo como gasto; una pieza retirada del vehículo al stock, como recuperación. Las líneas las crea este módulo al terminar la reparación, no el movimiento de stock, porque con Proyecto instalado (`project_stock_account`) Odoo solo las crea para algunos tipos de operación.
- **Servicios:** al terminar, su coste (precio de coste del servicio por la cantidad) se imputa también a esa cuenta.
- **Ingresos** (vehículo vendido): las líneas del presupuesto de venta de la reparación y las de su factura (creada desde la reparación o desde el presupuesto) llevan la cuenta analítica del vehículo.

Así la cuenta del vehículo reúne su compra, sus reparaciones y su venta.

## Pruebas

```
odoo-bin -c odoo20com.conf -d <bd> -i scrap_repair --test-tags /scrap_repair --stop-after-init
```
