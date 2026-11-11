"""Genera chat-ia-clientes-ayc.json (flujo de n8n) a partir de este script y de los .js de esta carpeta.

    python3 build_workflow.py

Un solo flujo con dos entradas:
- Chat → Agente clientes, con las herramientas consultar_clientes, consultar_precios_especiales,
  consultar_descuentos y consultar_surtido, y actualizar_precio_especial, actualizar_descuento y actualizar_surtido.
- Consulta (Execute Workflow Trigger) → ¿Condiciones? → ...: es lo que ejecutan las herramientas (se llama a sí mismo
  por su id fijo, WORKFLOW_ID; n8n solo admite un Execute Workflow Trigger por flujo, así que el campo accion
  elige el camino):
  - clientes: API clientes → Normalizar, para poner el dato en mayúsculas, quitar los espacios de relleno y
    devolver como mucho 10 clientes al modelo.
  - el resto (preciosEspeciales / descuentos / surtidos y actualizar…): ¿Buscar tabla? → API tabla (consultar) →
    Tabla → ¿Actualizar?. Si se da codigo_tabla se salta consultar.
    - consultar: ¿Hay tabla? → API productos (listarProductos) → ¿Surtido? → Normalizar condiciones o Normalizar
      surtido.
    - actualizar…: Preparar actualización → API líneas act → Plan actualización → (vista previa | ¿Ejecutar? →
      API actualizar → Resultado actualización → Tabla registro → Registro → Respuesta).
Los nodos Code llevan delante comun.js (funciones comunes).
"""
import json
from pathlib import Path

AQUI = Path(__file__).parent
API = 'http://88.27.249.204:50880/api'
SUBEMPRESA = 'AYC'
WORKFLOW_ID = 'ChatIaClienAYC01'
CREDENCIAL = {'httpHeaderAuth': {'id': 'AycApiKeyHeader1', 'name': 'API AYC (X-api-key)'}}
OPENROUTER = {'openRouterApi': {'id': 'BAhp65TskxSwWt7J', 'name': 'OpenRouter account'}}

