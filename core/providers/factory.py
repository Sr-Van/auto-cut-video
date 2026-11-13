"""Factory e resolucao de provedores de IA."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from core.config import AI_BASE_URL, AI_MODELS, PROVIDERS_CATALOG, detect_provider
from core.providers.base import BaseAIProvider, KeyTarget
from core.providers.gemini_provider import GeminiProvider
from core.providers.groq_provider import GroqProvider
from core.providers.ollama_provider import OllamaProvider
from core.providers.openai_provider import (
    CerebrasProvider,
    MistralProvider,
    OpenAIProvider,
    OpenRouterProvider,
)

if TYPE_CHECKING:
    from core.options import ProcessingOptions

_PROVIDER_INSTANCES: dict[str, BaseAIProvider] = {
    "google": GeminiProvider(),
    "gemini": GeminiProvider(),
    "openrouter": OpenRouterProvider(),
    "groq": GroqProvider(),
    "cerebras": CerebrasProvider(),
    "mistral": MistralProvider(),
    "openai": OpenAIProvider(),
    "ollama": OllamaProvider(),
}


def get_provider(
    provider_name: str,
    options: ProcessingOptions | None = None,
) -> BaseAIProvider:
    """Retorna a instancia do provedor correspondente ao identificador."""
    norm = (provider_name or "").strip().lower()
    if norm in _PROVIDER_INSTANCES:
        return _PROVIDER_INSTANCES[norm]
    return _PROVIDER_INSTANCES["openrouter"]


def detect_provider_and_key(raw_key: str) -> tuple[str, str]:
    """Detecta o provedor suportando tambem prefixos explicitos para openai e ollama."""
    text = (raw_key or "").strip()
    if ":" in text:
        prefix, rest = text.split(":", 1)
        prov = prefix.strip().lower()
        if prov in ("openai", "ollama") and rest.strip():
            return prov, rest.strip()
    return detect_provider(text)


def _preferred_model(options, provider_id: str) -> str:
    """Modelo escolhido na GUI, se for deste provedor."""
    choice = (getattr(options, "ai_model", "") or "").strip()
    if ":" not in choice:
        return ""
    prov, model = choice.split(":", 1)
    prov = "google" if prov.strip().lower() == "gemini" else prov.strip().lower()
    return model.strip() if prov == provider_id and model.strip() else ""


# Modelos que nao servem para gerar texto (filtrados da lista da GUI).
_NON_CHAT_HINTS = (
    "embed", "tts", "whisper", "audio", "image", "imagen", "veo", "guard",
    "moderation", "transcribe", "realtime", "dall-e", "aqa", "learnlm", "ocr",
)


def list_available_models(
    raw_keys: list[str],
    *,
    client: httpx.Client | None = None,
    live: bool = True,
) -> list[tuple[str, str, tuple[str, ...]]]:
    """Agrupa os modelos disponiveis por provedor das chaves configuradas.

    Retorna [(provider_id, nome, modelos)]. Recomendados do catalogo primeiro,
    depois os que a API devolveu ao vivo (quando `live`).
    """
    seen: dict[str, tuple[str, str, str]] = {}
    for raw in raw_keys:
        provider_id, clean_key = detect_provider_and_key(raw)
        if clean_key and provider_id not in seen:
            provider_obj = get_provider(provider_id)
            cat = PROVIDERS_CATALOG.get(provider_id)
            base = AI_BASE_URL or (cat["base_url"] if cat else provider_obj.default_base_url)
            seen[provider_id] = (clean_key, base, cat["name"] if cat else provider_obj.provider_name)

    result = []
    for provider_id, (key, base, name) in seen.items():
        provider_obj = get_provider(provider_id)
        cat = PROVIDERS_CATALOG.get(provider_id)
        recommended = list(cat["models"] if cat else provider_obj.default_models)
        fetched: tuple[str, ...] = ()
        if live:
            if provider_id == "openrouter":
                fetched = provider_obj.get_models(base_url=base, client=client)
            else:
                fetched = provider_obj.fetch_models(key, base, client=client)
        extras = sorted(
            m for m in fetched
            if m not in recommended and not any(h in m.lower() for h in _NON_CHAT_HINTS)
        )
        if fetched:
            # recomendados que a chave nao enxerga ficam de fora
            live_set = set(fetched)
            recommended = [m for m in recommended if m in live_set] or recommended
        result.append((provider_id, name, tuple(recommended + extras)))
    return result


def resolve_targets(
    raw_keys: list[str],
    options: ProcessingOptions | None = None,
    *,
    base_url_override: str | None = None,
    models_override: list[str] | None = None,
    client: httpx.Client | None = None,
) -> list[KeyTarget]:
    """Converte chaves brutas em alvos de execucao (KeyTarget) via Factory."""
    targets: list[KeyTarget] = []
    eff_base_override = (
        base_url_override if base_url_override is not None else AI_BASE_URL
    )
    eff_models_override = (
        models_override if models_override is not None else AI_MODELS
    )

    for raw in raw_keys:
        provider_id, clean_key = detect_provider_and_key(raw)
        if not clean_key:
            continue
        provider_obj = get_provider(provider_id, options=options)
        cat_info = PROVIDERS_CATALOG.get(provider_id)
        default_base = (
            cat_info["base_url"] if cat_info else provider_obj.default_base_url
        )
        provider_name = (
            cat_info["name"] if cat_info else provider_obj.provider_name
        )
        base_url = eff_base_override or default_base

        if eff_models_override:
            models = tuple(eff_models_override)
        else:
            fallback = (
                cat_info["models"]
                if cat_info
                else list(provider_obj.default_models)
            )
            models = provider_obj.get_models(
                base_url=base_url,
                custom_models=None if provider_id == "openrouter" else fallback,
                client=client,
            )

        preferred = _preferred_model(options, provider_obj.provider_id)
        if preferred:
            models = (preferred,) + tuple(m for m in models if m != preferred)

        targets.append(
            KeyTarget(
                provider=provider_obj.provider_id,
                provider_name=provider_name,
                api_key=clean_key,
                base_url=base_url,
                models=models,
            )
        )
    return targets

