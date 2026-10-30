"""Provedor Google Gemini (via endpoint compativel com OpenAI da Google AI Studio)."""

from __future__ import annotations

from core.config import PROVIDERS_CATALOG
from core.providers.base import BaseAIProvider


class GeminiProvider(BaseAIProvider):
    provider_id = "google"
    provider_name = PROVIDERS_CATALOG["google"]["name"]
    default_base_url = PROVIDERS_CATALOG["google"]["base_url"]
    default_models = tuple(PROVIDERS_CATALOG["google"]["models"])

