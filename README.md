# Despiece cárnico para Odoo 20

Módulos para salas de despiece. Cubren el ciclo completo:

- Se compra por canales y se recibe cada una con su crotal y su peso real.
- Se despieza en una pantalla táctil que pesa y etiqueta cada corte.
- Se vende por pieza completa o por peso, en fresco o congelado y con distintas presentaciones.
- Se sirve en cajas etiquetadas con su contenido.
- Se factura el peso real, tanto en la compra como en la venta.

Funcionan en Odoo 20 Community; no requieren Enterprise.

| Módulo | Depende de | Qué aporta |
|---|---|---|
| `meat_cutting` | `mrp`, `product_expiry`, `barcodes` | Crotales, registro de canales en la recepción, pantalla de fábrica (despiece de canales, segundo corte, preparación con presentación, elaborados, cajas y reimpresión de etiquetas, con menú principal e instalable como aplicación), etiquetas GS1-128, piezas en paquetes, fresco y congelado, etiqueta de caja con SSCC, recepciones y entregas por pieza (reserva de piezas enteras, sin pedidos pendientes) |
| `meat_cutting_sale` | `meat_cutting`, `sale_stock` | Factura en kg reales a precio por kilo las líneas vendidas en piezas. Se instala solo cuando están los dos módulos |
| `meat_cutting_purchase` | `meat_cutting`, `purchase_stock` | Factura en kg reales a precio por kilo las canales compradas por número. Se instala solo cuando están los dos módulos |
| `meat_cutting_demo` | `meat_cutting_sale`, `meat_cutting_purchase`, `sale_management` | Datos de ejemplo: canales, compras, despieces, crotales, recepciones, sesiones, ventas, cajas y formatos de etiqueta |

## Cómo se modela el producto

La regla general es **un producto por corte y estado (fresco o congelado), con el stock y el precio en kg**. La pieza entera, la presentación y la caja se montan sobre ese producto, sin catálogos paralelos.

| Necesidad | Solución |
|---|---|
| Vender por peso | Unidad de medida kg y tarifa en €/kg |
| Comprar por canales | Embalaje "Canal" con su peso medio y precio del proveedor en €/kg. Cada canal se registra al recibirla con su crotal y su peso. La factura recoge el peso real |
| Vender por pieza entera (por ejemplo, un solomillo) | Embalaje "Pieza completa" del producto, con su peso medio. Cada pieza pesada en el despiece va en su propio paquete. La factura recoge el peso real |
| Fresco y congelado | Dos productos con distinto precio y caducidad, enlazados por *Producto congelado*. Se congela al despiezar o después, desde el stock |
| Corte o envasado especial bajo pedido | Atributo "Presentación" sin variantes (*Crear variantes: Nunca*) con sobreprecio por kg. El almacén lo ve en el albarán |
| Presentación que se guarda en stock (con su caducidad o su código de barras) | Producto propio, que sale del despiece como un corte más |
| Cajas con el contenido | Paquetes anidados: las piezas van dentro de la caja, y la caja lleva una etiqueta con su contenido y un SSCC |

Opciones descartadas:

- **Variantes con stock por presentación:** multiplican el catálogo por corte, estado y presentación.
- **Productos en unidades con fabricación de transformación:** duplican el catálogo y añaden un paso por pieza.
- **La unidad "1 pieza = 1 kg":** el presupuesto sale mal.
- **La unidad secundaria de OCA:** en v20 los embalajes nativos hacen lo mismo.

## Flujo

### 1. Compra y recepción
Las canales se piden por número, en el embalaje "Canal"; el precio de la línea es el del peso medio (90 kg × 2,10 €/kg = 189,00 € por canal).

En el albarán, **Register Carcasses** anota cada canal: en la cabecera, los datos comunes de la partida (matadero, registro sanitario, fecha y orden de sacrificio, países y halal por defecto), y una fila por animal con su crotal, peso real, sexo, raza, calidad, fecha de nacimiento, países y halal. Cada canal crea su crotal y su lote, con el nombre del crotal y la caducidad contada desde el sacrificio. La recepción está completa con las canales pedidas, pesen lo que pesen; si falta una, se propone un pedido pendiente.

