# Ideas: la misma metodología para otros documentos

Recogido de las conversaciones del 16 al 20/10/2026. Las ideas están sin implementar. Para el caso de los albaranes de cliente con sus propios códigos, ver [`albaranes_nagarmur.md`](albaranes_nagarmur.md).

**La metodología:**
1. Foto o PDF del documento.
2. Lectura con IA, con un esquema JSON estricto.
3. Comparación con el ERP o con otra fuente.
4. Revisión humana, solo de las diferencias.
5. Aplicar el cambio en el ERP.
6. Guardar lo aprendido.

**El aprendizaje es del sistema, no del modelo.** Las correcciones del revisor se guardan en tablas y se aplican en el siguiente documento:
- huella del emisor (el CIF) → cliente o proveedor;
- código ajeno → nuestro artículo, con factor de unidad;
- notas por emisor que se añaden al prompt;
- ejemplos corregidos.

Cada regla guarda quién la creó, cuándo y desde qué incidencia, y se puede borrar. Lo aproximado nunca se aplica sin confirmación.

## Documentos con su equivalente en el ERP

| # | Documento | Se compara con | Qué detecta |
|---|---|---|---|
| 1 | Factura de proveedor | Pedido de compra y albarán de entrada | Diferencias de precio, cantidad o descuento; portes; duplicados |
| 2 | Albarán de proveedor en la recepción | Pedido de compra | Faltas, sobrantes, roturas, sustituciones |
| 3 | Pedido de cliente (email, PDF, fax, foto) | Catálogo, tarifa y stock | Artículos desconocidos, precio fuera de tarifa, falta de stock |
| 4 | Hoja de devolución de cliente | Albarán y factura de origen | Devoluciones de lo no vendido o fuera de plazo |
| 5 | CMR o comprobante de entrega firmado | Expedición | Reservas manuscritas, entregas parciales, falta de firma |
| 6 | Hoja de recuento de inventario | Stock teórico | Diferencias, ubicaciones equivocadas |
| 7 | Lotes, caducidades y temperaturas | Trazabilidad | Lote no registrado, caducidad corta, temperatura fuera de rango (APPCC) |
| 8 | Tarifa de proveedor en PDF | Precios de compra | Subidas, artículos nuevos o descatalogados |
| 9 | Tickets y notas de gasto | Política de gastos y tarjetas | Gastos fuera de límite, duplicados, IVA |
| 10 | Partes de trabajo y hojas de horas | Proyectos o pedidos de servicio | Horas sin imputar, material no registrado |

**Prioridades:**
- **Más rentables:** el 1 y el 3. Comparten el aprendizaje de equivalencias con Nagarmur.
- **Variantes casi directas del prototipo:** el 2, el 4 y el 5.
- **Valor regulatorio:** el 7.

**Si el documento es estructurado** (Facturae, VeriFactu, EDI, Norma 43), no hace falta visión: se lee directamente.

## Documentos fuera del ERP: plazos, alertas y cruces

| # | Documento | Para qué |
|---|---|---|
| 1 | Multas de tráfico | Identificar al conductor (cruzando con el cuadrante o el GPS) dentro del plazo legal; aviso del 50 % por pronto pago |
| 2 | DNI / NIE | Altas sin teclear y caducidades. La zona de lectura mecánica se decodifica sin IA |
| 3 | Permiso de conducir, CAP, tarjeta de tacógrafo, ADR | Alertas de caducidad |
| 4 | ITV, seguro, permiso de circulación | Calendario de la flota |
| 5 | Notificaciones de Hacienda, Seguridad Social, ayuntamiento y juzgados | Clasificar, asignar un responsable y vigilar el plazo |
| 6 | Contratos | Preavisos y renovaciones automáticas |
| 7 | Pólizas de seguro | Vencimientos, coberturas, comparación entre años |
| 8 | Certificados de subcontratas (CAE) | Bloquear a quien tenga papeles caducados |
| 9 | Facturas de suministros | Consumos anómalos, potencia mal contratada |
| 10 | Formación y reconocimientos médicos | Renovaciones. Solo "apto / no apto" y fechas, nunca diagnósticos |
| 11 | Tickets de combustible y peajes | Cruce con rutas o GPS |
| 12 | Tarjetas de visita y hojas de feria | Alta en el CRM, que encaja con `ia-support-contactos` |

**Por dónde empezar:** por las multas (1) y las notificaciones (5), que tienen plazos cortos y una base legal clara. Después, las caducidades de flota y conductores (3 y 4).

**RGPD:**
- base legal y finalidad para cada uso;
- minimización: no guardar la imagen del DNI y borrar las fotos tras extraer los datos;
- contrato de encargo de tratamiento con el proveedor de IA y revisión de las transferencias internacionales;
- usuarios nominales y registro de accesos;
- los datos de salud son categoría especial.

## IA local (Docling + Ollama con Gemma, Qwen-VL…) o Claude

- **Docling** convierte PDF e imágenes en texto estructurado. Funciona muy bien con documentos impresos y flojea con la escritura a mano.
- **Modelos de visión locales:** Ollama acepta `format` con esquema JSON, así que se integra como un proveedor más en `albaranes-api/vision.py`, junto a `openrouter` y `anthropic`.

**¿Basta con lo local?**
- **Sí:** en impresos (multas, notificaciones, certificados, pólizas, suministros). En el DNI basta la zona de lectura mecánica, sin LLM.
- **Dudoso:** en tachones y números manuscritos (albaranes, partes de trabajo). Hay que medirlo.

**Hardware:**
- El servidor actual (4 vCPU, 7 GB de RAM, sin GPU) **no sirve**.
- Los modelos de 12–27 B necesitan una GPU de 16–24 GB, o un Mac con 32 GB o más de memoria unificada.

**Propuesta híbrida:**
- documentos con datos personales: en local;
- documentos comerciales: con Claude.

**Alternativa sin hardware propio:** Claude por AWS Bedrock o Google Vertex en una región de la UE, con contrato de encargo de tratamiento.

**Antes de decidir:** pasar el mismo lote de `pruebas/`, más la foto real #17, por cada modelo y comparar aciertos por línea, tiempo y coste.
