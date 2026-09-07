"""Pruebas de la descripción corta de cada documento.

La barra lateral muestra qué documentación tiene cargada el agente. Para que
esa lista sirva de algo, cada entrada necesita decir de qué tamaño es lo que
hay detrás: no es lo mismo una planilla de 77 filas que un reglamento de
media carilla.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resumen import describir, es_tabla, icono

TABLA = (
    "Tabla: lista_precios.csv\n"
    "Columnas: SKU, Producto, Precio (77 filas)\n"
    "\n"
    "| SKU | Producto | Precio |\n"
    "| --- | --- | --- |\n"
    "| 4801 | YERBA ROSAMONTE | 2859,90 |"
)
DOCUMENTO = "POLÍTICA DE LICENCIAS\n\n" + "palabra " * 1234


class TestReconocerUnaTabla:
    def test_una_tabla_se_reconoce(self):
        assert es_tabla(TABLA)

    def test_un_documento_de_texto_no(self):
        assert not es_tabla(DOCUMENTO)

    def test_un_texto_que_menciona_la_palabra_tabla_no_alcanza(self):
        # La deteccion exige la linea literal del renderizado, no cualquier
        # mencion: un PDF que hable de tablas no es una tabla.
        assert not es_tabla("El presente documento incluye una Tabla: de aranceles.")

    def test_un_texto_vacio_no_es_tabla(self):
        assert not es_tabla("")


class TestDescribir:
    def test_una_tabla_se_describe_por_sus_filas(self):
        assert describir(TABLA) == "77 filas"

    def test_una_fila_sola_va_en_singular(self):
        una = TABLA.replace("(77 filas)", "(1 filas)")
        assert describir(una) == "1 fila"

    def test_un_documento_se_describe_por_sus_palabras(self):
        # El esperado se calcula, no se escribe a mano: contar palabras de
        # cabeza es justo la clase de cosa que hace fallar un test por el
        # motivo equivocado.
        esperado = len(DOCUMENTO.split())
        assert describir(DOCUMENTO) == f"{esperado:,}".replace(",", ".") + " palabras"

    def test_los_miles_van_con_separador_argentino(self):
        # Punto para los miles, que es como se escribe en Argentina.
        assert "." in describir("palabra " * 5000)

    def test_un_documento_corto_no_lleva_separador(self):
        assert describir("una dos tres") == "3 palabras"

    def test_un_texto_vacio_lo_dice(self):
        assert describir("") == "vacío"

    def test_un_texto_de_solo_espacios_tambien(self):
        assert describir("   \n  ") == "vacío"


class TestIcono:
    def test_las_tablas_llevan_icono_de_planilla(self):
        assert icono(TABLA) == "📊"

    def test_los_documentos_llevan_icono_de_hoja(self):
        assert icono(DOCUMENTO) == "📄"