La factura de proveedor, con control *Cantidades recibidas*, recoge los kg reales a precio por kilo: 268,9 kg × 2,10 €/kg = 564,69 €.

Las canales se reciben con lote. El lote es el animal y puede llevar su **crotal**, con estos datos:

- Sexo, raza y calidad.
- Fechas de nacimiento y sacrificio.
- Países de nacimiento y engorde.
- Proveedor.
- Halal, con certificador y número de certificado.

Si el lote no tiene crotal, se crea uno al despiezar. Los datos del crotal se guardan también en lotes y stock, así que se puede **filtrar y agrupar el stock** por cualquiera de ellos; por ejemplo, el stock halal por país de engorde.

### 2. Pantalla de fábrica (*Meat Cutting → Cutting Screen*)
La pantalla está pensada para tablet. Empieza en un **menú principal**, como el de la aplicación Barcode:

- Arriba, la **cuadrícula de puntos** vuelve a Odoo y, a la derecha, un botón **instala la pantalla como aplicación** (PWA) en la tablet, que abre directamente este menú (ruta `/odoo/meat-cutting`). En la aplicación instalada hay un botón para cerrar sesión.
- Con el lector, **escanear una etiqueta** de pieza o de caja en el menú la abre en *Labels* para reimprimirla.
- Un botón por proceso.

Dentro de cada proceso, la cuadrícula de puntos (arriba a la izquierda) vuelve al menú, y una sesión a medias se retoma al volver a entrar. Un lector de códigos de barras funciona sin tocar antes el buscador: lo escaneado se busca como si se escribiera y se pulsara Intro. El albarán de recepción y la sesión abren directamente su proceso. El peso se escribe con el teclado del dispositivo o la báscula. Los procesos son:

- **Receipts:** despiece de las canales recibidas (abajo).
- **Cutting:** segundo corte de un paquete en stock; por ejemplo, un lomo en chuletas.
- **Preparation:** divide un paquete en varios del mismo producto, cada uno con su presentación (entera, fileteado…). Lo que sobra queda en el original. Los paquetes que se guardan en stock se pueden congelar.
- **Production:** elaborados (longanizas, morcillas…). Se indica cuánto se va a elaborar y la pantalla recomienda la cantidad de cada ingrediente según la receta. Los ingredientes se pesan de sus paquetes (se pueden escanear), hay que usarlos todos, y el producto sale en un lote nuevo que caduca con el ingrediente que caduca antes, con su presentación y, si se quiere, congelado.

Los paquetes y productos se eligen por familia (la categoría del producto), por ejemplo *Cerdo fresco* o *Elaborado congelado*.
- **Packing:** mete en cajas las piezas de una entrega, con su etiqueta resumen.
- **Labels:** reimprime una etiqueta deteriorada de una pieza o una caja, escaneándola o buscándola, con el tipo de etiqueta a elegir y sus textos editables.

Los detalles de cada uno están en el README de `meat_cutting`. El despiece de canales:

1. **Buscar.** Un buscador filtra por albarán, producto, lote o crotal.
2. **Elegir.** Se selecciona el albarán, la canal y el lote.
3. **Elegir el método de despiece.** Una canal puede tener varias listas de materiales, cada una un método distinto.
4. **Pesar.** Se escribe el peso y se pulsa el corte. Un corte se puede pesar varias veces:
   - Si el producto tiene **Piezas completas**, cada pesada es una pieza y va en su propio paquete desde ese momento. Su etiqueta ya identifica la pieza.
   - Si no, las pesadas se suman (por ejemplo, varias cajas de magro).
5. **Por cada línea se puede:**
   - Marcar **Congelar**, para producir el producto congelado.
   - **Editar la etiqueta** sin tocar el crotal.
   - Imprimir la etiqueta.
   - Borrar la línea.
