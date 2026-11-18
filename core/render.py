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
from core.exceptions import check_cancelled, run_cmd, run_interruptible_cmd
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
        result = run_cmd(cmd, timeout=30)
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
        out = run_cmd(cmd, timeout=30)
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


def _focus_base(src: str, out: str, w: int, h: int, plan, src_w: int, src_h: int):
    """Enquadramento base do "seguir quem fala" (compartilhado pelos modos).

    Devolve (pre, src, cw, ch, pos, expr_x, expr_y) ou None sem plano.
    """
    aspect = w / h
    shots = list(getattr(plan, "shots", None) or [])
    if not shots or not src_w or not src_h:
        return None
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
    return pre, src, cw, ch, pos, expr_x, expr_y


def _focus_slot(src: str, out: str, w: int, h: int, plan, src_w: int, src_h: int) -> str:
    """Recorte com a proporcao do slot que acompanha o rosto em foco.

    O formato nunca muda: trechos sem rosto ja chegam no plano como posicao
    mantida ou centro. Trocas de pessoa na mesma cena deslizam (GLIDE_S);
    trocas de cena reais sao saltos secos.
    """
    base = _focus_base(src, out, w, h, plan, src_w, src_h)
    if base is None:
        return (
            f"[{src}]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,format=yuv420p[{out}]"
        )
    pre, src, cw, ch, _pos, expr_x, expr_y = base
    return (
        f"{pre}[{src}]crop=w={cw}:h={ch}:x='{expr_x}':y='{expr_y}',"
        f"scale={w}:{h},setsar=1,format=yuv420p[{out}]"
    )


# Margem minima entre a cabeca e a borda do quadro no zoom maximo (fracao).
HEAD_MARGIN = 0.05
# A cabeca nunca passa destas fracoes da largura/altura do quadro.
HEAD_MAX_SHARE = 0.78
HEAD_MAX_HEIGHT = 0.80


def _head_box(face_slot):
    """Caixa da cabeca a partir do rosto do detector (cabelo/testa e queixo)."""
    cx, cy, fw, fh = face_slot
    return cx - fw * 0.6, cx + fw * 0.6, cy - fh * 0.85, cy + fh * 0.65


def safe_zoom(face_slot, target: float) -> float:
    """Maior zoom (<= target) em que a cabeca ainda cabe inteira no quadro.

    O quadro se reposiciona durante o zoom (ver `head_screen_target`), entao
    o limite e so o tamanho da cabeca ampliada, nao onde ela esta.
    """
    left, right, top, bottom = _head_box(face_slot)
    z = float(target)
    if right - left > 0:
        z = min(z, HEAD_MAX_SHARE / (right - left))
    if bottom - top > 0:
        z = min(z, HEAD_MAX_HEIGHT / (bottom - top))
    return max(1.0, z)


# Onde o centro do rosto fica na tela no zoom maximo: centralizado na
# horizontal e um pouco acima do meio (regra dos tercos para rosto).
FACE_SCREEN_X = 0.5
FACE_SCREEN_Y = 0.40


def head_screen_target(face_slot, zoom: float) -> tuple[float, float]:
    """Posicao de tela do centro do rosto no zoom maximo.

    O zoom leva o rosto para o centro (FACE_SCREEN_X/Y); se a cabeca ampliada
    nao couber ali com HEAD_MARGIN, empurra o minimo necessario.
    """
    cx, cy, _fw, _fh = face_slot
    left, right, top, bottom = _head_box(face_slot)
    m = HEAD_MARGIN

    def fit(want, lo_ext, hi_ext):
        lo, hi = m + lo_ext * zoom, 1 - m - hi_ext * zoom
        return (lo + hi) / 2 if lo > hi else max(lo, min(hi, want))

    return (fit(FACE_SCREEN_X, cx - left, right - cx),
            fit(FACE_SCREEN_Y, cy - top, bottom - cy))


def _glide_pos(t: float, shots, xs, cuts) -> tuple[float, float]:
    """Posicao do recorte base no instante t (mesma regra das expressoes)."""
    for idx, s in enumerate(shots):
        if t < s.end or idx == len(shots) - 1:
            if idx > 0:
                prev = shots[idx - 1]
                e = prev.end
                at_cut = any(abs(c - e) <= 0.3 for c in cuts)
                if not at_cut and t < e + GLIDE_S and xs[idx - 1] != xs[idx]:
                    import math

                    k = (1 - math.cos(math.pi * (t - e) / GLIDE_S)) / 2
                    (x0, y0), (x1, y1) = xs[idx - 1], xs[idx]
                    return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
            return xs[idx]
    return xs[-1]


def _head_delta(head, t: float) -> tuple[float, float]:
    if not head:
        return 0.0, 0.0
    if t <= head[0][0]:
        return head[0][1], head[0][2]
    for (t0, x0, y0), (t1, x1, y1) in zip(head, head[1:]):
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
    return head[-1][1], head[-1][2]


