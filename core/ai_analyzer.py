import json
import random
import re
import time
from dataclasses import dataclass

import httpx

from core.config import (
    AI_BACKOFF_BASE,
    AI_BACKOFF_MAX,
    AI_BASE_URL,
    AI_MAX_ATTEMPTS,
    AI_MODELS,
    AI_TIMEOUT_S,
    API_KEYS,
    MAX_CLIPS,
    MIN_VIRAL_SCORE,
    PROVIDERS_CATALOG,
    TEMPERATURA,
    detect_provider,
)
from utils.timefmt import seconds_to_hhmmss

RULES = """
Você é um editor sênior de Shorts/Reels/TikTok especializado na cultura da internet brasileira. Seu trabalho é encontrar os melhores cortes de um vídeo a partir da transcrição com minutagem. Seu objetivo é encontrar TODOS os trechos do vídeo que funcionam como Short — não apenas o melhor. Busque sempre clipes nota 10, mas clipes com nota {MIN_SCORE} ou 9 também são bons e devem ser incluídos. Seja rigoroso na qualidade de cada clipe, mas NÃO limite artificialmente a quantidade: um vídeo longo normalmente rende vários cortes.

## COMO ANALISAR (siga esta ordem)
1. Leia a transcrição inteira, do início ao fim, e liste TODOS os momentos de impacto (frase de efeito, revelação, piada, confronto, virada emocional, dica surpreendente), distribuídos ao longo de todo o vídeo — não pare no primeiro bom momento.
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
- Máximo de {MAX_CLIPS} clipes (é um teto, não uma meta). Inclua todos os que atingirem a nota mínima; só retorne lista vazia se realmente nenhum trecho atingir.

## NOTA DE VIRALIDADE (0-10) — some os pontos
- Gancho nos primeiros 3 segundos (0-3): 0 = nenhum, 3 = para o scroll imediatamente.
- Payoff/emoção (0-3): 0 = nenhum, 3 = risada, raiva, surpresa ou identificação forte.
- Autonomia (0-2): 0 = precisa de contexto, 2 = totalmente compreensível sozinho.
- Compartilhabilidade (0-2): 0 = ninguém mandaria para amigos, 2 = "olha isso!" imediato.
Inclua TODOS os clipes com nota >= {MIN_SCORE}. A meta é nota 10, mas clipes {MIN_SCORE} e 9 NÃO devem ser descartados. Avalie cada clipe de forma independente e honesta: não há cota de notas altas por vídeo, e a existência de um clipe nota 10 não reduz a nota nem exclui os demais. Ordene a lista pela nota, da maior para a menor.

## CATEGORIAS
EDUCATIVO (revelação do tipo "não sabia disso", dica prática), POLÊMICO (opinião forte, crítica, quebra de tabu), ENGRAÇADO (quebra de expectativa, ironia, gíria, reação exagerada), RELEVANTE (superação, conselho, reflexão). Escolha a que melhor explica POR QUE o clipe prende.

## SAÍDA
Retorne JSON seguindo o schema. Preencha os campos NA ORDEM do schema: primeiro "hook_text" e "analysis", depois as notas.
"""

CLIP_REQUIRED_FIELDS = [
    "start",
    "end",
    "hook",
    "hook_text",
    "opening_check",
    "analysis",
    "is_standalone",
    "score_hook",
    "score_payoff",
    "score_standalone",
    "score_shareability",
    "viral_score",
    "category",
    "title",
    "description",
    "summary",
    "last_line",
    "has_promo_or_cta",
]

