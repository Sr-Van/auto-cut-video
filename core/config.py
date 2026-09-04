import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

API_KEY = os.getenv("API_KEY", "")
MODELO_GEMINI = "gemini-3.6-flash"
WHISPER_MODEL = "large"
TEMPERATURA = 0.3
PADDING_S = 5
MIN_CLIP_DURATION = 30
MAX_CLIP_DURATION = 90
PAUSE_GAP = 1.5
LANGUAGE = "pt"
