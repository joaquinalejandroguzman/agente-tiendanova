"""Test de humo: prueba que el arnes e2e llega a una app viva.

Es deliberadamente minimo. Su trabajo es fallar fuerte si se rompe el
navegador, el fixture del servidor o la estructura de la app. No verifica
comportamiento de producto, que corresponde a suites dedicadas.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_la_app_renderiza_sin_api_key(page: Page, streamlit_server: str) -> None:
    """La app tiene que renderizar aunque no haya API key configurada."""
    page.goto(streamlit_server)

    # El copy del producto es en espanol por diseno: se verifica lo que ve el
    # usuario. La marca vive en la barra lateral, no como titulo del area
    # principal: una herramienta no se presenta a si misma cada vez que se abre.
    expect(page.get_by_text("Cotejo", exact=True).first).to_be_visible(timeout=30_000)
    expect(page.get_by_role("button", name="Nuevo chat")).to_be_visible()
    # El panel de documentacion es lo que distingue la herramienta de un chat.
    expect(page.get_by_text("DOCUMENTACIÓN", exact=True)).to_be_visible()


@pytest.mark.e2e
def test_el_input_esta_disponible_con_el_corpus_de_demo(page: Page, streamlit_server: str) -> None:
    """El corpus de demo carga por defecto, asi que el input tiene que estar usable."""
    page.goto(streamlit_server)

    chat_input = page.get_by_placeholder("Preguntá sobre precios, stock, licencias, facturas...")
    expect(chat_input).to_be_visible(timeout=30_000)
    expect(chat_input).to_be_editable()