# JSON Schema padrao (OpenAI Structured Outputs / OpenRouter / Groq / Cerebras / Mistral / Google)
SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "string",
                        "description": "Início do clipe (HH:MM:SS), copiado exatamente de um segmento da transcrição.",
                    },
                    "end": {
                        "type": "string",
                        "description": "Fim do clipe (HH:MM:SS), copiado exatamente de um segmento da transcrição.",
                    },
                    "hook": {
                        "type": "string",
                        "description": "Instante do pico (HH:MM:SS).",
                    },
                    "hook_text": {
                        "type": "string",
                        "description": "Frase exata, citada da transcrição, que abre o clipe.",
                    },
                    "opening_check": {
                        "type": "string",
                        "description": "A primeira frase prende sozinha? O que falta de contexto, se algo?",
                    },
                    "analysis": {
                        "type": "string",
                        "description": "Raciocínio em 2-4 frases: por que esse trecho funciona ou não como Short, citando falas.",
                    },
                    "is_standalone": {
                        "type": "boolean",
                        "description": "True somente se o clipe é compreensível sem ver o resto do vídeo.",
                    },
                    "score_hook": {"type": "integer", "minimum": 0, "maximum": 3},
                    "score_payoff": {"type": "integer", "minimum": 0, "maximum": 3},
                    "score_standalone": {"type": "integer", "minimum": 0, "maximum": 2},
                    "score_shareability": {"type": "integer", "minimum": 0, "maximum": 2},
                    "viral_score": {"type": "integer", "minimum": 0, "maximum": 10},
                    "category": {
                        "type": "string",
                        "enum": ["EDUCATIVO", "POLÊMICO", "ENGRAÇADO", "RELEVANTE"],
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "summary": {"type": "string"},
                    "last_line": {
                        "type": "string",
                        "description": "Última frase do clipe, citada exatamente.",
                    },
                    "has_promo_or_cta": {
                        "type": "boolean",
                        "description": "True se qualquer parte do clipe pede like, inscrição, comentário, cupom, link ou divulga produto/canal.",
                    },
                },
                "required": CLIP_REQUIRED_FIELDS,
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

SCHEMA_FALLBACK_INSTRUCTION = """

FORMATO JSON OBRIGATÓRIO (responda APENAS com um objeto JSON válido, sem markdown):
{
  "clips": [
    {
      "start": "HH:MM:SS",
      "end": "HH:MM:SS",
      "hook": "HH:MM:SS",
      "hook_text": "string",
      "opening_check": "string",
      "analysis": "string",
      "is_standalone": true,
      "score_hook": 3,
      "score_payoff": 3,
      "score_standalone": 2,
      "score_shareability": 2,
      "viral_score": 10,
      "category": "EDUCATIVO | POLÊMICO | ENGRAÇADO | RELEVANTE",
      "title": "string",
      "description": "string",
      "summary": "string",
      "last_line": "string",
      "has_promo_or_cta": false
    }
  ]
}
"""


@dataclass(frozen=True)
class _KeyTarget:
    provider: str
    provider_name: str
    api_key: str
    base_url: str
    models: tuple[str, ...]

    @property
    def id(self) -> tuple[str, str]:
        return (self.provider, self.api_key)


class _APIHTTPError(Exception):
    def __init__(self, status_code: int, message: str, response: httpx.Response | None = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.response = response


def build_rules() -> str:
    """Preenche os placeholders das regras com os valores da config."""
    return (
        RULES.replace("{MAX_CLIPS}", str(MAX_CLIPS))
        .replace("{MIN_SCORE}", str(MIN_VIRAL_SCORE))
    )


def _filter_by_score(clips) -> list[dict]:
    """Mantem clipes com nota >= MIN_VIRAL_SCORE, do maior para o menor."""
    kept = []
    for clip in clips or []:
        if not isinstance(clip, dict):
            continue
        start = str(clip.get("start") or "").strip()
        end = str(clip.get("end") or "").strip()
        if not start or not end:
            continue
        if clip.get("has_promo_or_cta") is True:
            continue
        try:
            score = int(round(float(clip.get("viral_score", 0))))
        except (TypeError, ValueError):
            continue
        if score >= MIN_VIRAL_SCORE:
            normalized = dict(clip)
            normalized["start"] = start
            normalized["end"] = end
            normalized[" hook" if False else "hook"] = str(clip.get("hook") or start).strip()
            normalized["viral_score"] = score
            normalized.setdefault("category", "RELEVANTE")
            normalized.setdefault("title", "Corte")
            normalized.setdefault("description", "")
            normalized.setdefault("summary", "")
            kept.append(normalized)
    kept.sort(key=lambda c: int(c.get("viral_score", 0)), reverse=True)
    return kept[:MAX_CLIPS]


def build_transcript_block(segments) -> str:
    lines = []
    for seg in segments:
        start = seconds_to_hhmmss(seg.start)
        end = seconds_to_hhmmss(seg.end)
        lines.append(f"[{start} - {end}] {seg.text}")
    return "\n".join(lines)


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}
OVERLOAD_STATUS = {502, 503, 504, 529}
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.TransportError,
    ConnectionError,
    TimeoutError,
)


