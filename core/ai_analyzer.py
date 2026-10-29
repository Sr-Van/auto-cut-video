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
Você é um editor sênior de Shorts/Reels/TikTok especializado na cultura da internet brasileira. Seu trabalho é encontrar os melhores cortes de um vídeo a partir da transcrição com minutagem. Seja EXIGENTE: a maioria dos trechos não merece virar corte, e retornar poucos clipes bons é melhor que muitos medianos.

## COMO ANALISAR (siga esta ordem)
1. Leia a transcrição inteira e identifique os momentos de maior impacto (frase de efeito, revelação, piada, confronto, virada emocional, dica surpreendente).
2. Para cada candidato, encontre o ponto onde o espectador de um Short entenderia e se interessaria SEM ter visto o resto do vídeo. Esse é o início do clipe.
3. Avalie cada candidato pelos critérios abaixo ANTES de dar a nota.
4. Descarte quem não passar nos filtros eliminatórios.

## FILTROS ELIMINATÓRIOS (se falhar em qualquer um, não inclua)
- Depende de contexto anterior para ser entendido (pronomes sem referência, "como eu disse antes", assunto que começa no meio).
- O pico acontece depois dos primeiros 8 segundos sem nada interessante antes.
- Termina no meio de uma ideia ou frase.
- Conteúdo difamatório contra pessoas reais, discurso de ódio, incitação à violência, conteúdo sexual explícito ou desinformação perigosa (saúde, golpes).
- Predominância de vícios de linguagem, enrolação ou ritmo monótono.
- O clipe NÃO PODE conter autopromoção, publicidade, pedido de like/inscrição/comentário,
  cupom, patrocínio, link, despedida ou agradecimento de audiência. Se o trecho bom é
  seguido por isso, o clipe termina ANTES. Fim do clipe = fim da ideia, nunca fim do vídeo.
- Se o conteúdo útil tiver menos que a duração mínima, DESCARTE o clipe. Nunca complete
  tempo com enrolação ou propaganda.

## REGRAS DE RECORTE
- Duração: entre 25 e 75 segundos (ideal: 35-60).
- O clipe deve COMEÇAR perto do gancho: a primeira frase deve prender (pergunta, afirmação forte, promessa, conflito). Corte introduções e preâmbulos, mas mantenha o mínimo para a frase fazer sentido sozinha.
- O clipe deve TERMINAR logo após o desfecho ou a reação, na conclusão natural da ideia. Não estenda além disso.
- Use SOMENTE timestamps que existem na transcrição. "start" é o início de um segmento e "end" é o fim de um segmento. Nunca invente tempos.
- Clipes não podem se sobrepor.
- Máximo de {MAX_CLIPS} clipes. Se nenhum merecer, retorne lista vazia.

## NOTA DE VIRALIDADE (0-10) — some os pontos
- Gancho nos primeiros 3 segundos (0-3): 0 = nenhum, 3 = para o scroll imediatamente.
- Payoff/emoção (0-3): 0 = nenhum, 3 = risada, raiva, surpresa ou identificação forte.
- Autonomia (0-2): 0 = precisa de contexto, 2 = totalmente compreensível sozinho.
- Compartilhabilidade (0-2): 0 = ninguém mandaria para amigos, 2 = "olha isso!" imediato.
Inclua apenas clipes com nota >= 7. Evite dar nota 9-10 a mais de um clipe a cada 30 minutos de vídeo, pois essa nota é rara.

## CATEGORIAS
EDUCATIVO (revelação do tipo "não sabia disso", dica prática), POLÊMICO (opinião forte, crítica, quebra de tabu), ENGRAÇADO (quebra de expectativa, ironia, gíria, reação exagerada), RELEVANTE (superação, conselho, reflexão). Escolha a que melhor explica POR QUE o clipe prende.

## SAÍDA
Retorne JSON seguindo o schema. Preencha os campos NA ORDEM do schema: primeiro "hook_text" e "analysis", depois as notas.
"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "clips": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    # 1) Localização: copiada da transcrição
                    "start": {"type": "STRING", "description": "Início do clipe (HH:MM:SS), copiado exatamente de um segmento da transcrição."},
                    "end": {"type": "STRING", "description": "Fim do clipe (HH:MM:SS), copiado exatamente de um segmento da transcrição."},
                    "hook": {"type": "STRING", "description": "Instante do pico (HH:MM:SS)."},

                    # 2) Evidência e raciocínio ANTES das notas
                    "hook_text": {"type": "STRING", "description": "Frase exata, citada da transcrição, que abre o clipe."},
                    "opening_check": {"type": "STRING", "description": "A primeira frase prende sozinha? O que falta de contexto, se algo?"},
                    "analysis": {"type": "STRING", "description": "Raciocínio em 2-4 frases: por que esse trecho funciona ou não como Short, citando falas."},
                    "is_standalone": {"type": "BOOLEAN", "description": "True somente se o clipe é compreensível sem ver o resto do vídeo."},

                    # 3) Subnotas e nota final
                    "score_hook": {"type": "INTEGER", "minimum": 0, "maximum": 3},
                    "score_payoff": {"type": "INTEGER", "minimum": 0, "maximum": 3},
                    "score_standalone": {"type": "INTEGER", "minimum": 0, "maximum": 2},
                    "score_shareability": {"type": "INTEGER", "minimum": 0, "maximum": 2},
                    "viral_score": {"type": "INTEGER", "minimum": 0, "maximum": 10},

                    # 4) Metadados para publicação
                    "category": {
                        "type": "STRING",
                        "enum": ["EDUCATIVO", "POLÊMICO", "ENGRAÇADO", "RELEVANTE"],
                    },
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "last_line": {
                        "type": "STRING",
                        "description": "Última frase do clipe, citada exatamente."
                    },
                    "has_promo_or_cta": {
                        "type": "BOOLEAN",
                        "description": "True se qualquer parte do clipe pede like, inscrição, comentário, cupom, link ou divulga produto/canal."
                    },
                },
                "propertyOrdering": [
                    "start", "end", "hook", "hook_text", "opening_check",
                    "analysis", "is_standalone",
                    "score_hook", "score_payoff", "score_standalone",
                    "score_shareability", "viral_score",
                    "category", "title", "description", "summary",
                    "last_line", "has_promo_or_cta",
                ],
                "required": [
                    "start", "end", "hook", "hook_text", "opening_check",
                    "analysis", "is_standalone",
                    "score_hook", "score_payoff", "score_standalone",
                    "score_shareability", "viral_score",
                    "category", "title", "description", "summary",
                    "last_line", "has_promo_or_cta",
                ],
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
