"""Provedor Groq (inferencia ultrarrapida compativel com OpenAI)."""

from __future__ import annotations

from core.config import PROVIDERS_CATALOG
from core.providers.base import BaseAIProvider


class GroqProvider(BaseAIProvider):
    provider_id = "groq"
    provider_name = PROVIDERS_CATALOG["groq"]["name"]
    default_base_url = PROVIDERS_CATALOG["groq"]["base_url"]
    default_models = tuple(PROVIDERS_CATALOG["groq"]["models"])

