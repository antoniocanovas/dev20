# Mercas: preguntas al cliente antes de la demo

*Preparado el 21/10/2026 a partir de los módulos `mercas_*` de dev20.*

Objetivo: en 20-30 minutos de conversación, saber **qué enseñar y qué saltarse**. Cada bloque tiene unas preguntas clave y, debajo, qué parte de la demo activa una respuesta afirmativa. Al final hay una tabla para anotar las prioridades.

Consejo: empezar por el bloque 1 y dejar que el cliente cuente su día. Las preguntas de los demás bloques suelen contestarse solas; solo hay que hacer las que falten.

---

## 1. El negocio y el día a día

1. ¿A qué os dedicáis exactamente: mayorista en Mercas, asentador, distribuidor, exportador?
2. ¿Qué productos movéis? ¿Solo fruta y verdura, o también otras familias?
3. ¿Cuántas personas trabajan en el puesto, en la oficina y en reparto? ¿Quién usaría Odoo?
4. ¿Cómo es un día normal, desde que llega la mercancía hasta que se cobra?
5. ¿Qué usáis hoy (ERP, programa del mercado, Excel, papel)? ¿Qué es lo que más os molesta de ello?
6. Si mañana tuvierais el sistema ideal, ¿qué es lo **primero** que querríais resolver?

> **Para qué sirve:** fijar el hilo de la demo con su propio vocabulario y su propio dolor. La pregunta 6 decide por dónde empezar.

## 2. Compras y procedencia de la mercancía

1. ¿Compráis **en firme** (precio cerrado al comprar) o recibís género **en consignación** / a comisión y liquidáis después al proveedor? ¿En qué proporción?
2. ¿Cada entrada de un proveedor se controla como una **partida o lote** propio? ¿Cómo la identificáis hoy?
3. ¿Necesitáis registrar el **país y la provincia de origen** de cada partida? ¿Os lo exige el cliente, el etiquetado o la trazabilidad?
4. ¿Trabajáis con una lista cerrada de orígenes habituales?
5. ¿Compráis por kilos, por bultos o de ambas formas?

> **Si dicen sí:** compras con lote automático al confirmar, columnas de país y provincia de origen con el filtro de orígenes del mercado, y negociación en firme por defecto según el proveedor.

## 3. Liquidaciones a proveedores (consignación)

*Solo si en el bloque 2 hay consignación o comisión.*

1. ¿Cómo liquidáis hoy al proveedor: por partida terminada, por periodos, con anticipos?
2. ¿Qué **margen o comisión** aplicáis? ¿Es igual para todos los proveedores o depende de cada uno?
3. ¿Qué hacéis con la **merma o el desecho**? ¿Se descuenta al proveedor? ¿Debe verse en la liquidación?
4. ¿El proveedor quiere ver en la factura el **detalle de las ventas** de su partida (fecha, pedido, kilos, precio)?
5. ¿Hay proveedores que a la vez son clientes? ¿**Compensáis** facturas de compra con facturas de venta?
6. ¿La factura del proveedor se confirma sola o la revisa alguien antes?

> **Si dicen sí:** ficha del lote (kilos comprados, vendidos, desechados, importe y margen), asistente de facturación de lotes terminados (liquidar, anticipo o en firme), los dos modos de liquidación (precio medio, o precio medio con la merma aparte), desglose de ventas en la factura y diario de compensación.

## 4. Ventas, lotes y entrega

1. ¿Al vender, el vendedor elige **de qué partida** sale la mercancía? ¿Una línea puede salir de varias partidas?
2. ¿Vendéis y entregáis en el momento (el cliente se lo lleva) o preparáis pedidos para repartir?
3. ¿Hacéis albarán, factura o ambos? ¿Facturáis cada venta o por periodos?
4. ¿Os pasa que se vende de una partida y luego hay que **cambiarla** por otra?
5. ¿Hay **negociaciones en firme** también en la venta (precio cerrado de antemano)?
6. ¿Cómo registráis hoy la merma o lo que se tira?

> **Si dicen sí:** *Vender y Entregar* en un paso, selección de uno o varios lotes por línea, asistente de cambio de lote y desechos desde el propio lote.

## 5. Envases y cajas retornables

1. ¿Usáis **cajas o envases retornables** (de plástico, palés, etc.)?
2. ¿Necesitáis saber **cuántas cajas tiene cada cliente y cada proveedor**?
3. ¿Las cajas se cobran o depositan, o solo se controlan?
4. ¿Imprimís **etiquetas** para las cajas o los bultos? ¿Con qué impresora (Dymo, Zebra, otra)?

