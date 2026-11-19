"""Geracao de estilos ASS, vetores de desenho (\\p1) e animacoes pop/slide."""

from __future__ import annotations

from pathlib import Path

from core.captions.fonts import font_effective_size, load_font
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


def _word_width(word: CaptionWord, options: ProcessingOptions, font) -> float:
    if word.width > 0:
        return word.width
    return font.getlength(display_text(word.text, options)) * (word.scale or 1.0)


def _bgr(hex_color: str) -> str:
    """Cor ASS sem canal alfa (&HBBGGRR&) para tags inline."""
    return "&H" + ass_color(hex_color)[4:] + "&"


def _glow_tags(options: ProcessingOptions, color: str | None = None) -> str:
    strength = int(getattr(options, "caption_glow_strength", 6) or 0)
    blur = max(1, strength)
    bord = max(2, int(round(strength * 0.66)))
    glow = _bgr(color or getattr(options, "caption_glow_color", "#FFFFFF"))
    return f"\\1a&HFF&\\3c{glow}\\3a&HB0&\\bord{bord}\\blur{blur}"


def _emph_size(word: CaptionWord, size: int) -> str:
    if abs((word.scale or 1.0) - 1.0) < 0.01:
        return ""
    return f"\\fs{int(round(size * word.scale))}"


def _emph_tags(word: CaptionWord, options: ProcessingOptions, size: int) -> str:
    """Override de tamanho (palavras ampliadas) e cor (so a palavra-chave)."""
    if not word.emphasis:
        return _emph_size(word, size)
    color = _bgr(getattr(options, "caption_emphasis_color", "#22C55E"))
    return f"{_emph_size(word, size)}\\1c{color}"


# Entrada com borrao + zoom horizontal (aproxima o motion blur do CapCut).
_BLUR_IN = "\\blur12\\fscx135\\alpha&H70&\\t(0,110,\\blur0\\fscx100\\alpha&H00&)"
DROP_MS = 220


def _drop_tags(word: CaptionWord, effective: float) -> str:
    """Cai de cima ate a posicao ganhando opacidade."""
    dy = effective * 0.6 * (word.scale or 1.0)
    return (
        f"\\an7\\move({_num(word.x)},{_num(word.y - dy)},{_num(word.x)},{_num(word.y)},0,{DROP_MS})"
        f"\\alpha&HFF&\\t(0,{DROP_MS},\\alpha&H00&)"
    )


