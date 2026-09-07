"""Elige que documentos entran en el contexto que se le manda al LLM.

Antes se mandaban los 6 documentos base enteros en cada pregunta: ~31.700
caracteres, casi 7.900 tokens. El plan gratuito de Groq permite entre 8.000 y
12.000 tokens por minuto segun el modelo, asi que una sola pregunta se comia
la cuota del minuto entero y la siguiente fallaba con 429 (o con 413 si el
historial habia crecido).

La solucion es mandar solo los documentos del tema que se pregunto. El
puntaje es lexico (TF-IDF sobre los propios documentos cargados), no una
lista de palabras clave escrita a mano: asi funciona igual con los PDFs que
sube el usuario, que no conocemos de antemano.

Un efecto util del IDF: las palabras que aparecen en todos los documentos
("tiendanova", "politica", "alcance", "proposito") quedan con peso cero
solas, sin necesidad de mantenerlas en una lista de exclusion.
"""

import math
import re
import unicodedata

from pdf_utils import Document

# Un documento puntuado: (nombre, texto, score de relevancia).
ScoredDocument = tuple[str, str, float]

# Presupuesto de contexto, calibrado contra el limite real del plan gratuito.
#
# El valor anterior, 14.000, asumia la regla de cuatro caracteres por token y
# estimaba unos 3.500 tokens de documentos. Medido contra la API, una sola
# pregunta sobre la lista de precios pedia 9.905 tokens y Groq la rechazaba
# con un 413:
#
#   Request too large for model openai/gpt-oss-120b ... service tier
#   on_demand on tokens per minute (TPM): Limit 8000, Requested 9905
#
# La causa es que una tabla en markdown tokeniza mucho peor que la prosa: los
# separadores de columna y los numeros sueltos se cuentan casi de a uno, y la
# relacion real ronda 1,5 caracteres por token en vez de 4.
#
# 9.000 caracteres de tabla son unos 6.000 tokens. Sumados al system prompt,
# al historial recortado y a la respuesta, entran debajo del techo de 8.000
# tokens por minuto con margen. Para prosa el margen es mayor todavia.
MAX_CONTEXT_CHARS = 9000

# Los terminos del titulo del documento pesan mas que los del cuerpo: que la
# pregunta diga "envio" y el documento se llame "Guia de Tiempos y Costos de
# Envio" es mucha mas señal que una mencion suelta en el medio del texto.
_TITLE_WEIGHT = 3.0

# Palabras vacias del español rioplatense. Sin esto, preguntas como "¿como
# hago para saber cuanto tarda?" puntuaban por "como" y "hago", que no dicen
# nada del tema.
_STOPWORDS = {
    "algo",
    "alguna",
    "algunas",
    "alguno",
    "algunos",
    "ante",
    "antes",
    "aqui",
    "cada",
    "como",
    "con",
    "contra",
    "cual",
    "cuales",
    "cuando",
    "cuanta",
    "cuantas",
    "cuanto",
    "cuantos",
    "dan",
    "das",
    "debe",
    "deben",
    "decir",
    "dejar",
    "del",
    "demas",
    "desde",
    "donde",
    "dos",
    "ella",
    "ellas",
    "ello",
    "ellos",
    "entre",
    "esa",
    "esas",
    "ese",
    "eso",
    "esos",
    "esta",
    "estan",
    "estar",
    "estas",
    "este",
    "esto",
    "estos",
    "estoy",
    "hace",
    "hacen",
    "hacer",
    "hago",
    "hasta",
    "hay",
    "las",
    "les",
    "los",
    "mas",
    "mia",
    "mio",
    "mis",
    "misma",
    "mismo",
    "mucha",
    "mucho",
    "muy",
    "nada",
    "necesito",
    "ninguna",
    "ninguno",
    "nos",
    "nosotros",
    "otra",
    "otras",
    "otro",
    "otros",
    "para",
    "pero",
    "poco",
    "podes",
    "podria",
    "por",
    "porque",
    "puede",
    "pueden",
    "puedo",
    "que",
    "quien",
    "quienes",
    "quiero",
    "saber",
    "ser",
    "sera",
    "sino",
    "sobre",
    "solo",
    "son",
    "soy",
    "sus",
    "tambien",
    "tener",
    "tengo",
    "tiene",
    "tienen",
    "tienes",
    "toda",
    "todas",
    "todo",
    "todos",
    "tus",
    "una",
    "unas",
    "uno",
    "unos",
    "usted",
    "ustedes",
    "vos",
    "ver",
}

_WORD = re.compile(r"[a-z0-9]+")

# Largo al que se recorta cada palabra para compararlas. Es un stemmer
# pobre pero suficiente y sin dependencias nuevas: alcanza para que
# "devolver" y "devoluciones" caigan las dos en "devol". Bug real: sin esto,
# "¿como hago para devolver un producto?" no traia la Politica de
# Reembolsos y Devoluciones, que es justo el documento que la contesta.
_STEM_LEN = 5


