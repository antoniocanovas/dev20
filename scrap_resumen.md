# Reciclaje de vehículos (CAT) en Odoo 20: estado para retomar

Actualizado: 2026-11-10. Módulos en `dev20`: `scrap_base`, `scrap_touch` y `scrap_demo` (también `scrap_crm` e `im_riocabo`, ya cerrados). El detalle funcional de cada uno está en su `README.md`; este fichero solo dice dónde estamos.

## Hecho (con tests en verde: 54 tests, incluido el recorrido táctil)

- **Entradas F1/F2:** compra y recepción de vehículos; un producto por vehículo copiado de la plantilla (cuenta analítica, ubicación y listas de materiales propias).
- **Producto:** la pestaña CAT es la primera y solo se ve con *Tipo desguace* (`scrap_unbuild_type`, que va en *Información general*, debajo de la categoría). Hay un filtro *Plantillas desguace*.
- **Demo:** las plantillas ni se compran ni se venden. Tienen listas de materiales (Turismo, Furgoneta, Motocicleta y *Motor usado*, que es una plantilla subproducto con la lista *Despiece motor*).
- **Descontaminar (F3):** pantalla con los productos de desecho de la compañía (pestaña CAT de la compañía, junto a la *Zona de desecho*).
  - Cada residuo se marca como Desechado (cualquier cantidad, escrita con el teclado o el numérico) o No existe.
  - Su ubicación es, por defecto, la zona de desecho.
  - Cada línea se puede editar o eliminar hasta marcar el vehículo como descontaminado; después no se puede tocar sin deshacer antes la descontaminación.
  - Producto demo: *Aceite para reciclar* (en litros).
- **Desguazar (F4):** pantalla con los componentes de la lista de materiales que quedan.
  - Opciones en una fila: Excelente / Buen estado / Media vida / Funcional / No existe / Desechado. La ubicación de destino se puede cambiar.
  - Cada pieza descuenta su línea de la lista de materiales y mueve el stock al momento.
  - Un componente que es plantilla se copia en un producto propio.
  - El desguace termina solo cuando no queda nada, o con el botón.
  - **Deshacer** una pieza marcada por error.
- **Subproductos (2026-11-10):** `scrap_origin_id` en el producto (lo primero desmontado: el vehículo o el subproducto comprado, también en el 2.º nivel) y `origin_id` en la pieza. Un motor comprado en F1 con una plantilla subproducto sigue siendo subproducto, sin origen, y se desguaza una vez recibido. El subproducto desmontado hereda la ubicación y la cuenta analítica del origen y se desguaza sin descontaminar. En F4 hay un filtro **Subproductos** (color *info*), y el vehículo ve las piezas de sus subproductos. Versión 20.0.1.3.0, con una migración en `scrap_base`; 59 tests en verde. Demo 20.0.1.1.0: el motor de todos los vehículos es la plantilla subproducto *Motor usado*, la *Culata* es plantilla (segundo nivel), la Transit tiene el motor desmontado y hay un motor comprado (`MOTOR0001`); depende también de `scrap_crm`, con categorías, proyecto *Peticiones de piezas (demo)*, tipos en las etapas del CRM y 5 oportunidades con tareas.
- Modelo `scrap.dismantle.line`, con la etapa *decontamination* o *dismantling*. Sus líneas se ven en la pestaña CAT del vehículo.

## Estado de la base `cat20`

- La lanza el usuario desde PyCharm con `odoo20com.conf`. **No instalar ni reiniciar sin permiso**: el permiso no vale para cambios nuevos.
- **2026-11-10:** el usuario va a borrar cat20 y crearla de nuevo instalando `scrap_demo` (que ya trae `scrap_crm`). No hace falta migrar datos.
- **Marcas (2026-11-10):** quitados `product_brand` (borrado de dev20) y `sale_management`. La marca de la oportunidad y de la tarea (`brand_id`) es la de Flota (`fleet.vehicle.model.brand`), solo marca, sin modelo. El producto tiene `scrap_vehicle_brand_id` (guardado, de su marca/modelo) y la oportunidad un botón **Disponibles** (vehículos y piezas de su marca en stock). Fabricante de piezas nuevas: opción a, nada por ahora. Vehículos de cliente: más adelante.
- **En venta (2026-11-10):** en F2, filtro **En venta** (color *info*) después de "Todos": vehículos `refurbish` en stock como tarjetas; se abre su resumen. Filtro `on_sale` de `get_vehicles`; recorrido táctil ampliado.
- **Reparar (2026-11-10):** módulo nuevo `scrap_repair` (depende de `repair`, que trae `sale_management`). Botón **Reparar** en el resumen de los vehículos `refurbish` (en stock o vendidos): abre la reparación abierta o crea una. Piezas y servicios (a coste) y, si está vendido, ventas y factura → cuenta analítica del vehículo. 5 tests en verde. Está en las dependencias de `scrap_demo`.
- **Pestaña CAT (2026-11-10):** como en `scrap_unbuild` v17: campos a la izquierda e `image_1920` grande a la derecha (`preview_image: image_1024`, alto hasta 768 px).
- **Disponibles (2026-11-10):** el botón de la oportunidad abre una pantalla táctil (`scrap_crm.available`, modelo `scrap.crm.available`) con **En stock** (fabricante seleccionable, por defecto el de la oportunidad) y **Ensamblados** (en stock, con la plantilla de la oportunidad pendiente en sus listas de materiales). Hay buscador por nombre, código de barras y referencias. `scrap_crm` depende ahora de `scrap_touch` y tiene README, tests y recorrido.
- **Disponibles: pestañas y fotos (2026-11-10):** En stock filtra por fabricante **y** plantilla. Cada tarjeta tiene un botón en la esquina para abrir el producto en una pestaña nueva. Su foto abre un visor a pantalla completa con las fotos de la tienda (`product.image`, la principal y las adicionales). `scrap_crm` depende ahora de `website_sale` (versión 20.0.1.1.0).
- **Kanban, vendibles e imágenes (2026-11-11):**
  - Cinta **Plantilla** en las kanban de productos y de variantes (`scrap_base`).
  - La copia que se crea al desmontar una plantilla sale siempre con `sale_ok = True` (`_scrap_copy_part_template`). Los vehículos para desguazar no se venden; los subproductos comprados (motor) tampoco, salvo a mano (no hay regla automática: el usuario no la ha pedido aún).
  - `scrap_demo` pone a cada producto de la demo y a lo creado de sus plantillas una imagen de color sólido con su nombre (`_set_images` en `hooks.py`, Pillow). Lo desmontado después hereda la de su plantilla.
  - Demo: el Kit de embrague tiene a Recambios Norte como proveedor (en Odoo 20 la ruta *Comprar* es del almacén, `product_selectable=False`: no se pone en el producto). Turismo 8642KLM con `sale_ok=False`; MOTOR0001 con `sale_ok=True`.
