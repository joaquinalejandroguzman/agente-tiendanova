"""Cliente minimo para hablar con la API de Groq (compatible con OpenAI)."""

import contextlib
import logging
import os
import re

import requests

# Un mensaje del formato de chat completions: {"role": ..., "content": ...}.
type ChatMessage = dict[str, str]

logger = logging.getLogger(__name__)

API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Variable de entorno que permite cambiar el modelo sin tocar el codigo.
# En Streamlit Community Cloud se carga como secret; en local, exportandola.
MODEL_ENV_VAR = "GROQ_MODEL"

# Modelo que se usa si nadie configura MODEL_ENV_VAR.
#
# Groq da de baja modelos con fecha fija y este proyecto ya se cayo dos veces
# por eso: meta-llama/llama-4-scout-17b-16e-instruct se apago el 17/07/2026, y
# llama-3.3-70b-versatile salio del plan gratuito el 16/08/2026. Por eso el
# modelo ahora se resuelve por entorno: cuando Groq de de baja el proximo,
# alcanza con cambiar un secret y reiniciar, sin editar codigo ni redeployar.
#
# Verificado el 01/09/2026 contra la API: responde correctamente sobre la
# documentacion del proyecto en ~0.9s. Antes de cambiarlo, mirar las fechas
# de baja en https://console.groq.com/docs/deprecations
FALLBACK_MODEL = "openai/gpt-oss-120b"


def resolve_model(override: str | None = None) -> str:
    """Decide que modelo usar, en orden de prioridad.

    1. El argumento explicito, si se pasa uno.
    2. La variable de entorno MODEL_ENV_VAR.
    3. FALLBACK_MODEL.

    Un valor vacio o solo espacios se ignora: un secret cargado sin valor no
    tiene que mandar un modelo vacio a la API, es preferible caer al que
    sabemos que funciona.
    """
    for candidato in (override, os.environ.get(MODEL_ENV_VAR)):
        if candidato and candidato.strip():
            return candidato.strip()
    return FALLBACK_MODEL


class GroqError(Exception):
    """Un fallo hablando con Groq, con un mensaje para cada audiencia.

    `str(error)` es lo que se le muestra al usuario final: alguien que esta
    trabajando y necesita saber que hacer ahora, no diagnosticar el sistema.
    Va sin jerga, sin nombres de variables y sin codigos de estado.

    `error.detalle_tecnico` es lo que necesita quien mantiene el sistema, y
    va al log. Ahi si aparecen el modelo, el codigo de estado y el paso
    concreto para arreglarlo.

    Estaban mezclados en un solo mensaje: el usuario terminaba leyendo
    instrucciones para editar variables de entorno, y quien mantenia el
    sistema no se enteraba de nada porque no estaba mirando esa pantalla.
    """

    def __init__(self, mensaje_usuario: str, detalle_tecnico: str | None = None) -> None:
        super().__init__(mensaje_usuario)
        self.detalle_tecnico = detalle_tecnico or mensaje_usuario


def _fallar(mensaje_usuario: str, detalle_tecnico: str | None = None) -> GroqError:
    """Deja el detalle tecnico en el log y devuelve el error para el usuario.

    Se llama en cada camino de error para que ningun fallo pueda quedar sin
    rastro: si no se loguea, el unico que se entera de que el sistema dejo de
    funcionar es el cliente, y se entera llamando por telefono.
    """
    error = GroqError(mensaje_usuario, detalle_tecnico)
    logger.error(error.detalle_tecnico)
    return error


# Lo que ve el usuario cuando el asistente no puede responder por un problema
# del sistema. Deliberadamente vago sobre la causa: quien lo lee no puede
# hacer nada con el detalle, y ver jerga tecnica en pantalla solo transmite
# que el sistema esta abandonado.
_MENSAJE_CAIDO = (
    "El asistente no está disponible en este momento. El problema quedó "
    "registrado automáticamente para el equipo técnico. Si tu consulta no "
    "puede esperar, escribile a soporte."
)


# El modelo no siempre evita la muletilla "segun el documento" solo con
# pedirselo en el prompt. La sacamos del inicio de la respuesta por codigo.
_HEDGE_PREFIX = re.compile(
    r"^(seg[uú]n (el|la|los|las|al) document\w*|de acuerdo (a|al|con) (el |la )?document\w*|"
    r"de acuerdo a la documentaci[oó]n|bas[aá]ndome en (el |la |al )?document\w*|"
    r"en base a(l)? (el |la )?document\w*)[,:]?\s*",
    re.IGNORECASE,
)


