import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.config import OUTPUT_DIR, PADDING_S
from utils.timefmt import clamp_seconds, hhmmss_to_seconds


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg nao encontrado. Instale o FFmpeg e adicione ao PATH.")
    return ffmpeg


def _require_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe nao encontrado. Instale o FFmpeg e adicione ao PATH.")
    return ffprobe


def get_duration(video_path: str) -> float:
    ffprobe = _require_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao obter duracao: {result.stderr}")
    return float(result.stdout.strip())


def cut_clip(video_path: str, start: str, end: str, total_duration: float, out_path: str) -> str:
    ffmpeg = _require_ffmpeg()

    start_s = hhmmss_to_seconds(start)
    end_s = hhmmss_to_seconds(end)
    cut_start = clamp_seconds(start_s - PADDING_S, total_duration)
    cut_end = clamp_seconds(end_s + PADDING_S, total_duration)

    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(cut_start),
        "-to",
        str(cut_end),
        "-i",
        str(video_path),
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao cortar clip: {result.stderr}")
    return out_path


def cut_all(
    video_path: str,
    clips,
    total_duration: float | None = None,
    output_dir: str | None = None,
) -> list[str]:
    if total_duration is None:
        total_duration = get_duration(video_path)

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR / Path(video_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for idx, clip in enumerate(clips, start=1):
        category = clip.get("category", "CORTE")
        out_path = out_dir / f"clip_{idx:03d}_{category}.mp4"
        jobs.append((clip, str(out_path)))

    with ThreadPoolExecutor() as executor:
        futures = {
            out_path: executor.submit(
                cut_clip,
                video_path,
                clip["start"],
                clip["end"],
                total_duration,
                out_path,
            )
            for clip, out_path in jobs
        }

    return [futures[out_path].result() for _, out_path in jobs]
