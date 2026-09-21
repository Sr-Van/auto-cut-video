import tempfile
from pathlib import Path

from core import ai_analyzer, audio, cache, transcriber, video_ops, downloader
from core.config import (
    LANGUAGE,
    MAX_CLIP_DURATION,
    MIN_CLIP_DURATION,
    OUTPUT_DIR,
    PAUSE_GAP,
    WHISPER_COMPUTE_TYPE,
    WHISPER_MODEL,
)
from utils.normalize import normalize_clips
from utils.report import save_report


def _emit(progress_callback, stage, percent, message):
    if progress_callback:
        progress_callback(stage, percent, message)


def run(yt_link=None, video_path=None, output_dir=None, progress_callback=None, force=False):
    if not yt_link and not video_path:
        raise ValueError("Informe yt_link ou video_path.")

    if yt_link:
        _emit(progress_callback, "baixando", 0, "Baixando video...")

        last_scaled = [0]

        def download_progress(stage, percent, message):
            scaled = int(percent * 0.1)
            if scaled == last_scaled[0]:
                return
            last_scaled[0] = scaled
            _emit(progress_callback, stage, scaled, message)

        video_path = downloader.download_video(
            yt_link,
            diretorio_saida=output_dir or str(OUTPUT_DIR),
            progress_callback=download_progress if progress_callback else None,
        )
        if not video_path:
            raise RuntimeError("Falha ao baixar o video.")

    video_path = str(video_path)
    video_stem = Path(video_path).stem
    out_root = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir = out_root / video_stem

    key = cache.make_key(video_path, WHISPER_MODEL, LANGUAGE, WHISPER_COMPUTE_TYPE)

    segments = None if force else cache.load_transcript(out_dir, key)
    if segments is not None:
        _emit(
            progress_callback,
            "transcricao",
            20,
            "Transcricao em cache, pulando...",
        )
    else:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _emit(progress_callback, "audio", 15, "Extraindo audio...")
            audio_path = audio.extract_audio(video_path, tmp_dir)

            _emit(progress_callback, "transcricao", 20, "Transcrevendo audio...")
            segments = transcriber.transcribe(audio_path)

        cache.save_transcript(out_dir, key, segments)


    if segments:
        _emit(progress_callback, "analise", 50, "Analisando com Gemini...")
        clips = ai_analyzer.analyze(segments)
    else:
        clips = []

    _emit(progress_callback, "normalizacao", 65, "Ajustando duracao dos clipes...")
    total_duration = video_ops.get_duration(video_path)
    clips = normalize_clips(
        clips,
        segments,
        total_duration,
        MIN_CLIP_DURATION,
        MAX_CLIP_DURATION,
        PAUSE_GAP,
    )

    _emit(progress_callback, "corte", 70, "Cortando clipes...")
    clip_paths = video_ops.cut_all(video_path, clips, total_duration, out_dir)

    _emit(progress_callback, "relatorio", 95, "Gerando relatorio...")
    report_path = save_report(clips, out_dir, clip_paths)

    _emit(progress_callback, "concluido", 100, "Concluido")

    return {"clips": clips, "clip_paths": clip_paths, "report_path": report_path}


def _cli_progress(stage, percent, message):
    print(f"[{percent:3d}%] {stage}: {message}", flush=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AutoCortesBR pipeline")
    parser.add_argument("alvo", help="Caminho do video ou URL")
    parser.add_argument(
        "--force", action="store_true", help="Ignora o cache e retranscreve"
    )
    args = parser.parse_args()

    entrada = ({"yt_link": args.alvo} if args.alvo.startswith(("http://", "https://"))
               else {"video_path": args.alvo})

    try:
        result = run(progress_callback=_cli_progress, force=args.force, **entrada)
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)

    print()
    print(f"Clipes gerados: {len(result['clip_paths'])}")
    for path in result["clip_paths"]:
        print(f"  {path}")
    print(f"Relatorio: {result['report_path']}")