def dynamic_crop_rects(plan, w: int, h: int, src_w: int, src_h: int,
                       fps: float = 30.0):
    """Retangulo de recorte (x, y, cw, ch) na origem para cada quadro.

    Fora dos ciclos: o recorte do "seguir quem fala". Num ciclo, o recorte
    encolhe (zoom) e e posicionado para o rosto ir de onde estava ate o
    centro (head_screen_target); na trava soma o deslocamento da cabeca.
    Devolve (cw, ch, [(t, x, y, rw, rh)]) ou None sem ciclos.
    """
    import math

    shots = list(getattr(plan, "shots", None) or [])
    beats = list(getattr(plan, "beats", None) or [])
    if not shots or not beats or not src_w or not src_h:
        return None
    aspect = w / h
    # mesmo tamanho base do _focus_base (tela cheia vertical: altura toda)
    face = sorted(s.size for s in shots)[len(shots) // 2] * src_w
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

    prepared = []
    for beat in beats:
        shot = next((s for s in shots if s.start <= beat.start < s.end), None)
        if shot is None:
            continue
        sx, sy = pos(shot)
        fcx, fcy, fw, fh = beat.face
        fpx, fpy = fcx * src_w, fcy * src_h
        # rosto no quadro base no instante em que o ciclo comeca
        d0 = _head_delta(beat.head, beat.start)
        s0 = ((fpx + d0[0] * src_w - sx) / cw, (fpy + d0[1] * src_h - sy) / ch)
        # alvo calculado com o rosto ja centrado (recorte centrado nele)
        cx0 = max(0, min(src_w - cw, fpx - cw / 2))
        cy0 = max(0, min(src_h - ch, fpy - ch * 0.42))
        face_slot = ((fpx - cx0) / cw, (fpy - cy0) / ch, fw * src_w / cw, fh * src_h / ch)
        zoom = safe_zoom(face_slot, beat.zoom)
        if zoom < 1.05:
            continue
        target = head_screen_target(face_slot, zoom)
        prepared.append((beat, zoom, fpx, fpy, s0, target))
    if not prepared:
        return None

    end = max([shots[-1].end] + [b.end for b, *_ in prepared])
    rects = []
    for n in range(int(math.ceil(end * fps)) + 1):
        t = n / fps
        bx, by = _glide_pos(t, shots, xs, cuts)
        rect = (bx, by, cw, ch)
        for beat, zoom, fpx, fpy, s0, target in prepared:
            if not (beat.start <= t < beat.end):
                continue
            if t < beat.peak:
                prog = math.sin(math.pi / 2 * (t - beat.start) / (beat.peak - beat.start))
            else:
                prog = 1.0
            z = 1 + (zoom - 1) * prog
            rw = _even(cw / z)
            rh = max(2, int(round(rw / aspect / 2)) * 2)
            # rosto onde ele realmente esta agora (zoom e trava seguem a trilha)
            dx, dy = _head_delta(beat.head, t)
            fx_src = fpx + dx * src_w
            fy_src = fpy + dy * src_h
            scr_x = s0[0] + (target[0] - s0[0]) * prog
            scr_y = s0[1] + (target[1] - s0[1]) * prog
            x = max(0, min(src_w - rw, fx_src - scr_x * rw))
            y = max(0, min(src_h - rh, fy_src - scr_y * rh))
            rect = (x, y, rw, rh)
            break
        rects.append((t, int(round(rect[0])), int(round(rect[1])),
                      int(rect[2]), int(rect[3])))
    return cw, ch, rects


def _dynamic_focus_slot(src: str, out: str, w: int, h: int, plan,
                        src_w: int, src_h: int, work_dir: str | None = None) -> str:
    """"Seguir quem fala" com ciclos de zoom + trava na cabeca.

    Um unico recorte por quadro (tamanho e posicao enviados por `sendcmd`)
    seguido de `scale` para o tamanho fixo do slot. O `crop` do FFmpeg nao
    acompanha um quadro que muda de tamanho no meio do grafo, entao o zoom e
    feito encolhendo o recorte, nunca ampliando a imagem antes dele.
    """
    data = dynamic_crop_rects(plan, w, h, src_w, src_h) if work_dir else None
    if data is None:
        return _focus_slot(src, out, w, h, plan, src_w, src_h)
    cw, ch, rects = data
    name = f"crop@dz{out}"
    lines, last = [], None
    for t, x, y, rw, rh in rects:
        cur = (x, y, rw, rh)
        if cur == last:
            continue
        lines.append(f"{t:.4f} {name} w {rw}, {name} h {rh}, {name} x {x}, {name} y {y};")
        last = cur
    cmd_file = f"zoom_{out}.cmd"
    with open(os.path.join(work_dir, cmd_file), "w", encoding="utf-8") as fh:
        fh.write(chr(10).join(lines))
    pre, src = _restore_live(src, out, plan, src_w, src_h)
    t0, x0, y0, rw0, rh0 = rects[0]
    return (
        f"{pre}[{src}]sendcmd=f={cmd_file},"
        f"{name}=w={rw0}:h={rh0}:x={x0}:y={y0}:exact=1,"
        f"scale={w}:{h},setsar=1,format=yuv420p[{out}]"
    )


def build_layout_filter(layout, heights, *, width: int, options, plan=None,
                        src_size=(0, 0), band_lines=(), band_font_size=0,
                        font_file: str = "", image_input: int | None = None,
                        work_dir: str | None = None) -> str:
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
            if getattr(slot, "motion", "static") == "dynamic":
                parts.append(_dynamic_focus_slot(f"src{i}", out, width, h, plan,
                                                 src_w, src_h, work_dir=work_dir))
            else:
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
                font_file=font_name, image_input=image_input, work_dir=work,
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
