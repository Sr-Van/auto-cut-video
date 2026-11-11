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
import tempfile
from functools import lru_cache
from threading import Event

from core.captions.fonts import find_font_path
from core.exceptions import check_cancelled, run_interruptible_cmd
from core.options import ProcessingOptions

# Ordem de preferencia dos encoders de hardware.
_HW_ENCODERS = ("h264_nvenc", "h264_qsv", "h264_amf")


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "FFmpeg nao encontrado. Instale o FFmpeg e adicione ao PATH."
        )
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


def _probe_has_audio(video_path: str) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return True
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return True
    return bool(out.stdout.strip())


def wrap_band_text(text: str, width: int, height: int, max_lines: int = 3,
                   char_w: float = 0.56) -> tuple[list[str], int]:
    """Quebra o texto e escolhe o maior tamanho de fonte que cabe na faixa."""
    words = " ".join(str(text or "").split()).split(" ")
    words = [w for w in words if w]
    if not words:
        return [], 0
    size = int(height * 0.42)
    while size >= 18:
        max_chars = max(6, int(width * 0.9 / (size * char_w)))
        lines: list[str] = []
        cur = ""
        for word in words:
            candidate = f"{cur} {word}".strip()
            if len(candidate) <= max_chars or not cur:
                cur = candidate
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        fits_h = len(lines) * size * 1.18 <= height * 0.86
        fits_w = all(len(line) <= max_chars for line in lines)
        if len(lines) <= max_lines and fits_h and fits_w:
            return lines, size
        size -= 2
    # texto longo demais: corta com reticencias na menor fonte
    size = 18
    max_chars = max(6, int(width * 0.9 / (size * char_w)))
    flat = " ".join(words)
    lines = [flat[i:i + max_chars] for i in range(0, len(flat), max_chars)][:max_lines]
    lines[-1] = lines[-1][: max(1, max_chars - 1)].rstrip() + "…"
    return lines, size


def _hex(color: str, fallback: str) -> str:
    c = (color or fallback).strip().lstrip("#")
    return "0x" + (c if len(c) == 6 else fallback.lstrip("#"))


def _video_slot(src: str, out: str, w: int, h: int, zoom: float, blur_sigma: float,
                blur_divisor: int, bg_brightness: float, pre: str = "",
                fit: str = "contain") -> str:
    """Contain * zoom sobre fundo desfocado, ou cover (zoom ate preencher o slot)."""
    if fit == "cover":
        pre = f"{pre}," if pre else ""
        return (
            f"[{src}]{pre}scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,format=yuv420p[{out}]"
        )
    bw = _even(w / max(1, blur_divisor))
    bh = _even(h / max(1, blur_divisor))
    pre = f"{pre}," if pre else ""
    bg = (
        f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
        f"gblur=sigma={blur_sigma}"
    )
    if bg_brightness:
        bg += f",eq=brightness={bg_brightness}"
    bg += f",scale={w}:{h}"
    fg = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw*{zoom}/2)*2:trunc(ih*{zoom}/2)*2"
    )
    return (
        f"[{src}]{pre}split=2[{out}a][{out}b];"
        f"[{out}a]{bg}[{out}bg];[{out}b]{fg}[{out}fg];"
        f"[{out}bg][{out}fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[{out}]"
    )


def _crop_box(box, src_w: int, src_h: int) -> str:
    x, y, bw, bh = box
    cw = _even(max(16, bw * src_w))
    ch = _even(max(16, bh * src_h))
    cx = int(max(0, min(src_w - cw, x * src_w)))
    cy = int(max(0, min(src_h - ch, y * src_h)))
    return f"crop={cw}:{ch}:{cx}:{cy}"


GLIDE_S = 0.4  # troca de pessoa dentro da mesma cena: desliza em vez de pular


