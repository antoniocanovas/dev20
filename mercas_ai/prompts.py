"""Business-domain instructions injected into the 'Consultas IA' classification
prompt (wizard/ai_domain_chat_wizard.py). Kept in its own module (not a DB
field) so it stays under version control and cannot be edited away by mistake
from the UI — the editable counterpart lives in res.config.settings as
mercas_ai.custom_instructions."""

BASE_BUSINESS_INSTRUCTIONS = (
    'CONTEXTO DEL NEGOCIO (fijo):\n'
    '- Este asistente corre sobre Odoo 19 Community. Quien pregunta es personal de un '
    'mayorista de frutas y hortalizas (un "Mercas" de mercado central): compra la mercancía '
    'a proveedores, la revende a clientes (comercios, hostelería, otros mayoristas) y la '
    'gestiona en el almacén por lotes trazables hasta su origen (país/provincia).\n'
    '- Si el usuario pregunta por un producto, cliente o proveedor concreto, la respuesta '
    'debe ceñirse exclusivamente a ese producto/cliente/proveedor: no mezcles cifras de '
    'otros productos ni de otros clientes/proveedores en el resultado.\n'
    '- Si el usuario pregunta por "cajas" o "envases", NO se refiere a un producto que se '
    'llame así, sino a los productos marcados como envase/caja retornable '
    '(campo is_box = True). En ese caso, en el dominio "stock" pon "only_boxes": true y deja '
    '"product" vacío, salvo que además mencione un producto concreto.\n'
    '- Cada lote se paga al proveedor de una de dos formas, que NO depende del tipo de '
    'pedido sino del propio lote: "liquidación por venta" (se paga según lo realmente '
    'vendido de ese lote, con anticipos mientras queda stock) o "facturación firme" (se '
    'paga la totalidad de lo recibido, se venda o no, en facturas parciales). Si preguntan '
    'qué queda "pendiente de facturar/pagar" de un lote o proveedor concreto, es sobre esto '
    '— usa el dominio "lote" con "lot" o "product" para un lote/producto concreto.\n'
)
