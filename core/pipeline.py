import sys
import tempfile
from pathlib import Path
from threading import Event

from core import ai_analyzer, audio, cache, downloader, transcriber, video_ops
from core.config import BASE_DIR, OUTPUT_DIR
from core.exceptions import PipelineCancelledError, check_cancelled
from core.options import ProcessingOptions
from utils.normalize import normalize_clips
from utils.report import save_report


def _emit(progress_callback, stage, percent, message):
    if progress_callback:
        progress_callback(stage, percent, message)


def _cleanup_temp_residuals(temp_dir: Path | None = None) -> None:
    """Remove arquivos temporarios residuais (.part, .ytdl, autocut_*) em temp/."""
    target = temp_dir or (BASE_DIR / "temp")
    if not target.exists():
        return
    for pattern in ("*.part", "*.ytdl", "autocut_*"):
        for item in target.glob(pattern):
            try:
                if item.is_file():
                    item.unlink()
            except OSError:
                pass


def run(
    yt_link=None,
    video_path=None,
    output_dir=None,
    progress_callback=None,
    force=False,
    options: ProcessingOptions | None = None,
    cancel_event: Event | None = None,
):
    options = (options or ProcessingOptions.from_env_or_config()).normalize()
    check_cancelled(cancel_event)

    if not yt_link and not video_path:
        raise ValueError("Informe yt_link ou video_path.")

    try:
        if yt_link:
            _emit(progress_callback, "baixando", 0, "Baixando video...")

            last_scaled = [0]

            def download_progress(stage, percent, message):
                check_cancelled(cancel_event)
                scaled = int(percent * 0.1)
                if scaled == last_scaled[0]:
                    return
                last_scaled[0] = scaled
                _emit(progress_callback, stage, scaled, message)

            video_path = downloader.download_video(
                yt_link,
                diretorio_saida=output_dir or str(OUTPUT_DIR),
                progress_callback=download_progress if progress_callback else None,
                cancel_event=cancel_event,
            )
            if not video_path:
                raise RuntimeError("Falha ao baixar o video.")

        check_cancelled(cancel_event)
        video_path = str(video_path)
        video_stem = Path(video_path).stem
        out_root = Path(output_dir) if output_dir else OUTPUT_DIR
        out_dir = out_root / video_stem

        key = cache.make_key(
            video_path,
            options.whisper_model,
            options.language,
            options.whisper_compute_type,
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
            with tempfile.TemporaryDirectory(prefix="autocut_pipeline_") as tmp_dir:
                check_cancelled(cancel_event)
                _emit(progress_callback, "audio", 15, "Extraindo audio...")
                audio_path = audio.extract_audio(
                    video_path, tmp_dir, cancel_event=cancel_event
                )

                check_cancelled(cancel_event)
                _emit(progress_callback, "transcricao", 20, "Transcrevendo audio...")
                segments = transcriber.transcribe(
                    audio_path,
                    word_timestamps=options.captions_enabled
                    and options.caption_transcribe_mode == "full",
                    model_name=options.whisper_model,
                    language=options.language,
                    compute_type=options.whisper_compute_type,
                    cancel_event=cancel_event,
                )

            cache.save_transcript(out_dir, key, segments)

        check_cancelled(cancel_event)
        if segments:
            focus = options.focus_instruction
            msg = (
                f"Analisando com IA (foco: {focus[:60]})..."
                if focus
                else "Analisando com IA..."
            )
            _emit(progress_callback, "analise", 50, msg)
            clips = ai_analyzer.analyze(
                segments,
                progress_callback=progress_callback,
                options=options,
                cancel_event=cancel_event,
            )
        else:
            clips = []

        check_cancelled(cancel_event)
        _emit(progress_callback, "normalizacao", 65, "Ajustando duracao dos clipes...")
        total_duration = video_ops.get_duration(video_path)
        clips = normalize_clips(
            clips,
            segments,
            total_duration,
            options.min_clip_duration,
            options.max_clip_duration,
            options.pause_gap,
        )

        check_cancelled(cancel_event)
        _emit(progress_callback, "corte", 70, "Cortando clipes...")
        clip_paths = video_ops.cut_all(
            video_path,
            clips,
            total_duration,
            out_dir,
            options=options,
            segments=segments,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

        check_cancelled(cancel_event)
        _emit(progress_callback, "relatorio", 95, "Gerando relatorio...")
        report_path = save_report(clips, out_dir, clip_paths)

        _emit(progress_callback, "concluido", 100, "Concluido")

        return {
            "clips": clips,
            "clip_paths": clip_paths,
            "report_path": report_path,
        }
    finally:
        _cleanup_temp_residuals()


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

    entrada = (
        {"yt_link": args.alvo}
        if args.alvo.startswith(("http://", "https://"))
        else {"video_path": args.alvo}
    )

    options = ProcessingOptions.from_env_or_config(
        captions_enabled=args.captions,
        focus_instruction=args.foco,
    )

    try:
        result = run(
            progress_callback=_cli_progress,
            force=args.force,
            options=options,
            **entrada,
        )
    except PipelineCancelledError as exc:
        print(f"Cancelado: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)

    print()
    print(f"Clipes gerados: {len(result['clip_paths'])}")
    for path in result["clip_paths"]:
        print(f"  {path}")
    print(f"Relatorio: {result['report_path']}")
