# Prompt: albaranes del cliente con sus códigos (Nagarmur)

> Prompt para retomar esta necesidad en otra sesión. Pégalo tal cual o di "lee `albaranes-ia/albaranes_nagarmur.md` y empieza".

## Contexto

Trabajas en `albaranes-ia/` de este repositorio: un prototipo que ya funciona para detectar cambios hechos a mano sobre **nuestro** albarán impreso. Lee antes `albaranes-ia/README.md`. Resumen:

- **Ingesta (n8n):** foto → `barcode-ocr` (código de barras) → modelo de visión (OpenRouter, credencial de n8n) → `albaranes-api` compara con el ERP → incidencia en la BD propia `albaranes_ia`.
- **Revisión (n8n):** pantallas `web/*.html` incrustadas en los flujos con `n8n/build_workflows.py`; Aprobar / Corregir y aprobar / Rechazar.
- **Rectificación:** devolución + abono en borrador, detrás de `DRY_RUN=true`.
- **Capa ERP sustituible:** `albaranes-api/erp/base.py` (interfaz) y `erp/odoo_json2.py` (Odoo 20 de pruebas). En producción el ERP es **AS400/DB2**, así que nada de la lógica nueva puede depender de Odoo.
- **Despliegue:** Easypanel, proyecto `ia-support` (`ssh -p 22022 root@217.154.182.5`), `scripts/desplegar.sh [api|ocr|n8n]`. Secretos en `/root/albaranes-ia/.env`.

## La necesidad

A algunos clientes no les vale nuestro albarán: revisan la mercancía y nos devuelven **su propio albarán, con sus códigos de producto**. Queremos:

1. Que en su albarán se escriba **a mano el número de nuestro albarán**.
2. Que el sistema lea la foto, **encuentre nuestro albarán en el ERP** y **detecte las diferencias**, traduciendo sus códigos a los nuestros con una **tabla de equivalencias** por cliente.
3. Que el sistema **aprenda con el uso**: lo que el revisor corrige se guarda y se aplica la próxima vez. Por ejemplo, si no reconoce al cliente y el revisor lo elige, la siguiente vez lo reconoce solo.

## Diseño acordado (pendiente de validar con albaranes reales)

**Lectura (IA):** ampliar el esquema `json_schema` estricto para que el modelo devuelva:
- el número de nuestro albarán escrito a mano;
- los datos del emisor: CIF, razón social, dirección;
- por línea: su código, su descripción, el EAN si lo hay, la cantidad, la unidad y las marcas manuscritas.

**Nuestro albarán:** el número manuscrito es el punto más frágil. Hay que validarlo:
- que exista;
- que sea de ese cliente;
- que la fecha sea razonable.

Si no cuadra, la revisión propone los últimos albaranes del cliente para elegir uno. Hay que valorar una pegatina con nuestro código de barras como alternativa.

**Traducción de códigos, por orden:**
1. Tabla de equivalencias: `(cliente, su_codigo) → nuestro producto + factor de unidad`.
2. EAN contra el código de barras del producto en el ERP.
3. Propuesta de la IA por descripción. **Siempre va a revisión, nunca se asigna sola.**

**Comparación:** produce tres tipos de diferencia:
- cantidad distinta (tras aplicar el factor de unidad);
- nuestra línea no aparece en su albarán;
- su línea no se encuentra en el nuestro.

**Aprendizaje: lo hace el sistema, no el modelo.** Son tablas nuevas en `albaranes_ia`:
- `cliente_huella`: CIF o nombre normalizado → cliente del ERP. El CIF da una coincidencia segura; el nombre solo genera una propuesta.
- `equivalencia`: cliente, su código, nuestro producto y factor.
- `nota_cliente`: particularidades del formato, que se añaden al prompt de visión de ese cliente.
- `ejemplo_cliente`: lecturas corregidas, para usarlas como ejemplos en el prompt. Es opcional y encarece cada llamada.

Cada regla guarda quién la creó, cuándo y desde qué incidencia. Hace falta una pantalla para ver y borrar lo aprendido. Lo aproximado nunca se aplica sin confirmación.

**Revisión:**
- columna "su código → nuestro producto", con selector de producto;
- selector de cliente cuando no se reconoce;
- al aprobar, se guardan las equivalencias y las huellas nuevas.

**Rectificación:** se reutiliza la actual, con `DRY_RUN`.

**Métricas:** correcciones por cliente y mes, para comprobar que el sistema mejora y detectar cambios de formato.

## Restricciones (las mismas del prototipo)

- Nada de secretos en el código: todo en `.env` y `.env.example`.
- Los flujos de n8n se versionan en `n8n/workflows/` y se generan con `build_workflows.py`. Las páginas se editan en `web/`.
- Las operaciones deben ser idempotentes. No se hace nada destructivo en Odoo sin avisar, y antes se hace `pg_dump`.
- El acceso al ERP va solo por la capa `erp/`. En el AS400 puede existir ya una tabla de referencias cruzadas cliente–artículo (típica con EDI): si existe, el adaptador debe usarla y nuestra tabla solo la complementa. Odoo estándar no tiene códigos de producto por cliente.
- Trabaja por fases con checkpoint y demuestra cada una con una prueba real. Responde en español.

## Primeros pasos

1. Pedir **2 o 3 albaranes reales de Nagarmur**, con los datos sensibles tapados si hace falta. Comprobar cómo los lee el modelo antes de construir nada: número manuscrito, CIF, líneas, unidades.
2. Confirmar si el cliente puede enviar PDF o EDI en lugar de foto, porque es más fiable y más barato.
3. Preguntar si en el AS400 existe ya la tabla de equivalencias cliente–artículo.
4. Fases propuestas:
   1. lectura ampliada y búsqueda de nuestro albarán;
   2. equivalencias y comparación;
   3. pantalla de revisión con aprendizaje;
   4. métricas y pantalla de reglas aprendidas.

## Preguntas abiertas

- ¿El cliente cuenta en cajas o en unidades? ¿Siempre igual?
- ¿Quién escribe nuestro número en su albarán: el repartidor, el cliente o administración?
- ¿Las diferencias se rectifican igual que ahora (devolución y abono) o el cliente solo factura lo que confirma?
- Usuarios nominales en la revisión (hoy es un único usuario Basic Auth): hacen falta para saber quién enseñó cada regla.
