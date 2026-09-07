"""Describe un documento ya extraido, para mostrarlo en la barra lateral.

La barra lateral lista la documentacion que el agente tiene cargada. Una
lista de nombres sola no dice nada util: hace falta saber de que tamano es lo
que hay detras de cada uno, porque no es lo mismo una planilla de setenta y
siete articulos que un reglamento de media carilla.

Todo se deduce del texto ya extraido. No se vuelve a abrir el archivo ni se
guarda metadata aparte: el texto es lo unico que el resto del sistema conoce
de un documento, y esta capa no introduce una segunda fuente de verdad que
pueda desincronizarse.
"""

import re

# La primera linea con la que `tabla_utils.renderizar` marca una tabla. Se
# exige al principio del texto y no en cualquier parte: un documento que
# mencione la palabra "tabla" no es una tabla.
_ENCABEZADO_TABLA = "Tabla: "
_CANTIDAD_DE_FILAS = re.compile(r"\((\d+) filas?\)")


def es_tabla(texto: str) -> bool:
    """¿El texto es una tabla renderizada, o un documento de prosa?"""
    return texto.startswith(_ENCABEZADO_TABLA)


def _con_separador_de_miles(numero: int) -> str:
    """Formatea con punto para los miles, como se escribe en Argentina."""
    return f"{numero:,}".replace(",", ".")


def describir(texto: str) -> str:
    """Devuelve una descripcion corta del tamano del documento."""
    if not texto.strip():
        return "vacío"

    if es_tabla(texto):
        encontrado = _CANTIDAD_DE_FILAS.search(texto)
        if encontrado:
            filas = int(encontrado.group(1))
            unidad = "fila" if filas == 1 else "filas"
            return f"{_con_separador_de_miles(filas)} {unidad}"

    palabras = len(texto.split())
    unidad = "palabra" if palabras == 1 else "palabras"
    return f"{_con_separador_de_miles(palabras)} {unidad}"


def icono(texto: str) -> str:
    """Distingue de un vistazo una planilla de un documento de texto."""
    return "📊" if es_tabla(texto) else "📄"
