"""Dialog de configuracoes (video vertical + legendas), persistido via QSettings.

Espelha o modal de configuracoes de `site/index.html` e mantem a API publica
(`ColorButton`, `SettingsDialog`, `RESOLUTIONS`, `PRESETS`).
"""

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.captions import PRECONFIGURED_FONTS, list_available_fonts
from core.options import ProcessingOptions
from gui.widgets import (
    PhonePreviewWidget,
    Switch,
    UnderlineTabs,
    eyebrow,
    label,
    separator,
)

RESOLUTIONS = [
    ("1080 × 1920 · Full HD", 1080, 1920),
    ("720 × 1280 · HD", 720, 1280),
    ("1440 × 2560 · 2K", 1440, 2560),
]

PRESETS = {
    "TikTok · roxo": ("#7C3AED", "#FFFFFF"),
    "Neon · ciano": ("#22D3EE", "#FFFFFF"),
    "Amarelo": ("#FACC15", "#111111"),
}


class ColorButton(QWidget):
    """Controle de cor `.color-control`: swatch clicavel + campo hex."""

    changed = Signal(str)

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = (color or "#FFFFFF").upper()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.swatch = QPushButton()
        self.swatch.setFixedSize(36, 36)
        self.swatch.setCursor(Qt.PointingHandCursor)
        self.swatch.clicked.connect(self._choose)

        self.hex_edit = QLineEdit(self._color)
        self.hex_edit.setObjectName("MonoInput")
        self.hex_edit.setMaxLength(7)
        self.hex_edit.textEdited.connect(self._on_hex_edited)

        layout.addWidget(self.swatch)
        layout.addWidget(self.hex_edit, 1)
        self._refresh()

    def _refresh(self):
        self.swatch.setStyleSheet(
            f"background-color: {self._color}; "
            "border: 1px solid rgba(255,255,255,0.18); border-radius: 8px;"
        )
        if self.hex_edit.text().upper() != self._color:
            self.hex_edit.setText(self._color)

    def _choose(self):
        chosen = QColorDialog.getColor(QColor(self._color), self, "Escolher cor")
        if chosen.isValid():
            self.set_color(chosen.name())
            self.changed.emit(self._color)

    def _on_hex_edited(self, text: str):
        value = text.strip().upper()
        if re.fullmatch(r"#[0-9A-F]{6}", value):
            self._color = value
            self.swatch.setStyleSheet(
                f"background-color: {self._color}; "
                "border: 1px solid rgba(255,255,255,0.18); border-radius: 8px;"
            )
            self.changed.emit(self._color)

    def color(self) -> str:
        return self._color

    def set_color(self, value: str):
        self._color = (value or "#FFFFFF").upper()
        self._refresh()


def _field_box(title: str, control: QWidget, hint: str = "") -> QWidget:
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    head = QHBoxLayout()
    head.setContentsMargins(0, 0, 0, 0)
    head.addWidget(label(title, "FieldLabel"))
    head.addStretch(1)
    if hint:
        head.addWidget(label(hint, "FieldHint"))
    layout.addLayout(head)
    layout.addWidget(control)
    return holder


