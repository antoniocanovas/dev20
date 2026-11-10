# Base del reciclaje de vehículos (`scrap_base`)

Datos comunes del vertical de reciclaje de vehículos, que usan los demás módulos `scrap_*`.

Depende de `purchase_stock`, `account`, `fleet` (por los modelos de vehículo) y `mrp` (por las listas de materiales de despiece). Funciona en Odoo 20 Community y Enterprise.

## Qué añade

- **Plantilla desguace** (`is_template`) en el producto: una casilla en la ficha, junto a *Se puede comprar*. Marca los productos que sirven de plantilla en el desguace, como los vehículos que se compran para desmontar. En el listado de productos hay un filtro **Plantillas desguace**, y en la vista kanban de productos y de variantes llevan una cinta **Plantilla**.

- **Tipo desguace** (`unbuild_type`) en la compra, con las mismas opciones que el campo del producto de `scrap_unbuild` en Odoo 17:
  - *Vehículo o Parte para desguace* (`main`): vehículos para desmontar.
  - *Subproducto* (`subproduct`).
  - *Para compra/venta* (`refurbish`): vehículos para reparar y vender completos.
  - *Otros finales desguazados* (`other`).

  Se ve en el formulario de la compra (editable mientras está en presupuesto), como columna en los listados de compras y en el buscador, con los filtros *Para desguace* y *Para compra/venta* y la agrupación por tipo.
- **Pestaña CAT** en la compañía, con la configuración de cada tipo de entrada de vehículos (*Vehículo o Parte para desguace* y *Para compra/venta*):
  - **Plan analítico**: donde se crea la cuenta analítica de cada vehículo. Al instalar se crean los planes *Vehículos para desguazar* y *Vehículos compra / venta* y se ponen en cada compañía.
  - **Ubicación**: la ubicación padre de las ubicaciones de los vehículos. Al instalar se crean *Para desguazar* y *Compra / Venta* dentro del stock del primer almacén de cada compañía. Las compañías nuevas también las reciben.
  - **Secuencia**: la de las referencias internas de los vehículos recibidos. No se crea por defecto; sin ella no se asigna referencia.

  Y, para la descontaminación:
  - **Zona de desecho** (`scrap_waste_location_id`): donde entran por defecto los residuos que se retiran al descontaminar. Al instalar (o actualizar a la 20.0.1.2.0) se crea *Zona de desecho* dentro del stock del primer almacén de cada compañía, como las otras.
  - **Productos de desecho** (`scrap_waste_product_ids`): los residuos que se retiran de los vehículos al descontaminarlos (aceite, combustible, baterías...). Son productos normales de Odoo, no plantillas: al retirarlos solo se incrementa su stock.

- **Tipo desguace del producto** (`scrap_unbuild_type`), visible en **todos los productos** (también los combos y en la ficha de la variante): en la pestaña *Información general*, debajo de la categoría, con las mismas opciones que el de la compra. También es columna opcional, visible por defecto, de los listados de productos y variantes, y en el buscador se puede agrupar por él. Las plantillas desguace lo llevan según lo que se compra con ellas (para desguazar o subproducto); los vehículos reciben el de su compra.

