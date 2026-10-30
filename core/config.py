import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

# Catalogo de provedores compativeis com o padrao OpenAI (/chat/completions).
PROVIDERS_CATALOG: dict[str, dict] = {
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3.5-super-vl:free",
            "dots-studio/dots-3-note-preview:free",
            "recursive/flint-v1.0:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "nvidia/nemotron-3.5-lightning:free",
            "google/gemma-4-26b-a4b-it:free",
            "xingchen-agi/xing4.0-29b-a4b:free",
            "poolside/laguna-s-2.1:free",
        ],
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
            "llama-3.1-8b-instant",
        ],
    },
    "cerebras": {
        "name": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "models": [
            "llama-3.3-70b",
            "gpt-oss-120b",
            "llama3.1-8b",
        ],
    },
    "mistral": {
        "name": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "models": [
            "mistral-small-latest",
            "mistral-large-latest",
        ],
    },
    "google": {
        "name": "Google AI Studio",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": [
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-2.5-flash",
        ],
    },
}

_PROVIDER_ENV_MAP = [
    ("openrouter", ("OPENROUTER_API_KEY", "OPENROUTER_API_KEYS")),
    ("groq", ("GROQ_API_KEY", "GROQ_API_KEYS")),
    ("cerebras", ("CEREBRAS_API_KEY", "CEREBRAS_API_KEYS")),
    ("mistral", ("MISTRAL_API_KEY", "MISTRAL_API_KEYS")),
    ("google", ("GOOGLE_API_KEY", "GOOGLE_API_KEYS", "GEMINI_API_KEY", "GEMINI_API_KEYS")),
]

AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip()
AI_MODELS = [
    m.strip()
    for m in re.split(r"[,\s]+", os.getenv("AI_MODELS", ""))
    if m.strip()
]


def detect_provider(raw_key: str) -> tuple[str, str]:
    """Retorna (provider_id, api_key_limpa) a partir do prefixo ou formato da chave."""
    text = (raw_key or "").strip()
    if ":" in text:
        prefix, rest = text.split(":", 1)
        prov = prefix.strip().lower()
        if prov == "gemini":
            prov = "google"
        if prov in PROVIDERS_CATALOG and rest.strip():
            return prov, rest.strip()

    match text:
        case _ if text.startswith("sk-or-"):
            return "openrouter", text
        case _ if text.startswith("gsk_"):
            return "groq", text
        case _ if text.startswith("csk-"):
            return "cerebras", text
        case _ if text.startswith(("AIza", "AQ.")):
            return "google", text
        case _ if AI_PROVIDER in PROVIDERS_CATALOG:
            return AI_PROVIDER, text
        case _ if re.fullmatch(r"[A-Za-z0-9]{32}", text):
            return "mistral", text
        case _ if AI_BASE_URL:
            return "openrouter", text
        case _:
            return "google", text


def _load_api_keys() -> list[str]:
    """Le chaves em variaveis por provedor, API_KEY_1..N, API_KEYS e API_KEY."""
    keys: list[str] = []

    for provider, env_names in _PROVIDER_ENV_MAP:
        for env_name in env_names:
            for part in re.split(r"[,\s]+", os.getenv(env_name, "")):
                val = part.strip()
                if not val:
                    continue
                detected, clean = detect_provider(val)
                if detected == provider and not val.startswith(f"{provider}:"):
                    keys.append(val)
                else:
                    keys.append(f"{provider}:{clean}")

    numbered: list[tuple[int, str]] = []
    for name, value in os.environ.items():
        match = re.fullmatch(r"API_KEY_(\d+)", name)
        if match and value.strip():
            numbered.append((int(match.group(1)), value.strip()))
    keys += [value for _, value in sorted(numbered)]

    for part in re.split(r"[,\s]+", os.getenv("API_KEYS", "")):
        if part.strip():
            keys.append(part.strip())

    single = os.getenv("API_KEY", "").strip()
    if single:
        keys.append(single)

    seen: set[tuple[str, str]] = set()
    unique: list[str] = []
    for key in keys:
        prov, clean = detect_provider(key)
        dedup_key = (prov, clean)
        if clean and dedup_key not in seen:
            seen.add(dedup_key)
            unique.append(key)
    return unique


