"""Genera un flujo temporal de n8n (id TmpSurtidoAYC01 por defecto) a partir de chat-ia-clientes-ayc.json, para probarlo
con `n8n execute` sin tocar el flujo publicado. Lo usa pruebas/n8n_tmp.sh.

    python3 flujo_tmp.py subflujo '<json con las entradas de Consulta>' salida.json
    python3 flujo_tmp.py agente   '<mensaje del usuario>'                salida.json

- subflujo: quita Chat, agente y herramientas, y cambia *Consulta* por un Code con las entradas fijas
  (accion, dato, codigo_cliente, codigo_tabla, articulo).
- agente: deja el agente con su modelo, memoria y herramientas (que llaman al flujo PUBLICADO ChatIaClienAYC01, así
  que hay que instalar antes la versión a probar) y le da el mensaje con un Code. Cada ejecución es una conversación
  nueva (la memoria no se conserva entre ejecuciones).
"""
import json
import os
import sys
from pathlib import Path

FLUJO = Path(__file__).resolve().parent.parent / 'n8n' / 'chat-ia-clientes-ayc.json'
TMP_ID = os.environ.get('TMP_ID', 'TmpSurtidoAYC01')
AGENTE = ('Agente clientes', 'OpenRouter', 'Memoria')

modo, entrada, salida = sys.argv[1:4]
w = json.loads(FLUJO.read_text())
es_tool = lambda n: n['type'] == '@n8n/n8n-nodes-langchain.toolWorkflow'
inicio = {'parameters': {}, 'id': 'tmp0', 'name': 'Inicio', 'type': 'n8n-nodes-base.manualTrigger',
          'typeVersion': 1, 'position': [-400, 0]}

if modo == 'subflujo':
    nodos = [n for n in w['nodes'] if n['name'] not in AGENTE + ('Chat',) and not es_tool(n)]
    for n in nodos:
        if n['name'] == 'Consulta':
            n.update(type='n8n-nodes-base.code', typeVersion=2,
                     parameters={'jsCode': 'return [{json:%s}];' % json.dumps(json.loads(entrada), ensure_ascii=False)})
    primero = 'Consulta'
elif modo == 'agente':
    nodos = [n for n in w['nodes'] if n['name'] in AGENTE or es_tool(n)]
    for n in nodos:
        if n['name'] == 'Memoria':
            n['parameters'].update(sessionIdType='customKey', sessionKey='tmp-pruebas')
    nodos.append({'parameters': {'jsCode': 'return [{json:%s}];' % json.dumps(
        {'chatInput': entrada, 'sessionId': 'tmp-pruebas'}, ensure_ascii=False)},
        'id': 'tmp1', 'name': 'Mensaje', 'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [-200, 0]})
    primero = 'Mensaje'
else:
    sys.exit(f'modo desconocido: {modo}')

nombres = {n['name'] for n in nodos}
conexiones = {k: v for k, v in w['connections'].items() if k in nombres}
conexiones['Inicio'] = {'main': [[{'node': primero, 'type': 'main', 'index': 0}]]}
if modo == 'agente':
    conexiones['Mensaje'] = {'main': [[{'node': 'Agente clientes', 'type': 'main', 'index': 0}]]}
Path(salida).write_text(json.dumps({'id': TMP_ID, 'name': 'TMP pruebas AYC', 'nodes': [inicio] + nodos,
                                    'connections': conexiones, 'settings': {'executionOrder': 'v1'}, 'pinData': {}},
                                   ensure_ascii=False))