- **Pestaña CAT en el producto**, la primera de la ficha, visible solo en los productos con *Tipo desguace*. Tiene el mismo diseño que la de `scrap_unbuild` en Odoo 17: los campos en la columna izquierda (datos CAT, vehículo y plazos legales) y la **imagen principal** del producto, en grande, a la derecha (la misma de la cabecera de la ficha, que no cambia). Debajo, las piezas marcadas y los textos. Lleva los datos de los vehículos y sus piezas, los mismos campos que `custom_product` en Odoo 17:
  - *Marca/Modelo* (`vehicle_model_id`): modelo de vehículo de Flota.
  - *Marca del vehículo* (`scrap_vehicle_brand_id`): la marca (fabricante) de ese modelo, guardada para buscar, filtrar y agrupar los vehículos y sus piezas por marca. Es la misma marca de Flota que usan las oportunidades de `scrap_crm`. No es el fabricante de la pieza (Valeo, Bosch...): ese, si hace falta, va en *Ref. visible* y *Referencias*. En el buscador hay además un filtro **En stock**.
  - *Placa* (`plate`): para los subproductos; no es la matrícula del vehículo (`scrap_lot_name`). No se copia al duplicar el producto.
  - *Ref. visible* (`ref_market`): la referencia escrita o troquelada en la pieza.
  - *Ref. OEM* (`ref_oem`): la referencia del fabricante del vehículo.
  - *Usos del producto* (`uses`) y *Referencias* (`references`), textos libres.
  - *Bastidor* (`chassis`): se guarda en cada variante (`product.product`). Si el producto no tiene variantes, se escribe y se ve en la plantilla y pasa a su única variante, como la referencia interna de Odoo; si las tiene, la plantilla no lo muestra y cada variante tiene el suyo, en su propio formulario. No se copia al duplicar.

  **Búsqueda:** un producto se encuentra también por su bastidor, placa, Ref. OEM, Ref. visible y referencias, tanto en el buscador de productos y variantes como al escribir en cualquier campo de producto (líneas de compra, venta, albaranes...). En estos campos salen primero las coincidencias por referencia interna, código de barras y nombre, y después las de los datos CAT.

  **Bastidor repetido:** si se escribe un bastidor que ya tiene otro producto (aunque esté archivado), Odoo avisa con el producto que lo tiene, como con la referencia interna. Es solo un aviso: se puede guardar.

  En los productos que no son plantilla, la misma pestaña muestra además la **plantilla del vehículo** y, si la tienen, la matrícula, la **cuenta analítica** y la **ubicación original** (la creada para el vehículo). Los responsables de productos pueden cambiarlos.

  **Vehículos creados a mano en el backend.** Lo recomendable es que todo vehículo entre por una compra, aunque sea a 0 € (por ejemplo, el que entrega un particular), porque crea todo lo necesario y deja rastro. Para corregir o completar un vehículo creado a mano: se pone su tipo desguace (*Vehículo o Parte para desguace* o *Para compra/venta*; con él aparece la pestaña CAT), su plantilla del vehículo y su matrícula, y el botón **Completar datos CAT** crea lo que le falte, igual que al confirmar la compra: la cuenta analítica y la ubicación con la matrícula como nombre, en el plan y la ubicación de su tipo, su distribución analítica y, si no tiene ninguna, las listas de materiales de su plantilla. Si el producto no tenía compañía, recibe la actual. Comprueba que la matrícula no la tenga otro vehículo y que no tenga variantes. Recibido después por cualquier compra, entra en su ubicación con su matrícula y, si es para desguazar, recibe su fecha de baja.

- **Un producto por vehículo.** Al confirmar una compra de tipo *Vehículo o Parte para desguace* o *Para compra/venta*, cada línea con un producto *Plantilla desguace* se convierte en un vehículo:
  - Se **duplica la plantilla** en un producto nuevo, con el nombre de la plantilla y la matrícula, *Plantilla desguace* desmarcada, la **matrícula** (`scrap_lot_name`), la **plantilla de origen** (`scrap_template_id`) y como **coste** el precio de la línea (en la moneda de la compañía, impuestos no incluidos y con descuento).
  - Se crea su **cuenta analítica**, con la matrícula como nombre, en el plan de su tipo, y una **distribución analítica** para el producto: la compra, su factura y cualquier otra factura del vehículo (por ejemplo, su venta) van a esa cuenta.
  - Se crea su **ubicación**, con la matrícula como nombre, dentro de la ubicación de su tipo.
  - La línea de la compra pasa al producto nuevo, con su cuenta analítica, y así el albarán y la factura. Al recibirlo, el vehículo entra en su ubicación con la matrícula como **número de serie**.
  - Se copian las **listas de materiales** de la plantilla (las de su compañía o sin compañía), con sus componentes y **operaciones**: cómo se despieza el vehículo (volante, ruedas, motor...). Cada vehículo tiene así las suyas, que se podrán cambiar sin tocar las de la plantilla; servirán para los desmontajes (*unbuild*), que se desarrollarán después.
  - Hereda de la plantilla la marca/modelo, los usos y las referencias. El producto del vehículo muestra estos datos en su pestaña **CAT**, y en el buscador de productos (y de variantes) hay un filtro **Vehículos**, se puede buscar por **Plantilla del vehículo** (escribiendo el nombre de la plantilla) y agrupar por ella.

  Para confirmar, cada vehículo va en su propia línea, con cantidad 1 y su matrícula (columna **Matrícula** de las líneas de la compra, que se guarda en mayúsculas y sin espacios ni guiones). No puede haber dos vehículos activos con la misma matrícula, ni la plantilla puede tener variantes. Las compras de otros tipos, o sin tipo, y los productos que no son plantilla no cambian.

  Si se **cancela** la compra, los vehículos que no llegaron a recibirse devuelven la línea a su plantilla, con su matrícula, y se archivan junto con su ubicación y su cuenta analítica, y se borra su distribución analítica. Así la matrícula se puede volver a comprar.

