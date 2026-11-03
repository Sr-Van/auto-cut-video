"""Geracao de estilos ASS, vetores de desenho (\\p1) e animacoes pop/slide."""

from __future__ import annotations

from pathlib import Path

from core.captions.fonts import effective_size, load_font
from core.captions.layout import display_text, group_words, layout_blocks
from core.captions.models import CaptionBlock, CaptionWord
from core.options import ProcessingOptions

# Pop aplicado ao bloco/palavra ativa: sobe para 108% e volta a 100%.
_POP = "\\t(0,80,\\fscx108\\fscy108)\\t(80,190,\\fscx100\\fscy100)"


def ass_color(hex_color: str, opacity: float = 1.0) -> str:
    value = (hex_color or "#FFFFFF").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    red, green, blue = (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )
    opacity = max(0.0, min(1.0, float(opacity)))
    alpha = int(round((1.0 - opacity) * 255))
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"


def ass_time(seconds: float) -> str:
    total_cs = int(round(max(0.0, float(seconds)) * 100))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _num(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def rounded_rect(width: float, height: float, radius: float) -> str:
    """Retangulo arredondado com canto superior esquerdo na origem."""
    w, h = width, height
    radius = max(0.0, min(radius, w / 2.0, h / 2.0))
    return (
        f"m {_num(radius)} 0 "
        f"l {_num(w - radius)} 0 "
        f"b {_num(w)} 0 {_num(w)} 0 {_num(w)} {_num(radius)} "
        f"l {_num(w)} {_num(h - radius)} "
        f"b {_num(w)} {_num(h)} {_num(w)} {_num(h)} {_num(w - radius)} {_num(h)} "
        f"l {_num(radius)} {_num(h)} "
        f"b 0 {_num(h)} 0 {_num(h)} 0 {_num(h - radius)} "
        f"l 0 {_num(radius)} "
        f"b 0 0 0 0 {_num(radius)} 0"
    )


def _clean(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def word_span(block: CaptionBlock, index: int) -> tuple[float, float]:
    """Intervalo em que a palavra fica ativa (vai ate o inicio da proxima)."""
    word = block.words[index]
    start = word.start
    if index + 1 < len(block.words):
        end = block.words[index + 1].start
    else:
        end = min(block.end, word.end + 0.25)
    if end <= start:
        end = start + 0.08
    return start, end


def generate_swing_tags(
    ev_start: float,
    ev_end: float,
    block_start: float,
    max_angle: float = 2.5,
    half_period_ms: int = 260,
) -> str:
    """Gera sequencia continua de tags \\frz e \\t para balanco pendular sincronizado no bloco."""
    h = max(50, int(half_period_ms))
    q = h // 2
    a = float(max_angle)

    def angle_at(tau: float) -> float:
        if tau <= 0:
            return 0.0
        if tau <= q:
            return a * (tau / q)
        u = tau - q
        m = int(u // h)
        r = u % h
        if m % 2 == 0:
            return a - 2.0 * a * (r / h)
        return -a + 2.0 * a * (r / h)

    tau_s = max(0.0, (ev_start - block_start) * 1000.0)
    tau_e = max(tau_s + 10.0, (ev_end - block_start) * 1000.0)
    dur = tau_e - tau_s

    init_angle = angle_at(tau_s)
    parts = [f"\\frz{_num(init_angle)}"]

    k_start = max(0, int((tau_s - q) // h) + 1) if tau_s > q else (1 if tau_s <= 0 else 0)
    curr_t = q if tau_s < q else q + k_start * h
    prev_rel = 0
    while curr_t < tau_e:
        if curr_t > tau_s:
            rel = int(round(curr_t - tau_s))
            target_angle = angle_at(curr_t)
            parts.append(f"\\t({prev_rel},{rel},\\frz{_num(target_angle)})")
            prev_rel = rel
        curr_t += h

    final_rel = int(round(dur))
    if final_rel > prev_rel:
        final_angle = angle_at(tau_e)
        parts.append(f"\\t({prev_rel},{final_rel},\\frz{_num(final_angle)})")

    return "".join(parts)


def render_ass(
    blocks: list[CaptionBlock],
    options: ProcessingOptions,
    canvas_w: int,
    canvas_h: int,
    family: str,
    bold: bool,
    font,
) -> str:
    size = options.caption_font_size
    effective = effective_size(size)
    pad = options.caption_box_padding
    box_h = effective * 1.1 + pad * 0.8

    text_c = ass_color(options.caption_text_color)
    box_opacity = max(0.0, min(1.0, float(options.caption_highlight_opacity)))
    highlight_box_c = ass_color(options.caption_highlight_color, box_opacity)
    highlight_word_c = ass_color(options.caption_highlight_color, 1.0)
    outline_c = ass_color(options.caption_outline_color)
    glow_c = ass_color("#FFFFFF", 0.28)
    bold_flag = -1 if bold else 0

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {canvas_w}",
        f"PlayResY: {canvas_h}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Phrase,{family},{size},{text_c},{text_c},{outline_c},{outline_c},"
        f"{bold_flag},0,0,0,100,100,0,0,1,{options.caption_outline_width},1,7,0,0,0,1",
        f"Style: ActiveWord,{family},{size},{highlight_word_c},{highlight_word_c},{outline_c},{outline_c},"
        f"{bold_flag},0,0,0,100,100,0,0,1,{options.caption_outline_width},1,7,0,0,0,1",
        f"Style: Glow,{family},{size},{glow_c},{glow_c},{glow_c},{glow_c},"
        f"{bold_flag},0,0,0,100,100,0,0,1,4,0,7,0,0,0,1",
        f"Style: Box,{family},{size},{highlight_box_c},{highlight_box_c},{highlight_box_c},"
        f"{highlight_box_c},{bold_flag},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: list[str] = []
    has_box = box_opacity > 0.01
    anim = getattr(options, "caption_animation", "pop")

    if anim in ("rise", "rise_swing"):
        for block in blocks:
            if not block.words:
                continue

            for index, word in enumerate(block.words):
                w_start = word.start
                if index + 1 < len(block.words):
                    w_active_end = block.words[index + 1].start
                else:
                    w_active_end = block.end

                if w_active_end <= w_start:
                    w_active_end = w_start + 0.08
                if w_active_end > block.end:
                    w_active_end = block.end
                w_start = min(w_start, block.end - 0.05)

                clean_word = _clean(display_text(word.text, options))
                width = font.getlength(display_text(word.text, options))
                rise_ms = min(100, max(40, int(round((w_active_end - w_start) * 600))))

                if has_box:
                    left = word.x - pad
                    top = word.y + effective * 0.42 - box_h / 2.0
                    shape = rounded_rect(
                        width + pad * 2, box_h, options.caption_corner_radius
                    )
                    events.append(
                        f"Dialogue: 0,{ass_time(w_start)},{ass_time(w_active_end)},Box,,0,0,0,,"
                        f"{{\\an7"
                        f"\\move({_num(left)},{_num(top + 18)},{_num(left)},{_num(top)},0,{rise_ms})"
                        f"\\fad(60,0)\\p1}}"
                        f"{shape}{{\\p0}}"
                    )

                if getattr(options, "caption_glow", False):
                    events.append(
                        f"Dialogue: 0,{ass_time(w_start)},{ass_time(w_active_end)},Glow,,0,0,0,,"
                        f"{{\\an7"
                        f"\\move({_num(word.x)},{_num(word.y + 18)},{_num(word.x)},{_num(word.y)},0,{rise_ms})"
                        f"\\fad(60,0)\\1a&HFF&\\3c&H00FFFFFF&\\3a&HB0&\\bord4\\blur6}}"
                        f"{clean_word}"
                    )

                # Fase ativa: sobe e destaca com a cor de highlight
                events.append(
                    f"Dialogue: 2,{ass_time(w_start)},{ass_time(w_active_end)},ActiveWord,,0,0,0,,"
                    f"{{\\an7"
                    f"\\move({_num(word.x)},{_num(word.y + 18)},{_num(word.x)},{_num(word.y)},0,{rise_ms})"
                    f"\\fad(60,0)}}"
                    f"{clean_word}"
                )

                if getattr(options, "caption_glow", False) and w_active_end < block.end:
                    events.append(
                        f"Dialogue: 0,{ass_time(w_active_end)},{ass_time(block.end)},Glow,,0,0,0,,"
                        f"{{\\an7\\pos({_num(word.x)},{_num(word.y)})\\1a&HFF&\\3c&H00FFFFFF&\\3a&HB0&\\bord4\\blur6}}"
                        f"{clean_word}"
                    )

                # Fase pós-ativa: permanece na tela com a cor base até o fim do bloco
                if w_active_end < block.end:
                    events.append(
                        f"Dialogue: 1,{ass_time(w_active_end)},{ass_time(block.end)},Phrase,,0,0,0,,"
                        f"{{\\an7\\pos({_num(word.x)},{_num(word.y)})}}"
                        f"{clean_word}"
                    )
    else:
        for block in blocks:
            boxes = []
            for word in block.words:
                width = font.getlength(display_text(word.text, options))
                left = word.x - pad
                top = word.y + effective * 0.42 - box_h / 2.0
                cx = word.x + width / 2.0
                cy = top + box_h / 2.0
                boxes.append((left, top, cx, cy, width))

            if has_box:
                # Camada 0: bloco arredondado colorido, com pop e deslize continuo.
                for index, word in enumerate(block.words):
                    start, end = word_span(block, index)
                    left, top, cx, cy, width = boxes[index]
                    shape = rounded_rect(
                        width + pad * 2, box_h, options.caption_corner_radius
                    )
                    pos = f"\\pos({_num(left)},{_num(top)})"
                    move = ""
                    if index + 1 < len(block.words):
                        nleft, ntop, _, _, _ = boxes[index + 1]
                        if abs(ntop - top) < 1.0:
                            dur_ms = max(1, int(round((end - start) * 1000)))
                            slide_ms = min(130, max(40, int(dur_ms * 0.5)))
                            move = (
                                f"\\move({_num(left)},{_num(top)},{_num(nleft)},{_num(ntop)},"
                                f"{max(0, dur_ms - slide_ms)},{dur_ms})"
                            )
                            pos = ""
                    events.append(
                        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Box,,0,0,0,,"
                        f"{{\\an7{pos}{move}\\org({_num(cx)},{_num(cy)}){_POP}\\p1}}"
                        f"{shape}{{\\p0}}"
                    )

            if getattr(options, "caption_glow", False):
                for index, word in enumerate(block.words):
                    events.append(
                        f"Dialogue: 0,{ass_time(block.start)},{ass_time(block.end)},Glow,,0,0,0,,"
                        f"{{\\an7\\pos({_num(word.x)},{_num(word.y)})\\1a&HFF&\\3c&H00FFFFFF&\\3a&HB0&\\bord4\\blur6}}"
                        f"{_clean(display_text(word.text, options))}"
                    )

            # Camada 1: texto base de todas as palavras do bloco.
            for index, word in enumerate(block.words):
                events.append(
                    f"Dialogue: 1,{ass_time(block.start)},{ass_time(block.end)},Phrase,,"
                    f"0,0,0,,{{\\an7\\pos({_num(word.x)},{_num(word.y)})}}"
                    f"{_clean(display_text(word.text, options))}"
                )

            # Camada 2 (quando sem caixa de fundo): palavra ativa muda de cor para highlight_color!
            if not has_box and (
                options.caption_highlight_color.upper()
                != options.caption_text_color.upper()
            ):
                for index, word in enumerate(block.words):
                    start, end = word_span(block, index)
                    events.append(
                        f"Dialogue: 2,{ass_time(start)},{ass_time(end)},ActiveWord,,"
                        f"0,0,0,,{{\\an7\\pos({_num(word.x)},{_num(word.y)})}}"
                        f"{_clean(display_text(word.text, options))}"
                    )

    return "\n".join(header + events) + "\n"


def build_ass(
    words: list[CaptionWord],
    options: ProcessingOptions,
    canvas_w: int | None = None,
    canvas_h: int | None = None,
) -> str:
    canvas_w = canvas_w or options.width
    canvas_h = canvas_h or options.height
    font, family, bold, _fontsdir = load_font(
        options.caption_font, options.caption_bold, options.caption_font_size
    )
    blocks = group_words(words, options)
    layout_blocks(blocks, options, canvas_w, canvas_h, font)
    return render_ass(blocks, options, canvas_w, canvas_h, family, bold, font)


def write_ass(
    words, out_path, options: ProcessingOptions, canvas_w=None, canvas_h=None
) -> str:
    content = build_ass(words, options, canvas_w, canvas_h)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)

