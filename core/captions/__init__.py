"""Subpacote de legendas dinamicas (modelos, fontes, layout, escrita ASS e presets virais)."""

from __future__ import annotations

from core.captions.ass_writer import (
    _POP,
    _clean,
    _num,
    ass_color as _ass_color,
    ass_time as _ass_time,
    build_ass,
    render_ass as _render_ass,
    rounded_rect as _rounded_rect,
    word_span as _word_span,
    write_ass,
)
from core.captions.fonts import (
    PRECONFIGURED_FONTS,
    _FALLBACK_FONTS,
    _FONT_DIRS,
    _LIBASS_FONT_SCALE,
    build_font_index as _build_font_index,
    effective_size as _effective_size,
    find_font_path,
    list_available_fonts,
    load_font as _load_font,
)
from core.captions.layout import (
    display_text as _display_text,
    ends_sentence as _ends_sentence,
    group_words,
    layout_blocks,
    words_in_window,
    wrap_lines as _wrap_lines,
)
from core.captions.models import CaptionBlock, CaptionWord
from core.captions.presets import (
    PRESETS,
    VIRAL_PRESETS,
    CaptionPreset,
    apply_preset,
    detect_active_preset,
)

__all__ = [
    "CaptionBlock",
    "CaptionPreset",
    "CaptionWord",
    "PRECONFIGURED_FONTS",
    "PRESETS",
    "VIRAL_PRESETS",
    "apply_preset",
    "build_ass",
    "detect_active_preset",
    "find_font_path",
    "group_words",
    "layout_blocks",
    "list_available_fonts",
    "words_in_window",
    "write_ass",
]