6. **En la cabecera se eligen:**
   - El **formato de etiqueta**.
   - **Congelar** por defecto para las nuevas pesadas.
   - Si se imprime al pesar (*Print label*; desactivado por defecto).
7. **Terminar.** Al pulsar *Finish* se consume el lote entero de la canal (la diferencia es la merma) mediante una orden de desmontaje. Los cortes salen con su peso real, en lotes con el nombre del lote de la canal, enlazados a su crotal y con caducidad contada desde la pesada.

Solo puede haber una sesión abierta por lote. Al volver a entrar se retoma, se llegue desde el albarán o sin él.

### 3. Congelar stock fresco
El stock fresco ya cortado se congela desde:

- El lote: botón **Congelar**.
- El stock: lista de existencias, *Acción → Congelar*.

El resultado:

- La cantidad pasa al producto congelado, en la misma ubicación y el mismo paquete, por lo que la pieza sigue siendo la misma.
- El lote se llama igual que el fresco. Si ya existe un lote congelado con ese nombre, se le añade la fecha.
- Conserva el crotal.
- La caducidad congelada empieza a contar ese día.
- La trazabilidad enlaza el lote congelado con el fresco.

El stock reservado para una entrega no se puede congelar.

### 4. Venta
- **Por peso:** la línea en kg.
- **Por pieza entera:** la línea en el embalaje "Pieza completa (…)".
  - El precio de la línea es el del peso medio; por ejemplo, 4,5 kg × 7,90 €/kg = 35,55 € por pieza.
  - La previsión usa ese peso estimado. La entrega reserva piezas enteras, un paquete por pieza, pese lo que pese; lo vendido por kg se reserva por peso.
- **Presentación:** se elige en la línea y su sobreprecio por kg se suma al de la pieza; por ejemplo, fileteado (+1,20 €/kg): 4,5 × 9,10 = 40,95 €.

### 5. Preparación y cajas
1. El operario coge las piezas, que son paquetes; puede escanear su etiqueta.
2. Las mete en una caja con *Poner en paquete*, usando un tipo de paquete con **prefijo de empresa SSCC**. La caja se nombra con un SSCC.
3. Imprime la **etiqueta de caja**:
   - Desde la caja: *Imprimir → Box Label*.
   - Desde el albarán, todas sus cajas: *Imprimir → Box Labels*.

La etiqueta de caja incluye:

- Cliente, pedido y albarán.
- Por producto y lote: piezas, peso y caducidad, y el crotal si no coincide con el lote.
- Total de piezas y peso neto.
- La caducidad más próxima.
- HALAL, si toda la carne de la caja lo es.
- El código GS1-128 (00) SSCC (13) fecha de envasado.

Sigue disponible una vez entregada la caja.

Al validar, **una línea por piezas está completa cuando se ha cogido el número de piezas pedido**, pese lo que pese. La demanda se ajusta al peso real y no se propone un pedido pendiente por la diferencia. Si falta una pieza, sí se propone.

### 6. Factura
Con la política *Cantidades entregadas*, las líneas vendidas en un embalaje se facturan **en kg reales a precio por kilo**, sin redondear a fracciones de pieza. Por ejemplo: 4,88 kg × 7,90 €/kg = 38,55 €. Las devoluciones generan el abono por el peso devuelto.

## Etiquetas y códigos de barras

**Etiqueta de corte** (modelo `meat.cutting.line`). Incluye:

- Producto (el congelado se reconoce por su nombre).
- Lote, crotal, pieza y HALAL.
- Países de nacimiento y engorde, y fecha de sacrificio.
- Fechas de fabricación y caducidad.
- Origen y proveedor.
- Peso.

El código de barras es GS1-128:

| AI | Contenido |
|---|---|
| (01) | GTIN del producto (su código de barras) |
| (3103) | Peso neto en kg con 3 decimales |
| (17) | Caducidad (AAMMDD) |
| (10) | Lote (al final, por ser de longitud variable) |

