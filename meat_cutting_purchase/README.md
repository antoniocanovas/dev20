# Meat Cutting Purchase

Compra de canales para `meat_cutting`: se piden por canal y se factura el peso real recibido a precio por kilo. Depende de `meat_cutting` y `purchase_stock`, y se instala solo cuando están los dos.

## Pedido

- **Por canal:** la línea en el embalaje "Canal" del producto.
  - El precio de la línea es el del peso medio; por ejemplo, 90 kg × 2,10 €/kg = 189,00 € por canal. Odoo lo convierte desde el precio por kg del proveedor al elegir la unidad en la línea.
  - La recepción y la previsión usan ese peso estimado.
- **Por peso:** la línea en kg. Se recibe y se factura como siempre.

## Recepción

En el albarán, **Register Carcasses** (de `meat_cutting`) anota cada canal con su crotal, su peso real y los datos del animal. La recepción está completa cuando llegan las canales pedidas, pesen lo que pesen, sin pedido pendiente por los kg de diferencia.

## Factura de proveedor

Con la política de control *Cantidades recibidas*, las líneas pedidas en un embalaje del producto se facturan **en la unidad del producto (kg reales) a precio por kilo**, sin redondear a fracciones de canal. Por ejemplo, tres canales pedidas de 90 kg que pesan 268,9 kg: 268,9 kg × 2,10 €/kg = 564,69 €.

En el pedido, las cantidades recibida y facturada siguen en canales, pero la cantidad a facturar se calcula en kg para que no queden restos por redondeo. Las devoluciones al proveedor generan el abono por el peso devuelto.

Las líneas pedidas en la unidad del producto, o facturadas por cantidades pedidas, se facturan como siempre.

## Configuración

Además de la de `meat_cutting`, en cada canal que se compre por número:

1. Proveedor con el precio en €/kg.
2. Embalaje "Canal" con el peso medio.
3. *Piezas completas*, para que la recepción se complete por número de canales.
4. Política de control *Cantidades recibidas*.

## Tests

```bash
odoo-bin -c odoo.conf -d test_db -i meat_cutting_purchase --test-tags /meat_cutting_purchase --stop-after-init
```

## Limitaciones conocidas

- **Pedidos por canal.** Muestran el importe estimado; la factura, el real.
- **Crear por código una línea en canales.** Si se crea la línea con la unidad ya puesta, Odoo no convierte el precio del proveedor. En la interfaz sí se convierte, porque la unidad se elige después del producto. La demo crea la línea en kg y luego cambia la unidad.