API_KEYS = _load_api_keys()
# Mantido por compatibilidade (primeira chave configurada).
API_KEY = API_KEYS[0] if API_KEYS else ""

# Modelos Gemini reais (mantido por compatibilidade com imports existentes).
MODELOS_GEMINI = list(PROVIDERS_CATALOG["google"]["models"])
MODELO_GEMINI = MODELOS_GEMINI[0]

AI_MAX_ATTEMPTS = int(os.getenv("AI_MAX_ATTEMPTS", os.getenv("GEMINI_MAX_ATTEMPTS", "4")))
AI_TIMEOUT_S = float(os.getenv("AI_TIMEOUT_S", os.getenv("GEMINI_TIMEOUT_S", "120")))
AI_BACKOFF_BASE = float(os.getenv("AI_BACKOFF_BASE", os.getenv("GEMINI_BACKOFF_BASE", "2")))
AI_BACKOFF_MAX = float(os.getenv("AI_BACKOFF_MAX", os.getenv("GEMINI_BACKOFF_MAX", "60")))

# Aliases legados
GEMINI_MAX_ATTEMPTS = AI_MAX_ATTEMPTS
GEMINI_TIMEOUT_S = AI_TIMEOUT_S
GEMINI_BACKOFF_BASE = AI_BACKOFF_BASE
GEMINI_BACKOFF_MAX = AI_BACKOFF_MAX

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "auto")
TEMPERATURA = 0.3
PADDING_S = 5
MIN_CLIP_DURATION = 30
MAX_CLIP_DURATION = 90
PAUSE_GAP = 1.5
# Nota minima (0-10) para um clipe ser mantido. A meta e nota 10, mas clipes
# a partir desta nota tambem sao aproveitados.
MIN_VIRAL_SCORE = int(os.getenv("MIN_VIRAL_SCORE", "8"))
# Limite de clipes por video (teto de seguranca, nao uma meta).
MAX_CLIPS = int(os.getenv("MAX_CLIPS", "15"))
LANGUAGE = os.getenv("LANGUAGE", "pt")

# --- Clip vertical 9:16 com fundo desfocado ---
VERTICAL_ENABLED = os.getenv("VERTICAL_ENABLED", "1").lower() not in ("0", "false", "no")
VERTICAL_WIDTH = int(os.getenv("VERTICAL_WIDTH", "1080"))
VERTICAL_HEIGHT = int(os.getenv("VERTICAL_HEIGHT", "1920"))
# Fator de zoom do video principal sobre o "contain" (1.0 = enquadra inteiro).
VERTICAL_ZOOM = float(os.getenv("VERTICAL_ZOOM", "1.7"))
VERTICAL_BLUR_SIGMA = float(os.getenv("VERTICAL_BLUR_SIGMA", "6"))
VERTICAL_BLUR_DIVISOR = int(os.getenv("VERTICAL_BLUR_DIVISOR", "4"))
VERTICAL_BG_BRIGHTNESS = float(os.getenv("VERTICAL_BG_BRIGHTNESS", "-0.05"))
# Encoder vazio = detecta automaticamente (hardware, com fallback libx264).
VERTICAL_ENCODER = os.getenv("VERTICAL_ENCODER", "").strip()
VERTICAL_CRF = int(os.getenv("VERTICAL_CRF", "20"))
VERTICAL_PRESET = os.getenv("VERTICAL_PRESET", "veryfast")
VERTICAL_MAX_WORKERS = int(os.getenv("VERTICAL_MAX_WORKERS", "2"))
