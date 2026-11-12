# Datos de ejemplo del reciclaje de vehículos (`scrap_demo`)

Carga datos de ejemplo para probar `scrap_base`, `scrap_touch` y `scrap_crm`. Depende de `scrap_touch`, `scrap_crm` (que trae `crm` y `project`) y `scrap_repair` (que trae `repair` y, con él, `sale_management`). Los datos se cargan siempre al instalar, aunque la base no tenga los datos de demostración de Odoo. Pensado para bases de prueba, no de producción.

## Qué crea

- **Compañía actual**, solo si no los tiene: secuencias *Vehículos para desguazar* (`DES2026-00001`) y *Vehículos compra / venta* (`CV2026-00001`), 10 días de descontaminación y 30 de desguace. Son valores de ejemplo, no los plazos legales.
- **Modelos de vehículo** (con las marcas de Flota): Renault Clio, Volkswagen Golf, Ford Transit, Peugeot 308, Citroën Berlingo, Opel Corsa y Honda CBR 600.
- **Proveedores y clientes**: Grúas Martínez (demo), Taller López (demo, ref. `TL01`), Ana García (demo, ref. `PA01`), que es un particular, y Recambios Norte (demo, ref. `RN01`). Los clientes tienen etiqueta *Taller (demo)* o *Particular (demo)*.
- **Marcas:** las de Flota (Renault, Volkswagen, Ford, Peugeot, Citroën, Opel y Honda). Cada vehículo y cada pieza tiene la *Marca del vehículo* de su marca/modelo, y las oportunidades usan esas mismas marcas.
- **Categorías** *Vehículos*, *Piezas* y *Residuos*.
- **Aceite para reciclar** (categoría *Residuos*, en litros), puesto como producto de desecho de la compañía: lo ofrece la descontaminación de la pantalla táctil.
- **Plantillas desguace**, almacenables y por número de serie, que ni se compran ni se venden (solo se copian para cada vehículo). Salen en la pantalla táctil:
  - *Turismo*, *Furgoneta* y *Motocicleta*, de tipo *Vehículo o Parte para desguace*.
  - *Motor usado*, de tipo *Subproducto*: el motor de todas las listas de despiece de vehículos y el motor que se compra para despiezarlo.
  - *Culata*, de tipo *Subproducto*: componente del motor que también se despieza, para probar el segundo nivel (vehículo → motor → culata).
- **Listas de materiales de despiece**, con los centros de trabajo *Zona de descontaminación* y *Zona de despiece*:
  - *Despiece turismo* (plantilla Turismo): operación *Descontaminar* (batería y depósito de combustible) y *Desmontar piezas* (motor, 4 ruedas, volante, 2 puertas delanteras y 2 asientos delanteros).
  - *Despiece motocicleta* (plantilla Motocicleta): *Descontaminar* (batería y depósito) y *Desmontar piezas* (motor, 2 ruedas y manillar).
  - *Despiece furgoneta* (plantilla Furgoneta): *Descontaminar* (batería y depósito) y *Desmontar piezas* (motor, 4 ruedas, volante, 2 puertas delanteras y 3 asientos delanteros).
  - *Despiece motor* (plantilla Motor usado): *Desmontar motor* (culata, bloque motor y turbo).
  - *Despiece culata* (plantilla Culata): *Desmontar culata* (16 válvulas y árbol de levas).
  - En las tres listas de vehículos, el motor es la plantilla *Motor usado*. Al desmontarlo se crea un producto propio, *Motor usado DES…*, que es un subproducto con el vehículo como **origen** y con su lista *Despiece motor*. Sale en Desguace → **Subproductos**. Al desmontar su culata pasa lo mismo: *Culata DES…*, con el mismo origen (el vehículo) y su lista *Despiece culata*.
  - Cada vehículo comprado tiene su copia; el vehículo creado a mano la recibe con **Completar datos CAT**.
- **Piezas** (las de los datos CAT y los componentes de las listas), de tipo *Subproducto*, para que muestren su pestaña CAT.
- **Piezas con datos CAT** para probar la búsqueda: *Alternador* (Ref. OEM `231001234R`, Ref. visible `TG11C068`, referencias `231009185R` y `8200667609`), *Faro delantero izquierdo* (`5G1941005`) y *Puerta lateral corredera derecha* (`BK31-V24630-AB`).
- **Compra de Grúas Martínez para desguace, recibida**, con cuatro vehículos en cada etapa de los plazos (las fechas se cuentan hacia atrás desde el día de instalación):
  - `1234BCD` Clio, baja hace 12 días: **descontaminación fuera de plazo**.
  - `5678CDF` Golf, baja hace 8 días: vence en 2 días.
  - `9012DFG` Transit, descontaminada y **a medio desmontar**: 2 ruedas desmontadas en buen estado (en su ubicación), la batería desechada y el **motor desmontado**, que ya es un subproducto (*Motor usado DES…*) pendiente de desguazar en **Subproductos**; desguace pendiente, vence en 5 días.
  - `3456FGH` CBR 600: descontaminada y desguazada.
  - A las dos descontaminadas se les retiró aceite (4,5 l la Transit y 1,5 l la CBR), que está en la *Zona de desecho*.