def _emit_retry(progress_callback, message, percent=50):
    if progress_callback:
        progress_callback("analise", percent, message)


def _retry_after_seconds(exc) -> float | None:
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


def _status_code(exc) -> int | None:
    """Codigo HTTP do erro, se houver."""
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def _is_retryable(exc) -> bool:
    """Retry para 408/429/5xx e falhas de transporte."""
    code = _status_code(exc)
    if code is not None:
        return code in RETRYABLE_STATUS
    return isinstance(exc, RETRYABLE_EXCEPTIONS)


def _is_overload(exc) -> bool:
    """Sobrecarga do modelo no servidor (503 / Overloaded / timeout / upstream congestion)."""
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return True
    code = _status_code(exc)
    if code in OVERLOAD_STATUS:
        return True
    text = str(exc).lower()
    if code == 429 and (
        "rate-limited upstream" in text
        or "temporarily rate-limited" in text
        or "provider returned error" in text
    ):
        return True
    if code is not None and 400 <= code < 500:
        return False
    return (
        "overloaded" in text
        or "high demand" in text
        or "capacity" in text
        or "service unavailable" in text
    )


def _is_quota(exc) -> bool:
    """Rate limit ou cota atingida (429 / RESOURCE_EXHAUSTED)."""
    if _status_code(exc) == 429:
        return True
    text = str(exc).lower()
    return "resource_exhausted" in text or "rate_limit" in text or "quota" in text


def _is_daily_or_billing_quota(exc) -> bool:
    """Distingue cota diaria/credito esgotado de limite por minuto (RPM)."""
    code = _status_code(exc)
    if code == 402:
        return True
    text = str(exc).lower()
    markers = (
        "per day",
        "per_day",
        "rpd",
        "tpd",
        "daily",
        "insufficient_quota",
        "billing",
        "credits",
        "credit balance",
        "free-models-per-day",
    )
    return any(m in text for m in markers)


def _is_context_or_tpm_limit(exc) -> bool:
    """Transcrição grande demais para o limite de tokens/minuto daquele modelo."""
    code = _status_code(exc)
    if code == 413:
        return True
    text = str(exc).lower()
    markers = (
        "context_length",
        "context length",
        "request too large",
        "tokens per minute",
        "tpm",
        "maximum context",
    )
    return any(m in text for m in markers)


def _is_auth_error(exc) -> bool:
    """Chave invalida / sem permissao (ignora 403 especifico de modelo restrito)."""
    code = _status_code(exc)
    if code == 401:
        return True
    if code == 403:
        text = str(exc).lower()
        model_restricted = (
            "only available on" in text
            or "moderation" in text
            or "provider returned error" in text
            or "region" in text
        )
        return not model_restricted
    return False


def _is_schema_unsupported(exc) -> bool:
    """Indica que o modelo nao aceitou response_format json_schema estrito."""
    code = _status_code(exc)
    if code not in (400, 404, 422):
        return False
    text = str(exc).lower()
    markers = (
        "response_format",
        "json_schema",
        "structured",
        "additionalproperties",
        "schema",
        "strict",
        "no endpoints found",
    )
    return any(m in text for m in markers)


def _wait_seconds(attempt, retry_after=None) -> float:
    """Backoff exponencial com jitter; Retry-After tem prioridade."""
    if retry_after is not None:
        return min(AI_BACKOFF_MAX, retry_after)
    delay = min(AI_BACKOFF_MAX, AI_BACKOFF_BASE ** max(0, attempt - 1))
    return delay + random.uniform(0, delay * 0.4)


def _key_label(key: str) -> str:
    """Identifica a chave sem expo-la (so os 4 ultimos caracteres)."""
    key = (key or "").strip()
    return f"...{key[-4:]}" if len(key) > 4 else "(chave)"


_OPENROUTER_LIVE_MODELS: tuple[str, ...] | None = None
_OPENROUTER_EXCLUDED_SUBSTRINGS = (
    "safety",
    "moderation",
    "guard",
    "embed",
    "tts",
    "whisper",
    "lyria",
    "inkling",
    "2.6b",
    "1b",
    "3b",
    "mini-code",
    "xs-",
)


