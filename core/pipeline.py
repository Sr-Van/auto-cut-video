from pathlib import Path

from core import ai_analyzer, audio, transcriber, video_ops
from core.config import OUTPUT_DIR
from utils.report import save_report


def _emit(progress_callback, stage, percent, message):
    if progress_callback:
        progress_callback(stage, percent, message)


def run(video_path, progress_callback=None):
    video_path = str(video_path)
    video_stem = Path(video_path).stem
    out_dir = OUTPUT_DIR / video_stem

    _emit(progress_callback, "audio", 5, "Extraindo audio...")
    audio_path = audio.extract_audio(video_path)

    _emit(progress_callback, "transcricao", 20, "Transcrevendo audio...")
    segments = transcriber.transcribe(audio_path)

    if segments:
        _emit(progress_callback, "analise", 50, "Analisando com Gemini...")
        clips = ai_analyzer.analyze(segments)
    else:
        clips = []

    _emit(progress_callback, "corte", 70, "Cortando clipes...")
    total_duration = video_ops.get_duration(video_path)
    clip_paths = video_ops.cut_all(video_path, clips, total_duration, out_dir)

    _emit(progress_callback, "relatorio", 95, "Gerando relatorio...")
    report_path = save_report(clips, out_dir, clip_paths)

    _emit(progress_callback, "concluido", 100, "Concluido")

    return {"clips": clips, "clip_paths": clip_paths, "report_path": report_path}


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Uso: python -m core.pipeline <video>")
        raise SystemExit(1)

    def cb(stage, percent, message):
        print(f"[{percent:3d}%] {stage}: {message}")

    result = run(sys.argv[1], progress_callback=cb)
    print("Clipes:", len(result["clip_paths"]))
    print("Relatorio:", result["report_path"])