def _normalize(text: str) -> str:
    """Minusculas y sin tildes, para que "envío" y "envio" sean lo mismo."""
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _stem(word: str) -> str:
    """Raiz aproximada: saca el plural y recorta a _STEM_LEN caracteres.

    El plural se saca antes de recortar para que "pago" y "pagos" terminen
    igual ("pago"); si solo se recortara, quedarian distintos.
    """
    if len(word) > 4 and word.endswith("es"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s"):
        word = word[:-1]
    return word[:_STEM_LEN]


def _tokens(text: str) -> list[str]:
    """Raices de las palabras de 3 letras o mas que no sean vacias.

    El minimo es 3 y no 4 para no perder terminos cortos con carga real
    ("iva", "cvv", "dni").
    """
    return [
        _stem(w) for w in _WORD.findall(_normalize(text)) if len(w) >= 3 and w not in _STOPWORDS
    ]


def _term_counts(tokens: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    return counts


def _score(
    query_terms: set[str],
    cuerpo: dict[str, int],
    titulo: set[str],
    idf: dict[str, float],
) -> float:
    total = 0.0
    for termino in query_terms:
        peso = idf.get(termino, 0.0)
        if peso <= 0:
            continue
        if termino in titulo:
            total += peso * _TITLE_WEIGHT
        cantidad = cuerpo.get(termino, 0)
        if cantidad:
            # tf amortiguado: que un termino aparezca 30 veces no vale 30
            # veces mas que aparecer una sola.
            total += peso * (1 + math.log(cantidad))
    return total


def rank_documents(question: str, docs: list[Document]) -> list[ScoredDocument]:
    """Ordena los documentos por relevancia contra la pregunta.

    docs: lista de tuplas (nombre, texto)
    Devuelve una lista de tuplas (nombre, texto, score), de mayor a menor
    score. Los empates conservan el orden original de docs.
    """
    if not docs:
        return []

    cuerpos = [_term_counts(_tokens(texto)) for _, texto in docs]
    titulos = [set(_tokens(nombre)) for nombre, _ in docs]

    # IDF calculado sobre los documentos efectivamente cargados (titulo +
    # cuerpo), no sobre un corpus fijo: si el usuario sube sus propios PDFs,
    # los pesos se recalculan para ese set.
    n_docs = len(docs)
    document_freq: dict[str, int] = {}
    for cuerpo, titulo in zip(cuerpos, titulos, strict=False):
        for termino in set(cuerpo) | titulo:
            document_freq[termino] = document_freq.get(termino, 0) + 1
    # IDF suavizado: log(1 + N/df) en vez de log(N/df). Con la formula sin
    # suavizar, un termino que aparece en los 6 documentos daba exactamente
    # 0 y quedaba descartado. Bug real: "¿cuanto dura la garantia?" no traia
    # el Manual de Garantia porque la palabra "garantia" se menciona al
    # pasar en los otros cinco documentos. Suavizado, el termino sigue
    # valiendo menos que uno exclusivo, pero ya no se anula.
    idf = {t: math.log(1 + n_docs / df) for t, df in document_freq.items()}

    query_terms = set(_tokens(question))
    puntuados = [
        (docs[i][0], docs[i][1], _score(query_terms, cuerpos[i], titulos[i], idf))
        for i in range(n_docs)
    ]
    # sorted es estable, asi que los empatados (incluido el caso "todos en
    # cero") quedan en el orden en que se cargaron.
    return sorted(puntuados, key=lambda x: x[2], reverse=True)


def select_relevant_docs(
    question: str, docs: list[Document], max_chars: int = MAX_CONTEXT_CHARS
) -> list[Document]:
    """Devuelve los documentos mas relevantes que entren en max_chars.

    docs: lista de tuplas (nombre, texto)
    Devuelve una lista de tuplas (nombre, texto) lista para combine_documents.

    Si todo entra en el presupuesto no se descarta nada. Si ningun documento
    matchea la pregunta se devuelven los primeros en el orden original: es
    preferible darle al modelo contexto de mas que dejarlo sin nada por una
    pregunta redactada con palabras que no figuran en ningun documento.
    """
    if not docs:
        return []

    total = sum(len(texto) for _, texto in docs)
    if total <= max_chars:
        return list(docs)

    seleccionados: list[Document] = []
    usados = 0
    for nombre, texto, _score in rank_documents(question, docs):
        if not seleccionados:
            # El documento mas relevante entra siempre, aunque haya que
            # recortarlo: devolver la lista vacia dejaria al agente sin fuente.
            recortado = texto[:max_chars]
            seleccionados.append((nombre, recortado))
            usados = len(recortado)
            continue
        if usados + len(texto) > max_chars:
            continue
        seleccionados.append((nombre, texto))
        usados += len(texto)
    return seleccionados