def _get_openrouter_models(base_url: str, fallback_models: list[str]) -> tuple[str, ...]:
    """Descobre dinamicamente os modelos :free ativos no OpenRouter, mantendo a prioridade."""
    global _OPENROUTER_LIVE_MODELS
    if _OPENROUTER_LIVE_MODELS is not None:
        return _OPENROUTER_LIVE_MODELS

    client = _get_http_client()
    if isinstance(getattr(client, "_transport", None), httpx.MockTransport):
        return tuple(fallback_models)

    try:
        url = f"{base_url.rstrip('/')}/models"
        resp = client.get(url, timeout=8.0)
        if resp.status_code == 200:
            items = resp.json().get("data") or []
            live_free: dict[str, int] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                mid = str(item.get("id") or "").strip()
                if not mid.endswith(":free"):
                    continue
                low = mid.lower()
                if any(bad in low for bad in _OPENROUTER_EXCLUDED_SUBSTRINGS):
                    continue
                ctx = int(item.get("context_length") or 0)
                if ctx < 64000:
                    continue
                modality = str((item.get("architecture") or {}).get("modality") or "")
                if "audio" in modality.split("->")[-1]:
                    continue
                live_free[mid] = ctx

            if live_free:
                ordered: list[str] = [m for m in fallback_models if m in live_free]
                extras = sorted(
                    (m for m in live_free if m not in ordered),
                    key=lambda m: live_free[m],
                    reverse=True,
                )
                _OPENROUTER_LIVE_MODELS = tuple(ordered + extras)
                return _OPENROUTER_LIVE_MODELS
    except Exception:
        pass

    return tuple(fallback_models)


def _resolve_targets(raw_keys: list[str]) -> list[_KeyTarget]:
    targets: list[_KeyTarget] = []
    for raw in raw_keys:
        provider, clean_key = detect_provider(raw)
        if not clean_key:
            continue
        info = PROVIDERS_CATALOG.get(provider, PROVIDERS_CATALOG["openrouter"])
        base_url = AI_BASE_URL or info["base_url"]
        if AI_MODELS:
            models = tuple(AI_MODELS)
        elif provider == "openrouter":
            models = _get_openrouter_models(base_url, info["models"])
        else:
            models = tuple(info["models"])
        targets.append(
            _KeyTarget(
                provider=provider,
                provider_name=info["name"],
                api_key=clean_key,
                base_url=base_url,
                models=models,
            )
        )
    return targets


def _extract_json(raw_text: str) -> dict:
    """Extrai o JSON de forma resiliente (remove <think> e cercas markdown se houver)."""
    text = (raw_text or "").strip()
    if not text:
        return {"clips": []}

    # Remove blocos de raciocinio <think>...</think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Tenta parse direto
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"clips": parsed}
    except json.JSONDecodeError:
        pass

    # Remove cercas ```json ... ```
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        inner = fenced.group(1).strip()
        try:
            parsed = json.loads(inner)
            return parsed if isinstance(parsed, dict) else {"clips": parsed}
        except json.JSONDecodeError:
            text = inner

    # Procura primeiro '{' e ultimo '}'
    start_obj = text.find("{")
    end_obj = text.rfind("}")
    if start_obj != -1 and end_obj > start_obj:
        try:
            parsed = json.loads(text[start_obj : end_obj + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start_arr = text.find("[")
    end_arr = text.rfind("]")
    if start_arr != -1 and end_arr > start_arr:
        try:
            parsed = json.loads(text[start_arr : end_arr + 1])
            if isinstance(parsed, list):
                return {"clips": parsed}
        except json.JSONDecodeError:
            pass

    raise ValueError("A resposta do modelo nao contem um JSON valido.")


_HTTP_CLIENT: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.Client(timeout=httpx.Timeout(AI_TIMEOUT_S))
    return _HTTP_CLIENT


def _post_completion(
    target: _KeyTarget,
    model: str,
    system_prompt: str,
    transcript_block: str,
    mode: str = "json_schema",
) -> dict:
    url = f"{target.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {target.api_key}",
        "Content-Type": "application/json",
    }
    if target.provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/autocortesbr"
        headers["X-Title"] = "AutoCortesBR"

    sys_content = (
        system_prompt
        if mode == "json_schema"
        else system_prompt + SCHEMA_FALLBACK_INSTRUCTION
    )

    payload: dict = {
        "model": model,
        "temperature": TEMPERATURA,
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": transcript_block},
        ],
    }

    if mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "clips_response",
                "strict": True,
                "schema": SCHEMA,
            },
        }
    elif mode == "json_object":
        payload["response_format"] = {"type": "json_object"}

    response = _get_http_client().post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        detail = response.text[:400]
        try:
            err_json = response.json()
            if isinstance(err_json, list) and err_json:
                err_json = err_json[0]
            if isinstance(err_json, dict) and "error" in err_json:
                err_obj = err_json["error"]
                if isinstance(err_obj, dict):
                    detail = err_obj.get("message") or detail
                    meta = err_obj.get("metadata")
                    if isinstance(meta, dict) and meta.get("raw"):
                        detail = f"{detail} ({meta['raw']})"
                elif isinstance(err_obj, str):
                    detail = err_obj
        except Exception:
            pass
        raise _APIHTTPError(response.status_code, detail, response=response)

    body = response.json()
    # Alguns gateways (ex.: OpenRouter) podem retornar HTTP 200 contendo {"error": {...}}
    if isinstance(body, dict) and "error" in body and not body.get("choices"):
        err_obj = body["error"]
        code = 502
        msg = str(err_obj)
        if isinstance(err_obj, dict):
            raw_code = err_obj.get("code")
            if isinstance(raw_code, int) and 400 <= raw_code < 600:
                code = raw_code
            msg = err_obj.get("message") or msg
            meta = err_obj.get("metadata")
            if isinstance(meta, dict) and meta.get("raw"):
                msg = f"{msg} ({meta['raw']})"
        raise _APIHTTPError(code, msg, response=response)

    choices = (body.get("choices") if isinstance(body, dict) else None) or []
    if not choices:
        raise _APIHTTPError(502, "Resposta sem choices do provedor.", response=response)

    message = choices[0].get("message") or {}
    content = message.get("content") or message.get("reasoning") or ""
    return _extract_json(content)


