# Meat Cutting

Despiece de canales en Odoo 20 Community, sin Enterprise. Depende de `mrp` y `product_expiry`.

Cubre el despiece y el almacén:

- Se recibe la canal con su crotal y su peso real.
- Se despieza en una pantalla táctil que pesa y etiqueta cada corte.
- Se guarda en stock en fresco o congelado, con cada pieza en su propio paquete.
- Se sirve en cajas etiquetadas con su contenido.

La compra y la venta por canal o por pieza, facturadas en kg reales, están en `meat_cutting_purchase` y `meat_cutting_sale`.

## Qué aporta

- **Crotales** (`stock.crotal`) enlazados a los lotes, con sus datos en lotes y stock para filtrar y agrupar.
- **Registro de canales** en la recepción: crotal, peso real y datos del animal, con lo común de la partida en la cabecera.
- **Pantalla de despiece** para tablet, que pesa, etiqueta y desmonta la canal con una orden de desmontaje.
- **Etiquetas de corte** con código GS1-128 y formatos de etiqueta intercambiables.
- **Piezas completas:** cada pesada de un corte así marcado es una pieza y va en su propio paquete.
- **Fresco y congelado:** dos productos enlazados. Se congela al despiezar o después, desde el stock.
- **Etiqueta de caja** con su contenido y un SSCC.
- **Recepciones y entregas por pieza:** se reservan piezas enteras y no se proponen pedidos pendientes por la diferencia de peso.

## Cómo se modela el producto

La regla general es **un producto por corte y estado (fresco o congelado), con el stock en kg**. La pieza entera y la caja se montan sobre ese producto, sin catálogos paralelos.

| Necesidad | Solución |
|---|---|
| Canal entera | El producto se marca como *Piezas completas* y lleva un embalaje "Canal" con su peso medio. Cada canal recibida es un lote con su crotal |
| Pieza entera (por ejemplo, un solomillo) | El producto se marca como *Piezas completas*. Cada pieza pesada en el despiece va en su propio paquete, y el stock se cuenta en paquetes |
| Fresco y congelado | Dos productos con distinta caducidad, enlazados por *Producto congelado* |
| Presentación que se guarda en stock (con su caducidad o su código de barras) | Producto propio, que sale del despiece como un corte más |
| Cajas con el contenido | Paquetes anidados: las piezas van dentro de la caja, y la caja lleva una etiqueta con su contenido y un SSCC |

## Flujo

### 1. Recepción
Las canales se reciben con lote. El lote es el animal y puede llevar su **crotal**, con estos datos:

- Sexo, raza y calidad.
- Fechas de nacimiento y sacrificio.
- Países de nacimiento y engorde.
- Proveedor.
- Halal, con certificador y número de certificado.

En el albarán de recepción, el botón **Register Carcasses** abre un asistente para anotar las canales una a una:

- **Cabecera**, con los datos comunes de la partida:
  - Matadero (el proveedor del albarán) y su registro sanitario, que se toma del último crotal de ese proveedor.
  - Fecha y orden de sacrificio.
  - Valores por defecto de las canales: países de nacimiento y engorde, y halal con su certificador y número de certificado.
- **Una fila por canal:** crotal, peso real, sexo, raza, calidad, fecha de nacimiento, países y halal.

Al confirmar, cada canal:

- Crea su crotal, o completa uno registrado de antemano que aún no se haya recibido.
- Crea su lote, con el nombre del crotal y la caducidad contada desde el sacrificio.
- Entra en el albarán con su peso real.

Un crotal ya recibido no se puede registrar otra vez.

Si la canal se pidió por número (embalaje "Canal" con su peso medio) y el producto tiene *Piezas completas*, la recepción está **completa cuando han llegado las canales pedidas**, pesen lo que pesen. No se propone un pedido pendiente por los kg de diferencia; si falta una canal, sí se propone.

Si el lote no tiene crotal, se crea uno al despiezar. Los datos del crotal se guardan también en lotes y stock, así que se puede **filtrar y agrupar el stock** por cualquiera de ellos; por ejemplo, el stock halal por país de engorde.

### 2. Despiece (*Meat Cutting → Cutting Screen*)
También se abre con el botón *Cutting Screen* del albarán de recepción. La pantalla está pensada para tablet:

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