- **Plazos legales de los vehículos para desguazar** (como `scrap_unbuild` en Odoo 17, con los mismos nombres de campo):
  - En la pestaña CAT de la compañía, los **días de descontaminación** (`decontamination_days`) y los **días de desguace** (`scrap_days`), contados desde la fecha de baja. Sin días no hay fecha límite.
  - En el producto (pestaña CAT, salvo en las plantillas desguace): **fecha de baja** (`discharge_date`), que se pone sola al validar su recepción (se puede corregir); **Descontaminar** y **Desguazar** (los límites legales), calculados con los días de la compañía del vehículo, y que se recalculan si cambian; y **Descontaminado el** y **Desguazado el** (`decontamination_date`, `scrap_date`). Las etiquetas son cortas, para que quepan en una línea; la explicación está en la ayuda de cada campo.
  - Cada vehículo guarda su **tipo desguace** (`scrap_unbuild_type`), el de su compra, y su compañía. Se puede corregir en *Información general*. Los de compra/venta se marcan como *Se puede vender*, aunque su plantilla no se venda.
  - Comprobaciones: no se descontamina antes de la fecha de baja ni se desguaza antes de descontaminar.

- **Residuos de la descontaminación** (en el mismo modelo que las piezas desmontadas, con la etapa *Descontaminación*): cada vez que el operario retira un producto de desecho de la compañía, *Desechado* (la cantidad que sea, que entra en stock desde la ubicación de producción en la zona de desecho o en otra ubicación interna) o *No existe* (sin movimiento). Se puede hacer tantas veces como haga falta y, mientras el vehículo no esté marcado como descontaminado, cada residuo se puede corregir (cantidad, resultado y ubicación: su stock vuelve y entra de nuevo) o eliminar (su stock vuelve). Una vez descontaminado ya no se puede cambiar, salvo que antes se deshaga la descontaminación.
- **Piezas desmontadas** (`scrap.dismantle.line`): cada componente de la lista de materiales de un vehículo que el operario marca al desguazarlo: *Desmontado* (con su estado: *Excelente*, *Buen estado*, *Media vida* o *Funcional*, y su ubicación de destino, por defecto la del vehículo), *No existe* o *Desechado*. La cantidad se descuenta de la lista de materiales del vehículo (la línea se queda a 0), que así guarda lo que queda por desmontar. Lo desmontado entra en stock desde la ubicación de producción; si el componente es una plantilla desguace, cada unidad se convierte en un producto propio (copia de la plantilla, con el nombre de la plantilla y la referencia del vehículo, su marca/modelo y las listas de materiales de la plantilla); si no, se incrementa el stock del componente. Lo desechado va a la ubicación de desecho de la compañía y lo que no existe no mueve stock. Cuando no queda nada por desmontar, el vehículo queda desguazado con la fecha de hoy. Una pieza marcada por error se **deshace**: su stock vuelve con un movimiento inverso (lo desmontado tiene que seguir en su destino, con su lote), el producto creado de una plantilla se archiva, la cantidad vuelve a la lista de materiales, la pieza se borra y, si el vehículo estaba desguazado, deja de estarlo. Se ven en la pestaña CAT del vehículo (usuarios de inventario); los responsables de inventario las pueden modificar.
- **Reglas del desmontaje de cada componente** (al marcarlo como *Desmontado*):
  - **No es plantilla** (una rueda, una batería...): se incrementa el stock del propio componente, en la ubicación de destino, sin crear ningún producto.
  - **Es plantilla desguace** (un motor, una puerta...): por cada unidad se **duplica la plantilla** en un producto nuevo, que recibe el **origen** (`scrap_origin_id`), su propia lista de materiales (copia de la de la plantilla) y **una unidad de stock** en la ubicación de destino. La plantilla no recibe stock.
  - **Se puede vender:** la copia se crea siempre con *Se puede vender* marcado, aunque la plantilla no se venda.
  - **Tipo de la copia:** si la plantilla es *Subproducto*, la copia también lo es. Una plantilla *Vehículo o Parte para desguace*, o sin tipo, también da subproducto. Las de *Para compra/venta* u *Otros finales desguazados* conservan su tipo.
  - **Lista de materiales:** en los dos casos, la cantidad se descuenta de la línea. Cuando llega a 0, el componente **desaparece de lo pendiente por desmontar**, aunque lo que haya quedado en stock sea su copia. La línea se queda en la lista a 0 para guardar el histórico y para poder deshacer.
  - **No existe** o **Desechado** no crean copia: lo desechado del componente va a la ubicación de desecho y lo que no existe no mueve stock.
  - **Lista para desguazar:** un subproducto desmontado aparece en la pantalla táctil, en Desguace → **Subproductos**, si su plantilla tenía lista de materiales (es decir, si tiene algo que desmontar). Una copia sin lista de materiales (por ejemplo, una puerta) es un subproducto en stock, pero no sale en esa lista.
