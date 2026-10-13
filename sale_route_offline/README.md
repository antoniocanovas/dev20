# Preventa en ruta sin conexión (`sale_route_offline`)

Aplicación de tablet para los comerciales de preventa que visitan a sus clientes, a menudo sin cobertura. Sin conexión permite:

- Consultar los clientes de la ruta: deuda vencida y no vencida, límite de crédito, facturas pendientes y últimos pedidos (con su estado, el estado de la factura y las fechas de entrega).
- Hacer pedidos a partir de los productos habituales de cada cliente, añadir otros desde un catálogo con imágenes y categorías, y escribir un texto en cada línea.
- Revisar el pedido y guardarlo como presupuesto o confirmarlo. También se pueden modificar los presupuestos que ya existían, incluidos los hechos en el backend.
- Registrar cobros, con o sin las facturas que pagan.

Al recuperar la conexión, todo se sincroniza solo y se crean los `sale.order` y `account.payment` reales.

La aplicación se llama *Ruta de venta* y aparece en la pantalla de inicio de Odoo. Su dirección es `/odoo/route-sales`.

Depende de `sale` y `account`. Funciona en Odoo 20 Community y Enterprise.

## Requisitos

- **HTTPS.** El navegador solo guarda y cifra los datos sin conexión en un contexto seguro: HTTPS, o `localhost` en el propio ordenador. Con HTTP la pantalla funciona mientras hay conexión, pero un pedido o un cobro hecho sin conexión da error.
- **Odoo instalado como aplicación (PWA)** en la tablet, para que arranque sin cobertura. Se instala desde la propia pantalla (el botón de descarga, arriba a la derecha), desde el menú de usuario (*Instalar aplicación*) o, en iPad, con *Compartir → Añadir a pantalla de inicio*.
  - Se instala **Odoo entero** (`/odoo`), no solo esta pantalla: el arranque sin conexión de Odoo solo cubre las direcciones `/odoo/...`.
  - Una pulsación larga sobre el icono instalado ofrece el acceso directo *Ruta de venta*.
- **Permisos:** el comercial necesita el permiso de Ventas *Usuario: solo sus documentos* o superior. Ve los clientes en cuya ficha figura como *Comercial* (empresas, sin sus contactos).

### Probar desde una tablet en la red local

Odoo 20 solo escucha en `127.0.0.1` por defecto. Para entrar desde la tablet:

1. En el fichero de configuración, poner `http_interface = 0.0.0.0` y reiniciar Odoo.
2. Entrar por la IP del ordenador, por ejemplo `http://192.168.1.42:8069`.
3. Para que funcione sin conexión hace falta HTTPS. Para pruebas, en una tablet Android con Chrome se puede marcar esa dirección como segura en `chrome://flags/#unsafely-treat-insecure-origin-as-secure`. Para uso real, poner delante un proxy con HTTPS y activar `proxy_mode = True`.

Con `http_interface = 0.0.0.0`, cualquiera de la red llega a Odoo, incluido el gestor de bases de datos: conviene que `admin_passwd` sea robusta.

## Configuración

En *Ajustes → Ventas → Ruta de venta*:

- **Pedidos recientes por cliente** que se cargan en la tablet (5 por defecto).
- **Diarios de cobro en ruta.** Si se deja vacío, valen todos los diarios de banco y de caja de la compañía.

Para editar el descuento en la tablet hay que activar *Descuentos* en *Ajustes → Ventas*. Sin esa opción no se muestra, y el servidor aplica el descuento de la tarifa.

## Uso

### 1. Preparar la ruta (cada mañana, con conexión)

Abrir *Ruta de venta* y pulsar **Preparar ruta**. Se descarga lo necesario para trabajar sin conexión:

