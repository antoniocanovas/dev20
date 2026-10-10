# Meat Cutting Sale

Venta por pieza completa para `meat_cutting`: se pide en piezas y se factura el peso real entregado a precio por kilo. Depende de `meat_cutting` y `sale_stock`, y se instala solo cuando están los dos.

## Venta

- **Por peso:** la línea en kg.
- **Por pieza entera:** la línea en el embalaje "Pieza completa (…)" del producto.
  - El precio de la línea es el del peso medio; por ejemplo, 4,5 kg × 7,90 €/kg = 35,55 € por pieza.
  - La previsión usa ese peso estimado. La entrega reserva piezas enteras, un paquete por pieza, pese lo que pese (ver `meat_cutting`).
  - La entrega se da por completa con el número de piezas pedido, sin pedido pendiente por la diferencia de peso (lo hace `meat_cutting`).
- **Presentación** (fileteado, troceado, envasado al vacío…): atributo sin variantes con sobreprecio por kg, que se suma al de la pieza; por ejemplo, fileteado (+1,20 €/kg): 4,5 × 9,10 = 40,95 €. El almacén lo ve en el albarán. Es funcionalidad estándar de Odoo; este módulo no la cambia.

## Factura

Con la política *Cantidades entregadas*, las líneas vendidas en un embalaje del producto se facturan **en la unidad del producto (kg reales) a precio por kilo**, sin redondear a fracciones de pieza. Por ejemplo, una pieza pedida de 4,5 kg que pesa 4,63 kg: 4,63 kg × 7,90 €/kg = 36,58 €.

En el pedido, las cantidades entregada y facturada siguen en piezas, pero la cantidad a facturar se calcula en kg para que no queden restos por redondeo. Las devoluciones generan el abono por el peso devuelto.

Las líneas pedidas en la unidad del producto, o facturadas por cantidades pedidas, se facturan como siempre.

## Configuración

Además de la de `meat_cutting`, en cada corte que se venda por pieza:

1. Precio de venta en €/kg.
2. Embalaje "Pieza completa" con el peso medio.
3. Política de facturación *Cantidades entregadas*.

Para las presentaciones: un atributo con *Crear variantes: Nunca* y sobreprecio por valor.

## Tests

```bash
odoo-bin -c odoo.conf -d test_db -i meat_cutting_sale --test-tags /meat_cutting_sale --stop-after-init
```

## Limitaciones conocidas

- **Presupuestos y pedidos por pieza.** Muestran el importe estimado; la factura, el real.