Lleva FNC1 al principio y como separador tras los campos de longitud variable, así que es un GS1-128 real. Sin GTIN, la etiqueta lleva un Code 128 con el lote.

**Formatos de etiqueta.** Son informes PDF del modelo `meat.cutting.line`. Cualquiera que se añada aparece en el selector de formato de la pantalla. La demo trae dos: compacto 60×40 y caja 100×150.

## Configuración

1. **Ajustes → Inventario:** activar *Lotes y números de serie*, *Fechas de caducidad*, *Paquetes* y *Unidades de medida y embalajes*.
2. **Canal:**
   - kg, seguimiento por lote y fecha de caducidad (días desde el sacrificio).
   - Una o varias listas de materiales (métodos de despiece) cuyas líneas son los cortes.
   - Si se compra por número: *Piezas completas*, embalaje "Canal" con el peso medio, proveedor con precio en €/kg y control *Cantidades recibidas*.
3. **Cada corte:**
   - kg, seguimiento por lote y fecha de caducidad (días).
   - *Producto congelado*, si se congela.
   - *Piezas completas*, si se vende por pieza: una pesada es una pieza.
   - Embalaje "Pieza completa" con el peso medio.
   - Política de facturación *Cantidades entregadas*.
4. **Presentaciones:** atributo con *Crear variantes: Nunca*, con sobreprecio por valor.
5. **Cajas:** un tipo de paquete con *Prefijo de empresa SSCC* (el prefijo de empresa GS1, de 6 a 12 dígitos).

## Datos de demostración (`meat_cutting_demo`)

- **Proveedores y canales:** dos mataderos, canales de cerdo y de ternera con dos métodos de despiece, y cuatro crotales (uno halal).
- **Familias:** *Canales*, *Vacuno fresco*, *Vacuno congelado*, *Cerdo fresco*, *Cerdo congelado*, *Elaborado fresco*, *Elaborado congelado* y *Otros ingredientes*.
- **Cortes:** fresco (30 días) y congelado (180 días), con embalaje de pieza completa.
- **Presentaciones:** pieza entera, fileteado, troceado y envasado al vacío. Hay además un solomillo envasado al vacío como producto propio (45 días).
- **Recepciones:** de cinco canales, con crotales y lotes cargados de antemano.
- **Compras:**
  - P00001 a Matadero del Sureste: tres canales de cerdo recibidas con *Register Carcasses*. Pesan 268,9 kg de los 270 estimados y no queda pedido pendiente. Está pendiente de facturar: al hacerlo se ven los kg reales.
  - P00002 a Carnes de la Sierra: dos medias canales de ternera recibidas (una halal y otra nacida en Francia), pendiente de facturar.
  - P00003 a Matadero del Sureste: dos canales de cerdo, confirmado y pendiente de recibir, para probar el registro de canales.
- **Despieces:**
  - Uno terminado, pieza a pieza, con dos cortes congelados (costillas y solomillo) y una etiqueta editada.
  - Otro en curso que congela por defecto.
- **Stock:** una paleta fresca congelada después desde el stock.
- **Ventas a Carnicería La Plaza:**
  - S00001: presupuesto en piezas (lomo fileteado y jamones) y en kg (chuletas).
  - S00002: pedido entregado en una caja con SSCC. Incluye una paleta más ligera que la estimada, entregada sin pedido pendiente, y está pendiente de facturar: al hacerlo se ven los kg reales.
- **Segundo corte:** el lomo se corta en chuletas.
- **Elaborados:** longaniza fresca y morcilla de cebolla, con receta para 100 kg, su producto congelado y las presentaciones *En ristra*, *Troceado* y *Envasado al vacío*.
  - Longaniza: magro y panceta de cerdo, sal, pimentón, pimienta y ajo.
  - Morcilla: papada y panceta de cerdo, cebolla pochada, sal, pimentón y pimienta.
