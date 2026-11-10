# Pantalla táctil de desguace (`scrap_touch`)

Pantalla para el reciclaje de vehículos, pensada para tablet o pantalla táctil. Reúne en una aplicación las tareas del desguace, cada una con su tecla de función:

- **F1 · Entrada para desguace:** compra de los vehículos de un proveedor para desmontarlos, cada uno con su matrícula, y su recepción en el mismo paso o más tarde.
- **F2 · Entrada Compra/Venta:** lo mismo, para los vehículos que se reparan y se venden completos como usados.
- **F3 · Descontaminación:** los vehículos para desguazar recibidos y por descontaminar, el límite legal más cercano primero, para marcarlos como descontaminados.
- **F4 · Desguace:** los vehículos descontaminados por desguazar, igual, y su desmontaje pieza a pieza.
- **F5 · Vehículos:** consulta de todos los vehículos comprados, con sus plazos, ubicación y listas de materiales.

La aplicación se llama *CAT* (centro autorizado de tratamiento) y aparece en la pantalla de inicio de Odoo. Su dirección es `/odoo/scrap-touch`. Sustituye al antiguo menú CAT del backend de `scrap_base`.

Depende de `purchase_stock` y de `scrap_base`. Funciona en Odoo 20 Community y Enterprise.

## Criterio

Sigue el mismo criterio que *Mostrador* (`mercas_touch`), aunque no depende de él:

- **Tarjetas grandes y teclado numérico en pantalla**, sin formularios ni listas del backend.
- **Se guarda mientras se trabaja.** La compra en curso se guarda como petición de presupuesto en borrador con cada cambio, en segundo plano. Se puede dejar a medias y retomarla después, en el mismo puesto, en otro o desde el backend.
- **Una llamada por operación.** *Comprar* y *Comprar y recibir* son un único método del servidor que guarda las últimas líneas, valida y confirma la compra (y, en el segundo caso, valida la recepción).
- **Sin duplicados.** La compra lleva un identificador (`scrap_touch_uuid`). Si se pulsa dos veces o se reintenta tras un corte, el servidor devuelve la compra ya creada.
- **Los permisos del usuario se aplican como en el backend.** El menú lo ven los usuarios de compras y los de inventario. Las entradas (F1 y F2) salen a los usuarios de compras; descontaminación, desguace y vehículos (F3 a F5), a los de inventario, que pueden marcar los vehículos como hechos aunque no puedan modificar productos.

## Configuración

Los vehículos son productos con:

- **Plantilla desguace** marcada (campo `is_template` de `scrap_base`). No hace falta *Se puede comprar*: las plantillas solo se copian para cada vehículo, y en la demo ni se compran ni se venden.
- **Seguimiento por número de serie.** El número de serie de cada vehículo es su **matrícula**, porque el bastidor no se conoce hasta recibirlo.

Solo esos productos salen en la pantalla. `scrap_base` activa *Números de serie y lote* al instalarse.

## Uso

### Inicio

Un botón por opción, con su tecla de función. Descontaminación y Desguace muestran cuántos vehículos hay **fuera de plazo** (en rojo) y **pendientes**; se actualiza al volver al inicio. Arriba, la **cuadrícula de puntos** vuelve a Odoo y el botón de descarga **instala Odoo como aplicación** en la tablet. Dentro de cada opción, la flecha (o **Esc**) vuelve atrás.

### F1 · Entrada para desguace y F2 · Entrada Compra/Venta

Las dos funcionan igual y usan los mismos productos. Cada una pone su tipo en la compra (campo *Tipo desguace* de `scrap_base`): la entrada para desguace, *Vehículo o Parte para desguace* (`main`); la de compra/venta, *Para compra/venta* (`refurbish`). Cada opción lista solo las compras de su tipo, y una compra no cambia de tipo desde la pantalla.

**1. Lista de compras.** Al entrar se ven las compras, la última modificada primero, con su proveedor, número de vehículos, importe, fecha y usuario. Se buscan por número de compra, proveedor o matrícula. Hay cuatro filtros, y uno más en compra/venta:

