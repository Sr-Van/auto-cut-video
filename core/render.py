"""Renderiza clipes verticais 9:16 com fundo desfocado (estilo Reels/Shorts).

Estrategia de desempenho:
- Um unico processo FFmpeg por clipe: seek + filtros + (legenda) + encode,
  sem arquivos intermediarios.
- O fundo e desfocado em resolucao reduzida (padrao 1/4) e so depois ampliado.
  O custo de blur cresce com a area, entao isso deixa o filtro barato.
- O encoder e detectado uma vez: tenta hardware (NVENC/QSV/AMF) e cai para
  libx264 se nao houver suporte (driver/GPU).
"""

import os
import shutil
import subprocess
from functools import lru_cache

from core.options import ProcessingOptions

# Ordem de preferencia dos encoders de hardware.
_HW_ENCODERS = ("h264_nvenc", "h264_qsv", "h264_amf")


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg nao encontrado. Instale o FFmpeg e adicione ao PATH.")
    return ffmpeg


def _even(value: float) -> int:
    """Arredonda para o inteiro par mais proximo (exigencia do yuv420p)."""
    return max(2, int(round(value / 2)) * 2)


def _probe_encoder(ffmpeg: str, encoder: str) -> bool:
    """Testa se o encoder abre de fato (evita 'existe na lista mas nao roda')."""
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=256x256:d=0.1",
        "-frames:v",
        "1",
        "-c:v",
        encoder,
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


@lru_cache(maxsize=1)
def _detect_auto_encoder() -> str:
    ffmpeg = _require_ffmpeg()
    for encoder in _HW_ENCODERS:
        if _probe_encoder(ffmpeg, encoder):
            return encoder
    return "libx264"


def detect_encoder(override: str = "") -> str:
    """Escolhe o encoder. `override` vazio = deteccao automatica."""
    if override:
        return override
    return _detect_auto_encoder()


def encoder_args(encoder: str, crf: int, preset: str) -> list[str]:
    """Flags de qualidade por encoder (o CRF/CQ e a qualidade alvo)."""
    if encoder == "h264_nvenc":
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p4", "-tune", "hq",
            "-rc", "vbr", "-cq", str(crf), "-b:v", "0",
        ]
    if encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", preset, "-global_quality", str(crf)]
    if encoder == "h264_amf":
        return [
            "-c:v", "h264_amf",
            "-quality", "balanced", "-rc", "cqp",
            "-qp_i", str(crf), "-qp_p", str(crf),
        ]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]


def build_vertical_filter(
    width: int,
    height: int,
    zoom: float,
    blur_sigma: float,
    blur_divisor: int = 4,
    bg_brightness: float = 0.0,
) -> str:
    """Fundo desfocado (cover) + video central (contain*zoom). Saida: [v]."""
    bw = _even(width / max(1, blur_divisor))
    bh = _even(height / max(1, blur_divisor))

    bg = (
        f"scale={bw}:{bh}:force_original_aspect_ratio=increase,"
        f"crop={bw}:{bh},gblur=sigma={blur_sigma}"
    )
    if bg_brightness:
        bg += f",eq=brightness={bg_brightness}"
    bg += f",scale={width}:{height}"

    fg = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw*{zoom}/2)*2:trunc(ih*{zoom}/2)*2"
    )

    return (
        f"[0:v]split=2[s1][s2];"
        f"[s1]{bg}[bg];"
        f"[s2]{fg}[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2:format=auto,"
        f"setsar=1,format=yuv420p[v]"
    )


def render_clip(
    video_path: str,
    start_s: float,
    end_s: float,
    out_path: str,
    *,
    options: ProcessingOptions | None = None,
    ass_path: str | None = None,
) -> str:
    """Corta [start_s, end_s] e entrega 9:16, opcionalmente queimando legenda."""
    options = options or ProcessingOptions()
    ffmpeg = _require_ffmpeg()
    # Absolutos: o cwd pode mudar para a pasta do .ass (filtro subtitles).
    video_path = os.path.abspath(str(video_path))
    out_path = os.path.abspath(str(out_path))
    duration = max(0.0, end_s - start_s)
    encoder = detect_encoder(options.encoder)

    filters = build_vertical_filter(
        options.width,
        options.height,
        options.zoom,
        options.blur_sigma,
        options.blur_divisor,
        options.bg_brightness,
    )

    vlabel = "[v]"
    cwd = None
    if ass_path:
        base = os.path.basename(ass_path)
        filters += f";[v]subtitles=filename='{base}':fontsdir='.'[vout]"
        vlabel = "[vout]"
        cwd = os.path.dirname(os.path.abspath(ass_path))

    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss", f"{start_s:.3f}",
        "-i", str(video_path),
        "-t", f"{duration:.3f}",
        "-filter_complex", filters,
        "-map", vlabel,
        "-map", "0:a?",
        *encoder_args(encoder, options.crf, options.preset),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao renderizar clip vertical: {result.stderr}")
    return str(out_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Renderiza um trecho em 9:16.")
    parser.add_argument("video")
    parser.add_argument("out")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--end", type=float, default=None)
    parser.add_argument("--zoom", type=float, default=None)
    parser.add_argument("--encoder", default=None, help="padrao: automatico")
    args = parser.parse_args()

    if args.end is None:
        from core.video_ops import get_duration

        args.end = get_duration(args.video)

    options = ProcessingOptions()
    if args.zoom is not None:
        options.zoom = args.zoom
    if args.encoder is not None:
        options.encoder = args.encoder

    print(f"Encoder: {detect_encoder(options.encoder)}")
    print(f"Filtro: {build_vertical_filter(options.width, options.height, options.zoom, options.blur_sigma, options.blur_divisor, options.bg_brightness)}")
    path = render_clip(args.video, args.start, args.end, args.out, options=options)
    print(f"Gerado: {path}")