def _call_with_schema_fallback(
    target: _KeyTarget,
    model: str,
    system_prompt: str,
    transcript_block: str,
) -> dict:
    """Tenta json_schema estrito; se o modelo nao suportar (ou for :free no OpenRouter), usa prompt."""
    client = _get_http_client()
    is_mock = isinstance(getattr(client, "_transport", None), httpx.MockTransport)
    if target.provider == "openrouter" and model.endswith(":free") and not is_mock:
        return _post_completion(
            target, model, system_prompt, transcript_block, mode="prompt"
        )

    try:
        return _post_completion(
            target, model, system_prompt, transcript_block, mode="json_schema"
        )
    except Exception as exc:
        if not _is_schema_unsupported(exc):
            raise

    try:
        return _post_completion(
            target, model, system_prompt, transcript_block, mode="json_object"
        )
    except Exception as exc:
        if not _is_schema_unsupported(exc):
            raise

    return _post_completion(
        target, model, system_prompt, transcript_block, mode="prompt"
    )


def analyze(segments, progress_callback=None, api_keys=None) -> list[dict]:
    raw_keys = [
        k.strip()
        for k in (api_keys if api_keys is not None else API_KEYS)
        if k and k.strip()
    ]
    targets = _resolve_targets(raw_keys)
    if not targets:
        raise RuntimeError(
            "Nenhuma API key configurada. Defina API_KEY, API_KEYS ou API_KEY_1 no .env."
        )

    block = build_transcript_block(segments)
    system_prompt = build_rules()

    # Intercala chaves e modelos em rodadas:
    # Rodada 0: (Chave 1, Modelo 1), (Chave 2, Modelo 1), ...
    # Rodada 1: (Chave 1, Modelo 2), (Chave 2, Modelo 2), ...
    max_model_depth = max(len(t.models) for t in targets)
    schedule: list[tuple[_KeyTarget, str]] = []
    for m_idx in range(max_model_depth):
        for target in targets:
            if m_idx < len(target.models):
                schedule.append((target, target.models[m_idx]))

    dropped_keys: set[tuple[str, str]] = set()
    cooldown_keys: dict[tuple[str, str], float] = {}
    dead_models: set[tuple[str, str]] = set()
    overloaded_models: set[tuple[str, str]] = set()

    attempt = 0
    max_attempts = max(AI_MAX_ATTEMPTS, AI_MAX_ATTEMPTS * len(schedule))
    last_error: Exception | None = None

    # Duas passagens: a 1ª pula imediatamente qualquer modelo sobrecarregado (503)
    # ou chave em cooldown; a 2ª aguarda o cooldown e retenta modelos sobrecarregados.
    for pass_num in range(2):
        if pass_num == 1:
            overloaded_models.clear()

        for target, model in schedule:
            if attempt >= max_attempts:
                break
            if target.id in dropped_keys:
                continue
            model_key = (target.provider, model)
            if model_key in dead_models or model_key in overloaded_models:
                continue

            # Se a chave esta em cooldown temporario (RPM)
            ready_at = cooldown_keys.get(target.id, 0.0)
            now = time.monotonic()
            if ready_at > now:
                # Na primeira passagem, se houver outra chave livre, pula sem dormir!
                other_free = any(
                    t.id not in dropped_keys and cooldown_keys.get(t.id, 0.0) <= now
                    for t in targets
                )
                if pass_num == 0 and other_free:
                    continue
                wait_cd = min(AI_BACKOFF_MAX, ready_at - now)
                _emit_retry(
                    progress_callback,
                    f"Aguardando {wait_cd:.0f}s para liberar cota ({target.provider_name})...",
                )
                time.sleep(wait_cd)

            attempt += 1
            _emit_retry(
                progress_callback,
                f"Analisando com {target.provider_name} ({model})...",
            )

            try:
                data = _call_with_schema_fallback(
                    target, model, system_prompt, block
                )
                return _filter_by_score(data.get("clips", []))
            except Exception as exc:
                last_error = exc

                # 1) Chave invalida (401/403) -> descarta a chave permanentemente
                if _is_auth_error(exc):
                    _emit_retry(
                        progress_callback,
                        f"Chave {_key_label(target.api_key)} ({target.provider_name}) inválida; trocando...",
                    )
                    dropped_keys.add(target.id)
                    continue

                # 2) Transcrição grande demais para o TPM/contexto desse modelo (ex.: Groq 413)
                if _is_context_or_tpm_limit(exc):
                    _emit_retry(
                        progress_callback,
                        f"Vídeo grande para o limite de tokens de {model}; trocando de modelo...",
                    )
                    dead_models.add(model_key)
                    continue

                # 3) Modelo sobrecarregado (503 / 529 / Overloaded / 429 upstream no OpenRouter) -> pula o modelo imediatamente!
                if _is_overload(exc):
                    _emit_retry(
                        progress_callback,
                        f"Modelo {model} ({target.provider_name}) com muito uso; pulando para outro modelo...",
                    )
                    overloaded_models.add(model_key)
                    continue

                # 4) Cota / Rate Limit da chave (429 / 402)
                if _is_quota(exc) or _status_code(exc) == 402:
                    if _is_daily_or_billing_quota(exc):
                        _emit_retry(
                            progress_callback,
                            f"Cota diária esgotada na chave {_key_label(target.api_key)} ({target.provider_name}); trocando de chave...",
                        )
                        dropped_keys.add(target.id)
                    else:
                        wait = _wait_seconds(attempt, _retry_after_seconds(exc))
                        cooldown_keys[target.id] = time.monotonic() + wait
                        _emit_retry(
                            progress_callback,
                            f"Limite por minuto em {_key_label(target.api_key)} ({target.provider_name}); alternando...",
                        )
                    continue

                # 5) Outros erros temporarios de rede / timeout
                if _is_retryable(exc):
                    wait = _wait_seconds(attempt, _retry_after_seconds(exc))
                    _emit_retry(
                        progress_callback,
                        f"Erro temporário em {target.provider_name} ({model}); tentando próximo em {wait:.0f}s...",
                    )
                    time.sleep(min(wait, 5.0))
                    continue

                # 6) Modelo inexistente/404/incompatível -> marca modelo como indisponivel
                _emit_retry(
                    progress_callback,
                    f"Modelo {model} ({target.provider_name}) indisponível; tentando o próximo...",
                )
                dead_models.add(model_key)
                continue

        if len(dropped_keys) >= len({t.id for t in targets}):
            break

    detalhe = f" Último erro: {last_error}" if last_error else ""
    raise RuntimeError(
        f"Todas as chaves ({len(targets)}) e modelos falharam ou esgotaram.{detalhe} "
        "Adicione uma chave gratuita do OpenRouter (sk-or-...) ou Groq (gsk_...) no .env."
    )