- **En curso** (por defecto): las compras en borrador hechas desde la pantalla.
- **Para recibir:** las confirmadas con la recepción pendiente.
- **Para facturar:** las confirmadas que aún no están facturadas del todo.
- **Todos:** cualquier compra salvo las canceladas, con su estado.
- **En venta** (solo en *Entrada Compra/Venta*, en otro color): los vehículos para reparar y vender que están **en stock**, como tarjetas igual que en Vehículos. El buscador también los filtra (por matrícula, nombre, referencia, bastidor o marca/modelo). Al tocar uno se abre su resumen, y **Volver a la lista** (o la flecha atrás) vuelve a los vehículos en venta.

Las compras hechas en el backend salen en la opción de su *Tipo desguace*; sin tipo no salen en ninguna.

Al tocar una compra en borrador se sigue con ella (paso 3). Al tocar una confirmada se abre su **resumen**: estado, recepción y facturación, vehículos con su matrícula, albarán y facturas. Desde ahí:

- **Recibir**, si falta recibir: valida la recepción, cada vehículo con su matrícula como número de serie.
- **Crear factura**, si falta facturar: crea la factura del proveedor en borrador y la abre en un diálogo para revisarla.
- Tocando una factura se abre para consultarla o terminarla.
- **Abrir** muestra la compra y **Volver a la lista** (o la flecha atrás) vuelve a la lista con el mismo filtro.

**Nueva compra** empieza una compra nueva: pide el proveedor (paso 2).

**2. Proveedor** (en una compra nueva). Se busca por nombre, referencia, NIF o teléfono; salen primero los proveedores con más compras. **Nuevo**, junto al buscador, da de alta un proveedor en un formulario corto (nombre, NIF, teléfono, correo y dirección), con el nombre ya escrito en el buscador; al guardar, la compra sigue con él. Se ve solo si el usuario puede crear contactos (*Creación de contactos*, que Odoo da por defecto a los usuarios internos). Empresa o persona lo decide Odoo según el NIF.

**3. Vehículos.** A la izquierda, los productos en tarjetas (por categoría si hay varias, o buscando por nombre o referencia). A la derecha, el **ticket** con los vehículos de la compra y el total.

Al tocar un producto se abre la línea, con la **matrícula** y el **precio** (con el teclado numérico, el del dispositivo o un teclado físico; puede ser 0). **Añadir** la pasa al ticket. La matrícula se guarda en mayúsculas y sin espacios ni guiones: «1234 abc», «1234-ABC» y «1234ABC» son la misma.

Tocando un vehículo del ticket se modifica, con **Actualizar línea**; la papelera de la línea lo quita. Arriba del ticket se ve si la compra está guardada.

La flecha atrás vuelve a la lista de borradores sin perder nada. La papelera del ticket **cancela la compra**, tras confirmarlo.

**4. Comprar o Comprar y recibir.** Al confirmar, `scrap_base` convierte cada línea en un vehículo: un producto propio copiado de la plantilla, con su matrícula, su cuenta analítica y su ubicación con el nombre de la matrícula (ver su README).

- **Comprar** confirma la compra. La recepción queda pendiente para cuando lleguen los vehículos, con la matrícula de cada uno ya puesta como número de serie: al recibirlos en el backend no hay que teclearla.
- **Comprar y recibir** confirma la compra y valida la recepción en el mismo paso, cada vehículo con su matrícula como número de serie y en su ubicación.

Al terminar se ven la compra, el albarán y los vehículos con su matrícula, su referencia interna (si ya se recibieron y hay secuencia en la pestaña CAT de la compañía) y su ubicación, con **Recibir** si se compró sin recibir y **Crear factura** cuando ya se puede facturar. **Abrir** muestra la compra y **Nueva compra** empieza otra del mismo proveedor.

### F3 · Descontaminación, F4 · Desguace y F5 · Vehículos

Funcionan como las listas de compras: buscador, filtros, tarjetas y, al tocar una, su resumen. Los plazos y fechas son los de `scrap_base` (días de la pestaña CAT de la compañía, contados desde la fecha de baja, que es la de recepción).

**1. Lista.** Se busca por matrícula, nombre, referencia interna, bastidor o marca/modelo.

