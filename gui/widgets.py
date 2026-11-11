"""Componentes visuais reutilizáveis e prévia vertical 9:16 do AutoCortesBR."""

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.options import ProcessingOptions
from gui import theme


def label(text: str, name: str | None = None, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def _luminance(hex_color: str) -> float:
    c = QColor(hex_color)
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def readable_text_on(bg: str, preferred: str) -> str:
    """Mantem a cor preferida se passar AA (4.5:1); senao usa escuro ou branco."""
    if contrast_ratio(preferred, bg) >= 4.5:
        return preferred
    dark, light = "#0A0D12", "#FFFFFF"
    return dark if contrast_ratio(dark, bg) >= contrast_ratio(light, bg) else light


class ElidedLabel(QLabel):
    """QLabel de linha unica que corta com reticencias em vez de alargar o layout."""

    def __init__(self, text: str = "", name: str | None = None, parent=None):
        super().__init__(parent)
        self._full_text = text
        if name:
            self.setObjectName(name)
        self.setMinimumWidth(40)
        from PySide6.QtWidgets import QSizePolicy

        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(text)
        self._refresh()

    def setText(self, text: str):  # noqa: N802
        self._full_text = text
        self.setToolTip(text)
        self._refresh()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        elided = self.fontMetrics().elidedText(
            self._full_text, Qt.ElideRight, max(0, self.width())
        )
        super().setText(elided)


def flash_button(button, text: str, ms: int = 1400) -> None:
    """Confirma uma acao trocando o texto do botao por alguns instantes."""
    original = button.property("_flash_original") or button.text()
    button.setProperty("_flash_original", original)
    button.setText(text)

    def restore():
        try:
            button.setText(original)
            button.setProperty("_flash_original", None)
        except RuntimeError:  # widget ja destruido
            pass

    QTimer.singleShot(ms, restore)


def eyebrow(text: str) -> QLabel:
    """Rótulo de seção compacto em caixa alta, sem ornamentos decorativos."""
    lbl = QLabel(text.upper())
    lbl.setObjectName("Eyebrow")
    return lbl


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFrameShape(QFrame.NoFrame)
    return line


class Panel(QFrame):
    """Painel utilitário com cabeçalho limpo e slot opcional para controles."""

    def __init__(
        self,
        kicker: str,
        title: str,
        compact: bool = False,
        source_accent: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("SourcePanel" if source_accent else "Panel")

        self.body = QVBoxLayout(self)
        pad = 14 if compact else 16
        self.body.setContentsMargins(pad, pad, pad, pad)
        self.body.setSpacing(10 if compact else 12)

        self.head = QHBoxLayout()
        self.head.setContentsMargins(0, 0, 0, 0)
        self.head.setSpacing(10)

        title_lbl = label(
            title, "PanelTitleCompact" if compact else "PanelTitle"
        )
        self.head.addWidget(title_lbl)

        if kicker and kicker.lower() != title.lower():
            sub_lbl = label(kicker, "Faint")
            self.head.addWidget(sub_lbl)

        self.head.addStretch(1)
        self.body.addLayout(self.head)

    def add_head_widget(self, widget: QWidget):
        self.head.addWidget(widget, 0, Qt.AlignVCenter)


class Switch(QAbstractButton):
    """Interruptor booleano enxuto e direto."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        width = 34 + 8 + self.fontMetrics().horizontalAdvance(self.text()) + 6
        return QSize(width, 22)

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked):  # noqa: N802
        super().setChecked(checked)
        self._anim.stop()
        self._offset = 1.0 if checked else 0.0
        self.update()

    def get_offset(self):
        return self._offset

    def set_offset(self, value):
        self._offset = value
        self.update()

    offset = Property(float, get_offset, set_offset)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        enabled = self.isEnabled()

        track = QRectF(0, (self.height() - 18) / 2, 32, 18)
        off = QColor("#282E3B")
        on = QColor(theme.ACCENT)
        color = QColor(
            int(off.red() + (on.red() - off.red()) * self._offset),
            int(off.green() + (on.green() - off.green()) * self._offset),
            int(off.blue() + (on.blue() - off.blue()) * self._offset),
        )
        if not enabled:
            color.setAlphaF(0.45)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(track, 9, 9)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(theme.ACCENT_TEXT), 1.5))
            painter.drawRoundedRect(track.adjusted(-2, -2, 2, 2), 11, 11)
            painter.setPen(Qt.NoPen)

        knob_x = track.left() + 3 + (32 - 18) * self._offset
        knob = QRectF(knob_x, track.top() + 3, 12, 12)
        painter.setBrush(
            QColor("#FFFFFF") if self._offset > 0.5 else QColor("#9CA3AF")
        )
        painter.drawEllipse(knob)

        painter.setPen(QColor(theme.TEXT if enabled else theme.FAINT))
        text_rect = self.rect().adjusted(40, 0, 0, 0)
        painter.drawText(
            text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text()
        )


class Segmented(QFrame):
    """Controle segmentado compacto."""

    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, text in enumerate(labels):
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.group.addButton(button, index)
            layout.addWidget(button)
        self.group.button(0).setChecked(True)
        self.group.idToggled.connect(self._on_toggled)

    def _on_toggled(self, index, checked):
        if checked:
            self.changed.emit(index)

    def current(self) -> int:
        return self.group.checkedId()

    def set_current(self, index: int):
        btn = self.group.button(index)
        if btn:
            btn.setChecked(True)


class UnderlineTabs(QFrame):
    """Abas horizontais sublinhadas com indicador sólido."""

    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("UnderlineBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, text in enumerate(labels):
            button = QPushButton(text.replace("&", "&&"))
            button.setObjectName("UnderlineTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.group.addButton(button, index)
            layout.addWidget(button)
        layout.addStretch(1)
        self.group.button(0).setChecked(True)
        self.group.idToggled.connect(self._on_toggled)

    def _on_toggled(self, index, checked):
        if checked:
            self.changed.emit(index)

    def set_current(self, index: int):
        btn = self.group.button(index)
        if btn:
            btn.setChecked(True)


class PipeStep(QFrame):
    """Indicador compacto de etapa do pipeline."""

    def __init__(self, title: str, hint: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Step")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(7)

        dot = QFrame()
        dot.setObjectName("StepDot")
        dot.setFixedSize(6, 6)
        layout.addWidget(dot, 0, Qt.AlignTop | Qt.AlignHCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        col.addWidget(label(title, "StepTitle"))
        col.addWidget(label(hint, "StepHint"))
        layout.addLayout(col, 1)
        self.set_state("idle")

    def set_state(self, state: str):
        self.setProperty("state", state)
        for widget in [self, *self.findChildren(QWidget)]:
            widget.style().unpolish(widget)
            widget.style().polish(widget)


SAMPLE_WORDS = [
    "o",
    "erro",
    "que",
    "ninguém",
    "conta",
    "sobre",
    "precificar",
    "de",
    "verdade",
]


class PhonePreviewWidget(QWidget):
    """Prévia técnica 9:16 neutra, destacando enquadramento, zoom e legenda real."""

    def __init__(
        self, phone_width: int = 160, in_settings: bool = False, parent=None
    ):
        super().__init__(parent)
        self._phone_width = phone_width
        self._in_settings = in_settings
        self._options = ProcessingOptions()
        self.setFixedSize(phone_width + 20, int(phone_width * 16 / 9) + 20)

    def set_options(self, options: ProcessingOptions):
        self._options = options
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        opts = self._options
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Container externo sóbrio
        stage_rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        stage_path = QPainterPath()
        stage_path.addRoundedRect(stage_rect, 8, 8)
        painter.fillPath(stage_path, QColor("#111318"))
        painter.setPen(QPen(QColor(theme.LINE), 1))
        painter.drawPath(stage_path)

        # Proporção da tela
        ratio = (opts.width / opts.height) if opts.height else (9 / 16)
        max_w = self.width() - 20
        max_h = self.height() - 20
        pw = min(max_w, max_h * ratio)
        ph = pw / ratio
        px = (self.width() - pw) / 2
        py = (self.height() - ph) / 2
        phone_rect = QRectF(px, py, pw, ph)
        radius = 12.0 if self._in_settings else 14.0

        phone_path = QPainterPath()
        phone_path.addRoundedRect(phone_rect, radius, radius)

        painter.save()
        painter.setClipPath(phone_path)

        # Fundo neutro ajustado por bg_brightness (sem orbes coloridos)
        bright = max(0.35, min(1.65, 1.0 + float(opts.bg_brightness)))

        def _adj(c: QColor) -> QColor:
            return QColor(
                min(255, int(c.red() * bright)),
                min(255, int(c.green() * bright)),
                min(255, int(c.blue() * bright)),
                c.alpha(),
            )

        bg_grad = QLinearGradient(
            phone_rect.topLeft(), phone_rect.bottomLeft()
        )
        bg_grad.setColorAt(0.0, _adj(QColor("#1D222D")))
        bg_grad.setColorAt(0.5, _adj(QColor("#252B38")))
        bg_grad.setColorAt(1.0, _adj(QColor("#14171F")))
        painter.fillRect(phone_rect, bg_grad)

        # Faixas superior/inferior representando o fundo desfocado (blur)
        crop_h = min(ph, (pw * 9 / 16) * max(1.0, float(opts.zoom) * 0.85))
        crop_y = py + (ph - crop_h) / 2
        if crop_h < ph - 4:
            blur_overlay = QColor(0, 0, 0, 75)
            painter.fillRect(QRectF(px, py, pw, crop_y - py), blur_overlay)
            painter.fillRect(
                QRectF(px, crop_y + crop_h, pw, (py + ph) - (crop_y + crop_h)),
                blur_overlay,
            )
            guide_pen = QPen(QColor(255, 255, 255, 22), 1, Qt.DashLine)
            painter.setPen(guide_pen)
            painter.drawLine(
                QPointF(px, crop_y), QPointF(px + pw, crop_y)
            )
            painter.drawLine(
                QPointF(px, crop_y + crop_h),
                QPointF(px + pw, crop_y + crop_h),
            )

        # Silhueta neutra escalada pelo zoom
        zoom_scale = max(0.75, min(1.75, float(opts.zoom) / 1.7))
        fig_w = pw * 0.50 * zoom_scale
        fig_h = fig_w * 1.15
        fig_x = px + (pw - fig_w) / 2
        fig_y = py + ph * 0.80 - fig_h

        head_r = fig_w * 0.21
        head_center = QPointF(px + pw / 2, fig_y - head_r * 0.35)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 34))
        painter.drawEllipse(head_center, head_r, head_r)

        torso_rect = QRectF(
            fig_x, fig_y + head_r * 0.55, fig_w, fig_h * 0.82
        )
        painter.drawRoundedRect(torso_rect, fig_w * 0.38, fig_w * 0.32)

        # Sombra inferior suave para leitura da legenda
        shade = QLinearGradient(0, py + ph * 0.45, 0, py + ph)
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 155))
        painter.fillRect(phone_rect, shade)

        # Legenda dinâmica
        self._draw_caption(painter, phone_rect, opts)

        painter.restore()

        # Borda externa do frame 9:16
        painter.setPen(QPen(QColor(theme.LINE_STRONG), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(phone_path)

    def _draw_caption(
        self, painter: QPainter, phone_rect: QRectF, opts: ProcessingOptions
    ):
        px, py, pw, ph = (
            phone_rect.x(),
            phone_rect.y(),
            phone_rect.width(),
            phone_rect.height(),
        )
        scale = pw / max(1, opts.width)
        font_px = max(8.0, min(22.0, opts.caption_font_size * scale))

        font = QFont(opts.caption_font or "Arial")
        font.setPixelSize(int(round(font_px)))
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetricsF(font)

        per_line = max(1, int(opts.caption_max_words_per_line))
        max_lines = max(1, int(opts.caption_max_lines))
        words = SAMPLE_WORDS[: per_line * max_lines]
        if opts.caption_uppercase:
            words = [w.upper() for w in words]
        hi_index = min(3, len(words) - 1)

        lines: list[list[tuple[int, str]]] = []
        for start in range(0, len(words), per_line):
            chunk = [
                (start + i, w)
                for i, w in enumerate(words[start : start + per_line])
            ]
            lines.append(chunk)

        alpha = (
            1.0
            if opts.captions_enabled
            else (0.50 if self._in_settings else 0.22)
        )
        text_color = QColor(opts.caption_text_color or "#FFFFFF")
        text_color.setAlphaF(alpha)

        box_opacity = max(
            0.0, min(1.0, float(opts.caption_highlight_opacity))
        )
        has_box = box_opacity > 0.01
        hl_color = QColor(opts.caption_highlight_color or "#7C3AED")
        hl_color.setAlphaF(box_opacity * alpha)

        active_word_color = QColor(opts.caption_highlight_color or "#FACC15")
        active_word_color.setAlphaF(alpha)

        outline_color = QColor(opts.caption_outline_color or "#000000")
        outline_color.setAlphaF(alpha * 0.9)

        pad_x = max(2.5, opts.caption_box_padding * scale * 0.55)
        pad_y = max(1.5, opts.caption_box_padding * scale * 0.24)
        box_radius = max(2.0, opts.caption_corner_radius * scale * 0.26)
        word_gap = max(
            2.0, fm.horizontalAdvance(" ") * float(opts.caption_word_spacing)
        )
        line_h = fm.height() + pad_y * 2 + 2

        margin_pct = min(
            0.55, max(0.04, opts.caption_margin_bottom / max(1, opts.height))
        )
        total_h = len(lines) * line_h
        base_y = py + ph * (1.0 - margin_pct) - total_h

        for line_idx, line in enumerate(lines):
            widths = [fm.horizontalAdvance(w) + pad_x * 2 for _, w in line]
            line_w = sum(widths) + word_gap * max(0, len(line) - 1)
            cur_x = px + (pw - line_w) / 2
            cur_y = base_y + line_idx * line_h

            for (word_idx, word), w_box in zip(line, widths):
                rect = QRectF(cur_x, cur_y, w_box, fm.height() + pad_y * 2)
                if word_idx == hi_index and has_box:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(hl_color)
                    painter.drawRoundedRect(rect, box_radius, box_radius)

                if getattr(opts, "caption_glow", False):
                    glow_pen = QColor("#FFFFFF")
                    glow_pen.setAlpha(int(36 * alpha))
                    painter.setPen(glow_pen)
                    for dx, dy in (
                        (-2.0, 0),
                        (2.0, 0),
                        (0, -2.0),
                        (0, 2.0),
                        (-1.5, -1.5),
                        (1.5, -1.5),
                        (-1.5, 1.5),
                        (1.5, 1.5),
                    ):
                        painter.drawText(
                            rect.translated(dx, dy), Qt.AlignCenter, word
                        )

                if opts.caption_outline_width > 0:
                    painter.setPen(outline_color)
                    d = max(
                        0.6,
                        min(2.5, opts.caption_outline_width * scale * 0.45),
                    )
                    for dx, dy in (
                        (-d, 0),
                        (d, 0),
                        (0, -d),
                        (0, d),
                    ):
                        painter.drawText(
                            rect.translated(dx, dy), Qt.AlignCenter, word
                        )

                if word_idx == hi_index and not has_box:
                    painter.setPen(active_word_color)
                else:
                    painter.setPen(text_color)
                painter.drawText(rect, Qt.AlignCenter, word)
                cur_x += w_box + word_gap


class PresetCard(QFrame):
    """Card compacto clicável para representar um Preset Viral de legenda."""

    clicked = Signal(str)

    def __init__(self, preset, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.preset_id = preset.id
        self._selected = False
        self.setObjectName("PresetCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"Preset de legenda {preset.name}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        title_lbl = label(preset.name, "FieldLabel")
        tag_lbl = label(preset.tag, "MiniPill")
        top.addWidget(title_lbl, 1)
        top.addWidget(tag_lbl, 0, Qt.AlignRight)
        layout.addLayout(top)

        sample = QLabel(preset.sample_text)
        sample.setAlignment(Qt.AlignCenter)
        sample.setFixedHeight(28)
        s_cfg = preset.settings
        fg = s_cfg.get("caption_text_color", "#FFFFFF")
        hl = s_cfg.get("caption_highlight_color", "#7C3AED")
        opacity = float(s_cfg.get("caption_highlight_opacity", 0.0))
        font_family = s_cfg.get("caption_font", "Arial")

        if s_cfg.get("caption_glow"):
            sample.setStyleSheet(
                f"background-color: #0F1115; color: #FFFFFF; "
                f"font-family: '{font_family}'; font-weight: 900; font-size: 12px; "
                "border: 1px solid rgba(255, 255, 255, 0.35); border-radius: 5px; padding: 2px 6px;"
            )
        elif opacity > 0.05:
            fg = readable_text_on(hl, fg)
            sample.setStyleSheet(
                f"background-color: {hl}; color: {fg}; "
                f"font-family: '{font_family}'; font-weight: 800; font-size: 12px; "
                "border-radius: 5px; padding: 2px 6px;"
            )
        else:
            hl = readable_text_on("#12151C", hl)
            sample.setStyleSheet(
                f"background-color: #12151C; color: {hl}; "
                f"font-family: '{font_family}'; font-weight: 800; font-size: 12px; "
                f"border: 1px solid {theme.LINE}; border-radius: 5px; padding: 2px 6px;"
            )
        layout.addWidget(sample)

        desc = label(preset.description, "Faint", wrap=True)
        layout.addWidget(desc)
        self._apply_card_style()

    def set_selected(self, selected: bool):
        if self._selected != bool(selected):
            self._selected = bool(selected)
            self._apply_card_style()

    def is_selected(self) -> bool:
        return self._selected

    def _apply_card_style(self):
        if self._selected:
            self.setStyleSheet(
                "QFrame#PresetCard { "
                f"background-color: {theme.ACCENT_SOFT}; "
                f"border: 1.5px solid {theme.ACCENT}; "
                "border-radius: 6px; } "
                "QFrame#PresetCard:focus { "
                f"border: 2px solid {theme.ACCENT_TEXT}; }}"
            )
        else:
            self.setStyleSheet(
                "QFrame#PresetCard { "
                f"background-color: {theme.PANEL_2}; "
                f"border: 1px solid {theme.LINE}; "
                "border-radius: 6px; } "
                "QFrame#PresetCard:hover { "
                f"border: 1px solid {theme.LINE_STRONG}; }} "
                "QFrame#PresetCard:focus { "
                f"border: 1.5px solid {theme.ACCENT_TEXT}; }}"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.clicked.emit(self.preset_id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.preset_id)
            event.accept()
            return
        super().keyPressEvent(event)


class PresetGrid(QWidget):
    """Galeria em grade de PresetCards com seleção exclusiva."""

    preset_selected = Signal(str)

    def __init__(self, presets: dict, columns: int = 3, parent=None):
        super().__init__(parent)
        self.cards: dict[str, PresetCard] = {}
        self._selected_id: str | None = None

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        for idx, (preset_id, preset) in enumerate(presets.items()):
            card = PresetCard(preset, self)
            card.clicked.connect(self._on_card_clicked)
            self.cards[preset_id] = card
            layout.addWidget(card, idx // columns, idx % columns)

    def _on_card_clicked(self, preset_id: str):
        self.select_preset(preset_id)
        self.preset_selected.emit(preset_id)

    def select_preset(self, preset_id: str | None):
        self._selected_id = preset_id
        for cid, card in self.cards.items():
            card.set_selected(cid == preset_id)

    def selected_preset(self) -> str | None:
        return self._selected_id


class CollapsibleBox(QWidget):
    """Container retrátil (Accordion) para agrupar configurações avançadas."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str = "Configurações Avançadas",
        expanded: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._title = title
        self._expanded = bool(expanded)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("Ghost")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.clicked.connect(self.toggle)
        root.addWidget(self.toggle_button)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 4, 0, 0)
        self.content_layout.setSpacing(10)
        root.addWidget(self.content_area)

        self._sync_ui()

    def set_content_layout(self, layout):
        self.content_layout.addLayout(layout)

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool):
        self._expanded = bool(expanded)
        self._sync_ui()
        self.toggled.emit(self._expanded)

    def is_expanded(self) -> bool:
        return self._expanded

    def _sync_ui(self):
        arrow = "▾" if self._expanded else "▸"
        self.toggle_button.setText(f"{arrow}   {self._title}")
        self.content_area.setVisible(self._expanded)
