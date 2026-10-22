# Mercas Demo (`mercas_demo`)

Datos de demostración y de arranque para probar `mercas_base` (y `mercas_touch`) sobre un Odoo 20 limpio. **No se instala en producción.**

## Qué crea

- **Categorías:** *Envases*, *Frutas* y *Verduras*.
- **Envases:** *Caja1* y *Caja2*, marcados como caja/envase.
- **Fruta y verdura** en kg, almacenable, con trazabilidad por lote y *Caja1* como caja por defecto:
  - **Frutas:** *Manzana*, *Pera* y *Plátano*.
  - **Verduras:** *Tomate* y *Lechuga*.
  - *Manzana* es mercancía **clasificada**: sus variantes son el *Calibre* (03, 04, 05) y la *Marca* (Granel, Sobrino, Abuelo).
  - **Manzana granel** es mercancía **a granel**: un solo producto, con un único stock, en el que la *Calidad granel* (Extra, Primera, Segunda) y el *Calibre granel* (03, 04, 05) se eligen en cada venta, sin crear variantes. Ver *Ventas — Calidad y calibre* en `mercas_base`.
- **Atributos:** *Calibre* y *Marca*, que crean variantes; *Calidad granel* y *Calibre granel*, que nunca las crean. Los de calidad y calibre llevan su **Función en Mercas**.
- **Contactos:** *Cliente1* (con el contacto *Juan Pérez*), *Cliente2*, *Proveedor1* y *Proveedor2*.

## Al instalar (`post_init_hook`)

- Activa la trazabilidad por lotes para los usuarios internos.
- Pone un **margen Mercas** del 10 % en las compañías que no tienen.
- Asigna el **diario de compensación** (el de operaciones varias).
- **Impuestos** (solo con el plan contable español, `l10n_es`): 4 % de IVA en compras y ventas de la fruta y la verdura, *Manzana granel* incluida, y 0 % en los envases.
- **Precios** de coste y de venta de la fruta, la verdura y los envases.

Los datos se cargan con `noupdate`: actualizar el módulo no sobrescribe los cambios hechos a mano.

## Dependencias

- `mercas_base`
