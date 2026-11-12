# CRM del reciclaje de vehículos (`scrap_crm`)

Peticiones de piezas de los clientes como oportunidades del CRM, con sus tareas de taller. Migrado de `crm_scrap` (Odoo 17).

Depende de `crm`, `project`, `scrap_base`, `scrap_touch` (por el aspecto de la pantalla de disponibles) y `website_sale` (por las fotos de los productos, `product.image`, que también usa la tienda online).

## La oportunidad

- **Marca** (`brand_id`): la marca (fabricante) de Flota del vehículo para el que se piden piezas, la misma que la *Marca del vehículo* de los productos (`scrap_base`). Es obligatoria.
- **Plantilla desguace** (`scrap_template_id`), debajo de *Cargo empresa*: lo que pide el cliente, como un *Motor usado*. Solo plantillas.
- **Precio de cliente o mercado** y **precio ofertado**, **horquilla de negociación**, **notas técnicas** y la **referencia del cliente**, que se antepone al nombre.
- **Tareas** del proyecto SCRAP de la compañía, con marca, categoría, producto, procesos y fecha límite con hora. Están también en el menú *Parking*.
- **Tipo de etapa** del CRM: Pendiente Gestión Comercial, Taller, Administrativa o del cliente, y Gestión positiva o negativa.

## Disponibles

El botón **Disponibles** de la oportunidad muestra cuántos vehículos y piezas de su marca hay en stock. Abre una **pantalla táctil**, con el mismo aspecto que la de CAT, de la que se vuelve a la oportunidad con la flecha. Tiene dos opciones principales, cada una con su recuento:

- **En stock:** los productos en stock, salvo las plantillas.
- **Ensamblados:** los productos en stock (vehículos, motores...) que todavía tienen la plantilla por desguazar en sus listas de materiales. Cada tarjeta dice cuántas quedan.

Las dos opciones se filtran a la vez por dos desplegables, que se ven siempre:

- **Fabricante:** viene con la marca de la oportunidad; se puede elegir otra o *Todos los fabricantes*.
- **Plantilla:** viene con la plantilla de la oportunidad. En *En stock* muestra los productos hechos de ella (las copias que salen al desguazarla, como un *Acumulador hidráulico DES…*); *Todas las plantillas* quita el filtro. En *Ensamblados* es obligatoria: sin ella no se muestra nada.

El **buscador** de arriba filtra las dos opciones por nombre, código de barras, referencia interna, *Ref. visible*, *Ref. OEM*, referencias, bastidor, placa o matrícula.

Cada tarjeta muestra el producto, su marca y modelo, la cantidad en stock, la matrícula o placa, las referencias, el tipo desguace y la ubicación. Al tocarla se abre la ficha del producto en un diálogo; el botón de su esquina inferior derecha la abre en una **pestaña nueva**, para tener varias a la vista mientras se habla con el cliente. Al tocar la **foto** de la tarjeta (con el número de fotos si tiene más de una) se abren a pantalla completa todas las del producto, las de la tienda (`website_sale`: la principal y las adicionales): se pasan deslizando, con las flechas de la pantalla o del teclado, o tocando las miniaturas; *Producto* abre la ficha, *Pestaña nueva* la abre aparte y *Cerrar* (o Escape) vuelve a la lista.

## Pruebas

```
odoo-bin -c odoo20com.conf -d <bd> -i scrap_crm --test-tags /scrap_crm --stop-after-init
```

Incluye un recorrido táctil, desde la oportunidad hasta Ensamblados y de vuelta.

- **Fecha límite (20.0.1.2.0, 2026-11-11):** quitado `datetime_deadline` (de v17). En Odoo 20 la *Fecha límite* estándar (`date_deadline`) ya es fecha y hora, y es la que usan la kanban, la lista y sus colores. El formulario de la tarea vuelve a la estándar y la lista de tareas de la oportunidad también. La migración `20.0.1.2.0/post-migrate.py` copia `datetime_deadline` a `date_deadline` donde esta está vacía; Odoo borra la columna antigua.
