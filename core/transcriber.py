from dataclasses import dataclass, field
from threading import Lock

from faster_whisper import WhisperModel

from core.config import LANGUAGE, WHISPER_COMPUTE_TYPE, WHISPER_MODEL


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    id: str = ""
    words: list[Word] = field(default_factory=list)


# Modelo carregado uma unica vez por processo. Carregar o `large` custa
# alguns segundos; em lote (varios clipes) isso precisa ser reaproveitado.
_MODEL: WhisperModel | None = None
_MODEL_KEY: tuple | None = None
_INIT_LOCK = Lock()
_RUN_LOCK = Lock()


def get_model() -> WhisperModel:
    global _MODEL, _MODEL_KEY
    with _INIT_LOCK:
        key = (WHISPER_MODEL, WHISPER_COMPUTE_TYPE)
        if _MODEL is None or _MODEL_KEY != key:
            _MODEL = WhisperModel(
                WHISPER_MODEL, device="auto", compute_type=WHISPER_COMPUTE_TYPE
            )
            _MODEL_KEY = key
        return _MODEL


def transcribe(audio_path: str, word_timestamps: bool = False) -> list[Segment]:
    model = get_model()
    # O modelo e compartilhado entre threads (clipes em paralelo), entao a
    # inferencia e serializada. A geracao precisa ser consumida sob o lock,
    # pois o trabalho de fato acontece durante a iteracao.
    with _RUN_LOCK:
        raw_segments, _info = model.transcribe(
            audio_path,
            language=LANGUAGE,
            word_timestamps=word_timestamps,
        )
        raw_segments = list(raw_segments)

    result: list[Segment] = []
    for i, seg in enumerate(raw_segments, start=1):
        words: list[Word] = []
        if word_timestamps:
            for raw in getattr(seg, "words", None) or []:
                text = (getattr(raw, "word", "") or "").strip()
                if not text:
                    continue
                words.append(
                    Word(start=float(raw.start), end=float(raw.end), text=text)
                )
        result.append(
            Segment(
                id=f"S{i:04d}",
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                words=words,
            )
        )
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Uso: python -m core.transcriber <audio>")
        raise SystemExit(1)

    for seg in transcribe(sys.argv[1], word_timestamps=True):
        print(f"[{seg.start:7.2f} - {seg.end:7.2f}] {seg.text}")
        for word in seg.words:
            print(f"    {word.start:7.2f} - {word.end:7.2f}  {word.text}")