def _restore_live(src: str, out: str, plan, src_w: int, src_h: int) -> tuple[str, str]:
    """Desfaz a moldura de patrocinio: amplia a area viva para a tela cheia.

    Devolve (filtros, rotulo de saida). Sem moldura, nao faz nada.
    """
    from core.framing import restore_geometry

    lives = list(getattr(plan, "live_boxes", None) or [])
    if not lives:
        return "", src
    groups: dict[tuple, list] = {}
    for a, b, box in lives:
        g = restore_geometry(box, src_w, src_h)
        groups.setdefault(tuple(sorted(g.items())), []).append((a, b))
    parts = []
    cur = src
    for n, (key, spans) in enumerate(groups.items()):
        g = dict(key)
        enable = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in spans)
        parts.append(
            f"[{cur}]split=2[{out}l{n}a][{out}l{n}b];"
            f"[{out}l{n}b]crop={g['cw']}:{g['ch']}:{g['cx']}:{g['cy']},"
            f"scale={g['sw']}:{g['sh']},crop={src_w}:{src_h}:{g['ox']}:{g['oy']}[{out}l{n}z];"
            f"[{out}l{n}a][{out}l{n}z]overlay=0:0:enable='{enable}'[{out}l{n}]"
        )
        cur = f"{out}l{n}"
    return ";".join(parts) + ";", cur