- **Subproductos y origen.** Un **subproducto** (`subproduct`) es un producto propio hecho de una plantilla. Hay dos formas de tenerlo:
  - **Desmontado:** al desmontar una plantilla (por ejemplo, el motor de un vehículo). Una plantilla *para desguace* también da subproducto, porque no se recibe.
  - **Comprado:** en una compra *Vehículo o Parte para desguace* con una plantilla de tipo *Subproducto* (por ejemplo, el *Motor usado* de la demo). Se crea como los vehículos, con su matrícula (o identificador), su cuenta analítica y su ubicación, pero sigue siendo subproducto. Al recibirlo recibe su fecha de baja, sin plazos legales ni descontaminación.

  Cada subproducto desmontado guarda su **origen** (`scrap_origin_id`): lo primero que se desmontó, es decir, el vehículo o el subproducto comprado. Se mantiene aunque se desmonte de otro subproducto (vehículo → motor → culata: la culata tiene como origen el vehículo; motor comprado → culata: la culata tiene como origen el motor). Lo comprado no tiene origen. El subproducto desmontado hereda la ubicación y la cuenta analítica de su origen, con su distribución analítica, así que sus ventas van al origen. Se llama como la plantilla más la referencia (o matrícula) del origen.

  Un subproducto **se desguaza igual que un vehículo**, pero sin descontaminar y sin plazos legales; el comprado, solo después de recibirlo. Cuando no queda nada, o a mano, recibe su *Desguazado el*. Cada pieza marcada guarda también el origen (`origin_id` en `scrap.dismantle.line`). Por eso la pestaña CAT del vehículo, o del subproducto comprado, muestra **todas sus piezas**, también las de sus subproductos (columna *Desguazado de*), y la del subproducto desmontado muestra su origen y solo sus piezas. Un subproducto no se puede deshacer mientras tenga piezas marcadas: primero hay que deshacer su desguace. Al deshacerlo se archiva y se borra su distribución analítica. En el buscador de productos hay un filtro **Subproductos** y se puede buscar por *Origen*.
- **Descontaminación, desguace y consulta de vehículos:** en la pantalla táctil (`scrap_touch`, opciones F3 a F5 de la aplicación *CAT*). Los usuarios de inventario pueden marcar los vehículos como hechos aunque no puedan modificar productos; el resto de datos del vehículo los cambian los responsables de productos.
- **Marcas y modelos de vehículo** (de Flota): los pueden leer todos los usuarios internos, para ver la marca/modelo de productos y vehículos sin ser usuarios de Flota.
- **Referencia interna de los vehículos recibidos.** Al validar la recepción, cada vehículo recibe la siguiente referencia de la secuencia de su tipo, en la **Referencia interna** de su número de serie y, si no tiene, en la del producto del vehículo. Funciona igual se reciba desde la pantalla táctil o desde el backend. Un número de serie que ya tiene referencia la conserva.
- **Ajustes activados**: al instalar o actualizar el módulo se activan *Números de serie y lote* y *Ubicaciones de almacenamiento* (Ajustes de Inventario) *Contabilidad analítica* (Ajustes de Contabilidad) y *Órdenes de trabajo* (Ajustes de Fabricación, para las operaciones de las listas de materiales), que necesitan los vehículos. Si alguien los desactiva en Ajustes, vuelven a activarse con la siguiente actualización del módulo.

## Quién lo usa

- `scrap_touch`: las entradas de la pantalla táctil ofrecen los productos marcados como plantilla, y cada una pone su tipo en la compra: *Entrada para desguace* el tipo `main` y *Entrada Compra/Venta* el tipo `refurbish`. También tiene la descontaminación, el desguace y la consulta de vehículos.

## Actualización

Al actualizar a la versión 20.0.1.1.0 se crean los planes analíticos y las ubicaciones por defecto en las compañías que no los tengan, como al instalar.

Al actualizar a la versión 20.0.1.2.0 se crea la *Zona de desecho* en las compañías que no la tengan.

Al actualizar a la versión 20.0.1.3.0, los subproductos ya desmontados reciben su origen (a partir de las piezas marcadas), su ubicación, su cuenta analítica y su distribución analítica.