> **Si dicen sí:** productos marcados como caja, saldo de cajas por contacto, entregas y devoluciones de cajas y etiquetas de caja.

## 6. Clientes, cobros y riesgo

1. ¿Dais **crédito** a los clientes? ¿Con límite por cliente?
2. Cuando un cliente supera su crédito, ¿qué pasa hoy: se le sigue vendiendo, se avisa o se bloquea? ¿Quién puede autorizarlo?
3. ¿Se cobra en el puesto (efectivo, tarjeta) o por banco?
4. ¿Os interesa ver la **deuda vencida y pendiente** del cliente en el momento de venderle?

> **Si dicen sí:** límite de crédito y riesgo (OCA) con el aviso «supera su crédito (usado / concedido)», bloqueo con autorización de un responsable, información de riesgo en el pedido y cobros desde la pantalla táctil.

## 7. Forma de trabajar en el puesto

1. ¿Dónde se registra la venta: en el puesto, en una oficina, en el móvil?
2. ¿Tenéis o pondríais una **pantalla táctil** en el puesto? ¿Lector de códigos de barras?
3. ¿Los usuarios son rápidos con el **teclado** y prefieren atajos (F1, F2…) en lugar del ratón?
4. ¿Cuántas ventas hacéis en las horas punta? ¿Cuánto tiempo puede llevar cada una?

> **Si dicen sí:**
> - **Pantalla táctil (`mercas_touch`):** venta con lotes, recepción, cajas, lotes y cobros en modos F1-F5, con aviso de riesgo y borradores.
> - **Teclado (`mercas_keys`):** atajos de teclado sobre las pantallas estándar de Odoo.
>
> Enseñar solo uno de los dos según la respuesta. Todavía no está decidido cuál se mantiene.

## 8. Inteligencia artificial

1. ¿Os gustaría **preguntar en lenguaje natural** («¿cuánto le he vendido a X este mes?», «¿qué lotes de manzana quedan?»)?
2. ¿Quién la usaría: la gerencia, la oficina, los vendedores?
3. ¿Los vendedores **corrigen a mano** albaranes impresos (cantidades tachadas o reescritas)? ¿Cuántos al día? ¿Quién lo pasa luego al sistema?
4. ¿Hay alguna restricción para usar servicios de IA externos (protección de datos, política interna)?

> **Si dicen sí:**
> - **Chat de IA en Odoo (`mercas_ai`):** ventas, compras, facturación, stock, cajas y lotes.
> - **Albaranes corregidos a mano (prototipo `albaranes-ia`):** foto del albarán y aprobación de los cambios por Administración. Enseñarlo solo si la pregunta 3 es claramente sí.

## 9. Contabilidad, sistemas y arranque

1. ¿Quién lleva la contabilidad: vosotros o una gestoría? ¿Qué programa usa?
2. ¿Hay que **integrarse** con algo que se queda (ERP actual, banco, programa del mercado)?
3. ¿Cuántas empresas o CIF hay?
4. ¿Qué datos habría que traer: clientes, proveedores, artículos, saldos de cajas, deuda pendiente?
5. ¿Para cuándo lo necesitáis? ¿Hay alguna fecha clave (campaña, cierre de ejercicio)?
6. ¿Quién decide y quién estará en la demo?

> **Para qué sirve:** no es para la demo, sino para dimensionar el proyecto y saber a quién convencer.

---

## Hoja de prioridades para la demo

Marcar tras la conversación: **A** = imprescindible, **B** = interesa, **C** = no enseñar.

| Bloque de la demo | Prioridad | Notas del cliente |
|---|---|---|
| Compras con lote y origen | | |
| Liquidación a proveedores y margen | | |
| Merma y desechos | | |
| Vender y Entregar con lotes | | |
| Envases y cajas | | |
| Etiquetas | | |
| Crédito y riesgo | | |
| Pantalla táctil (`mercas_touch`) | | |
| Atajos de teclado (`mercas_keys`) | | |
| Chat de IA (`mercas_ai`) | | |
| Albaranes corregidos a mano | | |
| Compensación de facturas | | |

**Orden recomendado de la demo:** empezar por el dolor de la pregunta 1.6 y seguir el recorrido de la mercancía: compra → lote → venta → cajas → cobro y riesgo → liquidación. La IA, al final, como remate.

**Antes de la demo:** preparar `mercas_demo` con los productos, orígenes y proveedores que haya nombrado el cliente. Ver su propio género en pantalla convence más que la manzana de ejemplo.