- Los clientes, con su deuda, sus facturas pendientes y sus últimos pedidos.
- Los productos habituales de cada cliente (los del último año), con su precio de tarifa, el descuento y la cantidad media.
- Un catálogo de hasta 500 productos con sus categorías e imágenes. Las imágenes quedan en la caché del navegador; si falta alguna, el catálogo funciona igual, sin ella.
- Los diarios de cobro.

La pantalla muestra cuándo se preparó la ruta y avisa si es de otro día o tiene más de 12 horas.

### 2. En la ficha del cliente

- **Deuda:** vencida, no vencida y límite de crédito, resaltados si hay deuda vencida o se supera el límite.
- **Pedidos de hoy:** los hechos hoy en la tablet, con su estado (*Presupuesto* o *Confirmado*) y si están *Pendientes de conexión*. Un presupuesto se puede **revisar**, cambiar y confirmar; un pedido confirmado solo se puede ver.
- **Facturas pendientes:** las vencidas, resaltadas.
- **Últimos pedidos:** número, fecha, estado, estado de la factura, *Fecha de entrega* (la efectiva si ya se entregó; si no, la prometida o la prevista), *Entrega prometida* y total. Al tocar un pedido se ven sus líneas. Los presupuestos tienen el botón **Modificar**.

### 3. Hacer un pedido

1. **Nuevo pedido** parte de los productos habituales del cliente. *Cantidades habituales* las rellena todas de una vez; con **+/−** o tecleando se ajusta cada una.
2. **Catálogo** añade otros productos: por categoría (panel a la izquierda, o desplegable en pantallas pequeñas) o buscando por nombre o código. Al tocar una ficha se añade una unidad. Un producto añadido desde el catálogo sale del pedido al bajarlo a 0.
3. **Texto de la línea:** el botón de nota de cada línea abre un campo de texto (hasta 500 caracteres). En el pedido de venta queda en la descripción de la línea, debajo de la descripción del producto.
4. **Revisar pedido** muestra las líneas, sus textos, los subtotales y el total orientativo, y avisa si el cliente tiene deuda vencida o supera su límite. Desde ahí:
   - **Modificar** vuelve al pedido.
   - **Guardar presupuesto** lo guarda sin confirmar.
   - **Confirmar pedido** lo confirma.

El total es orientativo (cantidad × precio × (1 − descuento) + impuestos): el servidor recalcula precios, impuestos y totales.

**Modificar un presupuesto** de *Últimos pedidos*, también uno hecho en el backend, lo abre en el mismo editor: sus líneas (con sus textos) y, debajo, los productos habituales que no lleve. Al guardarlo:
- Solo cambian las líneas de producto. Se conservan las secciones y notas, y el precio de las líneas que se mantienen.
- La descripción de una línea solo cambia si se ha modificado su texto en la tablet.
- La tablet edita la versión descargada al preparar la ruta: si alguien cambió las líneas en el backend después, la versión de la tablet las sustituye.

### 4. Registrar un cobro

**Registrar cobro**: facturas que paga (opcional; al marcarlas se propone su importe), importe, diario y concepto. El cobro llega al servidor **en borrador**.

### 5. Sin conexión

Todo funciona igual. Lo que se guarda o confirma sin conexión queda en la tablet como *Pendiente de conexión* y aparece en el menú de sincronización de la barra superior. Al recuperar la conexión se envía solo, en el orden en que se hizo. Si un presupuesto pendiente se confirma o se vuelve a cambiar, solo se envía su última versión.

Cada vez que un pedido o un cobro llega al servidor, ya sea al momento o al vaciarse la cola, la pantalla vuelve a descargar los datos de la ruta en segundo plano. Así los últimos pedidos, la deuda y las facturas quedan al día, también en la copia que se usa sin conexión. Mientras no llegan al servidor, un cobro hecho sin conexión no descuenta la deuda en la tablet.

## Administración

