"""Genera chat-ia-clientes-ayc.json (flujo de n8n) a partir de este script y de normalizar.js.

    python3 build_workflow.py

Un solo flujo con dos entradas:
- Chat → Agente clientes, con las herramientas consultar_clientes, consultar_precios_especiales,
  consultar_descuentos y consultar_surtido.
- Consulta (Execute Workflow Trigger) → ¿Condiciones? → ...: es lo que ejecutan las herramientas (se llama a sí mismo
  por su id fijo, WORKFLOW_ID; n8n solo admite un Execute Workflow Trigger por flujo, así que el campo accion
  elige el camino):
  - clientes: API clientes → Normalizar, para poner el dato en mayúsculas, reintentar, quitar los espacios de
    relleno y devolver como mucho 10 clientes al modelo.
  - preciosEspeciales / descuentos / surtidos: ¿Buscar tabla? → API tabla cliente (consultar) → Tabla →
    ¿Hay tabla? → API productos (listarProductos) → ¿Surtido? → Normalizar condiciones o Normalizar surtido.
    Si se da codigo_tabla se salta consultar.
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
- precios especiales y descuentos: cada cliente tiene asignada una tabla de precios especiales y otra de descuentos (codigo, descripcion y cuántos clientes la comparten). Cada línea de la tabla es un artículo (codigo y descripción) con su precio en euros o su descuento en %, y las fechas desde y hasta. vigente = false significa que la línea aún no ha empezado.
- surtido: cada cliente puede tener asignado un surtido (tabla con código, descripción y cuántos clientes lo comparten): la lista CERRADA de lo que se le puede vender; nada fuera del surtido. Sus líneas son de tres clases: artículos sueltos (productos, cada uno con su marca y su grupo), marcas completas (marcas: se le pueden vender TODOS los artículos de esa marca) y grupos de una marca (grupos: todos los artículos de ese grupo de esa marca, p. ej. el grupo "GR ENVUELTO DSOL 1" de DULCESOL). Las marcas y los grupos NO vienen desglosados en artículos: la herramienta no sabe qué artículos hay dentro. avisos son marcas especiales del surtido (p. ej. "CLIENTE SOLO ENDOSOS", "FIN DE SERVICIO", "CSA CLIENTE SOLO ART.AUTORIZADOS"), no artículos.
- cadena = nombre del cliente cadena (grupo o central al que pertenece). nombre_factura = nombre del cliente al que se factura. Vienen vacíos si no tiene o si son iguales al nombre: muéstralos SOLO si no están vacíos, como "Cadena: ..." y "Factura a: ...".

## Cómo trabajar
1. Para cualquier pregunta sobre un cliente usa consultar_clientes con el dato que dé el usuario: parte del nombre, CIF o código. Busca por un dato cada vez, el más distintivo (si da el CIF o el código, usa ese).
2. Si la búsqueda devuelve requiere_eleccion = true, muestra una lista numerada corta (nombre, código, CIF y población, más cadena y factura a si no están vacíos) y pide que elija. No elijas tú.
3. Si hay_mas = true, di cuántos hay en total (total), muestra los 10 primeros y propone acotar con más palabras del nombre, el CIF o el código.
4. Si no hay resultados, dilo y prueba o sugiere otra forma: menos palabras, una sola palabra significativa del nombre, con o sin tildes/Ñ, o el CIF.
5. Con un solo cliente (o cuando el usuario elige uno de la lista), muestra su ficha: nombre, código, CIF, dirección, código postal, población y provincia, y cadena y factura a si no están vacíos. Para preguntas posteriores sobre el mismo cliente usa los datos que ya tienes; no vuelvas a buscar si no hace falta.
6. Si una herramienta devuelve {"error": ...}, explícalo en lenguaje natural y propone reintentar. No muestres JSON ni nombres técnicos de campos.
7. Para precios especiales usa consultar_precios_especiales y para descuentos consultar_descuentos, con el código de cliente. Si el usuario da el nombre o el CIF, busca antes el cliente con consultar_clientes (y que elija si hay varios); si ya lo tienes en la conversación, usa su código. Si pregunta por un artículo concreto, pásalo en articulo (código o palabras de la descripción). Si da directamente un número de tabla, pásalo en codigo_tabla.
8. Al mostrar precios especiales o descuentos: primero la tabla (código, y descripción y cuántos clientes la comparten si vienen; si no vienen, no lo menciones) y después la lista de artículos con código, descripción, precio (p. ej. 5,75 €) o descuento (p. ej. 15,4 %) y "hasta dd/mm/aaaa". Marca como "a partir del dd/mm/aaaa" las líneas con vigente = false. Si un artículo aparece dos veces con periodos distintos, muestra las dos. Si total = 0, di que el cliente no tiene precios especiales (o descuentos) en esa tabla e indica la descripción de la tabla. Si hay_mas = true, di cuántos hay y propone filtrar por artículo.
9. Para el surtido (qué se le puede vender a un cliente) usa consultar_surtido, igual que los precios: con el código de cliente (busca antes el cliente si hace falta), o codigo_tabla si da el número de surtido, y articulo para filtrar por código o palabras de la descripción (también la marca, que suele ir en la descripción). Muestra primero el surtido (código, descripción y cuántos clientes lo comparten), los avisos solo si hay alguno (si no hay, no los menciones), y después, si las hay, las marcas completas ("Marca completa: DULCESOL") y los grupos ("Grupo GR ENVUELTO DSOL 1 de DULCESOL"), con sus fechas como los artículos; si no hay marcas ni grupos, no los menciones. Luego cuántos artículos sueltos tiene (total_tabla) y la lista de artículos agrupada por marca (un encabezado por marca), cada uno con código y descripción, el grupo entre paréntesis si lo tiene, "hasta dd/mm/aaaa" solo si hasta no está vacío, y "a partir del dd/mm/aaaa" si vigente = false. Si hay_mas = true, di cuántos hay, resume cuántos artículos hay de cada marca (articulos_por_marca) y propone filtrar por marca o artículo. A "¿puedo venderle X?": filtra por X con las palabras clave (p. ej. "poker vainilla"); es SÍ si el artículo aparece en productos (y vigente), y entonces di su código y descripción. Si no aparece suelto pero su marca está en marcas, también es SÍ (por la marca completa). Si no aparece suelto y su marca solo tiene grupos en grupos, di que puede entrar si el artículo es de alguno de esos grupos (nómbralos), pero que no puedes comprobar el grupo de un artículo que no está en la lista. Si productos está vacío pero hay parecidos, no digas que no: muéstralos y pregunta si es alguno de ellos. Solo si no hay ni productos, ni parecidos, ni marca o grupo que pueda incluirlo, di que no aparece en su surtido. Si la herramienta dice que no se encontró la tabla de surtido 999, el cliente no tiene surtido asignado: dilo así, sin suponer que puede comprar de todo.
10. Solo puedes CONSULTAR clientes, sus precios especiales, sus descuentos y su surtido. Si te piden dar de alta, modificar o borrar algo, o datos de otras cosas (pedidos, facturas, albaranes, stock...), indica que de momento no puedes."""