- **Descontaminación:** los vehículos para desguazar ya recibidos. Filtros **Pendientes** (por defecto, el límite más cercano primero), **Fuera de plazo**, **Descontaminados** (el último primero) y **Todos**.
- **Desguace:** igual, con los ya descontaminados: **Pendientes**, **Fuera de plazo**, **Desguazados** y **Todos**. Después, en otro color, **Subproductos**: los que tienen lista de materiales. Son los productos propios que salieron de una plantilla al desguazar (por ejemplo, un motor) y los comprados en *Entrada para desguace* con una plantilla de subproducto (el *Motor usado* de la demo), estos una vez recibidos. Salen primero los que faltan por desguazar. Se buscan también por la matrícula o la referencia de su origen. La tarjeta muestra la matrícula del origen (o la suya, si se compró) y si está por desguazar o desguazado. Se desguazan igual que un vehículo, pero sin descontaminación ni plazos: el resumen muestra su **origen** y solo la etapa de desguace. Las piezas de un motor comprado tienen ese motor como origen.
- **Vehículos:** todos los vehículos creados desde plantillas, el último primero. Filtros **En stock** (por defecto), **Para desguazar**, **Compra/Venta** y **Todos**.

Cada tarjeta muestra el vehículo, su referencia, matrícula y marca/modelo, y su plazo: en rojo los días de retraso, en naranja si vence en 3 días o menos, en verde con la fecha si ya está hecho. En Vehículos, su estado (por recibir, recibido, descontaminado, desguazado o en stock) y su tipo.

**2. Resumen del vehículo:** matrícula, referencia, marca/modelo, plantilla, tipo, bastidor, ubicación, compra y proveedor, fecha de baja y sus listas de materiales (componentes y operaciones). En los vehículos para desguazar recibidos, una tarjeta por etapa (la de la opción abierta, resaltada) con su límite legal y:

- Descontaminación: **Descontaminar**, que abre la pantalla de descontaminación (debajo, cuántos residuos se han marcado). Ya descontaminado, **Residuos** muestra lo marcado.
- Desguace: **Desguazar**, que abre la pantalla de desmontaje (debajo, cuántas piezas quedan y cuántas se han marcado). Ya desguazado, **Piezas** muestra lo marcado.
- **Deshacer**, si se marcó por error, tras confirmarlo. La descontaminación no se deshace si ya está desguazado. Deshacer el desguace no deshace las piezas marcadas ni su stock.

Solo se desguaza un vehículo ya descontaminado. **Abrir** muestra la ficha del producto y **Volver a la lista** (o la flecha atrás) vuelve con el mismo filtro.

**3. Descontaminación.** Con el mismo estilo que el desmontaje, pero las tarjetas son los **productos de desecho** de la compañía (pestaña CAT de la compañía), siempre disponibles. Al tocar uno:

- **Cantidad**, la que se retire (admite decimales, por ejemplo litros de aceite): se escribe con el teclado del equipo (el campo queda listo para escribir al elegir el residuo; Intro confirma) o con el teclado numérico de la pantalla.
- **Desechado** o **No existe**.
- **Ubicación de destino** de lo desechado, por defecto la *Zona de desecho* de la compañía; **Cambiar** abre el buscador de ubicaciones internas.
- **Confirmar.** Lo desechado entra en stock en su destino (es un producto normal: solo se incrementa su stock); lo que no existe no mueve stock.

Se puede repetir tantas veces como haga falta. Debajo, **Residuos marcados**: mientras el vehículo no esté marcado como descontaminado, cada línea se puede **Editar** (se abre en el panel de la derecha, resaltada en la lista, para cambiar la cantidad, el resultado o la ubicación; **Actualizar** devuelve su stock y lo vuelve a dar de entrada con los nuevos datos) o **Eliminar** (tras confirmarlo, su stock vuelve). Una vez descontaminado ya no se puede cambiar: hay que deshacer antes la descontaminación desde el resumen. Se termina con **Descontaminado hoy** o con una fecha y **En esta fecha** (no posterior a hoy ni anterior a la baja); a partir de ahí no se puede marcar más.