def _strip_document_hedge(text: str) -> str:
    nuevo = _HEDGE_PREFIX.sub("", text, count=1)
    if nuevo and nuevo != text:
        nuevo = nuevo[0].upper() + nuevo[1:]
    return nuevo


def chat(
    messages: list[ChatMessage],
    model: str | None = None,
    api_key: str | None = None,
    timeout: int = 60,
) -> str:
    """Envia una conversacion al endpoint de chat completions de Groq
    y devuelve la respuesta del modelo.

    messages: lista de dicts {"role": "system"|"user"|"assistant", "content": str}
    model: si no se pasa, lo resuelve resolve_model() (entorno o por defecto).
    """
    model = resolve_model(model)
    if not api_key:
        raise _fallar(
            _MENSAJE_CAIDO,
            "Falta la API key de Groq. Configurala como GROQ_API_KEY en los "
            "secrets de la app (o como variable de entorno en local).",
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        # Bajada de 0.2 a 0.3: en 0.2 el modelo abusaba del mensaje de
        # "no tengo esa informacion" aunque el documento si la tenia.
        "temperature": 0.3,
    }
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.Timeout as exc:
        # Estos dos son transitorios y se resuelven solos, asi que al usuario
        # se le dice la verdad util: volve a intentar.
        raise _fallar(
            "El asistente tardó demasiado en responder. Probá de nuevo.",
            f"Timeout de {timeout}s hablando con Groq (modelo '{model}').",
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise _fallar(
            "No se pudo contactar al asistente. Revisá tu conexión e intentá de nuevo.",
            "No se pudo conectar con la API de Groq. Puede ser la red local o "
            "una caída del proveedor: https://groqstatus.com",
        ) from exc
    except requests.exceptions.HTTPError as exc:
        if resp.status_code == 401:
            raise _fallar(
                _MENSAJE_CAIDO,
                "Groq rechazó la API key (401). Está vencida, revocada o mal "
                "cargada: generá una nueva en https://console.groq.com/keys y "
                "actualizá el secret GROQ_API_KEY.",
            ) from exc
        if resp.status_code == 404:
            # Caso real, dos veces: Groq apago el modelo que teniamos
            # configurado y la app quedo caida. El usuario no puede hacer nada
            # con esa informacion; quien mantiene el sistema, todo.
            raise _fallar(
                _MENSAJE_CAIDO,
                f"El modelo '{model}' ya no está disponible en Groq (404). "
                "Groq da de baja modelos con fecha fija. Mirá los vigentes en "
                "https://console.groq.com/docs/models y cargá uno nuevo en la "
                f"variable {MODEL_ENV_VAR} (secret en Streamlit Cloud, o "
                "variable de entorno en local). No hace falta tocar el código.",
            ) from exc
        if resp.status_code == 429:
            # Transitorio: se recupera solo cuando pasa el minuto.
            raise _fallar(
                "El asistente está recibiendo muchas consultas en este momento. "
                "Esperá un minuto y volvé a preguntar.",
                f"Groq devolvió 429 con el modelo '{model}': se agotó la cuota "
                "de tokens por minuto del plan gratuito.",
            ) from exc
        if resp.status_code == 413:
            # Groq devuelve 413 cuando la consulta supera el limite de tokens
            # POR MINUTO del plan, no la ventana de contexto del modelo. El
            # cuerpo lo dice explicitamente: "on tokens per minute (TPM):
            # Limit 8000, Requested 9905". Es transitorio, igual que el 429,
            # asi que al usuario se le dice lo unico util: esperar.
            detalle = ""
            # El cuerpo puede no ser JSON valido; en ese caso el detalle
            # queda vacio y el mensaje al usuario no cambia.
            with contextlib.suppress(ValueError):
                detalle = str(resp.json().get("error", {}).get("message", ""))[:300]
            raise _fallar(
                "La consulta es más grande de lo que permite el plan gratuito en "
                "este momento. Esperá un minuto y volvé a preguntar.",
                f"Groq devolvió 413 con el modelo '{model}': la consulta supera "
                f"el límite de tokens por minuto del plan. {detalle}",
            ) from exc
        raise _fallar(
            _MENSAJE_CAIDO,
            f"Groq respondió con un error inesperado usando el modelo '{model}': {exc}",
        ) from exc

    data = resp.json()
    try:
        contenido = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise _fallar(
            _MENSAJE_CAIDO,
            f"Groq devolvió una respuesta con un formato inesperado usando el "
            f"modelo '{model}'. Puede ser un filtro de contenido o un cambio en "
            f"el formato de la API. Respuesta cruda: {str(data)[:400]}",
        ) from exc
    return _strip_document_hedge(contenido)