TOOL_DESC = ('Busca clientes en el ERP por parte del nombre, CIF/NIF o código de cliente. '
             'Devuelve total, requiere_eleccion, hay_mas y hasta 10 resultados con codigo, nombre, '
             'cadena, nombre_factura, cif, direccion, codigo_postal, poblacion y provincia.')
SURTIDO_DESC = ('Consulta el surtido asignado a un cliente (por su código de cliente) o un surtido por su código: '
                'la lista cerrada de lo que se le puede vender. Devuelve tabla (codigo, descripcion, '
                'num_clientes), avisos (marcas especiales del surtido), marcas (marcas completas incluidas), '
                'grupos (grupos de una marca incluidos completos), total_tabla (artículos sueltos), '
                'articulos_por_marca, total, hay_mas, hasta 60 productos con articulo, descripcion, marca, grupo, '
                'desde, hasta (vacío = sin fecha de fin) y vigente, y parecidos (si al filtrar por articulo no hay '
                'coincidencia exacta). marcas y grupos van siempre completos, aunque se filtre por articulo.')
CONDICIONES_DESC = ('Consulta la tabla de {que} asignada a un cliente (por su código de cliente) o una tabla por su '
                    'código, y lista sus artículos. Devuelve tabla (codigo, descripcion, num_clientes), total, hay_mas '
                    'y hasta 60 productos con articulo, descripcion, {campo}, desde, hasta y vigente.')


def nodo(id_, nombre, tipo, version, pos, params, **extra):
    return {'parameters': params, 'id': id_, 'name': nombre, 'type': tipo,
            'typeVersion': version, 'position': pos, **extra}


ENTRADAS = ['accion', 'dato', 'codigo_cliente', 'codigo_tabla', 'articulo']


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


