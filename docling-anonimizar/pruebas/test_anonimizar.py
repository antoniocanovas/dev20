"""Casos del anonimizador. Uso (con presidio y es_core_news_md instalados):
    python3 pruebas/test_anonimizar.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api"))
from anonimizar import Anonimizador  # noqa: E402

a = Anonimizador()
fallos = 0


def caso(nombre, texto, debe_quitar=(), debe_quedar=(), **kw):
    global fallos
    r = a.anonimizar(texto, **kw)["texto"]
    mal = [x for x in debe_quitar if x in r] + [f"(falta) {x}" for x in debe_quedar if x not in r]
    print(("OK   " if not mal else "FALLO") + f" {nombre}" + (f": {mal}\n      {r!r}" if mal else ""))
    fallos += bool(mal)


muestra = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "muestra.md"), encoding="utf-8").read()
caso("contrato completo", muestra,
     debe_quitar=["Juan Pérez", "María José", "12345678Z", "X1234567L", "B73123457", "Calle Mayor", "30001",
                  "968 123 456", "612 345 678", "juan.perez@", "ES91", "Antonio Ruiz", "Alfa-Centauro",
                  "Construcciones\nLevante", "Pérez García"],
     debe_quedar=["Gerente", "Técnico", "Start/Stop", "Configuración avanzada", "Dña.", "Murcia, a 3"],
     terminos=["Alfa-Centauro", "construcciones levante"])
caso("misma persona, misma etiqueta", "Firma Ana Ruiz Gil. Luego ana ruiz gil aprueba.",
     debe_quedar=["[PERSONA_1]. Luego [PERSONA_1]"])
caso("mayúsculas de contrato", "Firma: BLANCA RUIZ GARCÍA. TECLA BLANCA Y NEGRA.",
     debe_quitar=["RUIZ"], debe_quedar=["BLANCA Y NEGRA"])
caso("palabras comunes no son nombres", "La tecla blanca y negra. Pulse Rosa para el color rosa.",
     debe_quedar=["blanca y negra", "Rosa para"])
caso("términos sin tildes ni mayúsculas", "El proyecto ÁRBOL Azul y el arbol azul.",
     debe_quitar=["ÁRBOL Azul", "arbol azul"], terminos=["árbol azul"], categorias=[])
caso("solo teléfonos", "Juan Pérez García, tel. 968123456", debe_quitar=["968123456"],
     debe_quedar=["Juan Pérez García"], categorias=["telefonos"])
caso("código postal de EE. UU. no es teléfono", "Boston, MA 02110-1301 USA", debe_quedar=["02110-1301"])
caso("DNI con letra incorrecta no se toca", "Referencia 12345678A", debe_quedar=["12345678A"])
sys.exit(1 if fallos else 0)
