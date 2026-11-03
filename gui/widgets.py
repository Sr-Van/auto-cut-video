""" Componentes visuais reutilizáveis e prévia de celular 9:16 espelhando o design de /site """

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
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
    QRadialGradient,
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


def eyebrow(text: str) -> QLabel:
    """Kicker com traço na esquerda (igual `.eyebrow` do site)."""
    lbl = QLabel(
        f'<span style="color:{theme.LIME}; opacity:0.75;">—</span>&nbsp;&nbsp;{text.upper()}'
    )
    lbl.setObjectName("Eyebrow")
    lbl.setTextFormat(Qt.RichText)
    return lbl


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFrameShape(QFrame.NoFrame)
    return line


class Panel(QFrame):
    """Cartão `.panel` do site com eyebrow, título e slot opcional no cabeçalho."""

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
        self.body.setContentsMargins(22, 20, 22, 22)
        self.body.setSpacing(14)

        self.head = QHBoxLayout()
        self.head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(eyebrow(kicker))
        titles.addWidget(
            label(title, "PanelTitleCompact" if compact else "PanelTitle")
        )
        self.head.addLayout(titles)
        self.head.addStretch(1)
        self.body.addLayout(self.head)

    def add_head_widget(self, widget: QWidget):
        self.head.addWidget(widget, 0, Qt.AlignVCenter)