SYSTEM = """=Eres el asistente de consulta de clientes del ERP de AYC. Hablas en español, con frases breves y claras. Trabajas SOLO con las herramientas; nunca inventes datos, códigos ni resultados.

## Conceptos
- código = código de cliente (p. ej. 4300017472). Muestra los códigos de artículo tal cual vienen, con sus ceros a la izquierda (0126, no 126). CIF = CIF/NIF/NIE del cliente.
- Un mismo CIF puede tener varios códigos de cliente (una ficha por dirección o tienda): son clientes distintos, distínguelos por dirección y población.
- precios especiales y descuentos: cada cliente tiene asignada una tabla de precios especiales y otra de descuentos (codigo, descripcion y cuántos clientes la comparten). Cada línea de la tabla tiene su precio en euros o su descuento en %, y las fechas desde y hasta (hasta vacío = sin fecha de fin; vigente = false significa que la línea aún no ha empezado). Casi todas son de un artículo (productos: código, descripción, marca y grupo), pero también puede haber líneas de una marca completa (marcas), de un grupo de una marca (grupos), de una familia del ERP (familias) o generales, sin marca ni artículo (generales). Las marcas, grupos y familias NO vienen desglosados en artículos: la herramienta no sabe qué artículos hay dentro, salvo los que tienen línea propia.
- surtido: cada cliente puede tener asignado un surtido (tabla con código, descripción y cuántos clientes lo comparten): la lista CERRADA de lo que se le puede vender; nada fuera del surtido. Sus líneas son de tres clases: artículos sueltos (productos, cada uno con su marca y su grupo), marcas completas (marcas: se le pueden vender TODOS los artículos de esa marca) y grupos de una marca (grupos: todos los artículos de ese grupo de esa marca, p. ej. el grupo "GR ENVUELTO DSOL 1" de DULCESOL). Las marcas y los grupos NO vienen desglosados en artículos: la herramienta no sabe qué artículos hay dentro. avisos son marcas especiales del surtido (p. ej. "CLIENTE SOLO ENDOSOS", "FIN DE SERVICIO", "CSA CLIENTE SOLO ART.AUTORIZADOS"), no artículos.
- cliente factura del surtido: cada línea del surtido es de un cliente factura, el subdistribuidor que hace el endoso (quien factura la venta; el comercial decide en la tienda si la venta la hace, p. ej., Vicky Foods u otro). "Genérico" = la línea vale sea quien sea el que factura. Una línea de un cliente factura concreto (p. ej. VICKY FOODS PRODUCTS SLU) solo vale cuando el endoso lo hace él. No tiene nada que ver con el "Factura a" de la ficha del cliente.
- cadena = nombre del cliente cadena (grupo o central al que pertenece). nombre_factura = nombre del cliente al que se factura. Vienen vacíos si no tiene o si son iguales al nombre: muéstralos SOLO si no están vacíos, como "Cadena: ..." y "Factura a: ...".

## Cómo trabajar
1. Para cualquier pregunta sobre un cliente usa consultar_clientes con el dato que dé el usuario: parte del nombre, CIF o código. Busca por un dato cada vez, el más distintivo (si da el CIF o el código, usa ese).
2. Si la búsqueda devuelve requiere_eleccion = true, muestra una lista numerada corta (nombre, código, CIF y población, más cadena y factura a si no están vacíos) y pide que elija. No elijas tú.
3. Si hay_mas = true, di cuántos hay en total (total), muestra los 10 primeros y propone acotar con más palabras del nombre, el CIF o el código.
4. Si no hay resultados, dilo y prueba o sugiere otra forma: menos palabras, una sola palabra significativa del nombre, con o sin tildes/Ñ, o el CIF.
5. Con un solo cliente (o cuando el usuario elige uno de la lista), muestra su ficha: nombre, código, CIF, dirección, código postal, población y provincia, y cadena y factura a si no están vacíos. Para preguntas posteriores sobre el mismo cliente usa los datos que ya tienes; no vuelvas a buscar si no hace falta.
6. Si una herramienta devuelve {"error": ...}, explícalo en lenguaje natural y propone reintentar. No muestres JSON ni nombres técnicos de campos.
7. Para precios especiales usa consultar_precios_especiales y para descuentos consultar_descuentos, con el código de cliente. Si el usuario da el nombre o el CIF, busca antes el cliente con consultar_clientes (y que elija si hay varios); si ya lo tienes en la conversación, usa su código. Si pregunta por un artículo concreto, pásalo en articulo (código o palabras de la descripción). Si da directamente un número de tabla, pásalo en codigo_tabla.
8. Al mostrar precios especiales o descuentos: primero la tabla (código, y descripción y cuántos clientes la comparten si vienen; si no vienen, no lo menciones). Después, solo si las hay, las líneas que no son de un artículo: generales ("General, sin marca ni artículo: 6 %"), marcas completas ("Marca completa CARRETILLA: 14 %"), grupos ("Grupo GR ENVUELTO DSOL 1 de DULCESOL: 14,65 %") y familias ("Familia X (prefamilia Y): ..."); de las clases que vengan vacías no digas nada (nunca "no hay descuentos generales", "no hay familias"...). Luego la lista de artículos (total_tabla en total) con código, descripción, precio (p. ej. 5,75 €) o descuento (p. ej. 15,4 %) y "hasta dd/mm/aaaa" solo si hasta no está vacío. Marca como "a partir del dd/mm/aaaa" las líneas con vigente = false. Si un artículo aparece dos veces con periodos distintos, muestra las dos. Si no hay ni artículos ni otras líneas, di que el cliente no tiene precios especiales (o descuentos) en esa tabla e indica la descripción de la tabla. Si hay_mas = true, di cuántos hay y propone filtrar por artículo o marca. Qué se aplica a un artículo (regla del ERP): la línea general vale para todos los artículos, salvo que haya otra más específica; manda la más concreta y vigente: la del artículo, si no la de su grupo, si no la de su marca, y si no la general. Si preguntan por un artículo concreto: si aparece en productos (vigente), se le aplica su línea; dilo así y no sumes ni mezcles la general, la de marca o la de grupo. Si no aparece, no digas que no tiene: si su marca o su grupo tienen línea (por productos[].marca/grupo de otros artículos, o porque lo dice el usuario), se aplica esa; si no sabes su marca ni su grupo, di qué se aplicaría en cada caso (p. ej. "si es del grupo GR ENVUELTO DSOL 1, 14,65 %; si no, el general del 6 %"). No ofrezcas comprobar la marca o el grupo de un artículo sin línea propia en la tabla: no hay forma de saberlo (aunque te den su código); como mucho, pregunta al usuario si sabe de qué grupo es. Si no hay ninguna línea que le afecte, no tiene precio especial (o descuento) en esa tabla. Las líneas de familia no entran en esta regla: muéstralas, sin decir si se aplican.
9. Para el surtido (qué se le puede vender a un cliente) usa consultar_surtido, igual que los precios: con el código de cliente (busca antes el cliente si hace falta), o codigo_tabla si da el número de surtido, y articulo para filtrar por código o palabras de la descripción (también la marca, que suele ir en la descripción). Muestra primero el surtido (código, descripción y cuántos clientes lo comparten), los avisos solo si hay alguno (si no hay, no los menciones), y después el contenido AGRUPADO POR CLIENTE FACTURA (clientes_factura: un apartado por cada uno, con su nombre y código, p. ej. "Si el endoso lo hace VICKY FOODS PRODUCTS SLU (4400000173)" y "Genérico (vale para cualquiera)"; cada marca, grupo y producto trae su cliente_factura). Si solo hay uno, no hagas apartados: di de quién es en una línea. Dentro de cada apartado, las marcas completas ("Marca completa: DULCESOL") y los grupos ("Grupo GR ENVUELTO DSOL 1 de DULCESOL"), con sus fechas como los artículos; si no hay marcas ni grupos, no los menciones. Luego cuántos artículos sueltos tiene (total_tabla) y la lista de artículos agrupada por marca (un encabezado por marca), cada uno con código y descripción, el grupo entre paréntesis si lo tiene, "hasta dd/mm/aaaa" solo si hasta no está vacío, y "a partir del dd/mm/aaaa" si vigente = false. Si hay_mas = true, di cuántos hay, resume por cliente factura cuántos artículos hay de cada marca (clientes_factura[].articulos_por_marca) y propone filtrar por marca, artículo o cliente factura. A "¿puedo venderle X?": filtra por X con las palabras clave (p. ej. "poker vainilla"); es SÍ si el artículo aparece en productos (y vigente), y entonces di su código y descripción y, si su cliente_factura no es Genérico, añade que solo cuando el endoso lo hace ese cliente factura. Si no aparece suelto pero su marca está en marcas, también es SÍ (por la marca completa). Si no aparece suelto y su marca solo tiene grupos en grupos, di que puede entrar si el artículo es de alguno de esos grupos (nómbralos), pero que no puedes comprobar el grupo de un artículo que no está en la lista. Si productos está vacío pero hay parecidos, no digas que no: muéstralos y pregunta si es alguno de ellos. Solo si no hay ni productos, ni parecidos, ni marca o grupo que pueda incluirlo, di que no aparece en su surtido. Si la herramienta dice que no se encontró la tabla de surtido 999, el cliente no tiene surtido asignado: dilo así, sin suponer que puede comprar de todo.
   Surtido de un cliente factura (p. ej. "¿qué surtido tiene Vicky Foods?"): un cliente factura no tiene surtido propio (la herramienta dirá que no tiene tabla de surtido asignada); sus líneas están dentro de los surtidos de los clientes. Dilo así y pregunta de qué surtido (número de tabla) quiere ver sus líneas. Con el número, llama a consultar_surtido con codigo_tabla y cliente_factura = su código de cliente, y muestra solo sus líneas; si cliente_factura.lineas_de_otros > 0, di cuántas líneas más tiene la tabla de otros clientes factura (incluido el genérico). Usa cliente_factura también cuando, de un cliente o una tabla, pidan solo las líneas de un cliente factura.
10. Puedes DAR DE ALTA o MODIFICAR líneas de precios especiales (actualizar_precio_especial), de descuentos (actualizar_descuento) y del surtido (actualizar_surtido). NO puedes borrar líneas: si piden quitar una, dilo y pregunta si quieren cerrarla poniéndole fecha fin (eso sí es una modificación). Cómo hacerlo, siempre en este orden:
   a) Necesitas el código del artículo (o de la marca o el grupo, si la línea es de marca completa o de grupo) y el código de cliente o el número de tabla. Si te dan el nombre del artículo, búscalo antes con la herramienta de consulta (filtrando por articulo) y usa su código; si no está en la tabla y es un alta, pide el código. El valor (precio o descuento) pásalo tal cual lo dice el usuario (p. ej. "1,25" o "6,5 %"). Las fechas, en dd/mm/aaaa ("a partir del 1 de diciembre" → fecha_desde 01/12 del año que toque); si no las dicen, déjalas vacías (alta: desde hoy y sin fin; modificación: se mantienen).
   b) Llama a la herramienta SIN confirmacion. Puede devolver vista_previa, pregunta, sin_cambios o error.
   c) vista_previa: muestra el cambio de forma clara: tabla (código y descripción), alta o modificación, producto (código y descripción), valor anterior → valor nuevo, fechas desde y hasta, y en surtidos el cliente factura. Si tabla_compartida es true, avisa en negrita: "Esta tabla la comparten N clientes: el cambio les afecta a todos". Si tabla_compartida es null, avisa de que la tabla puede estar compartida por otros clientes. Termina preguntando "¿Confirmas el cambio?" y escribe al final, entre paréntesis, "código de confirmación: " y el codigo_confirmacion.
   d) Solo cuando el usuario conteste que SÍ de forma explícita (sí, confirmo, adelante...) en su siguiente mensaje, vuelve a llamar a la herramienta con EXACTAMENTE los mismos datos y confirmacion = ese código. Nunca confirmes por tu cuenta, ni en la misma respuesta que la vista previa, ni con un código inventado. Si cambia algún dato, empieza de nuevo por b).
   e) pregunta: hazle la pregunta al usuario (con las opciones o líneas que vengan) y vuelve a b) con su respuesta. sin_cambios: díselo. error: explícalo.
   f) resultado: si guardado es true, confirma lo que ha quedado (alta o modificación, valor y fechas); si es false, explica el mensaje de la API. No digas que se ha guardado si guardado no es true.
   g) Para cambiar un valor a partir de una fecha manteniendo el actual hasta entonces hacen falta dos cambios: cerrar la línea actual (fecha_fin = el día anterior) y dar de alta la nueva desde esa fecha, cada uno con su vista previa y su confirmación.
11. No tienes datos de otras cosas (pedidos, facturas, albaranes, stock...): si te los piden, indica que de momento no puedes."""

