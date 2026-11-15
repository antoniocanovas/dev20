# GAIA en los albaranes (`scrap_gaia`)

GAIA es el organismo oficial al que se informa del material vendido y reciclado según su composición: kg de férreo, de plástico, de neumáticos... Este módulo calcula esos kg en cada albarán de salida, a partir del peso de los productos y de su porcentaje de cada material. Se pueden corregir a mano y se imprimen en el albarán. Cada periodo, normalmente un mes, se crea un informe con los albaranes de salida y sus kg, que se descarga en PDF y Excel y queda registrado como presentado.

Depende de `scrap_base`, por las plantillas desguace y el tipo de desguace de los productos, y de `sale_stock`, por el menú de informes de Ventas. Funciona en Odoo 20 Community y Enterprise.

## Materiales

**Inventario → Configuración → Productos → Materiales GAIA** (responsables de inventario). La lista se ordena arrastrando las filas, y un material que ya no se usa se archiva.

El módulo instala los que se usan ahora:

- Férreo
- No férreo
- Metales
- Plástico
- Neumáticos

## En el producto

Pestaña **GAIA** en la ficha del producto y de la variante; no sale en servicios ni combos:

- **Peso**: el mismo campo que en la pestaña *Inventario*. Se puede cambiar en cualquiera de las dos.
- **Líneas de materiales**:
  - **Material**, cada uno una sola vez por producto;
  - **Estimado (%)**, entre 0 y 100, con su total al pie;
  - **Peso**: los kg de ese material según el peso del producto.
- Los porcentajes no pueden ser negativos ni sumar más de 100 %. Lo que falte hasta 100 % no se informa a GAIA.

### Desde la plantilla desguace

Un producto creado desde una plantilla desguace (*Plantilla de vehículo*) recibe **el peso y las líneas de la plantilla**. Pasa con:

- los vehículos creados al confirmar una compra;
- los subproductos desmontados de una plantilla, como el motor;
- un producto creado a mano con la plantilla ya puesta.

Si al crearlo ya trae su peso o sus líneas, se quedan las suyas.

Después todo es editable en el producto, sin que cambie la plantilla. Si se cambia la plantilla a mano, el peso y las líneas pasan a ser los de la nueva plantilla: se ve en la ficha en cuanto se elige, antes de guardar. Volver a poner la misma plantilla no cambia nada. Las líneas también se pueden crear a mano en cualquier producto.

## En el albarán de salida

Pestaña **GAIA** en los albaranes de salida:

- **Solo los productos con tipo de desguace** (*Vehículo o Parte para desguace*, *Subproducto*, *Para compra/venta*, *Otros finales desguazados*). Un producto que solo se compra y se vende, como una lata de aceite nueva, no cuenta aunque tenga peso y materiales.
- **Una línea por material**, con sus kg: la suma, en esos productos del albarán, de *peso × cantidad × %*. Usa la cantidad pedida de cada movimiento, en la unidad del producto, y deja fuera los cancelados.
- **Editable**: los kg se pueden cambiar y se pueden añadir o quitar líneas.
- **Cuándo se recalcula**: al añadir o quitar productos o cambiar sus cantidades. No se recalcula al validar el albarán ni al cambiar después el peso o los porcentajes de un producto, así que lo corregido a mano se mantiene.
- **Calcular desde los productos**: vuelve a calcularlo con los datos actuales de los productos y pierde lo escrito a mano; pide confirmación.
- **Avisos**: en amarillo, los productos almacenables con tipo de desguace sin peso o sin materiales GAIA.

Las entradas y los albaranes internos no se calculan; la pestaña solo sale en las salidas.

### Impresión

El **albarán de entrega** (*Imprimir → Albarán de entrega*) añade, tras los productos, una tabla **Material GAIA / Peso** con las líneas que tienen kg y el total.

## Informe periódico

**Ventas → Informes → Informes GAIA** (responsables de ventas o de inventario). Cada informe queda guardado, con su estado, como registro de lo presentado.

- **Periodo**: *Desde* y *Hasta*. Al crear uno nuevo se propone el mes siguiente al último informe o, si no hay ninguno, el mes pasado. Puede ser de cualquier duración, pero **los periodos de una compañía no pueden solaparse**.
- **Nombre**: *GAIA 2026-10* si es un mes natural; si no, *GAIA desde / hasta*. Se puede cambiar.
- **Qué recoge**: **solo los albaranes de salida validados** de la compañía con fecha de validación en el periodo, en la zona horaria del usuario, y que lleven algún producto con tipo de desguace. No entran entradas, internos ni devoluciones de cliente, ni salidas solo con productos sin tipo de desguace.
- **Calcular**: guarda en el informe los albaranes y los kg de cada material **tal como están escritos en cada albarán**, incluidas las correcciones a mano. Desde ese momento, lo que cambie en los albaranes no cambia el informe hasta que se pulse *Volver a calcular*.
- **Pestañas**: *Peso por material*, con el total; *Peso por albarán*, con fecha, albarán, cliente, material y kg; *Notas*, por ejemplo para el justificante de la presentación. El botón *Albaranes* abre los albaranes incluidos.
- **PDF**: periodo, estado, peso por material con el total, una fila por albarán con los kg de cada material, y los movimientos (fecha, albarán, producto, cantidad y peso).
- **Excel**: tres hojas, *Resumen*, *Albaranes* (una columna por material) y *Movimientos*.
- **Marcar como presentado**: guarda la fecha de presentación y bloquea el informe; no se puede cambiar, recalcular ni borrar, salvo las notas. El PDF de un informe presentado se guarda como adjunto, y se vuelve a imprimir tal como se presentó.
- **Volver a borrador**: para corregirlo y presentarlo de nuevo. Los cambios de estado quedan en el historial.

## Pruebas

`tests/test_scrap_gaia.py`:

- los materiales instalados;
- un vehículo copiado de su plantilla, con su peso y sus líneas, editables sin cambiar la plantilla;
- un producto creado con la plantilla, con y sin peso y líneas propios;
- el cambio de plantilla, por escrito y en la ficha;
- el límite de los porcentajes;
- el albarán de salida:
  - el cálculo y los avisos;
  - el recálculo al cambiar una cantidad;
  - lo escrito a mano, que se mantiene al validar y al cambiar el producto;
  - la tabla en el albarán impreso;
  - el botón para recalcular;
- una entrada, que no se calcula;
- un producto sin tipo de desguace (una lata de aceite nueva), que no cuenta ni avisa.

`tests/test_scrap_gaia_report.py`:

- los periodos: mes por defecto tras el último, nombre, solape, fechas al revés, otra compañía;
- el informe: solo los albaranes de salida con productos con tipo de desguace, el límite del periodo en la zona horaria, los kg corregidos a mano, el PDF, el Excel, el bloqueo al presentarlo y volver a borrador;
- no se puede presentar sin calcular.