**4. Desmontaje.** Las tarjetas son los componentes que quedan por desmontar de las listas de materiales del vehículo, con la cantidad pendiente y su operación. Al tocar una, a la derecha:

- **Cantidad**, con − y +, si queda más de una (por defecto, 1).
- **Una sola fila de opciones**, de un toque: el estado de la pieza desmontada (**Excelente**, **Buen estado**, **Media vida** o **Funcional**), **No existe** o **Desechado**.
- **Ubicación de destino** de la pieza desmontada, por defecto la del vehículo; **Cambiar** abre un buscador de las ubicaciones internas de la compañía.
- **Confirmar.** La cantidad se descuenta de la lista de materiales del vehículo, que así guarda lo que queda por desmontar (la línea se queda a 0). Lo desmontado entra en stock en su destino, desde la ubicación de producción; lo desechado va a la ubicación de desecho; lo que no existe no mueve stock. Si el componente es una **plantilla desguace** (por ejemplo, un motor que se despiezará después), cada unidad desmontada se convierte en un producto propio, copia de la plantilla, como los vehículos comprados: con el nombre de la plantilla y la referencia del vehículo, su marca/modelo y las listas de materiales de la plantilla. Si no lo es, se incrementa el stock del propio componente. La copia de una plantilla *Subproducto* también es subproducto, con su **origen**, y si tiene lista de materiales aparece en Desguace → **Subproductos** para desguazarla después; la plantilla deja de estar pendiente y no recibe stock. Las reglas completas están en el README de `scrap_base` (*Reglas del desmontaje de cada componente*). Los componentes con lote o número de serie reciben uno nuevo, a partir de la referencia del vehículo.

Debajo, **Piezas marcadas**: en un vehículo también salen las de sus subproductos, con el subproducto debajo del nombre de la pieza; esas se deshacen desde el subproducto. Para cada pieza: cantidad, pieza, resultado, estado, destino, fecha y operario, con **Deshacer** para una pieza marcada por error (tras confirmarlo): su stock vuelve a donde estaba (lo desmontado tiene que seguir en su destino, con su lote; si ya se movió, no se puede deshacer), el producto creado de una plantilla se archiva, la cantidad vuelve a estar por desmontar y, si el vehículo estaba desguazado, deja de estarlo. El desguace se **termina solo** cuando no queda nada por desmontar, con la fecha de hoy; también se puede terminar antes con **Desguazado hoy** o con una fecha y **En esta fecha**. **Volver al vehículo** (o la flecha atrás) vuelve al resumen.

### Comprobaciones

- Una matrícula pertenece a un solo vehículo: no se puede usar si ya la tiene otro vehículo comprado (aunque sea de otra plantilla) o recibido, ni estar en dos líneas de la misma compra. Se comprueba al guardar cada cambio y otra vez al comprar, por si otra compra la usó mientras tanto. Si se cancela la compra de un vehículo sin recibir, su matrícula queda libre.
- Solo se admiten productos marcados como *Plantilla desguace* y con seguimiento por número de serie (aunque no estén marcados como *Se puede comprar*).
- El proveedor y el tipo de una compra no se pueden cambiar desde la pantalla.

En el backend, las líneas de la compra muestran la columna **Matrícula** (de `scrap_base`). La factura del proveedor se crea desde el resumen de la compra en la pantalla, o desde la compra en el backend, como cualquier otra.

## Actualización

- **20.0.1.1.0:** las compras hechas antes desde la pantalla, que no tenían tipo, pasan a *Vehículo o Parte para desguace*.
- **20.0.1.2.0:** la matrícula de las líneas pasa al campo de `scrap_base`; las ya guardadas se copian. Las compras confirmadas antes siguen con el producto plantilla: solo las nuevas crean un producto por vehículo.
- **20.0.1.3.0:** filtro **Subproductos** en Desguace (los datos los migra `scrap_base`).

## Pruebas

```
odoo-bin -c odoo20.conf -d <bd> -i scrap_touch --test-tags /scrap_touch --stop-after-init
```

El recorrido de la pantalla (`test_ui`) necesita Chrome y la librería `websocket-client`. Sin ella, Odoo lo salta con un aviso.