TOOL_DESC = ('Busca clientes en el ERP por parte del nombre, CIF/NIF o código de cliente. '
             'Devuelve total, requiere_eleccion, hay_mas y hasta 10 resultados con codigo, nombre, '
             'cadena, nombre_factura, cif, direccion, codigo_postal, poblacion y provincia.')
SURTIDO_DESC = ('Consulta el surtido asignado a un cliente (por su código de cliente) o un surtido por su código: '
                'la lista cerrada de lo que se le puede vender. Con cliente_factura, solo las líneas de ese cliente factura. Devuelve tabla (codigo, descripcion, '
                'num_clientes), avisos (marcas especiales del surtido), clientes_factura (por cada cliente '
                'factura de las líneas: codigo, nombre, marcas, grupos, articulos y articulos_por_marca), marcas (marcas completas incluidas), '
                'grupos (grupos de una marca incluidos completos), total_tabla (artículos sueltos), '
                'total, hay_mas, hasta 60 productos con articulo, descripcion, marca, grupo, cliente_factura, '
                'desde, hasta (vacío = sin fecha de fin) y vigente, y parecidos (si al filtrar por articulo no hay '
                'coincidencia exacta). marcas y grupos van siempre completos, aunque se filtre por articulo.')
CONDICIONES_DESC = ('Consulta la tabla de {que} asignada a un cliente (por su código de cliente) o una tabla por su '
                    'código, y lista sus líneas. Devuelve tabla (codigo, descripcion, num_clientes); generales, marcas, '
                    'grupos y familias (líneas que no son de un artículo, siempre completas aunque se filtre por articulo); '
                    'total_tabla (artículos), total, hay_mas y hasta 60 productos con articulo, descripcion, marca, grupo, '
                    '{campo}, desde, hasta (vacío = sin fin) y vigente.')