class Switch(QAbstractButton):
    """Interruptor `.switch-row` animado."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        width = 34 + 10 + self.fontMetrics().horizontalAdvance(self.text()) + 6
        return QSize(width, 24)

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
        off = QColor("#2b2a35")
        on = QColor(theme.LIME)
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

        knob_x = track.left() + 3 + (32 - 18) * self._offset
        knob = QRectF(knob_x, track.top() + 3, 12, 12)
        painter.setBrush(
            QColor("#0a0a0d") if self._offset > 0.5 else QColor("#8b8a96")
        )
        painter.drawEllipse(knob)

        painter.setPen(QColor(theme.MUTED if enabled else theme.FAINT))
        text_rect = self.rect().adjusted(42, 0, 0, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Segmented(QFrame):
    """Abas segmentadas `.source-tabs`."""

    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
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
    """Abas sublinhadas em lime (`.settings-tabs` do modal de configurações)."""

    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("UnderlineBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 0, 26, 0)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, text in enumerate(labels):
            button = QPushButton(text)
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


class PipeStep(QFrame):
    """Card de etapa do pipeline (`.pipe-step` do site)."""

    def __init__(self, title: str, hint: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Step")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
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
    """Renderiza o `.preview-phone` do site com cena, silhueta, zoom e legenda ao vivo."""

    def __init__(self, phone_width: int = 200, in_settings: bool = False, parent=None):
        super().__init__(parent)
        self._phone_width = phone_width
        self._in_settings = in_settings
        self._options = ProcessingOptions()
        self.setFixedSize(phone_width + 28, int(phone_width * 16 / 9) + 28)

    def set_options(self, options: ProcessingOptions):
        self._options = options
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        opts = self._options
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Estágio externo arredondado
        stage_rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        stage_path = QPainterPath()
        stage_path.addRoundedRect(stage_rect, 12, 12)
        stage_grad = QRadialGradient(
            stage_rect.center().x(),
            stage_rect.bottom(),
            stage_rect.height() * 0.75,
        )
        stage_grad.setColorAt(0.0, QColor(139, 92, 246, 28))
        stage_grad.setColorAt(1.0, QColor(0, 0, 0, 48))
        painter.fillPath(stage_path, stage_grad)
        painter.setPen(QPen(QColor(255, 255, 255, 19), 1))
        painter.drawPath(stage_path)

        # Proporção da tela do telefone
        ratio = (opts.width / opts.height) if opts.height else (9 / 16)
        max_w = self.width() - 28
        max_h = self.height() - 28
        pw = min(max_w, max_h * ratio)
        ph = pw / ratio
        px = (self.width() - pw) / 2
        py = (self.height() - ph) / 2
        phone_rect = QRectF(px, py, pw, ph)
        radius = 17.0 if self._in_settings else 22.0

        phone_path = QPainterPath()
        phone_path.addRoundedRect(phone_rect, radius, radius)

        painter.save()
        painter.setClipPath(phone_path)

        # Cena com brilho ajustado por bg_brightness
        bright = max(0.35, min(1.65, 1.0 + float(opts.bg_brightness)))

        def _adj(c: QColor) -> QColor:
            return QColor(
                min(255, int(c.red() * bright)),
                min(255, int(c.green() * bright)),
                min(255, int(c.blue() * bright)),
                c.alpha(),
            )

        bg_grad = QLinearGradient(phone_rect.topLeft(), phone_rect.bottomRight())
        bg_grad.setColorAt(0.0, _adj(QColor("#2d2549")))
        bg_grad.setColorAt(0.75, _adj(QColor("#0c0b12")))
        bg_grad.setColorAt(1.0, _adj(QColor("#070709")))
        painter.fillRect(phone_rect, bg_grad)

        # Orbe lime superior direito
        orb_lime = QRadialGradient(
            px + pw * 0.68, py + ph * 0.24, pw * 0.42
        )
        orb_lime.setColorAt(0.0, _adj(QColor(201, 255, 79, 55)))
        orb_lime.setColorAt(1.0, QColor(201, 255, 79, 0))
        painter.fillRect(phone_rect, orb_lime)

        # Orbe violeta inferior esquerdo
        orb_violet = QRadialGradient(
            px + pw * 0.24, py + ph * 0.76, pw * 0.55
        )
        orb_violet.setColorAt(0.0, _adj(QColor(139, 92, 246, 92)))
        orb_violet.setColorAt(1.0, QColor(139, 92, 246, 0))
        painter.fillRect(phone_rect, orb_violet)

        # Silhueta escalada pelo zoom (como `.preview-figure` do site)
        zoom_scale = max(0.75, min(1.75, float(opts.zoom) / 1.7))
        fig_w = pw * 0.54 * zoom_scale
        fig_h = fig_w * 1.15
        fig_x = px + (pw - fig_w) / 2
        fig_y = py + ph * 0.84 - fig_h

        head_r = fig_w * 0.22
        head_center = QPointF(px + pw / 2, fig_y - head_r * 0.35)
        fig_grad = QLinearGradient(fig_x, fig_y - head_r, fig_x, fig_y + fig_h)
        fig_grad.setColorAt(0.0, QColor(255, 255, 255, 48))
        fig_grad.setColorAt(1.0, QColor(0, 0, 0, 95))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fig_grad)
        painter.drawEllipse(head_center, head_r, head_r)

        torso_rect = QRectF(fig_x, fig_y + head_r * 0.55, fig_w, fig_h * 0.85)
        painter.drawRoundedRect(torso_rect, fig_w * 0.42, fig_w * 0.35)

        # Vinheta escura na base
        shade = QLinearGradient(0, py + ph * 0.38, 0, py + ph)
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 165))
        painter.fillRect(phone_rect, shade)

        # Notch no topo
        notch_w, notch_h = 34.0, 7.0
        notch = QRectF(px + (pw - notch_w) / 2, py + 7, notch_w, notch_h)
        painter.setBrush(QColor("#000000"))
        painter.drawRoundedRect(notch, 3.5, 3.5)

        # Legenda dinâmica
        self._draw_caption(painter, phone_rect, opts)

        painter.restore()

        # Borda externa do aparelho
        painter.setPen(QPen(QColor("#353541"), 1.2))
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
                (start + i, w) for i, w in enumerate(words[start : start + per_line])
            ]
            lines.append(chunk)

        alpha = 1.0 if opts.captions_enabled else (0.55 if self._in_settings else 0.22)
        text_color = QColor(opts.caption_text_color or "#FFFFFF")
        text_color.setAlphaF(alpha)

        box_opacity = max(0.0, min(1.0, float(opts.caption_highlight_opacity)))
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
        word_gap = max(2.0, fm.horizontalAdvance(" ") * float(opts.caption_word_spacing))
        line_h = fm.height() + pad_y * 2 + 2

        margin_pct = min(0.55, max(0.04, opts.caption_margin_bottom / max(1, opts.height)))
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
                    # Halo suave de baixa opacidade ao redor da palavra
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
                    d = max(0.6, min(2.5, opts.caption_outline_width * scale * 0.45))
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
    """Card visual clicavel para representar um Preset Viral de legenda."""

    clicked = Signal(str)

    def __init__(self, preset, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.preset_id = preset.id
        self._selected = False
        self.setObjectName("PresetCard")
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        title_lbl = label(preset.name, "FieldLabel")
        tag_lbl = label(preset.tag, "MiniPill")
        top.addWidget(title_lbl, 1)
        top.addWidget(tag_lbl, 0, Qt.AlignRight)
        layout.addLayout(top)

        # Mini-amostra estilizada do preset
        sample = QLabel(preset.sample_text)
        sample.setAlignment(Qt.AlignCenter)
        sample.setFixedHeight(32)
        s_cfg = preset.settings
        fg = s_cfg.get("caption_text_color", "#FFFFFF")
        hl = s_cfg.get("caption_highlight_color", "#7C3AED")
        opacity = float(s_cfg.get("caption_highlight_opacity", 0.0))
        font_family = s_cfg.get("caption_font", "Arial")

        if s_cfg.get("caption_glow"):
            sample.setStyleSheet(
                f"background-color: #0b0d13; color: #FFFFFF; "
                f"font-family: '{font_family}'; font-weight: 900; font-size: 13px; "
                "border: 1px solid rgba(255, 255, 255, 0.45); border-radius: 7px; padding: 3px 8px;"
            )
        elif opacity > 0.05:
            sample.setStyleSheet(
                f"background-color: {hl}; color: {fg}; "
                f"font-family: '{font_family}'; font-weight: 800; font-size: 13px; "
                "border-radius: 7px; padding: 3px 8px;"
            )
        else:
            sample.setStyleSheet(
                f"background-color: #16181d; color: {hl}; "
                f"font-family: '{font_family}'; font-weight: 800; font-size: 13px; "
                "border: 1px solid rgba(255,255,255,0.08); border-radius: 7px; padding: 3px 8px;"
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
                f"background-color: rgba(201, 255, 79, 0.07); "
                f"border: 1.5px solid {theme.LIME}; "
                "border-radius: 10px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame#PresetCard { "
                "background-color: rgba(255, 255, 255, 0.025); "
                "border: 1px solid rgba(255, 255, 255, 0.09); "
                "border-radius: 10px; } "
                "QFrame#PresetCard:hover { "
                "border: 1px solid rgba(255, 255, 255, 0.24); }"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.preset_id)
        super().mousePressEvent(event)


class PresetGrid(QWidget):
    """Galeria em grade de PresetCards com selecao exclusiva."""

    preset_selected = Signal(str)

    def __init__(self, presets: dict, columns: int = 2, parent=None):
        super().__init__(parent)
        self.cards: dict[str, PresetCard] = {}
        self._selected_id: str | None = None

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

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
    """Container tipo sanfona (Accordion) para agrupar Configuracoes Avancadas."""

    toggled = Signal(bool)

    def __init__(self, title: str = "Configurações Avançadas", expanded: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        self._expanded = bool(expanded)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("Ghost")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.clicked.connect(self.toggle)
        root.addWidget(self.toggle_button)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 4, 0, 0)
        self.content_layout.setSpacing(12)
        root.addWidget(self.content_area)

        self._sync_ui()

    def set_content_layout(self, layout):
        # Move widgets/layouts into content_layout
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
