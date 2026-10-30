"""Camada base de provedores de IA (Strategy Pattern)."""

from __future__ import annotations

import json
import re
from abc import ABC
from dataclasses import dataclass

import httpx

from core.config import AI_TIMEOUT_S, TEMPERATURA

SCHEMA_UNSUPPORTED_MARKERS = (
    "response_format",
    "json_schema",
    "structured",
    "additionalproperties",
    "schema",
    "strict",
    "no endpoints found",
)


@dataclass(frozen=True)
class KeyTarget:
    provider: str
    provider_name: str
    api_key: str
    base_url: str
    models: tuple[str, ...]

    @property
    def id(self) -> tuple[str, str]:
        return (self.provider, self.api_key)


class APIHTTPError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        response: httpx.Response | None = None,
    ):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.response = response


_HTTP_CLIENT: httpx.Client | None = None


def get_http_client(timeout_s: float = AI_TIMEOUT_S) -> httpx.Client:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.Client(timeout=httpx.Timeout(timeout_s))
    return _HTTP_CLIENT


def status_code_from_exc(exc: Exception) -> int | None:
    """Extrai codigo HTTP do erro, se houver."""
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


def is_schema_unsupported(exc: Exception) -> bool:
    """Indica que o modelo nao aceitou response_format json_schema estrito."""
    code = status_code_from_exc(exc)
    if code not in (400, 404, 422):
        return False
    text = str(exc).lower()
    return any(m in text for m in SCHEMA_UNSUPPORTED_MARKERS)


def extract_json(raw_text: str) -> dict:
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
    fenced = re.search(
        r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE
    )
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


class BaseAIProvider(ABC):
    """Contrato base para provedores compativeis com Chat Completions."""

    provider_id: str = "base"
    provider_name: str = "Base Provider"
    default_base_url: str = ""
    default_models: tuple[str, ...] = ()

    def build_headers(self, api_key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def get_models(
        self,
        base_url: str | None = None,
        custom_models: list[str] | tuple[str, ...] | None = None,
        client: httpx.Client | None = None,
    ) -> tuple[str, ...]:
        if custom_models:
            return tuple(custom_models)
        return self.default_models

    def prefers_prompt_schema(self, model: str, is_mock: bool = False) -> bool:
        return False

    def post_completion(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        transcript_block: str,
        *,
        base_url: str | None = None,
        mode: str = "json_schema",
        schema: dict | None = None,
        fallback_instruction: str = "",
        temperature: float = TEMPERATURA,
        client: httpx.Client | None = None,
    ) -> dict:
        effective_base = (base_url or self.default_base_url).rstrip("/")
        url = f"{effective_base}/chat/completions"
        headers = self.build_headers(api_key)

        sys_content = (
            system_prompt
            if mode == "json_schema" or not fallback_instruction
            else system_prompt + fallback_instruction
        )

        payload: dict = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": transcript_block},
            ],
        }

        if mode == "json_schema" and schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "clips_response",
                    "strict": True,
                    "schema": schema,
                },
            }
        elif mode == "json_object":
            payload["response_format"] = {"type": "json_object"}

        http_client = client or get_http_client()
        response = http_client.post(url, headers=headers, json=payload)

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
            raise APIHTTPError(response.status_code, detail, response=response)

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
                if isinstance(meta, dict) and isinstance(meta.get("raw"), str):
                    msg = f"{msg} ({meta['raw']})"
            raise APIHTTPError(code, msg, response=response)

        choices = (body.get("choices") if isinstance(body, dict) else None) or []
        if not choices:
            raise APIHTTPError(
                502, "Resposta sem choices do provedor.", response=response
            )

        message = choices[0].get("message") or {}
        content = message.get("content") or message.get("reasoning") or ""
        return extract_json(content)

    def analyze_transcript(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        transcript_block: str,
        *,
        base_url: str | None = None,
        schema: dict | None = None,
        fallback_instruction: str = "",
        temperature: float = TEMPERATURA,
        client: httpx.Client | None = None,
    ) -> dict:
        """Executa a analise tentando json_schema estrito com fallback automatico."""
        http_client = client or get_http_client()
        is_mock = isinstance(
            getattr(http_client, "_transport", None), httpx.MockTransport
        )
        if self.prefers_prompt_schema(model, is_mock=is_mock):
            return self.post_completion(
                api_key,
                model,
                system_prompt,
                transcript_block,
                base_url=base_url,
                mode="prompt",
                schema=schema,
                fallback_instruction=fallback_instruction,
                temperature=temperature,
                client=http_client,
            )

        try:
            return self.post_completion(
                api_key,
                model,
                system_prompt,
                transcript_block,
                base_url=base_url,
                mode="json_schema",
                schema=schema,
                fallback_instruction=fallback_instruction,
                temperature=temperature,
                client=http_client,
            )
        except Exception as exc:
            if not is_schema_unsupported(exc):
                raise

        try:
            return self.post_completion(
                api_key,
                model,
                system_prompt,
                transcript_block,
                base_url=base_url,
                mode="json_object",
                schema=schema,
                fallback_instruction=fallback_instruction,
                temperature=temperature,
                client=http_client,
            )
        except Exception as exc:
            if not is_schema_unsupported(exc):
                raise

        return self.post_completion(
            api_key,
            model,
            system_prompt,
            transcript_block,
            base_url=base_url,
            mode="prompt",
            schema=schema,
            fallback_instruction=fallback_instruction,
            temperature=temperature,
            client=http_client,
        )