def herramienta_condiciones(id_, nombre, pos, accion, que, campo=None, descripcion=None):
    return nodo(id_, nombre, '@n8n/n8n-nodes-langchain.toolWorkflow', 2.2, pos, {
        'description': descripcion or CONDICIONES_DESC.format(que=que, campo=campo),
        'workflowId': {'__rl': True, 'mode': 'id', 'value': WORKFLOW_ID},
        'workflowInputs': entradas(
            accion=accion,
            codigo_cliente="={{ $fromAI('codigo_cliente', 'Código de cliente (p. ej. 4300016289); vacío si se da codigo_tabla', 'string', '') }}",
            codigo_tabla=f"={{{{ $fromAI('codigo_tabla', 'Código de la tabla de {que}, solo si el usuario lo da; si no, vacío', 'string', '') }}}}",
            articulo="={{ $fromAI('articulo', 'Código o palabras de la descripción del artículo (o de la marca o el grupo, en surtidos) para filtrar; vacío para todos', 'string', '') }}"),
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
    devolvería nada), 3 intentos y sin cortar el flujo si falla (el error lo trata el Code siguiente)."""
    return nodo(id_, nombre, 'n8n-nodes-base.httpRequest', 4.2, pos, {
        'method': 'GET',
        'url': url,
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendQuery': True,
        'queryParameters': {'parameters': parametros + [{'name': 'subEmpresa', 'value': SUBEMPRESA}]},
        'options': {'response': {'response': {'responseFormat': 'text', 'outputPropertyName': 'data'}},
                    'timeout': 30000},
    }, credentials=CREDENCIAL, retryOnFail=True, maxTries=3, waitBetweenTries=1000,
        onError='continueRegularOutput')


nodes = [
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e01', 'Chat', '@n8n/n8n-nodes-langchain.chatTrigger', 1.1, [0, 0], {
        'public': True,
        'mode': 'hostedChat',
        'authentication': 'basicAuth',
        'initialMessages': 'Hola 👋 Soy el asistente de clientes de AYC. Puedo buscar clientes por nombre, CIF o código, y consultar sus precios especiales, descuentos y surtido. ¿Qué necesitas?',
        'options': {
            'title': 'Asistente de clientes AYC',
            'subtitle': 'ia-support · clientes, precios especiales, descuentos y surtidos',
            'inputPlaceholder': 'Ej.: busca Ñam Ñam / precios especiales del 4300016289…',
        },
    }, webhookId='6d2b7e41-58c3-4f0a-a9e2-4b1d9c0e7a31',
        credentials={'httpBasicAuth': {'id': 'AlbIaBasicAuth01', 'name': 'Albaranes IA - Basic Auth'}}),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e02', 'Agente clientes', '@n8n/n8n-nodes-langchain.agent', 2.2, [300, 0], {
        'options': {'systemMessage': SYSTEM, 'maxIterations': 8},
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
    herramienta_condiciones('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e18', 'consultar_surtido', [1000, 300],
                            'surtidos', 'surtido', descripcion=SURTIDO_DESC),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e06', 'Consulta', 'n8n-nodes-base.executeWorkflowTrigger', 1.1, [0, 600], {
        'workflowInputs': {'values': [{'name': n} for n in ENTRADAS]},
    }),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e11', '¿Condiciones?', [220, 600],
       '={{ ["preciosEspeciales", "descuentos", "surtidos"].includes($json.accion) }}'),
    api('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e07', 'API clientes', [440, 800], f'{API}/clientes/consultarClientes', [
        # La API distingue mayúsculas: "cartagena" no encuentra nada y "CARTAGENA" sí.
        {'name': 'dato', 'value': '={{ String($json.dato || "").trim().toUpperCase() }}'},
    ]),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e08', 'Normalizar', 'n8n-nodes-base.code', 2, [660, 800], {
        'jsCode': (AQUI / 'normalizar.js').read_text(),
    }),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e12', '¿Buscar tabla?', [440, 500],
       '={{ !String($json.codigo_tabla || "").trim() && !!String($json.codigo_cliente || "").trim() }}'),
    api('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e13', 'API tabla cliente', [660, 400],
        f'={{{{ "{API}/" + $json.accion + "/consultar" }}}}', [
            {'name': 'codigoCliente', 'value': '={{ String($json.codigo_cliente || "").trim() }}'},
        ]),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e14', 'Tabla', 'n8n-nodes-base.code', 2, [880, 500], {
        'jsCode': (AQUI / 'tabla.js').read_text(),
    }),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e15', '¿Hay tabla?', [1100, 500], '={{ !!$json.tabla }}'),
    api('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e16', 'API productos', [1320, 400],
        f'={{{{ "{API}/" + $("Consulta").first().json.accion + "/listarProductos" }}}}', [
            {'name': 'codigoTabla', 'value': '={{ $json.tabla.codigo }}'},
        ]),
    si('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e19', '¿Surtido?', [1540, 500],
       '={{ $("Consulta").first().json.accion === "surtidos" }}'),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e17', 'Normalizar condiciones', 'n8n-nodes-base.code', 2, [1760, 600], {
        'jsCode': (AQUI / 'normalizar_condiciones.js').read_text(),
    }),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e20', 'Normalizar surtido', 'n8n-nodes-base.code', 2, [1760, 400], {
        'jsCode': (AQUI / 'normalizar_surtido.js').read_text(),
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
    'Consulta': enlace('¿Condiciones?'),
    '¿Condiciones?': bifurca('¿Buscar tabla?', 'API clientes'),
    'API clientes': enlace('Normalizar'),
    '¿Buscar tabla?': bifurca('API tabla cliente', 'Tabla'),
    'API tabla cliente': enlace('Tabla'),
    'Tabla': enlace('¿Hay tabla?'),
    '¿Hay tabla?': bifurca('API productos', '¿Surtido?'),
    'API productos': enlace('¿Surtido?'),
    '¿Surtido?': bifurca('Normalizar surtido', 'Normalizar condiciones'),
}

flujo = {'id': WORKFLOW_ID, 'name': 'Chat IA clientes AYC', 'nodes': nodes, 'connections': connections,
         'settings': {'executionOrder': 'v1'}, 'pinData': {}}
(AQUI / 'chat-ia-clientes-ayc.json').write_text(json.dumps(flujo, ensure_ascii=False, indent=2) + '\n')
print('chat-ia-clientes-ayc.json generado')
