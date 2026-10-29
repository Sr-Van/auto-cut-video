"""Legendas dinamicas no formato ASS.

Estrategia:
- Agrupa palavras (com timestamp) em blocos de 1-2 linhas.
- Cada palavra vira um texto branco posicionado individualmente (camada 1).
- Atrás dela (camada 0), um retangulo arredondado roxo "persegue" a palavra
  falada: faz um pop e desliza para a proxima palavra no fim do intervalo.
- Posicoes calculadas com as metricas da mesma fonte que o libass usa
  (PIL/FreeType + mesmo .ttf), garantindo alinhamento texto <-> bloco.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageFont

from core.options import ProcessingOptions


# O libass deste build renderiza a fonte a ~90% do `Fontsize` informado no ASS
# (constante de 36 a 144px). O PIL precisa medir na MESMA escala, senao as
# palavras ficam mais afastadas que o normal. Ajustavel por env, se o FFmpeg
# mudar de comportamento.
_LIBASS_FONT_SCALE = float(os.getenv("CAPTION_FONT_SCALE", "0.9"))


def _effective_size(size: float) -> float:
    return max(1.0, float(size) * _LIBASS_FONT_SCALE)


@dataclass
class CaptionWord:
    start: float
    end: float
    text: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class CaptionBlock:
    start: float
    end: float
    words: list[CaptionWord] = field(default_factory=list)


_FALLBACK_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def find_font_path(font_name: str = "Arial", bold: bool = True) -> str | None:
    """Localiza um .ttf concreto para uso no PIL e no libass."""
    slug = (font_name or "Arial").lower().replace(" ", "")
    win = "C:/Windows/Fonts/"
    candidates: list[str] = []
    if bold:
        candidates += [f"{win}{slug}bd.ttf", f"{win}{slug}b.ttf", f"{win}{slug} bold.ttf"]
    candidates.append(f"{win}{slug}.ttf")
    candidates += _FALLBACK_FONTS
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _load_font(font_name: str, bold: bool, size: int):
    """Retorna (font PIL, familia, bold, pasta da fonte)."""
    path = find_font_path(font_name, bold)
    if path:
        font = ImageFont.truetype(path, round(_effective_size(size)))
        try:
            family, style = font.getname()
        except Exception:
            family, style = font_name, "Bold" if bold else "Regular"
        return font, family, "bold" in (style or "").lower(), os.path.dirname(path)
    return ImageFont.load_default(), font_name, bold, None


def words_in_window(segments, window_start: float, window_end: float) -> list[CaptionWord]:
    """Extrai palavras do intervalo e rebaseia os tempos para comecar em 0."""
    result: list[CaptionWord] = []
    for seg in segments:
        for raw in getattr(seg, "words", None) or []:
            text = (getattr(raw, "text", "") or "").strip()
            if not text:
                continue
            if raw.end <= window_start or raw.start >= window_end:
                continue
            start = max(0.0, raw.start - window_start)
            end = max(0.0, min(raw.end, window_end) - window_start)
            if end <= start:
                end = start + 0.05
            result.append(CaptionWord(start=start, end=end, text=text))
    result.sort(key=lambda word: word.start)
    return result


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", "...", "…", ":", ";"))


def group_words(words: list[CaptionWord], options: ProcessingOptions) -> list[CaptionBlock]:
    max_words = max(1, options.caption_max_words_per_line * options.caption_max_lines)
    blocks: list[CaptionBlock] = []
    current: list[CaptionWord] = []

    def flush():
        nonlocal current
        if current:
            blocks.append(
                CaptionBlock(start=current[0].start, end=current[-1].end, words=current)
            )
            current = []

    for word in words:
        if current:
            gap = word.start - current[-1].end
            duration = word.end - current[0].start
            if (
                gap >= options.caption_gap_break
                or duration > options.caption_max_block_duration
                or len(current) >= max_words
            ):
                flush()
        current.append(word)
        if _ends_sentence(word.text):
            flush()
    flush()
    return blocks


def _display_text(text: str, options: ProcessingOptions) -> str:
    return text.upper() if options.caption_uppercase else text


def _wrap_lines(words: list[CaptionWord], options: ProcessingOptions):
    per_line = max(1, options.caption_max_words_per_line)
    lines: list[list[CaptionWord]] = []
    line: list[CaptionWord] = []
    for word in words:
        if line and len(line) >= per_line:
            lines.append(line)
            line = []
        line.append(word)
    if line:
        lines.append(line)
    return lines


def layout_blocks(blocks, options: ProcessingOptions, canvas_w: int, canvas_h: int, font):
    line_height = _effective_size(options.caption_font_size) * 1.35
    space = font.getlength(" ") * max(0.4, options.caption_word_spacing)
    for block in blocks:
        lines = _wrap_lines(block.words, options)
        total_height = len(lines) * line_height
        top = canvas_h - options.caption_margin_bottom - total_height
        for row, line_words in enumerate(lines):
            y = top + row * line_height
            widths = [font.getlength(_display_text(w.text, options)) for w in line_words]
            line_width = sum(widths) + space * max(0, len(line_words) - 1)
            x = (canvas_w - line_width) / 2
            for word, width in zip(line_words, widths):
                word.x = x
                word.y = y
                x += width + space
    return blocks


def _ass_color(hex_color: str, opacity: float = 1.0) -> str:
    value = (hex_color or "#FFFFFF").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    opacity = max(0.0, min(1.0, float(opacity)))
    alpha = int(round((1.0 - opacity) * 255))
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"


def _ass_time(seconds: float) -> str:
    total_cs = int(round(max(0.0, float(seconds)) * 100))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _num(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _rounded_rect(width: float, height: float, radius: float) -> str:
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


# Pop aplicado ao bloco: sobe para 108% e volta a 100% (nunca encolhe).
_POP = "\\t(0,80,\\fscx108\\fscy108)\\t(80,190,\\fscx100\\fscy100)"


def _clean(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _word_span(block: CaptionBlock, index: int):
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


def _render_ass(blocks, options, canvas_w, canvas_h, family, bold, font) -> str:
    size = options.caption_font_size
    effective = _effective_size(size)
    line_height = effective * 1.35
    pad = options.caption_box_padding
    box_h = effective * 1.1 + pad * 0.8

    text_c = _ass_color(options.caption_text_color)
    highlight_c = _ass_color(options.caption_highlight_color, options.caption_highlight_opacity)
    outline_c = _ass_color(options.caption_outline_color)
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
        f"Style: Box,{family},{size},{highlight_c},{highlight_c},{highlight_c},"
        f"{highlight_c},{bold_flag},0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    events: list[str] = []
    for block in blocks:
        boxes = []
        for word in block.words:
            width = font.getlength(_display_text(word.text, options))
            left = word.x - pad
            top = word.y + effective * 0.42 - box_h / 2.0
            cx = word.x + width / 2.0
            cy = top + box_h / 2.0
            boxes.append((left, top, cx, cy, width))

        # Camada 0: bloco roxo arredondado, com pop e deslize continuo.
        for index, word in enumerate(block.words):
            start, end = _word_span(block, index)
            left, top, cx, cy, width = boxes[index]
            shape = _rounded_rect(width + pad * 2, box_h, options.caption_corner_radius)
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
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Box,,0,0,0,,"
                f"{{\\an7{pos}{move}\\org({_num(cx)},{_num(cy)}){_POP}\\p1}}"
                f"{shape}{{\\p0}}"
            )

        # Camada 1: texto de todas as palavras do bloco.
        for index, word in enumerate(block.words):
            events.append(
                f"Dialogue: 1,{_ass_time(block.start)},{_ass_time(block.end)},Phrase,,"
                f"0,0,0,,{{\\an7\\pos({_num(word.x)},{_num(word.y)})}}"
                f"{_clean(_display_text(word.text, options))}"
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
    font, family, bold, _fontsdir = _load_font(
        options.caption_font, options.caption_bold, options.caption_font_size
    )
    blocks = group_words(words, options)
    layout_blocks(blocks, options, canvas_w, canvas_h, font)
    return _render_ass(blocks, options, canvas_w, canvas_h, family, bold, font)


def write_ass(words, out_path, options: ProcessingOptions, canvas_w=None, canvas_h=None) -> str:
    content = build_ass(words, options, canvas_w, canvas_h)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)
