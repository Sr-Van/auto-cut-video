import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"


def _load_api_keys() -> list[str]:
    """Le chaves em API_KEY_1..N, API_KEYS (virgula/espaco) e API_KEY (legado)."""
    keys: list[str] = []

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

    seen: set[str] = set()
    unique: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


API_KEYS = _load_api_keys()
# Mantido por compatibilidade (primeira chave configurada).
API_KEY = API_KEYS[0] if API_KEYS else ""
# Lista de fallback: se um modelo falhar, tenta o proximo da lista.
MODELOS_GEMINI = [
    "gemini-3.8-flash",      # Mais recente e inteligente da linha Flash
    "gemini-3.7-flash",      # Versão anterior excelente
    "gemini-3.6-flash",      # Versão equilibrada
    "gemini-3.5-flash",      # Versão anterior de texto
    "gemini-3.5-flash-lite", # Versão leve com maior limite de RPM (15)
    "gemini-3.1-flash-lite", # Versão leve alternativa
]
# Mantido por compatibilidade (primeiro modelo da lista).
MODELO_GEMINI = MODELOS_GEMINI[0]
GEMINI_MAX_ATTEMPTS = int(os.getenv("GEMINI_MAX_ATTEMPTS", "4"))
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "120"))
GEMINI_BACKOFF_BASE = float(os.getenv("GEMINI_BACKOFF_BASE", "2"))
GEMINI_BACKOFF_MAX = float(os.getenv("GEMINI_BACKOFF_MAX", "60"))
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
