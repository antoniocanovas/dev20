# ia-support · Contactos (n8n + API + Odoo 20)

Primera fase del asistente de surtidos: una API REST de contactos que escribe
por SQL directamente en `res_partner` de un Odoo 20, más un flujo de prueba en
el n8n existente. Entorno interno de pruebas: sin autenticación y sin HTTPS propio.

```
Proyecto ia-support (Easypanel, servidor 217.154.182.5)

  n8n (existente) --HTTP--> contactos-api:8000 --SQL--> surtidos-db:5432 (BD odoo) <-- odoo20:8069
  navegador ------------------------------------------------------------------------> odoo20 (dominio Easypanel)
```

## Servicios creados

| Servicio Easypanel | Host interno (red `easypanel-ia-support`) | Tipo / imagen | Exposición |
|---|---|---|---|
| `surtidos-db` | `ia-support_surtidos-db:5432` | PostgreSQL 16 (`postgres:16`), BD `odoo`, usuario `odoo` | Sin puerto público |
| `odoo20` | `ia-support_odoo20:8069` | App, imagen `odoo:20` | https://ia-support-odoo20.kw2y1s.easypanel.host |
| `contactos-api` | `ia-support_contactos-api:8000` | App, código subido a Easypanel (Upload) + build con `Dockerfile` | Sin dominio ni puerto público |

No se ha modificado ningún servicio existente de ia-support (`db`, `docling`, `n8n`, `n8n-db`, `n8n-runner`, `odoo`, `odoo-db`).

### Accesos

- **Odoo 20**: https://ia-support-odoo20.kw2y1s.easypanel.host, usuario `admin` / `admin`. BD `odoo` con el módulo Contactos y datos demo.
- **n8n**: https://ia-support-n8n.kw2y1s.easypanel.host. Flujo **"Prueba API contactos"**.
- **API (Swagger)**: solo red interna. Desde el portátil, con un túnel (ver más abajo): http://localhost:18000/docs.
- **Easypanel**: solo por túnel SSH (`~/sshn8n` reenvía el puerto 3000): http://localhost:3000.

### Variables de entorno (en Easypanel, no en el repositorio)

- `odoo20`: `HOST=ia-support_surtidos-db`, `USER=odoo`, `PASSWORD=<pg>`, `PORT=5432`, `ODOO_ADMIN_PASSWD=<contraseña maestra>`.
- `contactos-api`: `DB_HOST=ia-support_surtidos-db`, `DB_PORT=5432`, `DB_NAME=odoo`, `DB_USER=odoo`, `DB_PASSWORD=<pg>`.

La contraseña de Postgres es aleatoria (16 bytes en hexadecimal) y está en Easypanel → surtidos-db → Credenciales.

## Decisiones tomadas (no estaban en el encargo)

- **`PORT=5432` en odoo20**: Easypanel inyecta `PORT=8069` y el entrypoint de la imagen de Odoo lo usa como puerto de la BD.
- **Comando de odoo20**: genera `/tmp/odoo.conf` al arrancar con `admin_passwd` (de la variable `ODOO_ADMIN_PASSWD`), `list_db = False`, `proxy_mode = True` y `http_interface = 0.0.0.0` (Odoo 20 escucha por defecto solo en 127.0.0.1). Después lanza `odoo -d odoo -i contacts --with-demo`; desde Odoo 19 los datos demo no se cargan si no se pide. El `-i contacts` se repite en cada arranque y es inocuo.
- **Build de la API**: Easypanel no despliega imágenes que solo existen en local (intenta hacer `pull`). Por eso el código de `api/` se sube como archivo `.tar.gz` (origen "Upload") y Easypanel lo construye con el `Dockerfile`. Para redesplegar: Easypanel → contactos-api → Origen → Upload → subir `api.tar.gz` → Deploy.
- **Tipos**: para escribir se aceptan `FACTURA`, `ALBARAN` y `CADENA`. Al leer, los contactos de Odoo que no encajan (p. ej. los hijos de Azure Interior, con `type = contact`) se devuelven con el tipo estándar de Odoo (`contact`, `other`).
- **Campos extra**: `telefono` → `phone` y `email` → `email`.
- **Código único**: solo entre contactos **activos**. Así el flujo de n8n se puede repetir (la baja final archiva el T001).
- **NIF**: NIF, NIE o CIF español con letra o dígito de control, prefijo `ES` opcional. Se guarda en mayúsculas, sin espacios ni guiones. Los hijos heredan el NIF de la cadena si no traen uno propio, como hace Odoo.
- **Reglas de CADENA**: una CADENA no puede tener `cadena_id`. `cadena_id` debe ser una empresa activa.
- **Deshacer**: un ALTA deshecho queda archivado (nunca DELETE), una BAJA deshecha se reactiva y una MODIF restaura la foto `antes`. Devuelve 409 si el contacto ha cambiado después del cambio o si ese cambio ya estaba deshecho. Un UNDO no se puede deshacer (400).
- **`create_uid` / `write_uid` = 1 y `company_id` = 1**, como pide el encargo (los contactos demo de Odoo tienen `company_id` vacío).
- **Recalculados por la API**: `complete_name`, `commercial_partner_id`, `commercial_company_name` (también en los hijos al renombrar una cadena), `email_normalized`, `lang`, `write_date` y `write_uid`. **No** se recalculan `phone_sanitized` ni el chatter: el historial está en `api.contactos_log`.

