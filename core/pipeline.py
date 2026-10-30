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
from core.options import ProcessingOptions
from utils.normalize import normalize_clips
from utils.report import save_report


def _emit(progress_callback, stage, percent, message):
    if progress_callback:
        progress_callback(stage, percent, message)


def run(
    yt_link=None,
    video_path=None,
    output_dir=None,
    progress_callback=None,
    force=False,
    options: ProcessingOptions | None = None,
):
    options = options or ProcessingOptions()

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

    whisper_model = (options.whisper_model or WHISPER_MODEL).strip() or WHISPER_MODEL
    min_dur = int(options.min_clip_duration or MIN_CLIP_DURATION)
    max_dur = max(min_dur, int(options.max_clip_duration or MAX_CLIP_DURATION))
    pause_gap = float(options.pause_gap if options.pause_gap is not None else PAUSE_GAP)

    key = cache.make_key(
        video_path,
        whisper_model,
        LANGUAGE,
        WHISPER_COMPUTE_TYPE,
        word_timestamps=options.captions_enabled
        and options.caption_transcribe_mode == "full",
    )

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
            segments = transcriber.transcribe(
                audio_path,
                word_timestamps=options.captions_enabled
                and options.caption_transcribe_mode == "full",
                model_name=whisper_model,
            )

        cache.save_transcript(out_dir, key, segments)


    if segments:
        focus = (options.focus_instruction or "").strip()
        msg = f"Analisando com IA (foco: {focus[:60]})..." if focus else "Analisando com IA..."
        _emit(progress_callback, "analise", 50, msg)
        clips = ai_analyzer.analyze(
            segments,
            progress_callback=progress_callback,
            focus=focus,
            max_clips=options.max_clips,
            min_viral_score=options.min_viral_score,
            min_clip_duration=min_dur,
            max_clip_duration=max_dur,
        )
    else:
        clips = []

    _emit(progress_callback, "normalizacao", 65, "Ajustando duracao dos clipes...")
    total_duration = video_ops.get_duration(video_path)
    clips = normalize_clips(
        clips,
        segments,
        total_duration,
        min_dur,
        max_dur,
        pause_gap,
    )

    _emit(progress_callback, "corte", 70, "Cortando clipes...")
    clip_paths = video_ops.cut_all(
        video_path,
        clips,
        total_duration,
        out_dir,
        options=options,
        segments=segments,
        progress_callback=progress_callback,
    )

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
    parser.add_argument(
        "--captions", action="store_true", help="Gera legendas dinamicas"
    )
    parser.add_argument(
        "--foco", default="", help="Regra extra: em que a IA deve focar"
    )
    args = parser.parse_args()

    entrada = ({"yt_link": args.alvo} if args.alvo.startswith(("http://", "https://"))
               else {"video_path": args.alvo})

    options = ProcessingOptions()
    options.captions_enabled = args.captions
    options.focus_instruction = args.foco

    try:
        result = run(
            progress_callback=_cli_progress,
            force=args.force,
            options=options,
            **entrada,
        )
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)

    print()
    print(f"Clipes gerados: {len(result['clip_paths'])}")
    for path in result["clip_paths"]:
        print(f"  {path}")
    print(f"Relatorio: {result['report_path']}")
