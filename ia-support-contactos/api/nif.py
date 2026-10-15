"""Validación de NIF, NIE y CIF españoles (con prefijo ES opcional)."""
import re

DNI_LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"
CIF_LETRAS_CONTROL = "JABCDEFGHI"


def normalizar(valor: str) -> str:
    return re.sub(r"[\s.\-]", "", valor or "").upper()


def es_valido(valor: str) -> bool:
    nif = normalizar(valor)
    if nif.startswith("ES"):
        nif = nif[2:]

    if re.fullmatch(r"\d{8}[A-Z]", nif):
        return DNI_LETRAS[int(nif[:8]) % 23] == nif[8]

    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", nif):
        numero = str("XYZ".index(nif[0])) + nif[1:8]
        return DNI_LETRAS[int(numero) % 23] == nif[8]

    if re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", nif):
        digitos = nif[1:8]
        pares = sum(int(d) for d in digitos[1::2])
        impares = sum(sum(divmod(int(d) * 2, 10)) for d in digitos[0::2])
        control = (10 - (pares + impares) % 10) % 10
        return nif[8] in (str(control), CIF_LETRAS_CONTROL[control])

    return False
