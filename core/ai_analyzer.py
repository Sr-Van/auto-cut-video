import json
import random
import time
from collections import deque

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from core.config import (
    API_KEYS,
    GEMINI_BACKOFF_BASE,
    GEMINI_BACKOFF_MAX,
    GEMINI_MAX_ATTEMPTS,
    GEMINI_TIMEOUT_S,
    MODELOS_GEMINI,
    TEMPERATURA,
)
from utils.timefmt import seconds_to_hhmmss

RULES = """
Você é um curador e analista de conteúdo viral altamente especializado na cultura da internet brasileira, focado em redes como TikTok, Instagram Reels e YouTube Shorts.

Sua missão é analisar a transcrição com minutagem de um vídeo de origem brasileira, identificar os trechos relevantes e ignorar partes monótonas, pausas longas ou falas sem impacto.

IMPORTANTE: cada "clipe" deve ser um trecho contínuo entre 30 e 90 segundos. Ele deve conter o contexto completo do momento forte: a construção, o pico e a reação. O clipe deve TERMINAR no fim natural do assunto (quando o raciocínio conclui ou a fala muda de tema), e não no meio de uma frase. Agrupe falas consecutivas sobre o mesmo assunto em um único clipe, respeitando o limite de 90 segundos. NÃO entregue frases isoladas nem trechos curtos — prefira blocos coerentes que sustentem o momento de impacto e que fechem o assunto.

Para cada clipe, classifique em uma das categorias abaixo e atribua uma "Nota de Viralidade" de 0 a 10.

CRITÉRIOS DE CATEGORIZAÇÃO:
1. EDUCATIVO: explicações claras de temas complexos, dicas práticas, curiosidades ou conhecimentos que geram o efeito "eu não sabia disso".
2. POLÊMICO: opiniões impopulares, críticas contundentes, debates acalorados ou quebra de tabus (sem violar regras de segurança).
3. ENGRAÇADO: quebra de expectativa, humor autodepreciativo, ironia, reações autênticas e exageradas ou uso criativo de gírias regionais brasileiras.
4. RELEVANTE: histórias de superação, conselhos de vida, discursos motivacionais ou reflexões profundas.

CRITÉRIOS DE VIRALIDADE (RANKING 0 a 10):
- 9-10: pico (hook) forte e claro, fala com ritmo, não depende de muito contexto externo, gera forte emoção e é altamente compartilhável.
- 7-8: excelente conteúdo, mas com construção levemente lenta ou exigindo leve edição externa.
- 4-6: conteúdo bom apenas para nichos específicos; fala arrastada ou dependente de muito contexto.
- 0-3: descarte (vícios de linguagem, assunto irrelevante, ritmo monótono). NÃO inclua estes na resposta.

O campo "hook" deve indicar o instante aproximado do pico (o momento mais forte dentro do clipe).
O campo "start" e "end" devem delimitar o trecho completo do clipe (formato HH:MM:SS), com duração entre 30 e 90 segundos, abrangendo o contexto antes e depois do pico. O "end" deve cair no fim natural do assunto (mudança de tema ou conclusão da fala).
O campo "viral_score" é um número de 0 a 10.
O campo "category" deve ser um de: EDUCATIVO, POLÊMICO, ENGRAÇADO, RELEVANTE.
Escreva "title" (título do corte) e "description" (descrição do corte) baseados no que foi dito.
Escreva "summary" (fala principal resumida) e "justification" (por que recebeu essa nota e como atinge o público brasileiro).
"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "clips": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "start": {"type": "STRING", "description": "Inicio do clipe (HH:MM:SS). Duracao entre 30 e 90 segundos."},
                    "end": {"type": "STRING", "description": "Fim do clipe (HH:MM:SS). Deve cair no fim natural do assunto."},
                    "hook": {"type": "STRING", "description": "Instante do pico dentro do clipe (HH:MM:SS)."},
                    "category": {"type": "STRING"},
                    "viral_score": {"type": "NUMBER"},
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "justification": {"type": "STRING"},
                },
                "required": ["start", "end", "category", "viral_score"],
            },
        }
    },
    "required": ["clips"],
}


def build_transcript_block(segments) -> str:
    lines = []
    for seg in segments:
        start = seconds_to_hhmmss(seg.start)
        end = seconds_to_hhmmss(seg.end)
        lines.append(f"[{start} - {end}] {seg.text}")
    return "\n".join(lines)


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.TransportError,
    ConnectionError,
    TimeoutError,
)


def _emit_retry(progress_callback, message, percent=50):
    if progress_callback:
        progress_callback("analise", percent, message)


def _retry_after_seconds(exc):
    """Le o header Retry-After, se presente (ex.: 429)."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _is_retryable(exc) -> bool:
    """Retry para 408/429/5xx e falhas de transporte."""
    code = _status_code(exc)
    if code is not None:
        return code in RETRYABLE_STATUS
    return isinstance(exc, RETRYABLE_EXCEPTIONS)