def _focus_slot(src: str, out: str, w: int, h: int, plan, src_w: int, src_h: int) -> str:
    """Recorte com a proporcao do slot que acompanha o rosto em foco.

    O formato nunca muda: trechos sem rosto ja chegam no plano como posicao
    mantida ou centro. Trocas de pessoa na mesma cena deslizam (GLIDE_S);
    trocas de cena reais sao saltos secos.
    """
    aspect = w / h
    shots = list(getattr(plan, "shots", None) or [])
    if not shots or not src_w or not src_h:
        return (
            f"[{src}]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,format=yuv420p[{out}]"
        )
    pre, src = _restore_live(src, out, plan, src_w, src_h)
    face = sorted(s.size for s in shots)[len(shots) // 2] * src_w
    # rosto ocupa ~1/3 da largura em slots largos; em tela cheia vertical usa a altura toda
    cw = max(face * 3.0, src_h * aspect * 0.5) if aspect > 1 else src_h * aspect
    ch = cw / aspect
    if ch > src_h:
        ch = src_h
        cw = ch * aspect
    if cw > src_w:
        cw = src_w
        ch = cw / aspect
    cw, ch = _even(cw), _even(ch)

    def pos(s):
        x = int(max(0, min(src_w - cw, s.cx * src_w - cw / 2)))
        y = int(max(0, min(src_h - ch, s.cy * src_h - ch * 0.42)))
        return x, y

    cuts = list(getattr(plan, "scene_cuts", None) or [])
    xs = [pos(s) for s in shots]
    expr_x, expr_y = str(xs[-1][0]), str(xs[-1][1])
    for idx in range(len(shots) - 2, -1, -1):
        s = shots[idx]
        (x, y), (nx, ny) = xs[idx], xs[idx + 1]
        e = s.end
        at_cut = any(abs(c - e) <= 0.3 for c in cuts)
        if at_cut or (x, y) == (nx, ny):
            expr_x = f"if(lt(t,{e:.2f}),{x},{expr_x})"
            expr_y = f"if(lt(t,{e:.2f}),{y},{expr_y})"
        else:
            # desliza de (x,y) ate (nx,ny) em GLIDE_S, com suavizacao
            k = f"(1-cos(PI*(t-{e:.2f})/{GLIDE_S}))/2"
            expr_x = (f"if(lt(t,{e:.2f}),{x},if(lt(t,{e + GLIDE_S:.2f}),"
                      f"{x}+({nx - x})*{k},{expr_x}))")
            expr_y = (f"if(lt(t,{e:.2f}),{y},if(lt(t,{e + GLIDE_S:.2f}),"
                      f"{y}+({ny - y})*{k},{expr_y}))")
    return (
        f"{pre}[{src}]crop=w={cw}:h={ch}:x='{expr_x}':y='{expr_y}',"
        f"scale={w}:{h},setsar=1,format=yuv420p[{out}]"
    )


def build_layout_filter(layout, heights, *, width: int, options, plan=None,
                        src_size=(0, 0), band_lines=(), band_font_size=0,
                        font_file: str = "", image_input: int | None = None) -> str:
    """Monta o filter_complex de um layout por slots. Saida: [v]."""
    src_w, src_h = src_size
    video_kinds = {"video", "focus", "cam", "content"}
    users = [i for i, s in enumerate(layout.slots) if s.kind in video_kinds]
    parts: list[str] = []
    if len(users) == 1:
        parts.append(f"[0:v]null[src{users[0]}]")
    elif users:
        parts.append(
            f"[0:v]split={len(users)}" + "".join(f"[src{i}]" for i in users)
        )

    labels = []
    for i, (slot, h) in enumerate(zip(layout.slots, heights)):
        out = f"s{i}"
        labels.append(f"[{out}]")
        if slot.kind == "video":
            parts.append(_video_slot(f"src{i}", out, width, h, slot.zoom,
                                     options.blur_sigma, options.blur_divisor,
                                     options.bg_brightness, fit=getattr(slot, "fit", "contain")))
        elif slot.kind == "focus":
            parts.append(_focus_slot(f"src{i}", out, width, h, plan, src_w, src_h))
        elif slot.kind == "cam":
            box = getattr(plan, "cam_box", None)
            if box and src_w and src_h:
                pre = _crop_box(box, src_w, src_h)
                parts.append(
                    f"[src{i}]{pre},scale={width}:{h}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{h},setsar=1,format=yuv420p[{out}]"
                )
            else:
                parts.append(_focus_slot(f"src{i}", out, width, h, plan, src_w, src_h))
        elif slot.kind == "content":
            box = getattr(plan, "content_box", None)
            pre = _crop_box(box, src_w, src_h) if box and src_w and src_h else ""
            parts.append(_video_slot(f"src{i}", out, width, h, 1.0,
                                     options.blur_sigma, options.blur_divisor,
                                     options.bg_brightness, pre=pre))
        elif slot.kind == "image" and image_input is not None:
            parts.append(
                f"[{image_input}:v]scale={width}:{h}:force_original_aspect_ratio=increase,"
                f"crop={width}:{h},fps=30,setsar=1,format=yuv420p[{out}]"
            )
        else:  # text (ou imagem ausente): faixa solida com texto
            color = _hex(options.layout_band_color, "#D90A0A")
            chain = f"color=c={color}:s={width}x{h}:r=30"
            if getattr(options, "layout_band_border", False):
                bc = _hex(options.layout_text_color, "#FFFFFF")
                t = max(4, _even(h * 0.03))
                chain += (
                    f",drawbox=x=0:y=0:w=iw:h={t}:color={bc}:t=fill"
                    f",drawbox=x=0:y=ih-{t}:w=iw:h={t}:color={bc}:t=fill"
                )
            if band_lines and band_font_size and font_file:
                fc = _hex(options.layout_text_color, "#FFFFFF")
                line_h = band_font_size * 1.18
                top = (h - line_h * len(band_lines)) / 2
                for n in range(len(band_lines)):
                    y = int(top + n * line_h + (line_h - band_font_size) / 2)
                    chain += (
                        # expansion=none: '%' do gancho e texto, nao codigo do drawtext
                        f",drawtext=fontfile='{font_file}':textfile='band_{i}_{n}.txt'"
                        f":expansion=none"
                        f":fontsize={band_font_size}:fontcolor={fc}"
                        f":x=(w-text_w)/2:y={y}"
                    )
            parts.append(f"{chain},setsar=1,format=yuv420p[{out}]")

    if len(labels) == 1:
        parts.append(f"{labels[0]}null[v]")
    else:
        parts.append(
            "".join(labels) + f"vstack=inputs={len(labels)}:shortest=1,format=yuv420p[v]"
        )
    return ";".join(parts)


def build_music_filter(music_input: int, volume: float, has_voice: bool) -> str:
    """Musica em loop que abaixa sozinha quando ha voz (sidechain). Saida: [a]."""
    music = f"[{music_input}:a]aresample=48000,volume={volume:.3f}"
    if not has_voice:
        return f"{music}[a]"
    return (
        f"[0:a]aresample=48000,asplit=2[voice][key];{music}[mus];"
        "[mus][key]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
        "[voice][duck]amix=inputs=2:duration=first:normalize=0[a]"
    )


def render_clip(
    video_path: str,
    start_s: float,
    end_s: float,
    out_path: str,
    *,
    options: ProcessingOptions | None = None,
    ass_path: str | None = None,
    cancel_event: Event | None = None,
    plan=None,
    band_text: str = "",
) -> str:
    """Corta [start_s, end_s] no formato escolhido, com legenda e musica opcionais."""
    check_cancelled(cancel_event)
    options = (options or ProcessingOptions.from_env_or_config()).normalize()
    ffmpeg = _require_ffmpeg()
    from core.layouts import get_layout, slot_heights

    # Absolutos: o cwd muda para a pasta de trabalho (fontes, textos, .ass).
    video_path = os.path.abspath(str(video_path))
    out_path = os.path.abspath(str(out_path))
    duration = max(0.0, end_s - start_s)
    encoder = detect_encoder(options.encoder)
    layout = get_layout(options.layout_id)

    with tempfile.TemporaryDirectory(prefix="autocut_render_") as work:
        inputs = ["-ss", f"{start_s:.3f}", "-i", video_path]
        next_input = 1

        if layout.legacy:
            filters = build_vertical_filter(
                options.width, options.height, options.zoom, options.blur_sigma,
                options.blur_divisor, options.bg_brightness,
            )
        else:
            image_input = None
            if layout.has_image and options.aux_image_path and os.path.isfile(options.aux_image_path):
                inputs += ["-loop", "1", "-i", os.path.abspath(options.aux_image_path)]
                image_input = next_input
                next_input += 1
            heights = slot_heights(layout, options.height)
            lines, size, font_name = [], 0, ""
            if layout.has_text and band_text:
                if getattr(options, "layout_text_uppercase", False):
                    band_text = band_text.upper()
                text_h = next(h for s, h in zip(layout.slots, heights) if s.kind == "text")
                font = (
                    find_font_path(getattr(options, "layout_text_font", ""), True)
                    or find_font_path(getattr(options, "layout_text_font", ""), False)
                    or find_font_path(options.caption_font, True)
                    or find_font_path("Arial", True)
                )
                # fontes condensadas (Impact, Bebas, Anton, Oswald) cabem mais por linha
                narrow = any(k in os.path.basename(font or "").lower()
                             for k in ("impact", "bebas", "anton", "oswald", "condensed"))
                lines, size = wrap_band_text(band_text, options.width, text_h,
                                             char_w=0.44 if narrow else 0.56)
                if font:
                    font_name = "band_font" + os.path.splitext(font)[1]
                    shutil.copy2(font, os.path.join(work, font_name))
                for i, slot in enumerate(layout.slots):
                    if slot.kind == "text":
                        for n, line in enumerate(lines):
                            with open(os.path.join(work, f"band_{i}_{n}.txt"), "w",
                                      encoding="utf-8") as fh:
                                fh.write(line)
            src_size = (
                (plan.src_width, plan.src_height)
                if plan is not None and plan.src_width
                else _probe_size(video_path)
            )
            filters = build_layout_filter(
                layout, heights, width=options.width, options=options, plan=plan,
                src_size=src_size, band_lines=lines, band_font_size=size,
                font_file=font_name, image_input=image_input,
            )

        vlabel = "[v]"
        if ass_path:
            for item in os.listdir(os.path.dirname(os.path.abspath(ass_path))):
                src = os.path.join(os.path.dirname(os.path.abspath(ass_path)), item)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(work, item))
            base = os.path.basename(ass_path)
            filters += f";[v]subtitles=filename='{base}':fontsdir='.'[vout]"
            vlabel = "[vout]"

        audio_map = ["-map", "0:a?"]
        music = options.aux_audio_path
        if music and os.path.isfile(music) and options.aux_audio_volume > 0:
            inputs += ["-stream_loop", "-1", "-i", os.path.abspath(music)]
            filters += ";" + build_music_filter(
                next_input, options.aux_audio_volume, _probe_has_audio(video_path)
            )
            audio_map = ["-map", "[a]"]
            next_input += 1

        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            *inputs,
            "-t", f"{duration:.3f}",
            "-filter_complex", filters,
            "-map", vlabel,
            *audio_map,
            *encoder_args(encoder, options.crf, options.preset),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_path),
        ]

        result = run_interruptible_cmd(
            cmd, cancel_event=cancel_event, cwd=work, cleanup_path=out_path,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao renderizar clip vertical: {result.stderr}")
    return str(out_path)


def _probe_size(video_path: str) -> tuple[int, int]:
    from core.framing import probe_size

    return probe_size(video_path)


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

    options = ProcessingOptions.from_env_or_config()
    if args.zoom is not None:
        options.zoom = args.zoom
    if args.encoder is not None:
        options.encoder = args.encoder

    print(f"Encoder: {detect_encoder(options.encoder)}")
    print(f"Filtro: {build_vertical_filter(options.width, options.height, options.zoom, options.blur_sigma, options.blur_divisor, options.bg_brightness)}")
    path = render_clip(args.video, args.start, args.end, args.out, options=options)
    print(f"Gerado: {path}")
