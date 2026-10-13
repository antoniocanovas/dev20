# Preventa en ruta sin conexión (`sale_route_offline`)

Pantalla de tablet para los comerciales de preventa. Funciona sin cobertura:

- Consultar los clientes de la ruta con su deuda (vencida y no vencida), su límite de crédito, sus facturas pendientes y sus últimos pedidos.
- Crear pedidos a partir de los productos habituales de cada cliente y añadir otros desde un catálogo con imágenes y categorías, con un total orientativo.
- Revisar el pedido y guardarlo como presupuesto o confirmarlo. Los pedidos del día se pueden reabrir para cambiarlos o confirmarlos.
- Registrar cobros, con o sin las facturas que pagan.

Al recuperar la conexión, los pedidos llegan como **presupuestos** o **pedidos confirmados**, según lo que se eligiera en la tablet, y los cobros como **pagos en borrador**. El servidor recalcula los precios, los impuestos y los totales. Administración revisa los cobros (filtro *Cobros de ruta* en *Facturación → Pagos*) y los confirma: al confirmarlos se concilian solos con las facturas que eligió el comercial, que quedan pagadas, o parcialmente pagadas si el importe no llega.

Aplicación propia: *Ruta de venta* en la pantalla de inicio de Odoo. Dirección: `/odoo/route-sales`.

## Requisitos

- **HTTPS.** El navegador solo cifra y guarda los datos sin conexión en un contexto seguro. Con HTTP la pantalla funciona con conexión, pero un pedido o un cobro hecho sin conexión da error.
- **Odoo instalado como aplicación (PWA).** En la pantalla de *Ruta de venta*, el botón de descarga de arriba a la derecha instala Odoo en la tablet; también desde el menú de usuario (*Instalar aplicación*) o, en iPad, con *Compartir → Añadir a pantalla de inicio*. Una pulsación larga sobre el icono instalado ofrece el acceso directo *Ruta de venta*. Así el cliente web arranca aunque no haya cobertura. Hay que instalar **la aplicación general de Odoo** (`/odoo`), no una aplicación propia del módulo: el *service worker* de Odoo solo cubre las direcciones `/odoo/...`.
- Cada comercial ve los clientes en cuya ficha figura como *Comercial* (empresas, sin sus contactos). Necesita el permiso de Ventas *Usuario: solo sus documentos* o superior.

## Configuración

En *Ajustes → Ventas → Ruta de venta*:

- **Pedidos recientes por cliente** (5 por defecto).
- **Diarios de cobro en ruta**. Si se deja vacío, valen todos los diarios de banco y de caja de la compañía.

Para editar el descuento en la tablet hay que activar *Descuentos* en las líneas de pedido. Sin esa opción, el servidor aplica el descuento de la tarifa.

## Rutina diaria

1. **Antes de salir, con conexión:** abrir la aplicación *Ruta de venta* y pulsar **Preparar ruta**. Se descargan los clientes, la deuda, las facturas, los últimos pedidos, los productos habituales con su precio de tarifa, un catálogo de hasta 500 productos con sus imágenes y los diarios de cobro. Las imágenes quedan en la caché del navegador; si alguna falta, el catálogo funciona igual, sin ella. La pantalla muestra la hora de la última preparación y avisa si es de otro día o tiene más de 12 horas.
2. **En ruta:** en la ficha del cliente, *Nuevo pedido* parte de sus productos habituales; *Catálogo* añade otros, por categoría o buscándolos. *Revisar pedido* muestra el resumen con el total y avisa si el cliente tiene deuda vencida; desde ahí se guarda como **presupuesto** o se **confirma**. Los *Pedidos de hoy* de la ficha se pueden reabrir: un presupuesto se puede cambiar o confirmar; un pedido confirmado ya solo se puede ver.

   En *Últimos pedidos*, cada pedido muestra su estado, el estado de la factura, la fecha de entrega y la entrega prometida. Los presupuestos, también los hechos en el backend, tienen el botón *Modificar*: se editan igual que un pedido nuevo (sus líneas y después los productos habituales) y se guardan o se confirman. La tablet solo cambia las líneas de producto; las secciones y notas del presupuesto se conservan.

   Con conexión, todo se envía al momento y cualquier error se ve en el acto. Sin conexión, se guarda en la tablet y aparece como *Pendiente de conexión*.

   Cada vez que un pedido o un cobro llega al servidor, ya sea al momento o al vaciarse la cola tras recuperar la conexión, la pantalla vuelve a descargar los datos de la ruta en segundo plano. Así *Últimos pedidos*, la deuda y las facturas quedan al día, también en la copia que se usa sin conexión.
3. **Al recuperar la conexión:** se envían solos, en el orden en que se hicieron. No hay que reabrir la pantalla.

La deuda y los precios son los de la última preparación: un cobro hecho sin conexión no descuenta la deuda en la tablet hasta la siguiente preparación.

## Errores de sincronización

El menú de sincronización de la barra superior de Odoo muestra lo que queda por enviar. Si un envío falla (por ejemplo, un producto que ya no se vende), aparece **en rojo** con el motivo y **no se reintenta solo**.

- **Un pedido:** reabrirlo en *Pedidos de hoy*, corregirlo y guardarlo otra vez. La nueva versión sustituye a la que falló.
- **Un cobro:** copiarlo con el botón de copiar de la ficha del cliente, descartarlo con la papelera del menú de sincronización y volver a registrarlo.

Enviar dos veces lo mismo no lo duplica. Cada pedido y cada cobro llevan un identificador único (`offline_uuid`), y cada versión de un pedido un número (`offline_revision`): el servidor aplica cada versión una sola vez y descarta las que lleguen tarde.

## Notas técnicas

- Se reutiliza el modo sin conexión de `web` mediante su API pública: `OfflinePlugin.isOffline()`, `scheduleORM()` y `orm.cache({type: "disk", update: "always"})`. No se modifica ningún módulo del núcleo.
- Con conexión, la llamada se hace directamente y solo se encola si se pierde la conexión (`ConnectionLostError`). El motivo es que el plugin no tiene una forma pública de sincronizar al momento, y que así los errores de validación se ven con el formulario abierto.
- El módulo extiende la plantilla `web.OfflineSystray`, porque el menú de sincronización falla con métodos que no son de las vistas (`save_from_tablet`, `create_from_tablet`).
- El catálogo estándar de las líneas de venta no funciona sin conexión: necesita el pedido guardado en el servidor y hace una llamada por cada cambio. La pantalla tiene un catálogo propio con el mismo aspecto (fichas con imagen, precio y +/−, y panel de categorías) que usa los datos de la ruta preparada.
- Los comerciales no tienen acceso a los pagos ni a todas las facturas. El servidor lee la deuda y las facturas pendientes de sus clientes, y crea el pago en borrador, como superusuario, después de validar todo lo que envía la tablet. El comercial queda como creador del pago.