- **Otros ingredientes:** sal, pimentón dulce, pimienta negra, ajo picado y cebolla pochada en stock, por lotes con caducidad. Hay dos lotes de cebolla, para ver que se propone antes el que caduca antes.
- **Actualización:** al actualizar una base con la demo ya instalada, una migración aplica las familias, las recetas por 100 kg, los congelados y las presentaciones de los elaborados, y carga el stock de ingredientes.
- **Formatos de etiqueta:** compacto y de caja.

## Tests

```bash
odoo-bin -c odoo.conf -d test_db -i meat_cutting_sale,meat_cutting_purchase --test-tags /meat_cutting,/meat_cutting_sale,/meat_cutting_purchase --stop-after-init
```

El tour de la pantalla (`test_meat_cutting_ui`) necesita Chrome y la librería `websocket-client`.

## Limitaciones conocidas

- **Reetiquetar tras congelar.** Al congelar stock ya cortado, la pieza cambia de producto y de caducidad, pero no hay etiqueta de pieza para stock que no venga del despiece. Hay que reetiquetar a mano.
- **Caducidad de los cortes.** No se limita a la de la canal.
- **Coste por pieza.** Es el coste medio del producto, no el de cada pieza.
- **Presupuestos y pedidos por pieza o por canal.** Muestran el importe estimado; la factura, el real.
- **Qué se puede despiezar.** Todo producto con lista de materiales normal y stock aparece en la pantalla de despiece. Los productos que se fabrican en otro proceso, como los envasados en stock, salen del despiece como un corte más en lugar de tener su propia lista de materiales.
- **Prefijo SSCC.** Se configura por tipo de paquete, no por compañía.

## Otros módulos del repositorio

| Módulo | Depende de | Qué aporta |
|---|---|---|
| `sale_route_offline` | `sale`, `account` | Aplicación *Ruta de venta* para la tablet de los comerciales de preventa. Sin conexión: clientes con deuda y últimos pedidos, pedidos con productos habituales y catálogo, revisión y confirmación, y cobros. Todo se sincroniza al recuperar la conexión. Ver [su README](sale_route_offline/README.md) |

## Mercas (migrado desde dev19)

Solución para mercados mayoristas de fruta, traída del repositorio `dev19` (Odoo 19) y migrada a Odoo 20, más el mostrador táctil nuevo.

| Módulo | Origen | Qué aporta |
|---|---|---|
| `mercas_base` | dev19 | Venta y compra con lotes y cajas (*Vender y Entregar*, *Comprar y Recibir*), fianza y devolución de envases, etiquetas de caja, origen, liquidación de lotes al proveedor y compensación. Ver [su README](mercas_base/README.md) |
| `mercas_touch` | **nuevo** | Aplicación *Mostrador* para pantalla táctil: venta con lotes (F1) y compra con lotes nuevos (F2), guardadas como borrador mientras se elaboran para retomarlas después; cajas (F3), lotes, desechos y liquidación (F4) y cobros (F5). Ver [su README](mercas_touch/README.md) |
| `mercas_keys` | dev19 | Pantalla unificada del backend con F1-F4 y navegación con flechas en las listas |
| `mercas_ai` | dev19 | Consultas en lenguaje natural sobre ventas, compras, lotes y facturación (asistente y chat en Discuss) |
| `mercas_demo` | dev19 | Datos de ejemplo: productos de fruta y verdura, cajas, clientes y proveedores |
| `chat_ai` | dev19 | Bot de chat en Discuss sobre el que trabaja `mercas_ai` |
| `stock_restrict_lot` | OCA 19.0 | Lote obligatorio en los movimientos de stock. Base de los dos siguientes |
| `purchase_lot` | OCA (PR 19.0) | Lote en la línea de compra |
| `sale_order_lot_selection` | OCA 19.0, con cambios propios | Lote en la línea de venta, y selector de varios lotes en el popover de stock |
| `account_financial_risk`, `sale_financial_risk` | OCA 19.0 | Riesgo financiero del cliente. Opcionales: *Vender y Entregar* los usa si están instalados |
| `odoo_mcp_manager` | CybroAddons 20.0 | Proveedores de IA y servidor MCP, usado por `chat_ai` y `mercas_ai` |

