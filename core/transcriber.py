from dataclasses import dataclass

from faster_whisper import WhisperModel

from core.config import LANGUAGE, WHISPER_COMPUTE_TYPE, WHISPER_MODEL


@dataclass
class Segment:
    start: float
    end: float
    text: str
    id: str = ""


def transcribe(audio_path: str) -> list[Segment]:
    model = WhisperModel(WHISPER_MODEL, device="auto", compute_type=WHISPER_COMPUTE_TYPE)
    segments, _info = model.transcribe(audio_path, language=LANGUAGE)
    return [
        Segment(id=f"S{i:04d}", start=s.start, end=s.end, text=s.text.strip())
        for i, s in enumerate(segments, start=1)
    ]


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Uso: python -m core.transcriber <audio>")
        raise SystemExit(1)

    for seg in transcribe(sys.argv[1]):
        print(f"[{seg.start:7.2f} - {seg.end:7.2f}] {seg.text}")
