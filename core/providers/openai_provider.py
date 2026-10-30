"""Provedores OpenAI e gateways compativeis (OpenRouter, Cerebras, Mistral)."""

from __future__ import annotations

import httpx

from core.config import PROVIDERS_CATALOG
from core.providers.base import BaseAIProvider, get_http_client

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


def get_openrouter_models(
    base_url: str,
    fallback_models: list[str] | tuple[str, ...],
    client: httpx.Client | None = None,
) -> tuple[str, ...]:
    """Descobre dinamicamente os modelos :free ativos no OpenRouter, mantendo a prioridade."""
    global _OPENROUTER_LIVE_MODELS
    if _OPENROUTER_LIVE_MODELS is not None:
        return _OPENROUTER_LIVE_MODELS

    http_client = client or get_http_client()
    if isinstance(getattr(http_client, "_transport", None), httpx.MockTransport):
        return tuple(fallback_models)

    try:
        url = f"{base_url.rstrip('/')}/models"
        resp = http_client.get(url, timeout=8.0)
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
                modality = str(
                    (item.get("architecture") or {}).get("modality") or ""
                )
                if "audio" in modality.split("->")[-1]:
                    continue
                live_free[mid] = ctx

            if live_free:
                ordered: list[str] = [
                    m for m in fallback_models if m in live_free
                ]
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


def reset_openrouter_cache() -> None:
    global _OPENROUTER_LIVE_MODELS
    _OPENROUTER_LIVE_MODELS = None


class OpenAIProvider(BaseAIProvider):
    provider_id = "openai"
    provider_name = "OpenAI"
    default_base_url = "https://api.openai.com/v1"
    default_models = ("gpt-4o-mini", "gpt-4o")


class OpenRouterProvider(OpenAIProvider):
    provider_id = "openrouter"
    provider_name = PROVIDERS_CATALOG["openrouter"]["name"]
    default_base_url = PROVIDERS_CATALOG["openrouter"]["base_url"]
    default_models = tuple(PROVIDERS_CATALOG["openrouter"]["models"])

    def build_headers(self, api_key: str) -> dict[str, str]:
        headers = super().build_headers(api_key)
        headers["HTTP-Referer"] = "https://github.com/autocortesbr"
        headers["X-Title"] = "AutoCortesBR"
        return headers

    def get_models(
        self,
        base_url: str | None = None,
        custom_models: list[str] | tuple[str, ...] | None = None,
        client: httpx.Client | None = None,
    ) -> tuple[str, ...]:
        if custom_models:
            return tuple(custom_models)
        eff_base = base_url or self.default_base_url
        return get_openrouter_models(
            eff_base, self.default_models, client=client
        )

    def prefers_prompt_schema(self, model: str, is_mock: bool = False) -> bool:
        return model.endswith(":free") and not is_mock


class CerebrasProvider(OpenAIProvider):
    provider_id = "cerebras"
    provider_name = PROVIDERS_CATALOG["cerebras"]["name"]
    default_base_url = PROVIDERS_CATALOG["cerebras"]["base_url"]
    default_models = tuple(PROVIDERS_CATALOG["cerebras"]["models"])


class MistralProvider(OpenAIProvider):
    provider_id = "mistral"
    provider_name = PROVIDERS_CATALOG["mistral"]["name"]
    default_base_url = PROVIDERS_CATALOG["mistral"]["base_url"]
    default_models = tuple(PROVIDERS_CATALOG["mistral"]["models"])

