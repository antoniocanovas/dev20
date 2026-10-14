{
    "name": "Chat AI",
    "version": "20.0.1.0.0",
    "summary": "Habla con la IA como un contacto más de Discuss",
    "description": """
        Añade un usuario/partner "Asistente IA" con el que cualquier usuario
        interno autorizado puede chatear directamente desde Discuss, igual
        que con OdooBot.

        - El acceso al bot está limitado al grupo "Conversaciones IA".
        - El usuario del bot no puede iniciar sesión bajo ninguna circunstancia.
        - La lógica de negocio (qué responde) la aportan otros módulos
          sobreescribiendo `chat.ai.responder` (ver mercas_ai).
        - La ejecución de las tools de IA se hace con los permisos reales del
          usuario que pregunta, nunca con los del bot ni con superusuario.
    """,
    "author": "Antonio Cánovas",
    "license": "LGPL-3",
    "category": "Productivity/Discuss",
    "depends": [
        "odoo_mcp_manager",
        "mail",
    ],
    "data": [
        "security/chat_ai_security.xml",
        "data/chat_ai_bot_data.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
