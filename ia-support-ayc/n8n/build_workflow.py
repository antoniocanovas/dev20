"""Genera chat-ia-clientes-ayc.json (flujo de n8n) a partir de este script y de normalizar.js.

    python3 build_workflow.py

Un solo flujo con dos entradas:
- Chat → Agente clientes, con la herramienta consultar_clientes.
- Consulta (Execute Workflow Trigger) → API clientes → Normalizar: es lo que ejecuta
  la herramienta (se llama a sí mismo por su id fijo, WORKFLOW_ID), para poner el dato en mayúsculas, reintentar,
  quitar los espacios de relleno y devolver como mucho 10 clientes al modelo.
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
- código = código de cliente (p. ej. 4300017472). CIF = CIF/NIF/NIE del cliente.
- Un mismo CIF puede tener varios códigos de cliente (una ficha por dirección o tienda): son clientes distintos, distínguelos por dirección y población.
- cadena = nombre del cliente cadena (grupo o central al que pertenece). nombre_factura = nombre del cliente al que se factura. Vienen vacíos si no tiene o si son iguales al nombre: muéstralos SOLO si no están vacíos, como "Cadena: ..." y "Factura a: ...".

## Cómo trabajar
1. Para cualquier pregunta sobre un cliente usa consultar_clientes con el dato que dé el usuario: parte del nombre, CIF o código. Busca por un dato cada vez, el más distintivo (si da el CIF o el código, usa ese).
2. Si la búsqueda devuelve requiere_eleccion = true, muestra una lista numerada corta (nombre, código, CIF y población, más cadena y factura a si no están vacíos) y pide que elija. No elijas tú.
3. Si hay_mas = true, di cuántos hay en total (total), muestra los 10 primeros y propone acotar con más palabras del nombre, el CIF o el código.
4. Si no hay resultados, dilo y prueba o sugiere otra forma: menos palabras, una sola palabra significativa del nombre, con o sin tildes/Ñ, o el CIF.
5. Con un solo cliente (o cuando el usuario elige uno de la lista), muestra su ficha: nombre, código, CIF, dirección, código postal, población y provincia, y cadena y factura a si no están vacíos. Para preguntas posteriores sobre el mismo cliente usa los datos que ya tienes; no vuelvas a buscar si no hace falta.
6. Si una herramienta devuelve {"error": ...}, explícalo en lenguaje natural y propone reintentar. No muestres JSON ni nombres técnicos de campos.
7. En esta fase solo puedes CONSULTAR clientes. Si te piden dar de alta, modificar o borrar clientes, o datos de otras cosas (pedidos, facturas, albaranes, artículos...), indica que de momento solo consultas clientes."""

TOOL_DESC = ('Busca clientes en el ERP por parte del nombre, CIF/NIF o código de cliente. '
             'Devuelve total, requiere_eleccion, hay_mas y hasta 10 resultados con codigo, nombre, '
             'cadena, nombre_factura, cif, direccion, codigo_postal, poblacion y provincia.')


def nodo(id_, nombre, tipo, version, pos, params, **extra):
    return {'parameters': params, 'id': id_, 'name': nombre, 'type': tipo,
            'typeVersion': version, 'position': pos, **extra}


nodes = [
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e01', 'Chat', '@n8n/n8n-nodes-langchain.chatTrigger', 1.1, [0, 0], {
        'public': True,
        'mode': 'hostedChat',
        'authentication': 'n8nUserAuth',
        'initialMessages': 'Hola 👋 Soy el asistente de clientes de AYC. Puedo buscar clientes por nombre, CIF o código. ¿Qué cliente buscas?',
        'options': {
            'title': 'Asistente de clientes AYC',
            'subtitle': 'ia-support · consulta de clientes',
            'inputPlaceholder': 'Ej.: busca Ñam Ñam / B30682488 / 4300017472…',
        },
    }, webhookId='6d2b7e41-58c3-4f0a-a9e2-4b1d9c0e7a31'),
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
        'workflowInputs': {
            'mappingMode': 'defineBelow',
            'value': {'dato': "={{ $fromAI('dato', 'Parte del nombre, CIF/NIF o código de cliente a buscar', 'string') }}"},
            'matchingColumns': [],
            'schema': [{'id': 'dato', 'displayName': 'dato', 'required': False, 'defaultMatch': False,
                        'display': True, 'canBeUsedToMatch': True, 'type': 'string'}],
            'attemptToConvertTypes': False,
            'convertFieldsToString': False,
        },
    }),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e06', 'Consulta', 'n8n-nodes-base.executeWorkflowTrigger', 1.1, [0, 600], {
        'workflowInputs': {'values': [{'name': 'dato'}]},
    }),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e07', 'API clientes', 'n8n-nodes-base.httpRequest', 4.2, [220, 600], {
        'method': 'GET',
        'url': f'{API}/clientes/consultarClientes',
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendQuery': True,
        'queryParameters': {'parameters': [
            # La API distingue mayúsculas: "cartagena" no encuentra nada y "CARTAGENA" sí.
            {'name': 'dato', 'value': '={{ String($json.dato || "").trim().toUpperCase() }}'},
            {'name': 'subEmpresa', 'value': SUBEMPRESA},
        ]},
        # Texto y no JSON: un array vacío daría 0 items y el subflujo no devolvería nada.
        'options': {'response': {'response': {'responseFormat': 'text', 'outputPropertyName': 'data'}},
                    'timeout': 30000},
    }, credentials=CREDENCIAL, retryOnFail=True, maxTries=3, waitBetweenTries=1000,
        onError='continueRegularOutput'),
    nodo('3f6a1c52-7d0e-4b8a-9c11-0a1b2c3d4e08', 'Normalizar', 'n8n-nodes-base.code', 2, [440, 600], {
        'jsCode': (AQUI / 'normalizar.js').read_text(),
    }),
]


def enlace(destino, tipo='main'):
    return {tipo: [[{'node': destino, 'type': tipo, 'index': 0}]]}


connections = {
    'Chat': enlace('Agente clientes'),
    'OpenRouter': enlace('Agente clientes', 'ai_languageModel'),
    'Memoria': enlace('Agente clientes', 'ai_memory'),
    'consultar_clientes': enlace('Agente clientes', 'ai_tool'),
    'Consulta': enlace('API clientes'),
    'API clientes': enlace('Normalizar'),
}

flujo = {'id': WORKFLOW_ID, 'name': 'Chat IA clientes AYC', 'nodes': nodes, 'connections': connections,
         'settings': {'executionOrder': 'v1'}, 'pinData': {}}
(AQUI / 'chat-ia-clientes-ayc.json').write_text(json.dumps(flujo, ensure_ascii=False, indent=2) + '\n')
print('chat-ia-clientes-ayc.json generado')