def _wait_seconds(attempt, retry_after=None) -> float:
    """Backoff exponencial com jitter; Retry-After tem prioridade."""
    if retry_after is not None:
        return retry_after
    delay = min(GEMINI_BACKOFF_MAX, GEMINI_BACKOFF_BASE ** (attempt - 1))
    return delay + random.uniform(0, delay * 0.5)


def _build_http_options():
    """Timeout configuravel + retry do SDK desligado (o retry e nosso)."""
    return types.HttpOptions(
        timeout=int(GEMINI_TIMEOUT_S * 1000),
        retry_options=types.HttpRetryOptions(attempts=1),
    )


def _status_code(exc):
    """Codigo HTTP do erro, se houver."""
    if isinstance(exc, genai_errors.APIError):
        return getattr(exc, "code", None)
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _is_quota(exc) -> bool:
    """Cota esgotada (429 / RESOURCE_EXHAUSTED)."""
    if _status_code(exc) == 429:
        return True
    text = str(exc).lower()
    return "resource_exhausted" in text or "quota" in text


def _is_auth_error(exc) -> bool:
    """Chave invalida / sem permissao."""
    return _status_code(exc) in (401, 403)


def _key_label(key: str) -> str:
    """Identifica a chave sem expo-la (so os 4 ultimos caracteres)."""
    key = (key or "").strip()
    return f"...{key[-4:]}" if len(key) > 4 else "(chave)"


_CLIENTS: dict[str, genai.Client] = {}


def _get_client(key: str) -> genai.Client:
    if key not in _CLIENTS:
        _CLIENTS[key] = genai.Client(api_key=key, http_options=_build_http_options())
    return _CLIENTS[key]


def analyze(segments, progress_callback=None, api_keys=None) -> list[dict]:
    keys = [k.strip() for k in (api_keys if api_keys is not None else API_KEYS) if k and k.strip()]
    if not keys:
        raise RuntimeError(
            "Nenhuma API key configurada. Defina API_KEY ou API_KEYS no .env."
        )

    block = build_transcript_block(segments)

    config = types.GenerateContentConfig(
        system_instruction=RULES,
        temperature=TEMPERATURA,
        response_mime_type="application/json",
        response_schema=SCHEMA,
    )

    # Rotaciona entre as chaves: se uma esgotar/for invalida, tira da fila e
    # passa para a proxima sem esperar. Erros temporarios (5xx/timeout) giram a
    # fila com backoff. Se um modelo falhar (nao-retentavel), desce para o
    # proximo da lista de fallback.
    dropped_keys: set[str] = set()
    attempt = 0
    max_attempts = max(
        GEMINI_MAX_ATTEMPTS,
        GEMINI_MAX_ATTEMPTS * len(keys) * len(MODELOS_GEMINI),
    )

    for model in MODELOS_GEMINI:
        # Cada modelo tenta com as chaves que ainda nao foram descartadas.
        pool = deque(k for k in keys if k not in dropped_keys)
        while pool:
            if attempt >= max_attempts:
                break
            attempt += 1

            key = pool[0]
            try:
                response = _get_client(key).models.generate_content(
                    model=model,
                    config=config,
                    contents=block,
                )
                data = json.loads(response.text)
                return data.get("clips", [])
            except Exception as exc:
                if _is_quota(exc) or _is_auth_error(exc):
                    motivo = "esgotada" if _is_quota(exc) else "invalida"
                    _emit_retry(
                        progress_callback,
                        f"Chave {_key_label(key)} {motivo}; trocando de chave...",
                    )
                    dropped_keys.add(key)
                    pool.popleft()
                    continue

                if _is_retryable(exc):
                    wait = _wait_seconds(attempt, _retry_after_seconds(exc))
                    _emit_retry(
                        progress_callback,
                        f"Erro temporario com {_key_label(key)}; "
                        f"tentando outra chave em {wait:.0f}s...",
                    )
                    pool.rotate(-1)
                    time.sleep(wait)
                    continue

                # Modelo invalido/nao suportado: tenta o proximo da lista.
                _emit_retry(
                    progress_callback,
                    f"Modelo {model} indisponivel; tentando o proximo da lista...",
                )
                break

        if not [k for k in keys if k not in dropped_keys]:
            break

    raise RuntimeError(
        f"Todos os modelos ({len(MODELOS_GEMINI)}) falharam ou todas as "
        f"chaves ({len(keys)}) esgotaram. Aguarde o reset da cota, ajuste "
        "os modelos ou adicione outra chave no .env."
    )
