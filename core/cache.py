"""Cache de transcricao em disco.

A chave inclui o hash do video (tamanho + mtime + primeiros MB) e os
parametros que alteram a transcricao. Qualquer divergencia = cache miss.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.transcriber import Segment, Word

HEAD_BYTES = 1024 * 1024  # primeiros 1 MB do video
TRANSCRIPT_FILENAME = "transcript.json"


def video_hash(video_path: str, head_bytes: int = HEAD_BYTES) -> str:
    """Hash barato: tamanho + mtime + primeiros bytes. Nao le o video inteiro."""
    path = Path(video_path)
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode("utf-8"))
    digest.update(str(stat.st_mtime_ns).encode("utf-8"))
    with path.open("rb") as handle:
        digest.update(handle.read(head_bytes))
    return digest.hexdigest()


def make_key(video_path, whisper_model, language, compute_type, word_timestamps=False) -> dict:
    return {
        "video_hash": video_hash(video_path),
        "whisper_model": whisper_model,
        "language": language,
        "compute_type": compute_type,
        "word_timestamps": bool(word_timestamps),
    }


def make_clip_key(
    video_path, start_s, end_s, whisper_model, language, compute_type
) -> dict:
    """Chave para a transcricao de um trecho (sempre com palavras)."""
    key = make_key(
        video_path, whisper_model, language, compute_type, word_timestamps=True
    )
    key["window"] = [round(float(start_s), 3), round(float(end_s), 3)]
    return key


def transcript_path(out_dir) -> Path:
    return Path(out_dir) / TRANSCRIPT_FILENAME


def clip_transcript_path(cache_dir, index: int) -> Path:
    return Path(cache_dir) / f"clip_{int(index):03d}.json"


def _segment_to_dict(segment, index) -> dict:
    return {
        "id": getattr(segment, "id", "") or f"S{index:04d}",
        "start": float(segment.start),
        "end": float(segment.end),
        "text": segment.text,
        "words": [
            {"start": float(w.start), "end": float(w.end), "text": w.text}
            for w in (getattr(segment, "words", None) or [])
        ],
    }


def save_transcript_file(path, key, segments) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "key": key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "segments": [
            _segment_to_dict(seg, i) for i, seg in enumerate(segments, start=1)
        ],
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def load_transcript_file(path, key) -> list[Segment] | None:
    """Retorna os segmentos apenas se TODOS os campos da chave baterem."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("key") != key:
        return None
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        return None
    try:
        segments = []
        for i, raw in enumerate(raw_segments, start=1):
            words = [
                Word(
                    start=float(w["start"]),
                    end=float(w["end"]),
                    text=str(w.get("text", "")),
                )
                for w in (raw.get("words") or [])
            ]
            segments.append(
                Segment(
                    id=raw.get("id") or f"S{i:04d}",
                    start=float(raw["start"]),
                    end=float(raw["end"]),
                    text=str(raw.get("text", "")),
                    words=words,
                )
            )
        return segments
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def save_transcript(out_dir, key, segments) -> dict:
    return save_transcript_file(transcript_path(out_dir), key, segments)


def load_transcript(out_dir, key) -> list[Segment] | None:
    return load_transcript_file(transcript_path(out_dir), key)
