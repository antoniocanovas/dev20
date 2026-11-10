"""Resume la salida de `n8n execute --rawOutput`: herramientas llamadas por el agente y salida del último nodo."""
import json
import sys

s = open(sys.argv[1]).read()
try:
    rd = json.loads(s[s.find('{'):])['data']['resultData']
except Exception as e:
    sys.exit(f'No se pudo leer la ejecución ({e}):\n{s[-1500:]}')
for nombre, runs in rd['runData'].items():
    if nombre.startswith('consultar_'):
        for r in runs:
            print('  [herramienta]', nombre, json.dumps(r.get('inputOverride', {}), ensure_ascii=False)[:250])
ultimo = rd['lastNodeExecuted']
j = rd['runData'][ultimo][0]['data']['main'][0][0]['json']
if 'output' in j:
    print(j['output'])
else:
    for k in ('productos', 'resultados'):
        if isinstance(j.get(k), list):
            j[k] = f'{len(j[k])} → ' + json.dumps(j[k][:3], ensure_ascii=False)
    print(ultimo, '|', json.dumps(j, ensure_ascii=False)[:1500])
