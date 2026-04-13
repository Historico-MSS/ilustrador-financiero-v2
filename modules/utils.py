LISTA_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]


def mes_numero(nombre_mes: str) -> int:
    return LISTA_MESES.index(nombre_mes.lower()) + 1


def nombre_mes(numero_mes: int) -> str:
    return LISTA_MESES[numero_mes - 1]