def nodo(id_, nombre, tipo, version, pos, params, **extra):
    return {'parameters': params, 'id': id_, 'name': nombre, 'type': tipo,
            'typeVersion': version, 'position': pos, **extra}


ENTRADAS = ['accion', 'dato', 'codigo_cliente', 'codigo_tabla', 'articulo', 'cliente_factura',
            'codigo_marca', 'codigo_grupo', 'valor', 'fecha_desde', 'fecha_fin', 'confirmacion']


def entradas(**valores):
    """workflowInputs de una herramienta: todas las entradas de Consulta, vacías salvo las que se den."""
    return {
        'mappingMode': 'defineBelow',
        'value': {n: valores.get(n, '') for n in ENTRADAS},
        'matchingColumns': [],
        'schema': [{'id': n, 'displayName': n, 'required': False, 'defaultMatch': False,
                    'display': True, 'canBeUsedToMatch': True, 'type': 'string'} for n in ENTRADAS],
        'attemptToConvertTypes': False,
        'convertFieldsToString': False,
    }


def herramienta_condiciones(id_, nombre, pos, accion, que, campo=None, descripcion=None, **extra):
    return nodo(id_, nombre, '@n8n/n8n-nodes-langchain.toolWorkflow', 2.2, pos, {
        'description': descripcion or CONDICIONES_DESC.format(que=que, campo=campo),
        'workflowId': {'__rl': True, 'mode': 'id', 'value': WORKFLOW_ID},
        'workflowInputs': entradas(
            accion=accion,
            codigo_cliente="={{ $fromAI('codigo_cliente', 'Código de cliente (p. ej. 4300016289); vacío si se da codigo_tabla', 'string', '') }}",
            codigo_tabla=f"={{{{ $fromAI('codigo_tabla', 'Código de la tabla de {que}, solo si el usuario lo da; si no, vacío', 'string', '') }}}}",
            articulo="={{ $fromAI('articulo', 'Código o palabras de la descripción, la marca o el grupo del artículo para filtrar; vacío para todos', 'string', '') }}",
            **extra),
    })


