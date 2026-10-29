import shutil
import subprocess
from pathlib import Path


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg nao encontrado. Instale o FFmpeg e adicione ao PATH.")
    return ffmpeg


def extract_audio(video_path: str, output_dir: str) -> str:
    ffmpeg = _require_ffmpeg()
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video nao encontrado: {video_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{video.stem}.wav"

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao extrair audio: {result.stderr}")

    return str(output_path)


def extract_audio_segment(
    video_path: str, start_s: float, end_s: float, output_dir: str
) -> str:
    """Extrai apenas a janela [start_s, end_s] em WAV mono 16 kHz."""
    ffmpeg = _require_ffmpeg()
    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video nao encontrado: {video_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{int(round(start_s * 1000))}_{int(round(end_s * 1000))}"
    output_path = out_dir / f"{video.stem}_{tag}.wav"
    duration = max(0.0, end_s - start_s)

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_s:.3f}",
        "-i",
        str(video),
        "-t",
        f"{duration:.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao extrair audio do trecho: {result.stderr}")
    return str(output_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Uso: python -m core.audio <video> <output_dir>")
        raise SystemExit(1)

    audio_path = extract_audio(sys.argv[1], sys.argv[2])
    print(audio_path)