- **Iconos:** Odoo 20 **no carga FontAwesome** en el backend (`fa fa-…` o `icon="fa-…"` salen como elipses). Usar `<i class="oi" data-icon="…"/>` o `icon="…"` con nombres de Material Symbols que Odoo ya use (subconjunto): `location_on`, `open_in_new`, `photo_camera`, `edit`, `delete`, `close`, `arrow_back`, `arrow_forward`, `inventory_2`, `build`. Ya no queda ningún `fa` en los `scrap_*`.
- **Owl 3:** refs con `signal.ref()` y `t-ref="this.x"`; efectos con `useOnChange(() => [deps], fn)` (no hay `useRef` ni `useEffect(fn, deps)` de Owl 2).
- **Cambios hechos a mano en cat20 (2026-11-11):** proveedor Recambios Norte en el Kit de embrague; Turismo 8642KLM no vendible; MOTOR0001 vendible. Copia previa: `<scratchpad de la sesión>/cat20_antes_piezas_vendibles.dump` (temporal, se pierde). cat20 aún necesita `-u scrap_base,scrap_touch,scrap_crm` y reiniciar para ver la cinta, los iconos y el visor si no se ha hecho.
- **Enterprise:** `web_enterprise` (`auto_install: ['web']`), `crm_enterprise`, `project_enterprise` y `sale_enterprise` se instalan solos si el `addons_path` incluye `20enterprise` (`odoo20.conf`). Para Community, usar `odoo20com.conf`.
- Copias: `/Users/acanovas/pycharmprojects/backups/cat20_20261108_1353.dump` y `cat20_20261108_1717.dump`. Hacer un `pg_dump` antes de tocar cat20 otra vez.

## Cómo probar

```
cd /Users/acanovas/pycharmprojects/20odoo
PYTHONPATH=<scratchpad>/pylib /Users/acanovas/pycharmprojects/venv312/bin/python odoo-bin \
  -c /Users/acanovas/pycharmprojects/conf/odoo20com.conf -d <bd_prueba> -i scrap_demo \
  --test-tags /scrap_touch,/scrap_base,/scrap_demo,/scrap_crm,/scrap_repair \
  --stop-after-init --http-port 8079 --gevent-port 8084
```

- Último resultado (2026-11-11): **71 tests, 0 fallos** (scrap_base 34, scrap_touch 37 contados con sus tours, scrap_crm 10, scrap_repair 9, scrap_demo 3).
- El tour necesita `websocket-client`. En la sesión anterior estaba en `PYTHONPATH=<scratchpad>/pylib`; si falta, instalarlo en un directorio temporal y añadirlo a `PYTHONPATH`.
- Para borrar una base de prueba, antes hay que cortar sus conexiones con `pg_terminate_backend`, porque el servidor del usuario mantiene conexiones del bus.
- **Traducciones:** se exportan con `odoo-bin i18n export ... -o <m>.pot <m>` y se rellena `i18n/es.po` (había un script `make_es_po.py` en el scratchpad que ya no existirá: rehacerlo o editar el `.po` a mano). Un `-u` no sobrescribe una traducción que ya está en la base.

## Pendiente (no empezar sin que lo pida el usuario)

- Fase de recepción.
- Órdenes de desmontaje reales (`mrp.unbuild`).
- Migración de datos desde v17. El usuario dijo «No quiero migración» de momento.
- Posibles mejoras, no pedidas: editar una pieza ya desmontada, además de deshacerla.
- Ofrecido y sin respuesta: que todo subproducto comprado para despiezar sea vendible al recibirlo (hoy solo se marcó MOTOR0001 a mano).

## Forma de trabajar

En español, por fases y con pruebas reales, resúmenes breves, sin commits y sin acciones destructivas sin permiso (ver memoria `usuario-antonio`). Los módulos `scrap_*` aún no están en git: son ficheros sin seguimiento.