- **Compra de Taller López para desguace, recibida**: un *Motor usado* comprado directamente, `MOTOR0001`. Es un subproducto **sin origen**: sale en **Subproductos** y sus piezas (la culata...) tendrán como origen este motor. También se puede vender entero.
- **Compra de Ana García para desguace, a 0 €**: `7890GHJ` Peugeot 308, confirmada y **por recibir**.
- **Compra de Taller López para compra/venta, recibida**: `2468HJK` Berlingo, que se puede vender.
- **Reparación de la Berlingo** (`scrap_repair`), **confirmada y sin terminar**: patina el embrague, así que lleva un *Kit de embrague (demo)* (coste 120 €, hay 5 en stock; es un recambio nuevo, con Recambios Norte como proveedor, así que **Reponer** crea un presupuesto de compra por la ruta *Comprar* del almacén) y 3 horas de *Mano de obra taller (demo)* (25 €/h de coste). Está en stock, así que no tiene cliente. En la pantalla táctil, *F2 → En venta → Berlingo*: el botón **Reparar** muestra su referencia y la abre. Al terminarla, la cuenta analítica `2468HJK` recibe −120 € del embrague y −75 € de la mano de obra.
- **Presupuesto de Grúas Martínez para desguace**: `1357JKL`, guardado en la pantalla táctil: sale en *En curso* para continuarlo.
- **Imágenes:** cada producto de la demo (plantillas, piezas, componentes...) y cada uno creado de sus plantillas al instalar (los vehículos comprados, el motor desmontado de la Transit...) tiene una imagen de un color sólido distinto con su nombre. Salen en la ficha, en la pantalla táctil y en el visor de fotos de *Disponibles*. Lo que se desmonte después lleva la de su plantilla.
- **Un vehículo creado a mano**: *Turismo 8642KLM* (Opel Corsa), con plantilla, tipo y matrícula pero sin cuenta analítica ni ubicación, para probar el botón **Completar datos CAT** de la pestaña CAT.

## CRM de piezas (`scrap_crm`)

- **Categorías de las tareas:** Mecánica, Carrocería y Electricidad.
- **Proyecto *Peticiones de piezas (demo)***, con las etapas *Por hacer*, *En taller* y *Hecho* y los procesos (etiquetas) *Comprobar pieza*, *Desmontar* y *Fotografiar*. Se pone como proyecto SCRAP de la compañía, con el administrador como usuario SCRAP, si la compañía no tenía. Así las tareas creadas desde una oportunidad van a ese proyecto.
- **Tipos de las etapas del CRM:** *Nuevo* → Pendiente Gestión Comercial, *Calificado* → Pendiente Taller, *Propuesta* → Pendiente del cliente y *Ganado* → Gestión positiva. Se usan las etapas de `crm` (si alguna no existe, se crea) y solo se rellena el tipo cuando está vacío.
- **Oportunidades**, con su marca, precio de cliente o mercado, precio ofertado, horquilla de negociación y notas comerciales y técnicas:
  - *TL01 Motor 1.5 dCi para Clio IV* (Renault, Propuesta, plantilla *Motor usado*): dos tareas sobre el Clio `1234BCD`, comprobar la compresión (en taller) y fotografiar el motor (hecha).
  - *PA01 Faro delantero izquierdo Golf VI* (Volkswagen, Nuevo): tarea para buscar el faro en stock.
  - *RN01 Puerta lateral corredera Transit* (Ford, Ganado): tarea hecha para desmontar la puerta de la Transit `9012DFG`.
  - *RN01 Manillar CBR 600* (Honda, Calificado): tarea para desmontar el manillar de la CBR `3456FGH`.
  - *TL01 Alternador Clio III (Valeo TG11C068)* (Renault, Nuevo): sin tareas; el fabricante de la pieza (Valeo) va en el nombre y en las referencias.
- **Disponibles:** el botón de cada oportunidad abre la pantalla de disponibles. *En stock* muestra lo de su marca (la de Ford encuentra la Transit y su motor desmontado). *Ensamblados*, en la del motor del Clio (plantilla *Motor usado*), muestra los vehículos en stock que aún tienen el motor por desmontar, como el Golf `5678CDF`.

## Desinstalar

Al desinstalar se borran los registros del XML (modelos, proveedores, categorías, proyecto, plantillas y piezas) si nada los usa. Las compras, los vehículos, sus cuentas analíticas, ubicaciones y secuencias se crean al instalar y se quedan.

- **Tareas de las oportunidades (2026-11-11):** con la fecha límite estándar (`date_deadline`), relativa al día de instalación: dos vencidas, una para hoy y dos próximas (-2, -1, 0, +1 y +3 días), para ver los colores en Expedientes.

- **Expedientes (20.0.1.2.0, 2026-11-12):** `demo_files.py`, desde el hook de instalación (depende ahora de `project_task_touch`). Cuatro plantillas marcadas para Expedientes, con fechas de inicio y fin (desde el 1 de enero) y fechas límite en sus tareas, y expedientes creados con ellas: sus fechas límite y su fin salen de la plantilla, movidas a su inicio (`project_task_touch`):
  - *Salida de residuos*: una tarea con 4 subtareas que se repite cada mes; la del mes pasado hecha y la de este mes creada por la recurrencia.
  - *Onboarding de empleado*: 7 tareas con dependencias. *Onboarding Juan Pérez (mecánico)* en su segunda semana (una vencida, otras esperando) y *Onboarding Laura Martín (administración)* que empieza hoy.
  - *Gestión AEAT mensual*: revisar facturas, conciliar bancos, modelos 303, 111 y 115, presentar y archivar, con dependencias y hasta el día 20 del mes siguiente. El mes anterior al pasado presentado y el pasado en curso.
  - *Formación de taller*: cursos (PRL, descontaminación de VFU, carretilla, híbridos y eléctricos, corte) con las subtareas *Inscripción / Asistencia / Certificado entregado* y una evaluación final que depende de todos. *Formación de taller · Juan Pérez* con el PRL hecho y el resto en marcha.
  - En una base ya instalada no se crean solos (el hook es solo de instalación): `from odoo.addons.scrap_demo.demo_files import create_files; create_files(env)` desde `odoo-bin shell`.