# Palavra "acendendo" no karaoke cumulativo.
_LIGHT_UP = "\\alpha&HA0&\\t(0,90,\\alpha&H00&)"


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
    effective = font_effective_size(font, size)
    pad = options.caption_box_padding
    box_h = effective * 1.1 + pad * 0.8

    text_c = ass_color(options.caption_text_color)
    box_opacity = max(0.0, min(1.0, float(options.caption_highlight_opacity)))
    highlight_box_c = ass_color(options.caption_highlight_color, box_opacity)
    highlight_word_c = ass_color(options.caption_highlight_color, 1.0)
    outline_c = ass_color(options.caption_outline_color)
    glow_c = ass_color("#FFFFFF", 0.28)
    upcoming_c = ass_color(
        getattr(options, "caption_upcoming_color", options.caption_text_color),
        getattr(options, "caption_upcoming_opacity", 1.0),
    )
    bold_flag = -1 if bold else 0
    italic_flag = -1 if getattr(options, "caption_italic", False) else 0
    outline_w = options.caption_outline_width
    shadow = int(getattr(options, "caption_shadow", 1))
    # Sem contorno, a sombra vira um "drop" translucido e suave.
    # Sombras longas (>=3px) tambem ficam translucidas, mesmo com contorno.
    shadow_c = (
        outline_c
        if outline_w > 0 and shadow < 3
        else ass_color("#000000", 0.55)
    )

    def style(name, primary, outline, back, bord, shad) -> str:
        return (
            f"Style: {name},{family},{size},{primary},{primary},{outline},{back},"
            f"{bold_flag},{italic_flag},0,0,100,100,0,0,1,{bord},{shad},7,0,0,0,1"
        )

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
        style("Phrase", text_c, outline_c, shadow_c, outline_w, shadow),
        style("ActiveWord", highlight_word_c, outline_c, shadow_c, outline_w, shadow),
        style("Glow", glow_c, glow_c, glow_c, 4, 0),
        style("Box", highlight_box_c, highlight_box_c, highlight_box_c, 0, 0),
        style("Upcoming", upcoming_c, outline_c, shadow_c, outline_w, shadow),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: list[str] = []
    has_box = box_opacity > 0.01
    anim = getattr(options, "caption_animation", "pop")
    glow_on = bool(getattr(options, "caption_glow", False))
    emphasis_c = getattr(options, "caption_emphasis_color", "#22C55E")

    def glow_for(word: CaptionWord) -> str:
        return _emph_size(word, size) + _glow_tags(options)

    stairs = getattr(options, "caption_layout", "line") == "stairs"
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
                width = _word_width(word, options, font)
                emph = _emph_tags(word, options, size)
                if stairs:
                    # sobe de mais longe ganhando opacidade ate assentar
                    rise_ms = min(260, max(60, int(round((w_active_end - w_start) * 1000))))
                    dy = effective * 0.55
                    fade = f"\\alpha&HFF&\\t(0,{rise_ms},\\alpha&H00&)"
                else:
                    rise_ms = min(100, max(40, int(round((w_active_end - w_start) * 600))))
                    dy = 18
                    fade = "\\fad(60,0)"

                if has_box:
                    left = word.x - pad
                    top = word.y + effective * 0.42 - box_h / 2.0
                    shape = rounded_rect(
                        width + pad * 2, box_h, options.caption_corner_radius
                    )
                    events.append(
                        f"Dialogue: 0,{ass_time(w_start)},{ass_time(w_active_end)},Box,,0,0,0,,"
                        f"{{\\an7"
                        f"\\move({_num(left)},{_num(top + dy)},{_num(left)},{_num(top)},0,{rise_ms})"
                        f"{fade}\\p1}}"
                        f"{shape}{{\\p0}}"
                    )

                if glow_on:
                    events.append(
                        f"Dialogue: 0,{ass_time(w_start)},{ass_time(w_active_end)},Glow,,0,0,0,,"
                        f"{{\\an7"
                        f"\\move({_num(word.x)},{_num(word.y + dy)},{_num(word.x)},{_num(word.y)},0,{rise_ms})"
                        f"\\fad(60,0){glow_for(word)}}}"
                        f"{clean_word}"
                    )

                # Fase ativa: sobe e destaca com a cor de highlight
                events.append(
                    f"Dialogue: 2,{ass_time(w_start)},{ass_time(w_active_end)},ActiveWord,,0,0,0,,"
                    f"{{\\an7"
                    f"\\move({_num(word.x)},{_num(word.y + dy)},{_num(word.x)},{_num(word.y)},0,{rise_ms})"
                    f"{fade}{emph}}}"
                    f"{clean_word}"
                )

                if glow_on and w_active_end < block.end:
                    events.append(
                        f"Dialogue: 0,{ass_time(w_active_end)},{ass_time(block.end)},Glow,,0,0,0,,"
                        f"{{\\an7\\pos({_num(word.x)},{_num(word.y)}){glow_for(word)}}}"
                        f"{clean_word}"
                    )

                # Fase pós-ativa: permanece na tela com a cor base até o fim do bloco
                if w_active_end < block.end:
                    events.append(
                        f"Dialogue: 1,{ass_time(w_active_end)},{ass_time(block.end)},Phrase,,0,0,0,,"
                        f"{{\\an7\\pos({_num(word.x)},{_num(word.y)}){emph}}}"
                        f"{clean_word}"
                    )
    else:
        cumulative = (
            getattr(options, "caption_karaoke_mode", "active") == "cumulative"
        )
        entrance = _BLUR_IN if anim == "blur_in" else ""
        drop = anim == "drop"
        upcoming_visible = (
            float(getattr(options, "caption_upcoming_opacity", 1.0)) > 0.01
        )
        for block in blocks:
            boxes = []
            for word in block.words:
                width = _word_width(word, options, font)
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

            if glow_on:
                fade = "\\fad(110,0)" if entrance else ""
                for index, word in enumerate(block.words):
                    g_start = (
                        max(block.start, min(word.start, block.end - 0.05))
                        if cumulative or drop
                        else block.start
                    )
                    g_pos = (
                        _drop_tags(word, effective)
                        if drop
                        else f"\\an7\\pos({_num(word.x)},{_num(word.y)})"
                    )
                    events.append(
                        f"Dialogue: 0,{ass_time(g_start)},{ass_time(block.end)},Glow,,0,0,0,,"
                        f"{{{g_pos}{fade}{glow_for(word)}}}"
                        f"{_clean(display_text(word.text, options))}"
                    )

            # Camada 1: texto base de todas as palavras do bloco.
            for index, word in enumerate(block.words):
                text = _clean(display_text(word.text, options))
                emph = _emph_tags(word, options, size)
                org = ""
                if entrance:
                    _, _, cx, cy, _ = boxes[index]
                    org = f"\\org({_num(cx)},{_num(cy)})"
                pos = f"\\an7\\pos({_num(word.x)},{_num(word.y)})"
                if cumulative:
                    # Karaoke: antes de ser falada fica apagada (ou escondida,
                    # com opacidade 0); ao ser falada acende/cai e fica.
                    lit_start = max(block.start, min(word.start, block.end - 0.05))
                    if lit_start > block.start and upcoming_visible:
                        events.append(
                            f"Dialogue: 1,{ass_time(block.start)},{ass_time(lit_start)},Upcoming,,"
                            f"0,0,0,,{{{pos}{org}{entrance}{_emph_size(word, size)}}}{text}"
                        )
                    if drop:
                        pos = _drop_tags(word, effective)
                        lit_anim = ""
                    elif lit_start > block.start:
                        lit_anim = _LIGHT_UP
                    else:
                        lit_anim = entrance
                    events.append(
                        f"Dialogue: 1,{ass_time(lit_start)},{ass_time(block.end)},Phrase,,"
                        f"0,0,0,,{{{pos}{org}{lit_anim}{emph}}}{text}"
                    )
                elif drop:
                    # sem karaoke: cada palavra cai quando e falada e fica
                    d_start = max(block.start, min(word.start, block.end - 0.05))
                    events.append(
                        f"Dialogue: 1,{ass_time(d_start)},{ass_time(block.end)},Phrase,,"
                        f"0,0,0,,{{{_drop_tags(word, effective)}{emph}}}{text}"
                    )
                else:
                    events.append(
                        f"Dialogue: 1,{ass_time(block.start)},{ass_time(block.end)},Phrase,,"
                        f"0,0,0,,{{{pos}{org}{entrance}{emph}}}{text}"
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
                        f"0,0,0,,{{\\an7\\pos({_num(word.x)},{_num(word.y)}){_emph_size(word, size)}}}"
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
        options.caption_font,
        options.caption_bold,
        options.caption_font_size,
        bool(getattr(options, "caption_italic", False)),
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