## API

FastAPI + psycopg 3. Al arrancar espera a que exista `res_partner` y crea el esquema `api` (tabla `api.contactos_log`). Las consultas son siempre parametrizadas. Los errores salen como `{"error": "..."}` con códigos 400, 404, 409 o 422, nunca con trazas.

| Método y ruta | Función |
|---|---|
| `GET /health` | `{"ok": true}` (503 si la BD no responde) |
| `GET /contactos?q=&incluir_bajas=false` | Busca por NIF, código o nombre (ILIKE, también sobre "Cadena, Contacto"). Máx. 10. Devuelve `total`, `requiere_eleccion` y `resultados` |
| `GET /contactos/{id}` | Ficha (incluye archivados) |
| `POST /contactos` | Alta → 201 con la ficha + `log_id` |
| `PATCH /contactos/{id}` | Modifica solo los campos enviados (`codigo`, `nif`, `nombre`, `tipo`, `cadena_id`, `telefono`, `email`, `activo`) |
| `DELETE /contactos/{id}?sesion=&usuario=` | Baja lógica (`active = false`) |
| `POST /log/{log_id}/undo` | Deshace el cambio. Body opcional `{"sesion","usuario"}` |
| `GET /log?sesion=&limite=50` | Historial, más recientes primero |

`POST` y `PATCH` aceptan `sesion` y `usuario` en el body; `DELETE`, en la query. Cada escritura registra su fila de log en la misma transacción y devuelve `log_id`.

### Probar la API

**Desde el servidor** (contenedor efímero en la red interna):

```sh
ssh -p 22022 root@217.154.182.5
docker run --rm -i --network easypanel-ia-support --entrypoint sh curlimages/curl:8.11.1 < pruebas_api.sh   # batería completa
```

**Desde el portátil con túnel SSH.** El host no llega a la red overlay, así que se levanta un reenviador temporal publicado solo en 127.0.0.1 del servidor:

```sh
# 1) en el servidor: reenviador temporal (no expone nada a Internet)
ssh -p 22022 root@217.154.182.5 'docker run -d --rm --name contactos-api-tunel --network easypanel-ia-support \
  -p 127.0.0.1:18000:8000 alpine/socat:1.8.0.1 tcp-listen:8000,fork,reuseaddr tcp:ia-support_contactos-api:8000'
# 2) en el portátil: túnel y pruebas
ssh -p 22022 -N -L 18000:127.0.0.1:18000 root@217.154.182.5 &
A=http://localhost:18000 sh pruebas/pruebas_api.sh      # o abrir http://localhost:18000/docs
# 3) al terminar
ssh -p 22022 root@217.154.182.5 'docker stop contactos-api-tunel'
```

### curl de cada endpoint