ACTUALIZAR_DESC = ('Da de alta o modifica una línea de {que} (un artículo, o una marca completa o un grupo). Primero '
                   'llámala sin confirmacion: devuelve vista_previa (con codigo_confirmacion), pregunta, sin_cambios o '
                   'error. Solo cuando el usuario haya confirmado la vista previa, llámala otra vez con los mismos datos '
                   'y confirmacion = codigo_confirmacion: devuelve resultado (guardado true/false). No borra líneas.')


def herramienta_actualizar(id_, nombre, pos, accion, que, valor=None, cliente_factura=False):
    """Herramienta de alta/modificación: llama a Consulta con accion=actualizar…"""
    extra = {}
    if valor:
        extra['valor'] = f"={{{{ $fromAI('valor', '{valor}, tal como lo dice el usuario (p. ej. 1,25)', 'string', '') }}}}"
    if cliente_factura:
        extra['cliente_factura'] = ("={{ $fromAI('cliente_factura', 'Cliente factura de la línea (0000000001 genérico, "
                                    "4400000173 Vicky Foods...): el consultado o el que elija el usuario; vacío si no se sabe', 'string', '') }}")
    return nodo(id_, nombre, '@n8n/n8n-nodes-langchain.toolWorkflow', 2.2, pos, {
        'description': ACTUALIZAR_DESC.format(que=que),
        'workflowId': {'__rl': True, 'mode': 'id', 'value': WORKFLOW_ID},
        'workflowInputs': entradas(
            accion=accion,
            codigo_cliente="={{ $fromAI('codigo_cliente', 'Código del cliente cuya tabla se cambia (p. ej. 4300016289); vacío si se da codigo_tabla', 'string', '') }}",
            codigo_tabla="={{ $fromAI('codigo_tabla', 'Número de la tabla, solo si el usuario lo da; si no, vacío', 'string', '') }}",
            articulo="={{ $fromAI('articulo', 'Código del artículo (p. ej. 14403), no su descripción; vacío si la línea es de marca o de grupo', 'string', '') }}",
            codigo_marca="={{ $fromAI('codigo_marca', 'Código de la marca, solo para una línea de marca completa o de grupo; si no, vacío', 'string', '') }}",
            codigo_grupo="={{ $fromAI('codigo_grupo', 'Código del grupo, solo para una línea de grupo; si no, vacío', 'string', '') }}",
            fecha_desde="={{ $fromAI('fecha_desde', 'Fecha desde dd/mm/aaaa; vacío = por defecto (alta: hoy; modificación: la de la línea)', 'string', '') }}",
            fecha_fin="={{ $fromAI('fecha_fin', 'Fecha fin dd/mm/aaaa; vacío = por defecto (alta: sin fin; modificación: la de la línea)', 'string', '') }}",
            confirmacion="={{ $fromAI('confirmacion', 'Vacío la primera vez. Solo después de que el usuario confirme la vista previa: su codigo_confirmacion', 'string', '') }}",
            **extra),
    })


def si(id_, nombre, pos, condicion):
    """Nodo If con una condición booleana (expresión)."""
    return nodo(id_, nombre, 'n8n-nodes-base.if', 2.2, pos, {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 2},
            'conditions': [{'id': f'{id_}-c', 'leftValue': condicion, 'rightValue': '',
                            'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
            'combinator': 'and',
        },
        'options': {},
    })


def api(id_, nombre, pos, url, parametros):
    """HTTP Request a la API de AYC: respuesta como texto (un array vacío daría 0 items y el subflujo no
    devolvería nada) y sin cortar el flujo si falla (el error lo trata el Code siguiente).
    2 intentos con 0,3 s entre ellos: la API da a veces un 500 que se arregla al repetir (p. ej. con CARTAGENA).
    n8n reintenta también los 4xx, que siempre dan lo mismo: con 3 intentos y 1 s de espera, un 404 ("no hay
    tabla") tardaba 2,6 s; así tarda ~0,7 s. No se usa neverError porque entonces tampoco se reintentan los 500.
    Tiempo máximo 15 s por intento (antes 30 s × 3)."""
    return nodo(id_, nombre, 'n8n-nodes-base.httpRequest', 4.2, pos, {
        'method': 'GET',
        'url': url,
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendQuery': True,
        'queryParameters': {'parameters': parametros + [{'name': 'subEmpresa', 'value': SUBEMPRESA}]},
        'options': {'response': {'response': {'responseFormat': 'text', 'outputPropertyName': 'data'}},
                    'timeout': 15000},
    }, credentials=CREDENCIAL, retryOnFail=True, maxTries=2, waitBetweenTries=300,
        onError='continueRegularOutput')


