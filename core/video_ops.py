import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core import audio, cache, captions, render, transcriber
from core.config import (
    LANGUAGE,
    OUTPUT_DIR,
    WHISPER_COMPUTE_TYPE,
    WHISPER_MODEL,
)
from core.options import ProcessingOptions
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


def _cut_window(start: str, end: str, total_duration: float, padding_s: float):
    """Janela de corte com padding, limitada a duracao do video."""
    start_s = hhmmss_to_seconds(start)
    end_s = hhmmss_to_seconds(end)
    cut_start = clamp_seconds(start_s - padding_s, total_duration)
    cut_end = clamp_seconds(end_s + padding_s, total_duration)
    return cut_start, cut_end


def cut_clip(
    video_path: str,
    start: str,
    end: str,
    total_duration: float,
    out_path: str,
    padding_s: float = 5.0,
) -> str:
    ffmpeg = _require_ffmpeg()
    cut_start, cut_end = _cut_window(start, end, total_duration, padding_s)

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
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


def _write_clip_captions(words, options: ProcessingOptions, tmp_dir: str) -> str:
    """Grava o .ass no diretorio temporario e copia a fonte para o libass achar."""
    ass_path = os.path.join(tmp_dir, "captions.ass")
    captions.write_ass(words, ass_path, options, options.width, options.height)

    font_file = captions.find_font_path(options.caption_font, options.caption_bold)
    if font_file:
        try:
            shutil.copy2(font_file, tmp_dir)
        except OSError:
            pass
    return ass_path


def _transcribe_clip_words(
    video_path: str,
    cut_start: float,
    cut_end: float,
    out_dir: Path,
    index: int,
) -> list[captions.CaptionWord]:
    """Retranscreve so o trecho do clipe (timing local, mais preciso) com cache."""
    cache_dir = out_dir / ".cache"
    key = cache.make_clip_key(
        video_path, cut_start, cut_end, WHISPER_MODEL, LANGUAGE, WHISPER_COMPUTE_TYPE
    )
    path = cache.clip_transcript_path(cache_dir, index)

    segments = cache.load_transcript_file(path, key)
    if segments is None:
        with tempfile.TemporaryDirectory(prefix="autocut_audio_") as tmp_dir:
            wav_path = audio.extract_audio_segment(video_path, cut_start, cut_end, tmp_dir)
            segments = transcriber.transcribe(wav_path, word_timestamps=True)
        cache.save_transcript_file(path, key, segments)

    words: list[captions.CaptionWord] = []
    for seg in segments:
        for word in seg.words:
            text = (word.text or "").strip()
            if text:
                words.append(
                    captions.CaptionWord(start=word.start, end=word.end, text=text)
                )
    words.sort(key=lambda item: item.start)
    return words


def _clip_words(
    video_path: str,
    cut_start: float,
    cut_end: float,
    out_dir: Path,
    index: int,
    options: ProcessingOptions,
    segments,
):
    if options.caption_transcribe_mode == "clip":
        return _transcribe_clip_words(video_path, cut_start, cut_end, out_dir, index)
    if segments:
        return captions.words_in_window(segments, cut_start, cut_end)
    return []


def _process_vertical(
    video_path, clip, total_duration, out_path, options, segments, index
):
    cut_start, cut_end = _cut_window(
        clip["start"], clip["end"], total_duration, options.padding_s
    )

    if options.captions_enabled:
        words = _clip_words(
            video_path, cut_start, cut_end, Path(out_path).parent, index, options, segments
        )
        if words:
            with tempfile.TemporaryDirectory(prefix="autocut_caps_") as tmp_dir:
                ass_path = _write_clip_captions(words, options, tmp_dir)
                return render.render_clip(
                    video_path,
                    cut_start,
                    cut_end,
                    out_path,
                    options=options,
                    ass_path=ass_path,
                )

    return render.render_clip(
        video_path, cut_start, cut_end, out_path, options=options
    )


def _safe_filename(title, fallback: str, max_length: int = 120) -> str:
    """Converte o titulo em um nome de arquivo valido (Windows/Linux)."""
    name = str(title or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return fallback
    return name[:max_length].rstrip(" .")


def _process_copy(video_path, clip, total_duration, out_path, options, segments, index):
    return cut_clip(
        video_path,
        clip["start"],
        clip["end"],
        total_duration,
        out_path,
        options.padding_s,
    )


def cut_all(
    video_path: str,
    clips,
    total_duration: float | None = None,
    output_dir: str | None = None,
    vertical: bool | None = None,
    options: ProcessingOptions | None = None,
    segments=None,
    progress_callback=None,
) -> list[str]:
    options = options or ProcessingOptions()

    if total_duration is None:
        total_duration = get_duration(video_path)

    if vertical is None:
        # Legendas exigem o caminho de render (que queima o .ass).
        vertical = options.vertical_enabled or options.captions_enabled

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR / Path(video_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    process = _process_vertical if vertical else _process_copy

    jobs = []
    used_names: set[str] = set()
    for idx, clip in enumerate(clips, start=1):
        category = clip.get("category", "CORTE")
        fallback = f"clip_{idx:03d}_{category}"
        base_name = _safe_filename(clip.get("title"), fallback)
        name = base_name
        suffix = 2
        while name.lower() in used_names:
            name = f"{base_name}_{suffix}"
            suffix += 1
        used_names.add(name.lower())
        out_path = out_dir / f"{name}.mp4"
        jobs.append((idx, clip, str(out_path)))

    max_workers = options.max_workers if vertical else None
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process,
                video_path,
                clip,
                total_duration,
                out_path,
                options,
                segments,
                idx,
            ): out_path
            for idx, clip, out_path in jobs
        }

        total = len(futures)
        results: dict[str, str] = {}
        done = 0
        for future in as_completed(futures):
            out_path = futures[future]
            results[out_path] = future.result()
            done += 1
            if progress_callback:
                percent = 70 + int(22 * done / max(1, total))
                progress_callback(
                    "clipes", percent, f"Clipes renderizados: {done}/{total}"
                )

    return [results[out_path] for _, _, out_path in jobs]
