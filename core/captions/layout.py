"""Agrupamento de palavras, quebra de linha e posicionamento geometrico."""

from __future__ import annotations

from core.captions.fonts import effective_size
from core.captions.models import CaptionBlock, CaptionWord
from core.options import ProcessingOptions


def words_in_window(
    segments, window_start: float, window_end: float
) -> list[CaptionWord]:
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


def ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", "...", "…", ":", ";"))


def group_words(
    words: list[CaptionWord], options: ProcessingOptions
) -> list[CaptionBlock]:
    max_words = max(
        1, options.caption_max_words_per_line * options.caption_max_lines
    )
    blocks: list[CaptionBlock] = []
    current: list[CaptionWord] = []

    def flush():
        nonlocal current
        if current:
            blocks.append(
                CaptionBlock(
                    start=current[0].start, end=current[-1].end, words=current
                )
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
        if ends_sentence(word.text):
            flush()
    flush()
    return blocks


def display_text(text: str, options: ProcessingOptions) -> str:
    return text.upper() if options.caption_uppercase else text


def wrap_lines(
    words: list[CaptionWord], options: ProcessingOptions
) -> list[list[CaptionWord]]:
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


def layout_blocks(
    blocks: list[CaptionBlock],
    options: ProcessingOptions,
    canvas_w: int,
    canvas_h: int,
    font,
) -> list[CaptionBlock]:
    line_height = effective_size(options.caption_font_size) * 1.35
    space = font.getlength(" ") * max(0.4, options.caption_word_spacing)
    for block in blocks:
        lines = wrap_lines(block.words, options)
        total_height = len(lines) * line_height
        top = canvas_h - options.caption_margin_bottom - total_height
        for row, line_words in enumerate(lines):
            y = top + row * line_height
            widths = [
                font.getlength(display_text(w.text, options)) for w in line_words
            ]
            line_width = sum(widths) + space * max(0, len(line_words) - 1)
            x = (canvas_w - line_width) / 2
            for word, width in zip(line_words, widths):
                word.x = x
                word.y = y
                x += width + space
    return blocks