class SettingsDialog(QDialog):
    def __init__(self, options: ProcessingOptions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuracoes")
        self.resize(820, 690)
        self.setMinimumSize(680, 560)
        self.options = options

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- cabecalho (.settings-head)
        head = QFrame()
        head.setObjectName("SettingsHead")
        head_layout = QVBoxLayout(head)
        head_layout.setContentsMargins(26, 22, 26, 18)
        head_layout.setSpacing(6)
        head_layout.addWidget(eyebrow("Configuracoes"))
        head_layout.addWidget(label("Ajustes do processamento", "PanelTitle"))
        sub = QLabel(
            'Os mesmos parametros do <span style="color:#c9ff4f; font-family:Consolas;">ProcessingOptions</span> usados pelo pipeline.'
        )
        sub.setObjectName("Faint")
        sub.setTextFormat(Qt.RichText)
        head_layout.addWidget(sub)
        root.addWidget(head)

        # --- abas sublinhadas (.settings-tabs)
        self.tabs = UnderlineTabs(["Video", "Legenda"])
        root.addWidget(self.tabs)

        # --- corpo rolavel (.settings-scroll)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._wrap_scroll(self._build_video_tab()))
        self.stack.addWidget(self._wrap_scroll(self._build_caption_tab()))
        self.tabs.changed.connect(self.stack.setCurrentIndex)
        root.addWidget(self.stack, 1)

        # --- rodape (.settings-foot)
        foot = QFrame()
        foot.setObjectName("Footer")
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(26, 14, 26, 14)

        restore_btn = QPushButton("Restaurar padroes")
        restore_btn.setObjectName("Ghost")
        restore_btn.setCursor(Qt.PointingHandCursor)
        restore_btn.clicked.connect(self._restore_defaults)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Salvar configuracoes")
        save_btn.setObjectName("Primary")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self.accept)

        foot_layout.addWidget(restore_btn)
        foot_layout.addStretch(1)
        foot_layout.addWidget(cancel_btn)
        foot_layout.addWidget(save_btn)
        root.addWidget(foot)

        self._load(options)
        self._connect_live_preview()
        self._refresh_preview()

    @staticmethod
    def _wrap_scroll(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content)
        return scroll

    # --- abas ---------------------------------------------------------
    def _build_video_tab(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("Root")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)

        layout.addWidget(label("ENQUADRAMENTO VERTICAL", "SectionTitle"))

        grid1 = QGridLayout()
        grid1.setHorizontalSpacing(14)
        grid1.setVerticalSpacing(14)

        self.zoom = QDoubleSpinBox()
        self.zoom.setRange(1.0, 3.0)
        self.zoom.setSingleStep(0.05)
        self.zoom.setDecimals(2)
        grid1.addWidget(_field_box("Zoom do video", self.zoom, "1.0 – 3.0"), 0, 0)

        self.blur = QDoubleSpinBox()
        self.blur.setRange(0.0, 50.0)
        self.blur.setSingleStep(0.5)
        self.blur.setDecimals(1)
        grid1.addWidget(_field_box("Desfoque do fundo", self.blur, "0 – 50"), 0, 1)

        self.bg_brightness = QDoubleSpinBox()
        self.bg_brightness.setRange(-0.5, 0.5)
        self.bg_brightness.setSingleStep(0.02)
        self.bg_brightness.setDecimals(2)
        grid1.addWidget(
            _field_box("Brilho do fundo", self.bg_brightness, "-0.5 – 0.5"), 0, 2
        )

        self.resolution = QComboBox()
        for res_label, width, height in RESOLUTIONS:
            self.resolution.addItem(res_label, (width, height))
        grid1.addWidget(_field_box("Resolucao", self.resolution), 1, 0)

        layout.addLayout(grid1)
        layout.addWidget(separator())
        layout.addWidget(label("CODIFICACAO", "SectionTitle"))

        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(14)
        grid2.setVerticalSpacing(14)

        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        grid2.addWidget(_field_box("Qualidade / CRF", self.crf, "0 – 51"), 0, 0)

        self.preset = QComboBox()
        self.preset.addItems(
            ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"]
        )
        grid2.addWidget(_field_box("Preset (CPU)", self.preset), 0, 1)

        self.encoder = QComboBox()
        self.encoder.addItems(
            ["auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf"]
        )
        grid2.addWidget(_field_box("Encoder", self.encoder), 0, 2)

        layout.addLayout(grid2)

        note = label(
            "O modo auto tenta o encoder de hardware e cai para libx264 quando necessario. "
            "CRF menor = mais qualidade e arquivos maiores.",
            "Note",
            wrap=True,
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return pane

    def _build_caption_tab(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("Root")
        outer = QHBoxLayout(pane)
        outer.setContentsMargins(26, 22, 26, 22)
        outer.setSpacing(24)

        # --- coluna de campos
        left = QVBoxLayout()
        left.setSpacing(14)
        left.addWidget(label("PRESET E TIPOGRAFIA", "SectionTitle"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(13)

        self.caption_preset = QComboBox()
        self.caption_preset.addItems(list(PRESETS.keys()))
        apply_preset = QPushButton("Aplicar")
        apply_preset.setObjectName("Ghost")
        apply_preset.setCursor(Qt.PointingHandCursor)
        apply_preset.clicked.connect(self._apply_preset)
        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 0, 0, 0)
        preset_row.setSpacing(6)
        preset_row.addWidget(self.caption_preset, 1)
        preset_row.addWidget(apply_preset)
        grid.addWidget(
            _field_box("Preset de cores", self._wrap(preset_row)), 0, 0, 1, 2
        )

        self.caption_font = QComboBox()
        self.caption_font.setEditable(False)
        self.caption_font.setMaxVisibleItems(16)
        self._populate_font_combo()
        grid.addWidget(_field_box("Fonte", self.caption_font), 1, 0)

        self.caption_font_size = QSpinBox()
        self.caption_font_size.setRange(24, 180)
        grid.addWidget(
            _field_box("Tamanho", self.caption_font_size, "24 – 180"), 1, 1
        )

        self.caption_text_color = ColorButton()
        grid.addWidget(_field_box("Cor do texto", self.caption_text_color), 2, 0)

        self.caption_highlight_color = ColorButton()
        grid.addWidget(
            _field_box("Cor do destaque", self.caption_highlight_color), 2, 1
        )

        self.caption_highlight_opacity = QDoubleSpinBox()
        self.caption_highlight_opacity.setRange(0.0, 1.0)
        self.caption_highlight_opacity.setSingleStep(0.05)
        self.caption_highlight_opacity.setDecimals(2)
        grid.addWidget(
            _field_box(
                "Opacidade do bloco", self.caption_highlight_opacity, "0 – 1"
            ),
            3,
            0,
        )

        self.caption_box_padding = QSpinBox()
        self.caption_box_padding.setRange(0, 60)
        grid.addWidget(
            _field_box("Padding do bloco", self.caption_box_padding), 3, 1
        )

        self.caption_corner_radius = QSpinBox()
        self.caption_corner_radius.setRange(0, 80)
        grid.addWidget(
            _field_box("Cantos arredondados", self.caption_corner_radius), 4, 0
        )

        self.caption_word_spacing = QDoubleSpinBox()
        self.caption_word_spacing.setRange(0.5, 1.5)
        self.caption_word_spacing.setSingleStep(0.05)
        self.caption_word_spacing.setDecimals(2)
        grid.addWidget(
            _field_box(
                "Espaco entre palavras", self.caption_word_spacing, "0.5 – 1.5"
            ),
            4,
            1,
        )

        self.caption_outline_color = ColorButton()
        grid.addWidget(
            _field_box("Cor do contorno", self.caption_outline_color), 5, 0
        )

        self.caption_outline_width = QSpinBox()
        self.caption_outline_width.setRange(0, 20)
        grid.addWidget(
            _field_box("Contorno", self.caption_outline_width, "0 – 20"), 5, 1
        )

        self.caption_max_words_per_line = QSpinBox()
        self.caption_max_words_per_line.setRange(1, 8)
        grid.addWidget(
            _field_box("Palavras por linha", self.caption_max_words_per_line), 6, 0
        )

        self.caption_max_lines = QSpinBox()
        self.caption_max_lines.setRange(1, 3)
        grid.addWidget(_field_box("Linhas", self.caption_max_lines), 6, 1)

        self.caption_margin_bottom = QSpinBox()
        self.caption_margin_bottom.setRange(0, 1200)
        self.caption_margin_bottom.setSingleStep(10)
        grid.addWidget(
            _field_box("Margem do rodape", self.caption_margin_bottom, "px"), 7, 0
        )

        self.caption_transcribe_mode = QComboBox()
        self.caption_transcribe_mode.addItem("Por clipe · mais preciso", "clip")
        self.caption_transcribe_mode.addItem("Completa · mais rapido", "full")
        grid.addWidget(
            _field_box("Transcricao", self.caption_transcribe_mode), 7, 1
        )

        left.addLayout(grid)
        left.addWidget(separator())

        toggles = QHBoxLayout()
        toggles.setSpacing(22)
        self.captions_enabled_toggle = Switch("Gerar legendas dinamicas")
        self.caption_uppercase = Switch("Texto em maiusculas")
        toggles.addWidget(self.captions_enabled_toggle)
        toggles.addWidget(self.caption_uppercase)
        toggles.addStretch(1)
        left.addLayout(toggles)

        left.addWidget(
            label(
                "Margens altas colocam a legenda na faixa desfocada do rodape. "
                "O modo “por clipe” retranscreve cada corte e exige mais processamento.",
                "Note",
                wrap=True,
            )
        )
        left.addStretch(1)
        outer.addLayout(left, 1)

        # --- coluna lateral de previa (.settings-preview)
        preview_box = QFrame()
        preview_box.setObjectName("SettingsPreviewBox")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(13, 13, 13, 13)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(label("PREVIA", "SectionTitle"))
        self.preview_widget = PhonePreviewWidget(phone_width=148, in_settings=True)
        preview_layout.addWidget(self.preview_widget, 0, Qt.AlignHCenter)
        outer.addWidget(preview_box, 0, Qt.AlignTop)

        return pane

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    def _populate_font_combo(self):
        """Preenche o seletor com fontes pré-configuradas e todas as fontes do computador."""
        qt_families = [
            f.strip()
            for f in QFontDatabase.families()
            if f and not f.startswith("@")
        ]
        discovered = list_available_fonts()
        seen: set[str] = set()
        preconfigured: list[str] = []
        system_fonts: list[str] = []

        qt_lookup = {f.lower(): f for f in qt_families}
        disc_lookup = {f.lower(): f for f in discovered}

        for name in PRECONFIGURED_FONTS:
            key = name.lower()
            if key in qt_lookup or key in disc_lookup:
                seen.add(key)
                preconfigured.append(name)

        merged_system = sorted(
            set(qt_families) | set(discovered), key=str.casefold
        )
        for name in merged_system:
            key = name.lower()
            if key and key not in seen:
                seen.add(key)
                system_fonts.append(name)

        self.caption_font.clear()
        for name in preconfigured or list(PRECONFIGURED_FONTS):
            self.caption_font.addItem(name, name)
        if system_fonts:
            self.caption_font.insertSeparator(self.caption_font.count())
            for name in system_fonts:
                self.caption_font.addItem(name, name)

    # --- carga / gravacao / previa ao vivo ----------------------------
    def _connect_live_preview(self):
        for spin in (
            self.zoom,
            self.blur,
            self.bg_brightness,
            self.crf,
            self.caption_font_size,
            self.caption_highlight_opacity,
            self.caption_box_padding,
            self.caption_corner_radius,
            self.caption_word_spacing,
            self.caption_outline_width,
            self.caption_max_words_per_line,
            self.caption_max_lines,
            self.caption_margin_bottom,
        ):
            spin.valueChanged.connect(self._refresh_preview)
        for combo in (
            self.resolution,
            self.preset,
            self.encoder,
            self.caption_font,
            self.caption_transcribe_mode,
        ):
            combo.currentIndexChanged.connect(self._refresh_preview)
            if combo.isEditable():
                combo.editTextChanged.connect(self._refresh_preview)
        for color_btn in (
            self.caption_text_color,
            self.caption_highlight_color,
            self.caption_outline_color,
        ):
            color_btn.changed.connect(self._refresh_preview)
        self.captions_enabled_toggle.toggled.connect(self._refresh_preview)
        self.caption_uppercase.toggled.connect(self._refresh_preview)

    def _draft_options(self) -> ProcessingOptions:
        draft = ProcessingOptions.from_dict(self.options.to_dict())
        self._write_into(draft)
        return draft

    def _refresh_preview(self, *_args):
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_options(self._draft_options())

    def _restore_defaults(self):
        self._load(ProcessingOptions())
        self._refresh_preview()

    def _load(self, options: ProcessingOptions):
        self.zoom.setValue(options.zoom)
        self.blur.setValue(options.blur_sigma)
        self.bg_brightness.setValue(options.bg_brightness)
        self.crf.setValue(options.crf)
        self.preset.setCurrentText(options.preset)
        self.encoder.setCurrentText(options.encoder or "auto")
        for index in range(self.resolution.count()):
            width, height = self.resolution.itemData(index)
            if (width, height) == (options.width, options.height):
                self.resolution.setCurrentIndex(index)
                break

        self.captions_enabled_toggle.setChecked(options.captions_enabled)
        font_name = (options.caption_font or "Arial").strip()
        font_idx = self.caption_font.findText(font_name, Qt.MatchFixedString)
        if font_idx < 0:
            self.caption_font.insertItem(0, font_name, font_name)
            font_idx = 0
        self.caption_font.setCurrentIndex(font_idx)
        self.caption_font_size.setValue(options.caption_font_size)
        self.caption_text_color.set_color(options.caption_text_color)
        self.caption_highlight_color.set_color(options.caption_highlight_color)
        self.caption_highlight_opacity.setValue(options.caption_highlight_opacity)
        self.caption_box_padding.setValue(options.caption_box_padding)
        self.caption_corner_radius.setValue(options.caption_corner_radius)
        self.caption_word_spacing.setValue(options.caption_word_spacing)
        self.caption_outline_color.set_color(options.caption_outline_color)
        self.caption_outline_width.setValue(options.caption_outline_width)
        self.caption_max_words_per_line.setValue(options.caption_max_words_per_line)
        self.caption_max_lines.setValue(options.caption_max_lines)
        self.caption_margin_bottom.setValue(options.caption_margin_bottom)
        self.caption_uppercase.setChecked(options.caption_uppercase)

        mode = options.caption_transcribe_mode or "clip"
        for idx in range(self.caption_transcribe_mode.count()):
            if self.caption_transcribe_mode.itemData(idx) == mode:
                self.caption_transcribe_mode.setCurrentIndex(idx)
                break

    def _apply_preset(self):
        name = self.caption_preset.currentText()
        if name not in PRESETS:
            return
        highlight, text = PRESETS[name]
        self.caption_highlight_color.set_color(highlight)
        self.caption_text_color.set_color(text)
        self._refresh_preview()

    def _write_into(self, options: ProcessingOptions):
        options.zoom = self.zoom.value()
        options.blur_sigma = self.blur.value()
        options.bg_brightness = self.bg_brightness.value()
        options.crf = self.crf.value()
        options.preset = self.preset.currentText()
        options.encoder = (
            "" if self.encoder.currentText() == "auto" else self.encoder.currentText()
        )
        res_data = self.resolution.currentData()
        if res_data:
            options.width, options.height = res_data

        options.captions_enabled = self.captions_enabled_toggle.isChecked()
        options.caption_font = (
            self.caption_font.currentData()
            or self.caption_font.currentText().strip()
            or "Arial"
        )
        options.caption_font_size = self.caption_font_size.value()
        options.caption_text_color = self.caption_text_color.color()
        options.caption_highlight_color = self.caption_highlight_color.color()
        options.caption_highlight_opacity = self.caption_highlight_opacity.value()
        options.caption_box_padding = self.caption_box_padding.value()
        options.caption_corner_radius = self.caption_corner_radius.value()
        options.caption_word_spacing = self.caption_word_spacing.value()
        options.caption_outline_color = self.caption_outline_color.color()
        options.caption_outline_width = self.caption_outline_width.value()
        options.caption_max_words_per_line = self.caption_max_words_per_line.value()
        options.caption_max_lines = self.caption_max_lines.value()
        options.caption_margin_bottom = self.caption_margin_bottom.value()
        options.caption_uppercase = self.caption_uppercase.isChecked()
        options.caption_transcribe_mode = (
            self.caption_transcribe_mode.currentData()
            or self.caption_transcribe_mode.currentText()
        )

    def _apply(self):
        self._write_into(self.options)

    def accept(self):
        self._apply()
        super().accept()