def codigo(id_, nombre, pos, *ficheros):
    """Nodo Code con comun.js y uno o varios .js detrás (se concatenan; sin la línea module.exports de numero_es.js)."""
    js = '\n'.join((AQUI / f).read_text() for f in ('comun.js', *ficheros))
    js = '\n'.join(l for l in js.splitlines() if 'module.exports' not in l) + '\n'
    return nodo(id_, nombre, 'n8n-nodes-base.code', 2, pos, {'jsCode': js})


# accion → base de la URL de la API (/api/<base>/...). La misma tabla está en comun.js (TIPOS).
BASES = ('{preciosEspeciales: "preciosEspeciales", descuentos: "descuentos", surtidos: "surtidos", '
         'actualizarPreciosEspeciales: "preciosEspeciales", actualizarDescuentos: "descuentos", '
         'actualizarSurtidos: "surtidos"}')
REGISTRO = 'Cambios ERP AYC'
COLUMNAS_REGISTRO = [('fecha', 'date'), ('usuario', 'string'), ('tipo', 'string'), ('codigo_tabla', 'number'),
                     ('codigo_cliente', 'string'), ('cliente_factura', 'string'), ('producto', 'string'),
                     ('operacion', 'string'), ('valor_anterior', 'string'), ('valor_nuevo', 'string'),
                     ('fecha_desde', 'string'), ('fecha_fin', 'string'), ('resultado', 'string'),
                     ('mensaje', 'string'), ('peticion', 'string')]

