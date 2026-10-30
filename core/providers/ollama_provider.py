"""Provedor Ollama local (endpoint /v1/chat/completions)."""

from __future__ import annotations

from core.providers.base import BaseAIProvider


class OllamaProvider(BaseAIProvider):
    provider_id = "ollama"
    provider_name = "Ollama"
    default_base_url = "http://localhost:11434/v1"
    default_models = ("llama3.1:8b", "qwen2.5:7b", "gemma2:9b")

    def build_headers(self, api_key: str) -> dict[str, str]:
        token = (api_key or "ollama").strip() or "ollama"
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

