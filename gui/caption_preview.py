"""Desenha a legenda da previa com a MESMA geometria do render (libass).

Usa o agrupamento e o layout de `core.captions` (posicao, tamanho por
palavra, escada, enfase) e reproduz o estilo do ASS: fonte/italico, caixa,
glow, sombra, contorno e cor da palavra em foco/ativa. Mostra o estado final
do primeiro bloco (todas as palavras ja reveladas).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from core.captions.fonts import font_effective_size, load_font
from core.captions.layout import (
    _glyph_metrics,
    display_text,
    group_words,
    layout_blocks,
)
from core.captions.models import CaptionWord
from core.options import ProcessingOptions


_QT_FAMILIES: dict[str, str] = {}


def qt_family_for(font, fallback: str) -> str:
    """Registra no Qt o MESMO arquivo que o PIL/libass usam e devolve a
    familia, para a previa nao cair numa fonte substituta mais larga."""
    path = getattr(font, "path", None)
    if not path:
        return fallback
    if path not in _QT_FAMILIES:
        from PySide6.QtGui import QFontDatabase

        fid = QFontDatabase.addApplicationFont(path)
        families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _QT_FAMILIES[path] = families[0] if families else fallback
    return _QT_FAMILIES[path]


def sample_block(options: ProcessingOptions, sample_words: list[str]):
    """Primeiro bloco ja posicionado no canvas, como o render faria."""
    font, family, bold, _ = load_font(
        options.caption_font,
        options.caption_bold,
        options.caption_font_size,
        bool(getattr(options, "caption_italic", False)),
    )
    words = [
        CaptionWord(start=i * 0.3, end=i * 0.3 + 0.25, text=t)
        for i, t in enumerate(sample_words)
    ]
    family = qt_family_for(font, family)
    blocks = group_words(words, options)
    if not blocks:
        return None, font, family, bold
    layout_blocks(blocks[:1], options, options.width, options.height, font)
    return blocks[0], font, family, bold


def _color(hex_color: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_color or "#FFFFFF")
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def draw_caption(
    painter: QPainter,
    phone_rect: QRectF,
    options: ProcessingOptions,
    sample_words: list[str],
    opacity: float = 1.0,
) -> None:
    block, font, family, bold = sample_block(options, sample_words)
    if block is None or not block.words:
        return
    size = options.caption_font_size
    effective = font_effective_size(font, size)
    base_off, _ = _glyph_metrics(font, size)
    base_ratio = base_off / float(size or 1)
    scale = phone_rect.width() / max(1, options.width)

    italic = bool(getattr(options, "caption_italic", False))
    pad = options.caption_box_padding
    box_h = effective * 1.1 + pad * 0.8
    box_opacity = max(0.0, min(1.0, float(options.caption_highlight_opacity)))
    has_box = box_opacity > 0.01
    outline_w = float(options.caption_outline_width)
    shadow = int(getattr(options, "caption_shadow", 1))
    glow_on = bool(getattr(options, "caption_glow", False))
    glow_strength = int(getattr(options, "caption_glow_strength", 6) or 0)
    text_hex = options.caption_text_color
    hl_hex = options.caption_highlight_color
    emph_hex = getattr(options, "caption_emphasis_color", "#22C55E")
    cumulative = getattr(options, "caption_karaoke_mode", "active") == "cumulative"
    # palavra "falando agora" (mesma regra da previa antiga)
    active = min(3, len(block.words) - 1)

    painter.save()
    painter.setOpacity(opacity)
    painter.translate(phone_rect.topLeft())
    painter.scale(scale, scale)
    painter.setRenderHint(QPainter.Antialiasing)

    for index, word in enumerate(block.words):
        fs = size * (word.scale or 1.0)
        em_px = font_effective_size(font, fs)
        qfont = QFont(family)
        qfont.setPixelSize(max(1, int(round(em_px))))
        qfont.setBold(bool(bold))
        qfont.setItalic(italic)
        text = display_text(word.text, options)
        path = QPainterPath()
        path.addText(QPointF(word.x, word.y + base_ratio * fs), qfont, text)

        is_active = index == active and not cumulative
        if has_box and is_active:
            width = word.width or path.boundingRect().width()
            top = word.y + effective * 0.42 - box_h / 2.0
            rect = QRectF(word.x - pad, top, width + pad * 2, box_h)
            painter.setPen(Qt.NoPen)
            painter.setBrush(_color(hl_hex, box_opacity))
            r = min(options.caption_corner_radius, box_h / 2)
            painter.drawRoundedRect(rect, r, r)

        if glow_on and glow_strength > 0:
            glow_hex = getattr(options, "caption_glow_color", "#FFFFFF")
            bord = max(2, round(glow_strength * 0.66))
            # aproxima o \blur com tracos concentricos cada vez mais fracos
            for step in range(4, 0, -1):
                pen = QPen(_color(glow_hex, 0.045 * (5 - step)))
                pen.setWidthF((bord + glow_strength * step / 4) * 2)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.strokePath(path, pen)

        if shadow > 0:
            if outline_w > 0 and shadow < 3:
                shadow_c = _color(options.caption_outline_color)
            else:
                shadow_c = _color("#000000", 0.45)
            shadow_path = path.translated(shadow, shadow)
            if outline_w > 0:
                pen = QPen(shadow_c, outline_w * 2)
                pen.setJoinStyle(Qt.RoundJoin)
                painter.strokePath(shadow_path, pen)
            painter.fillPath(shadow_path, shadow_c)

        if outline_w > 0:
            pen = QPen(_color(options.caption_outline_color), outline_w * 2)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.strokePath(path, pen)

        if word.emphasis:
            fill = emph_hex
        elif is_active and not has_box and hl_hex.upper() != text_hex.upper():
            fill = hl_hex
        else:
            fill = text_hex
        painter.fillPath(path, _color(fill))

    painter.restore()
