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

