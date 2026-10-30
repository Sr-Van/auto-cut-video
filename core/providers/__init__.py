"""Subpacote de provedores de IA (Strategy + Factory)."""

from core.providers.base import (
    APIHTTPError,
    BaseAIProvider,
    KeyTarget,
    extract_json,
    get_http_client,
    is_schema_unsupported,
    status_code_from_exc,
)
from core.providers.factory import (
    detect_provider_and_key,
    get_provider,
    resolve_targets,
)
from core.providers.gemini_provider import GeminiProvider
from core.providers.groq_provider import GroqProvider
from core.providers.ollama_provider import OllamaProvider
from core.providers.openai_provider import (
    CerebrasProvider,
    MistralProvider,
    OpenAIProvider,
    OpenRouterProvider,
    get_openrouter_models,
    reset_openrouter_cache,
)

__all__ = [
    "APIHTTPError",
    "BaseAIProvider",
    "CerebrasProvider",
    "GeminiProvider",
    "GroqProvider",
    "KeyTarget",
    "MistralProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "detect_provider_and_key",
    "extract_json",
    "get_http_client",
    "get_openrouter_models",
    "get_provider",
    "is_schema_unsupported",
    "reset_openrouter_cache",
    "resolve_targets",
    "status_code_from_exc",
]