nodes = [
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e01', 'Chat', '@n8n/n8n-nodes-langchain.chatTrigger', 1.1, [0, 0], {
        'public': True,
        'mode': 'hostedChat',
        'authentication': 'basicAuth',
        'initialMessages': 'Hola 👋 Soy el asistente de clientes de AYC. Puedo buscar clientes por nombre, CIF o código, consultar sus precios especiales, descuentos y surtido, y darlos de alta o modificarlos (siempre con tu confirmación). ¿Qué necesitas?',
        'options': {
            'title': 'Asistente de clientes AYC',
            'subtitle': 'ia-support · clientes, precios especiales, descuentos y surtidos',
            'inputPlaceholder': 'Ej.: busca Ñam Ñam / precios especiales del 4300016289…',
        },
    }, webhookId='6d2b7e41-58c3-4f0a-a9e2-4b1d9c0e7a31',
        credentials={'httpBasicAuth': {'id': 'AlbIaBasicAuth01', 'name': 'Albaranes IA - Basic Auth'}}),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e02', 'Agente clientes', '@n8n/n8n-nodes-langchain.agent', 2.2, [300, 0], {
        'options': {'systemMessage': SYSTEM, 'maxIterations': 10},
    }),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e03', 'OpenRouter', '@n8n/n8n-nodes-langchain.lmChatOpenRouter', 1, [0, 300], {
        'model': 'anthropic/claude-haiku-5.5',
        'options': {'temperature': 0.1},
    }, credentials=OPENROUTER),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e04', 'Memoria', '@n8n/n8n-nodes-langchain.memoryBufferWindow', 1.3, [200, 300], {
        'contextWindowLength': 20,
    }),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e05', 'consultar_clientes', '@n8n/n8n-nodes-langchain.toolWorkflow', 2.2, [400, 300], {
        'description': TOOL_DESC,
        'workflowId': {'__rl': True, 'mode': 'id', 'value': WORKFLOW_ID},
        'workflowInputs': entradas(
            accion='clientes',
            dato="={{ $fromAI('dato', 'Parte del nombre, CIF/NIF o código de cliente a buscar', 'string') }}"),
    }),
    herramienta_condiciones('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e09', 'consultar_precios_especiales', [600, 300],
                            'preciosEspeciales', 'precios especiales', 'precio (euros)'),
    herramienta_condiciones('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e10', 'consultar_descuentos', [800, 300],
                            'descuentos', 'descuentos', 'descuento (%)'),
    herramienta_actualizar('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e21', 'actualizar_precio_especial', [1200, 300],
                           'actualizarPreciosEspeciales', 'precios especiales', valor='Precio nuevo en euros'),
    herramienta_actualizar('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e22', 'actualizar_descuento', [1400, 300],
                           'actualizarDescuentos', 'descuentos', valor='Descuento nuevo en %'),
    herramienta_actualizar('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e23', 'actualizar_surtido', [1600, 300],
                           'actualizarSurtidos', 'surtido', cliente_factura=True),
    herramienta_condiciones('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e18', 'consultar_surtido', [1000, 300],
                            'surtidos', 'surtido', descripcion=SURTIDO_DESC,
                            cliente_factura="={{ $fromAI('cliente_factura', 'Código del cliente factura (p. ej. 4400000173 de Vicky Foods, 0000000001 el genérico) para ver solo sus líneas; vacío para todas', 'string', '') }}"),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e06', 'Consulta', 'n8n-nodes-base.executeWorkflowTrigger', 1.1, [0, 600], {
        'workflowInputs': {'values': [{'name': n} for n in ENTRADAS]},
    }),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e11', '¿Condiciones?', [220, 600],
       f'={{{{ Object.keys({BASES}).includes($json.accion) }}}}'),
    api('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e07', 'API clientes', [440, 800], f'{API}/clientes/consultarClientes', [
        # La API distingue mayúsculas: "cartagena" no encuentra nada y "CARTAGENA" sí.
        {'name': 'dato', 'value': '={{ String($json.dato || "").trim().toUpperCase() }}'},
    ]),
    codigo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e08', 'Normalizar', [660, 800], 'normalizar.js'),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e12', '¿Buscar tabla?', [440, 500],
       '={{ !String($json.codigo_tabla || "").trim() && !!String($json.codigo_cliente || "").trim() }}'),
    api('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e13', 'API tabla', [660, 400],
        f'={{{{ "{API}/" + ({BASES})[$json.accion] + "/consultar" }}}}', [
            {'name': 'codigoCliente', 'value': '={{ String($json.codigo_cliente || "").trim() }}'},
        ]),
    codigo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e14', 'Tabla', [880, 500], 'tabla.js'),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e30', '¿Actualizar?', [1100, 500],
       '={{ String($("Consulta").first().json.accion || "").startsWith("actualizar") }}'),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e15', '¿Hay tabla?', [1320, 500], '={{ !!$json.tabla }}'),
    api('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e16', 'API productos', [1540, 400],
        f'={{{{ "{API}/" + $("Consulta").first().json.accion + "/listarProductos" }}}}', [
            {'name': 'codigoTabla', 'value': '={{ $json.tabla.codigo }}'},
        ]),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e19', '¿Surtido?', [1760, 500],
       '={{ $("Consulta").first().json.accion === "surtidos" }}'),
    codigo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e17', 'Normalizar condiciones', [1980, 600], 'normalizar_condiciones.js'),
    codigo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e20', 'Normalizar surtido', [1980, 400], 'normalizar_surtido.js'),
    # --- Altas y modificaciones (accion = actualizar…), detrás de ¿Actualizar?
    codigo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e33', 'Preparar actualización', [770, 1100],
           'numero_es.js', 'preparar_actualizacion.js'),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e34', '¿Preparado?', [990, 1100], '={{ !$json.error }}'),
    api('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e35', 'API líneas act', [1210, 1000],
        f'={{{{ "{API}/" + $json.base + "/listarProductos" }}}}', [
            {'name': 'codigoTabla', 'value': '={{ $json.tabla.codigo }}'},
            {'name': 'codigoArticulo', 'value': '={{ $json.producto.codigoArticulo }}'},
            {'name': 'codigoMarca', 'value': '={{ $json.producto.codigoMarca }}'},
            {'name': 'codigoGrupo', 'value': '={{ $json.producto.codigoGrupo }}'},
        ]),
    codigo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e36', 'Plan actualización', [1430, 1100], 'plan_actualizacion.js'),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e37', '¿Ejecutar?', [1650, 1100], '={{ $json.ejecutar === true }}'),
    # POST sin reintentos (no repetir un alta). 'Send Body' fijo a true y cuerpo en modo JSON: como expresión, n8n
    # no lo evalúa y manda el POST vacío.
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e38', 'API actualizar', 'n8n-nodes-base.httpRequest', 4.2, [1870, 1000], {
        'method': 'POST',
        'url': f'={{{{ "{API}/" + $json.base + "/actualizar" }}}}',
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendBody': True,
        'contentType': 'json',
        'specifyBody': 'json',
        'jsonBody': '={{ JSON.stringify($json.body) }}',
        'options': {'response': {'response': {'responseFormat': 'text', 'outputPropertyName': 'data'}},
                    'timeout': 60000},
    }, credentials=CREDENCIAL, onError='continueRegularOutput'),
    codigo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e39', 'Resultado actualización', [2090, 1000], 'resultado_actualizacion.js'),
    # Registro de cambios en la Data Table (se crea la primera vez). Si falla, el cambio ya está hecho: se avisa.
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e40', 'Tabla registro', 'n8n-nodes-base.dataTable', 1.1, [2310, 1000], {
        'resource': 'table',
        'operation': 'create',
        'tableName': REGISTRO,
        'columns': {'column': [{'name': n, 'type': tipo} for n, tipo in COLUMNAS_REGISTRO]},
        'options': {'createIfNotExists': True},
    }, onError='continueRegularOutput'),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e41', 'Registro', 'n8n-nodes-base.dataTable', 1.1, [2530, 1000], {
        'resource': 'row',
        'operation': 'insert',
        'dataTableId': {'__rl': True, 'mode': 'name', 'value': REGISTRO},
        'columns': {
            'mappingMode': 'defineBelow',
            'value': {n: f"={{{{ $('Resultado actualización').first().json.fila.{n} }}}}" for n, _ in COLUMNAS_REGISTRO},
            'matchingColumns': [],
            'schema': [{'id': n, 'displayName': n, 'required': False, 'defaultMatch': False, 'display': True,
                        'type': tipo, 'readOnly': False, 'removed': False} for n, tipo in COLUMNAS_REGISTRO],
            'attemptToConvertTypes': False,
            'convertFieldsToString': False,
        },
        'options': {},
    }, onError='continueRegularOutput'),
    # Vista previa, pregunta o error: el subflujo devuelve la salida del último nodo, y si es la rama "false" de un
    # If no devuelve nada. Este nodo las recoge.
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e43', 'Sin ejecutar', 'n8n-nodes-base.code', 2, [1870, 1200], {
        'jsCode': 'return $input.all();\n',
    }),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e42', 'Respuesta actualización', 'n8n-nodes-base.code', 2, [2750, 1000], {
        'jsCode': ("const r = $('Resultado actualización').first().json.respuesta;\n"
                   "const reg = $input.first().json;\n"
                   "return [{ json: { ...r, registro: reg.error ? 'No se ha podido apuntar en el registro de cambios.' "
                   ": 'Apuntado en el registro de cambios.' } }];\n"),
    }),
]


