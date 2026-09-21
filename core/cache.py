"""Cache de transcricao em disco.

A chave inclui o hash do video (tamanho + mtime + primeiros MB) e os
parametros que alteram a transcricao. Qualquer divergencia = cache miss.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.transcriber import Segment

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


def make_key(video_path, whisper_model, language, compute_type) -> dict:
    return {
        "video_hash": video_hash(video_path),
        "whisper_model": whisper_model,
        "language": language,
        "compute_type": compute_type,
    }


def transcript_path(out_dir) -> Path:
    return Path(out_dir) / TRANSCRIPT_FILENAME


def _segment_to_dict(segment, index) -> dict:
    return {
        "id": getattr(segment, "id", "") or f"S{index:04d}",
        "start": float(segment.start),
        "end": float(segment.end),
        "text": segment.text,
    }


def save_transcript(out_dir, key, segments) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "key": key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "segments": [
            _segment_to_dict(seg, i) for i, seg in enumerate(segments, start=1)
        ],
    }
    transcript_path(out_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def load_transcript(out_dir, key) -> list[Segment] | None:
    """Retorna os segmentos apenas se TODOS os campos da chave baterem."""
    path = transcript_path(out_dir)
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
        return [
            Segment(
                id=raw.get("id") or f"S{i:04d}",
                start=float(raw["start"]),
                end=float(raw["end"]),
                text=str(raw.get("text", "")),
            )
            for i, raw in enumerate(raw_segments, start=1)
        ]
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