- **Cobros:** en *Facturación → Pagos*, el filtro **Cobros de ruta** (junto con *Borrador*) muestra los cobros de la tablet pendientes de revisar. Al **confirmar** uno, se concilia solo con las facturas que eligió el comercial: quedan pagadas, o parcialmente pagadas si el importe no llega. Lo que sobra queda como crédito pendiente del cliente. Los pagos creados en el backend se comportan como siempre.
- **Pedidos:** los de la tablet son pedidos de venta normales, con el comercial como vendedor. En modo desarrollador, el formulario del pedido y del pago muestra su *Identificador sin conexión*.

## Errores de sincronización

Si un envío falla (por ejemplo, un producto que ya no se vende), aparece **en rojo** en el menú de sincronización, con el motivo, y **no se reintenta solo**.

- **Un pedido:** reabrirlo en *Pedidos de hoy*, corregirlo y guardarlo otra vez. La nueva versión sustituye a la que falló.
- **Un cobro:** en la ficha del cliente, copiarlo con el botón de copiar, descartarlo con la papelera del menú de sincronización y volver a registrarlo.

Enviar dos veces lo mismo no lo duplica. Cada pedido y cada cobro llevan un identificador único (`offline_uuid`), y cada versión de un pedido un número (`offline_revision`): el servidor aplica cada versión una sola vez y descarta las que lleguen tarde.

## Notas técnicas

- **Reutiliza el modo sin conexión de `web`** mediante su API pública: `OfflinePlugin.isOffline()`, `syncingORM()`, `scheduleORM()` y `orm.cache({type: "disk", update: "always"})`. No se modifica ningún módulo del núcleo.
- **Con conexión, la llamada se hace directamente** y solo se encola si se pierde la conexión (`ConnectionLostError`). El plugin no tiene una forma pública de sincronizar al momento, y así los errores de validación se ven con el formulario abierto.
- **Métodos del servidor:**
  - `res.partner.get_route_data()`: toda la ruta del comercial, sin argumentos, para que siempre lea la misma entrada de la caché.
  - `res.partner.get_route_sync_status(uuids)`: qué versión de cada pedido o cobro tiene el servidor.
  - `sale.order.save_from_tablet(vals)`: crea o actualiza un pedido y lo confirma si se pide. `create_from_tablet` se mantiene para llamadas encoladas por la primera versión.
  - `account.payment.create_from_tablet(vals)`: crea el cobro en borrador.
- **Permisos:** los comerciales no tienen acceso a los pagos, ni a todas las facturas o al límite de crédito. El servidor lee la deuda, las facturas pendientes y el límite de sus clientes, y crea el pago en borrador como superusuario, siempre después de validar lo que envía la tablet. El comercial queda como creador del pago.
- **Catálogo propio:** el estándar de las líneas de venta no funciona sin conexión, porque necesita el pedido guardado en el servidor y hace una llamada por cada cambio. La pantalla tiene un catálogo con el mismo aspecto que usa los datos de la ruta preparada.
- **Bandeja de sincronización:** el módulo extiende la plantilla `web.OfflineSystray`, que falla con métodos que no son de las vistas (`save_from_tablet`, `create_from_tablet`).
- **Diario local:** la tablet guarda en `localStorage` los pedidos del día y lo pendiente de enviar, porque el plugin no permite listar su cola. Esos datos no van cifrados, igual que la cola del propio plugin.

## Tests

- **Python:** idempotencia y versiones de los pedidos, confirmación, edición de presupuestos del backend, texto de las líneas, cobros (validación, permisos y conciliación al confirmar), contenido de `get_route_data` y acceso directo del manifiesto.
- **Hoot:** flujo con y sin conexión (encolar, sustituir en la cola y sincronizar), revisión y confirmación, catálogo (escritorio y móvil), últimos pedidos, texto de las líneas, refresco de los datos e instalación.

```
odoo-bin -c odoo20.conf -d <bd> -i sale_route_offline --test-tags /sale_route_offline --stop-after-init
```

Los tests de hoot necesitan Chrome y el paquete de Python `websocket-client`; sin él, Odoo los salta.