def enlace(destino, tipo='main'):
    return {tipo: [[{'node': destino, 'type': tipo, 'index': 0}]]}


def bifurca(si_, no):
    """Salidas true y false de un nodo If."""
    return {'main': [[{'node': si_, 'type': 'main', 'index': 0}], [{'node': no, 'type': 'main', 'index': 0}]]}


connections = {
    'Chat': enlace('Agente clientes'),
    'OpenRouter': enlace('Agente clientes', 'ai_languageModel'),
    'Memoria': enlace('Agente clientes', 'ai_memory'),
    'consultar_clientes': enlace('Agente clientes', 'ai_tool'),
    'consultar_precios_especiales': enlace('Agente clientes', 'ai_tool'),
    'consultar_descuentos': enlace('Agente clientes', 'ai_tool'),
    'consultar_surtido': enlace('Agente clientes', 'ai_tool'),
    'actualizar_precio_especial': enlace('Agente clientes', 'ai_tool'),
    'actualizar_descuento': enlace('Agente clientes', 'ai_tool'),
    'actualizar_surtido': enlace('Agente clientes', 'ai_tool'),
    'Consulta': enlace('¿Condiciones?'),
    'Preparar actualización': enlace('¿Preparado?'),
    '¿Preparado?': bifurca('API líneas act', 'Sin ejecutar'),
    'API líneas act': enlace('Plan actualización'),
    'Plan actualización': enlace('¿Ejecutar?'),
    '¿Ejecutar?': bifurca('API actualizar', 'Sin ejecutar'),
    'API actualizar': enlace('Resultado actualización'),
    'Resultado actualización': enlace('Tabla registro'),
    'Tabla registro': enlace('Registro'),
    'Registro': enlace('Respuesta actualización'),
    '¿Condiciones?': bifurca('¿Buscar tabla?', 'API clientes'),
    'API clientes': enlace('Normalizar'),
    '¿Buscar tabla?': bifurca('API tabla', 'Tabla'),
    'API tabla': enlace('Tabla'),
    'Tabla': enlace('¿Actualizar?'),
    '¿Actualizar?': bifurca('Preparar actualización', '¿Hay tabla?'),
    '¿Hay tabla?': bifurca('API productos', '¿Surtido?'),
    'API productos': enlace('¿Surtido?'),
    '¿Surtido?': bifurca('Normalizar surtido', 'Normalizar condiciones'),
}

flujo = {'id': WORKFLOW_ID, 'name': 'Chat IA clientes AYC', 'nodes': nodes, 'connections': connections,
         'settings': {'executionOrder': 'v1'}, 'pinData': {}}
(AQUI / 'chat-ia-clientes-ayc.json').write_text(json.dumps(flujo, ensure_ascii=False, indent=2) + '\n')
print('chat-ia-clientes-ayc.json generado')