### Qué cambió al migrar

Los módulos de OCA **no están migrados a 20.0 en OCA** (a fecha de 14/10/2026 las ramas `20.0` están casi vacías y no hay PR de migración). Aquí se han migrado como copias locales, así que conviene llevar los cambios a OCA o sustituirlas cuando OCA publique la 20.0.

Se aplicaron los scripts oficiales de Odoo 20 (`odoo-bin upgrade_code`: `ir.access.csv`, Owl 3, `t-call`, `t-out`…) y, además, a mano:

- **Interfaz:**
  - Las líneas de pedido de compra y venta agrupan producto, descripción, cantidad y unidad en `<column>`: se adaptaron las vistas heredadas.
  - El informe de pedido de venta muestra `line.label`.
  - Componentes con `props = useProps(...)` en lugar de `static props`, referencias con `signal.ref()`, y el servicio `action` en lugar de un plugin que no existe.
  - Odoo 20 ya no carga FontAwesome: los iconos `fa-*` pasan a los iconos `oi` (Material Symbols).
- **Stock:**
  - `stock.scrap` desaparece: los desechos son `stock.move` con `is_scrap`. Se adaptaron la pestaña y el botón de desechos del lote.
  - La devolución de albaranes ya no tiene asistente: `stock_restrict_lot` conserva el lote en `stock.picking._prepare_return_move_default_values`.
  - Cambios de API: los dominios de ubicación son cinco, la firma de `_push_prepare_move_copy_values`, y la UdM pasa a `uom_id` en compras y movimientos.
  - El seguimiento "sin lote" es `False` en lugar de `'none'`.
- **Otros:**
  - Parámetros de configuración con `get_bool`/`get_str`.
  - `uom.round()` en lugar de `rounding`.
  - `_setup_complete` desaparece: el grupo extra del límite de crédito se declara en el campo.
  - `_message_post_after_hook(message)` sin `msg_vals`.
  - `company_type` desaparece de los contactos de demo.
  - `report_file` desaparece de los informes.
- **Correcciones encontradas al probar:**
  - `mercas_base` creaba la ubicación propia del cliente o proveedor con los permisos del usuario, así que un usuario de almacén sin ser administrador no podía vender ni comprar. Ahora la crea como superusuario.
  - Los kg desechados de un lote no se recalculaban al desechar.
  - *Vender y Entregar*, *Comprar y Recibir* y los flujos de cajas dejaban el albarán sin validar cuando Odoo mostraba un aviso al validarlo (con `stock_sms`, la confirmación del SMS de la primera entrega), aunque el pedido pareciera entregado. Ahora se valida sin esos avisos y, si aun así no queda validado, da un error.
  - El módulo `odoo_mcp_manager` de CybroAddons 20.0 importaba un módulo JS que no existe en Odoo 20 y usaba `static props`. Al instalarlo se rompía el backend; está corregido aquí.
  - Algunos iconos de `sale_route_offline` (`groups`, `call`, `edit_note`, `fact_check`) no existen en Odoo 20 y se han cambiado.
- **Tests de OCA:**
  - En Odoo 20 los tests de `BaseCommon` se ejecutan con un usuario interno básico.
  - Solo se pueden enlazar rutas seleccionables.
  - Las transacciones de pago se escriben con `payment_safe_write`.

### Tests

```bash
odoo-bin -c odoo20.conf -d <bd> -i mercas_touch,mercas_keys,mercas_ai,mercas_demo,sale_financial_risk \
  --test-tags /stock_restrict_lot,/purchase_lot,/sale_order_lot_selection,/account_financial_risk,/sale_financial_risk,/mercas_base,/mercas_keys,/mercas_ai,/chat_ai,/odoo_mcp_manager,/mercas_touch,/mercas_demo \
  --stop-after-init
```

Incluye tours en el navegador del mostrador, del formulario de venta (fecha de la cantidad y lotes en el popover de stock), de `mercas_keys` y de `mercas_ai`. Necesitan Chrome y `websocket-client`.