### 4. Preparación y cajas
1. El operario coge las piezas, que son paquetes; puede escanear su etiqueta.
2. Las mete en una caja con *Poner en paquete*, usando un tipo de paquete con **prefijo de empresa SSCC**. La caja se nombra con un SSCC.
3. Imprime la **etiqueta de caja**:
   - Desde la caja: *Imprimir → Box Label*.
   - Desde el albarán, todas sus cajas: *Imprimir → Box Labels*.

La etiqueta de caja incluye:

- Cliente, origen (el pedido) y albarán.
- Por producto y lote: piezas, peso y caducidad, y el crotal si no coincide con el lote.
- Total de piezas y peso neto.
- La caducidad más próxima.
- HALAL, si toda la carne de la caja lo es.
- El código GS1-128 (00) SSCC (13) fecha de envasado.

Sigue disponible una vez entregada la caja.

### 5. Entrega por piezas
Cuando un movimiento de un producto con *Piezas completas* tiene un embalaje (por ejemplo, "Pieza completa"), es decir, cuando no se vende por kg:

- **Reserva piezas enteras.** Reserva un paquete libre por pieza pedida, en el orden de salida habitual y pese lo que pese, en lugar de repartir el peso estimado entre paquetes. Por ejemplo, para dos jamones de 11 kg reserva los dos paquetes enteros de 11,62 y 15,0 kg, no 22 kg repartidos.
  - No toma paquetes con parte reservada en otra entrega.
  - El stock que no está en paquetes se reserva por peso, como siempre.
  - El movimiento queda listo con las piezas pedidas, aunque pesen menos de lo estimado.
- **Está completo cuando se ha cogido el número de piezas pedido**, pese lo que pese, igual que en la recepción de canales. Al validar, la demanda se ajusta al peso real y no se propone un pedido pendiente por la diferencia. Si falta una pieza, sí se propone. Si se valida sin marcar nada como cogido, cuentan las piezas reservadas.

Cada paquete cuenta como una pieza, y cada línea sin paquete, como una más.

Lo vendido por kg se reserva y se entrega como siempre: por peso, aunque parta un paquete.

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

**Formatos de etiqueta.** Son informes PDF del modelo `meat.cutting.line`. Cualquiera que se añada aparece en el selector de formato de la pantalla.

## Configuración

1. **Ajustes → Inventario:** activar *Lotes y números de serie*, *Fechas de caducidad*, *Paquetes* y *Unidades de medida y embalajes*.
2. **Canal:**
   - kg, seguimiento por lote y fecha de caducidad (días desde el sacrificio).
   - Una o varias listas de materiales (métodos de despiece) cuyas líneas son los cortes.
   - *Piezas completas* y un embalaje "Canal" con el peso medio, si se pide por canales.
3. **Cada corte:**
   - kg, seguimiento por lote y fecha de caducidad (días).
   - *Producto congelado*, si se congela. Debe tener la misma unidad de medida.
   - *Piezas completas*, si se sirve por pieza: una pesada es una pieza.
   - Embalaje "Pieza completa" con el peso medio, si se pide por pieza.
4. **Cajas:** un tipo de paquete con *Prefijo de empresa SSCC* (el prefijo de empresa GS1, de 6 a 12 dígitos).

## Tests

```bash
odoo-bin -c odoo.conf -d test_db -i meat_cutting --test-tags /meat_cutting --stop-after-init
```

El tour de la pantalla (`test_meat_cutting_ui`) necesita Chrome y la librería `websocket-client`.

## Limitaciones conocidas

- **Reetiquetar tras congelar.** Al congelar stock ya cortado, la pieza cambia de producto y de caducidad, pero no hay etiqueta de pieza para stock que no venga del despiece. Hay que reetiquetar a mano.
- **Caducidad de los cortes.** No se limita a la de la canal.
- **Coste por pieza.** Es el coste medio del producto, no el de cada pieza.
- **Qué se puede despiezar.** Todo producto con lista de materiales normal y stock aparece en la pantalla de despiece. Los productos que se fabrican en otro proceso, como los envasados en stock, salen del despiece como un corte más en lugar de tener su propia lista de materiales.
- **Prefijo SSCC.** Se configura por tipo de paquete, no por compañía.
