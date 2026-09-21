import json
import random
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from core.config import (
    API_KEY,
    GEMINI_BACKOFF_BASE,
    GEMINI_BACKOFF_MAX,
    GEMINI_MAX_ATTEMPTS,
    GEMINI_TIMEOUT_S,
    MODELO_GEMINI,
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
    """Classifica o erro: retry apenas para 408/429/5xx e falhas de transporte."""
    if isinstance(exc, genai_errors.APIError):
        return getattr(exc, "code", None) in RETRYABLE_STATUS
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


def analyze(segments, progress_callback=None) -> list[dict]:
    client = genai.Client(api_key=API_KEY, http_options=_build_http_options())
    block = build_transcript_block(segments)

    config = types.GenerateContentConfig(
        system_instruction=RULES,
        temperature=TEMPERATURA,
        response_mime_type="application/json",
        response_schema=SCHEMA,
    )

    attempt = 0
    while True:
        attempt += 1
        try:
            response = client.models.generate_content(
                model=MODELO_GEMINI,
                config=config,
                contents=block,
            )
            data = json.loads(response.text)
            return data.get("clips", [])
        except Exception as exc:
            if not _is_retryable(exc) or attempt >= GEMINI_MAX_ATTEMPTS:
                raise
            wait = _wait_seconds(attempt, _retry_after_seconds(exc))
            _emit_retry(
                progress_callback,
                f"Analisando (tentativa {attempt + 1}/{GEMINI_MAX_ATTEMPTS}, "
                f"aguardando {wait:.0f}s)...",
            )
            time.sleep(wait)
