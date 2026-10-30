from dataclasses import dataclass, field
from threading import Event, Lock

from faster_whisper import WhisperModel

from core.config import LANGUAGE, WHISPER_COMPUTE_TYPE, WHISPER_MODEL
from core.exceptions import check_cancelled


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


def get_model(
    model_name: str | None = None,
    compute_type: str | None = None,
) -> WhisperModel:
    global _MODEL, _MODEL_KEY
    chosen = (model_name or WHISPER_MODEL).strip() or WHISPER_MODEL
    eff_compute = (compute_type or WHISPER_COMPUTE_TYPE).strip() or WHISPER_COMPUTE_TYPE
    with _INIT_LOCK:
        key = (chosen, eff_compute)
        if _MODEL is None or _MODEL_KEY != key:
            _MODEL = WhisperModel(
                chosen, device="auto", compute_type=eff_compute
            )
            _MODEL_KEY = key
        return _MODEL


def transcribe(
    audio_path: str,
    word_timestamps: bool = False,
    model_name: str | None = None,
    language: str | None = None,
    compute_type: str | None = None,
    cancel_event: Event | None = None,
) -> list[Segment]:
    check_cancelled(cancel_event)
    model = get_model(model_name, compute_type=compute_type)
    eff_lang = (language or LANGUAGE).strip() or LANGUAGE
    check_cancelled(cancel_event)

    # O modelo e compartilhado entre threads (clipes em paralelo), entao a
    # inferencia e serializada. A geracao precisa ser consumida sob o lock,
    # pois o trabalho de fato acontece durante a iteracao.
    raw_segments = []
    with _RUN_LOCK:
        check_cancelled(cancel_event)
        segments_iter, _info = model.transcribe(
            audio_path,
            language=eff_lang,
            word_timestamps=word_timestamps,
        )
        for seg in segments_iter:
            check_cancelled(cancel_event)
            raw_segments.append(seg)

    result: list[Segment] = []
    for i, seg in enumerate(raw_segments, start=1):
        check_cancelled(cancel_event)
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