```sh
A=http://ia-support_contactos-api:8000      # o http://localhost:18000 con túnel
J='Content-Type: application/json'

curl $A/health
curl "$A/contactos?q=azure"
curl "$A/contactos?q=T001&incluir_bajas=true"
curl $A/contactos/16
curl -X POST $A/contactos -H "$J" -d '{"codigo":"T001","nombre":"Contacto Prueba n8n","tipo":"FACTURA","sesion":"abc123","usuario":"antonio"}'
curl -X POST $A/contactos -H "$J" -d '{"codigo":"T010","nombre":"Tienda Centro","tipo":"ALBARAN","cadena_id":16,"nif":"ESB12345674"}'
curl -X PATCH $A/contactos/45 -H "$J" -d '{"telefono":"600111222","sesion":"abc123"}'
curl -X PATCH $A/contactos/45 -H "$J" -d '{"tipo":"OTRO"}'                # → 422
curl -X DELETE "$A/contactos/45?sesion=abc123&usuario=antonio"
curl -X POST $A/log/2/undo -H "$J" -d '{"sesion":"abc123"}'
curl "$A/log?sesion=abc123"
```

## Flujo de prueba en n8n

Archivo: `n8n/flujo-prueba-contactos.json`, importado en n8n como **"Prueba API contactos"** (https://ia-support-n8n.kw2y1s.easypanel.host/workflow/EJw0EPoA3D3s4QzS). Nodos en cadena (todos HTTP Request sin credenciales y sin nodos comunitarios):

`Manual Trigger → Set (sesion = test-<ms>) → Buscar (GET ?q=azure) → Alta (POST T001) → Modificar (PATCH teléfono) → Deshacer (POST /log/{log_id}/undo) → Baja (DELETE) → Ver log (GET /log?sesion=)`

**Cómo lanzarlo**: abrir el flujo → **Execute workflow**. Todos los nodos deben quedar en verde; al pulsar cada uno se ve su respuesta. El último ("Ver log") muestra los 4 cambios de la sesión: ALTA, MODIF (revertido), UNDO y BAJA.

**Qué mirar en Odoo**: Contactos → Filtros → **Archivados** (o quitar el filtro por defecto) → buscar por *Referencia* `T001`.
- Después del flujo, el contacto "Contacto Prueba n8n" aparece **archivado**, sin teléfono (el deshacer lo dejó vacío), y el tipo de dirección es Factura.
- Para ver cada paso por separado, ejecuta los nodos uno a uno ("Execute step") y refresca la ficha en Odoo: tras **Alta** aparece activo, tras **Modificar** muestra el teléfono 600111222, tras **Deshacer** lo pierde y tras **Baja** queda archivado.
- Cada ejecución crea un T001 nuevo, porque el anterior ya está archivado.

## Operación

```sh
ssh -p 22022 root@217.154.182.5        # o ~/sshn8n (abre además el túnel de Easypanel en :3000)

docker service ls --filter name=ia-support_                       # estado
docker service logs -f --tail 100 ia-support_contactos-api        # logs de la API
docker service logs -f --tail 100 ia-support_odoo20               # logs de Odoo
docker service logs -f --tail 100 ia-support_surtidos-db          # logs de Postgres
docker exec -it $(docker ps -q -f name=ia-support_surtidos-db) psql -U odoo -d odoo   # consola SQL
#   select * from api.contactos_log order by id desc limit 20;
```

Los logs también están en Easypanel → ia-support → servicio → Logs.

### Backup

Backup puntual hecho antes de la entrega: `/root/backups/surtidos-odoo-20261015-1504.dump` (2 MB, formato custom de pg_dump). Para repetirlo:

```sh
mkdir -p /root/backups
docker exec $(docker ps -q -f name=ia-support_surtidos-db) pg_dump -U odoo -Fc odoo > /root/backups/surtidos-odoo-$(date +%Y%m%d-%H%M).dump
# restaurar en una BD vacía: pg_restore -U odoo -d <bd> --no-owner fichero.dump
```

El filestore de Odoo está en el volumen `odoo20-data` (`/var/lib/odoo`). Con solo Contactos apenas tiene contenido.

## Estructura

```
api/            Código de la API (main.py, nif.py, Dockerfile, requirements.txt)
n8n/            flujo-prueba-contactos.json
pruebas/        pruebas_api.sh (batería curl de punta a punta)
```
