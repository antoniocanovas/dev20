# Mercas Demo (`mercas_demo`)

Datos de demostración y de arranque para probar `mercas_base` (y `mercas_touch`) sobre un Odoo 20 limpio. **No se instala en producción.**

## Qué crea

- **Categorías:** *Envases*, *Frutas* y *Verduras*. *Envases* no es *Mercancía de mercado*: sus productos no salen en el catálogo del mostrador táctil (las cajas se eligen aparte en cada línea).
- **Envases:** *Caja1* y *Caja2*, marcados como caja/envase, con su peso como tara de cada caja (0,5 y 0,8 kg).
- **Fruta y verdura** en kg, almacenable, con trazabilidad por lote y *Caja1* como caja por defecto:
  - **Frutas:** *Manzana*, *Pera* y *Plátano*.
  - **Verduras:** *Tomate* y *Lechuga*.
  - *Manzana* es mercancía **clasificada**: sus variantes son el *Calibre* (03, 04, 05) y la *Marca* (Granel, Sobrino, Abuelo).
  - **Manzana granel** es mercancía **a granel**: un solo producto, con un único stock, en el que la *Calidad granel* (Extra, Primera, Segunda) y el *Calibre granel* (03, 04, 05) se eligen en cada venta, sin crear variantes. Ver *Ventas — Calidad y calibre* en `mercas_base`.
- **Atributos:** *Calibre* y *Marca*, que crean variantes; *Calidad granel* y *Calibre granel*, que nunca las crean. Los de calidad y calibre llevan su **Función en Mercas**.
- **Contactos:** *Cliente1* (con el contacto *Juan Pérez*), *Cliente2*, *Proveedor1* y *Proveedor2*.
- **Palets y packing list** (ver *Palets y packing list* en `mercas_base`):
  - Envase *Europalet*, retornable como las cajas, con su peso (25 kg).
  - Tipos de palet: *Palet europeo* (1200 × 800 × 1500 mm, tara 25 kg, retornable con *Europalet*, numerado `PAL…`) y *Palet desechable* (1200 × 800 × 1200 mm, tara 15 kg, numerado `PALD…`).
  - Un presupuesto de *Cliente1* con referencia **Demo palets**, pesado en báscula (**bruto**; el neto, la cantidad, es bruto − cajas × peso de la caja): *Tomate* 163,5 kg brutos en 15 *Caja2* (tara 12 kg, neto 151,5 kg), *Pera* 85,3 kg en 8 *Caja1* (tara 4, neto 81,3) y *Plátano* 66,2 kg en 6 *Caja2* (tara 4,8, neto 61,4), repartidos en un *Palet europeo* (10 cajas de tomate y 8 de pera) y un *Palet desechable* (5 de tomate y 6 de plátano, con 1100 mm de altura). Para que se pueda vender en el momento, antes se compra y se recibe a *Proveedor1* (*Comprar y Recibir*), también por peso bruto, la mercancía con sus lotes: *DEMO-TOMATE* 218,4 kg brutos en 20 *Caja2* (neto 202,4), *DEMO-PERA* 106,2 kg en 10 *Caja1* (neto 101,2) y *DEMO-PLATANO* 109,6 kg en 10 *Caja2* (neto 101,6), y 5 *Europalet*; el presupuesto lleva ya esos lotes. El pedido, el albarán, la factura y el packing list muestran cajas, bruto, tara y neto (ver *Pesos: bruto, tara y neto* en `mercas_base`). Con *Vender y Entregar* cada palet queda como un paquete del albarán, y el *Packing list* se imprime desde el pedido (o desde *Imprimir* antes de venderlo).

## Al instalar (`post_init_hook`)

- Activa la trazabilidad por lotes para los usuarios internos.
- Pone un **margen Mercas** del 10 % en las compañías que no tienen.
- Asigna el **diario de compensación** (el de operaciones varias).
- **Impuestos** (solo con el plan contable español, `l10n_es`): 4 % de IVA en compras y ventas de la fruta y la verdura, *Manzana granel* incluida, y 0 % en los envases.
- **Precios** de coste y de venta de la fruta, la verdura y los envases.
- Compra y recibe la mercancía de los palets y crea el presupuesto **Demo palets** con sus lotes y palets, con los pesos brutos de la báscula en las líneas.

Los datos se cargan con `noupdate`: actualizar el módulo no sobrescribe los cambios hechos a mano.

## Dependencias

- `mercas_base`
