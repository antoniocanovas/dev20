# Mercas Keys (`mercas_keys`)

Teclas rápidas para trabajar en el backend de Odoo con el teclado: las teclas de función abren las listas de cada tarea, **Insert** añade una línea al pedido y las flechas recorren las listas por columnas. Solo cambia la interfaz web: no tiene modelos ni datos propios.

## Uso

### Teclas de función

Desde cualquier pantalla del backend:

| Tecla | Abre | Lista |
|---|---|---|
| **F1** | Ventas | Pedidos de venta (`sale.order`), sin los cancelados |
| **F2** | Compras | Pedidos de compra (`purchase.order`), sin los cancelados |
| **F3** | Facturas | Facturas de cliente, de proveedor y abonos de cliente (`account.move`) |
| **F4** | Pagos | Pagos (`account.payment`), sin los cancelados |

Cada una abre la lista, con el formulario al entrar en un registro, como una acción nueva en la ruta de navegación. Las teclas se capturan antes que las del navegador: **F1** no abre la ayuda del navegador ni **F3** su búsqueda. Si el foco está fuera de la página (por ejemplo, en la barra de direcciones), las recibe el navegador.

Con el mostrador táctil (`mercas_touch`) abierto, sus teclas F1-F6 tienen prioridad: abren los modos del mostrador y no estas listas.

### Insert · Nueva línea

En un formulario con líneas (pedido de venta, de compra, factura…), **Insert** pulsa *Añadir una línea* de la primera lista de líneas y pone el cursor en el producto de la línea nueva.

### Flechas en las listas

- **Lista editable** (las líneas de un pedido, en edición): **↓** y **↑** guardan la línea y pasan a la misma columna de la línea siguiente o anterior.
- **Lista de solo lectura:** **↓** y **↑** pasan el foco a la misma columna de la fila siguiente o anterior, en lugar de a la primera.

En la primera o la última fila la tecla sigue con su comportamiento estándar.

### Icono de la barra superior

El icono de teclado de la barra superior despliega los mismos accesos (F1-F4 y *Nueva línea*) con su tecla al lado, para usarlos con el ratón o en una tableta.

### Pantalla de gestión

La acción cliente *Gestión* (`mercas_keys.action_mercas_unified_screen`) muestra un botón grande por modo (F1-F4). No tiene menú: se abre con la dirección `/odoo/action-mercas_keys.action_mercas_unified_screen`.

## Notas técnicas

- **Modos:** `static/src/js/mercas_modes.js` define los modos (`MODES`: tecla, nombre, modelo y dominio), la acción de cada uno (`modeAction`) y `addLineAndFocusProduct`. Los usan las tres piezas: el servicio de teclas, el icono de la barra superior y la pantalla de gestión.
- **Teclas:** el servicio `mercas_hotkeys` escucha `keydown` en `document` en fase de captura y llama a `preventDefault` para F1-F4 e Insert.
- **Nueva línea:** `addLineAndFocusProduct` pulsa el enlace de añadir línea y luego la celda del producto de la última fila: `td[name="product_id"]` o, en Odoo 20, `td[name="product_and_description"]` (el producto con su descripción en una sola columna). Depende del DOM de las vistas de Odoo: es la parte que hay que revisar en cada versión.
- **Flechas:** parche de `ListRenderer` (`onCellKeydownEditMode` y `onCellKeydown`) en `static/src/js/list_renderer_patch.js`.
- **Icono:** componente `MercasTopBar` en el registro `systray`.

## Tests

Tour `mercas_keys_tour` (`static/tests/tours/`, lanzado por `tests/test_ui.py`): abre las ventas desde la pantalla de gestión, pulsa F2 para ir a las compras y abre los pagos desde el icono de la barra superior.

```bash
odoo-bin -c odoo20.conf -d <bd> -i mercas_keys --test-tags /mercas_keys --stop-after-init
```

Necesita Chrome y el paquete de Python `websocket-client`.

## Dependencias

- `web`, `sale`, `purchase`, `account`

## Compatibilidad

Odoo **20.0** Community y Enterprise. Portado desde Odoo 19 (dev19): Owl 3, `t-out` e iconos `oi`; ver `mercas_migracion_20.md` en dev19.

## Relación con `mercas_touch`

El mostrador táctil usa las mismas teclas de función para sus propios modos, que no son listas del backend sino una pantalla completa. Está pendiente decidir si `mercas_touch` sustituye a este módulo (ver el apartado 5 de `mercas_migracion_20.md` en dev19).
