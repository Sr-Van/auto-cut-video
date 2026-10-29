"""Dialog de configuracoes (video vertical + legendas), persistido via QSettings."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.options import ProcessingOptions

RESOLUTIONS = [
    ("1080x1920 (Full HD)", 1080, 1920),
    ("720x1280 (HD)", 720, 1280),
    ("1440x2560 (2K)", 1440, 2560),
]

PRESETS = {
    "TikTok (roxo)": ("#7C3AED", "#FFFFFF"),
    "Neon (ciano)": ("#22D3EE", "#FFFFFF"),
    "Amarelo": ("#FACC15", "#111111"),
}


class ColorButton(QPushButton):
    """Botao que mostra e escolhe uma cor."""

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedWidth(96)
        self.clicked.connect(self._choose)
        self._refresh()

    def _refresh(self):
        self.setText(self._color.upper())
        color = QColor(self._color)
        text = "#000000" if color.lightness() > 140 else "#FFFFFF"
        self.setStyleSheet(
            f"background-color: {self._color}; color: {text}; border: 1px solid #888;"
        )

    def _choose(self):
        chosen = QColorDialog.getColor(QColor(self._color), self, "Escolher cor")
        if chosen.isValid():
            self._color = chosen.name()
            self._refresh()

    def color(self) -> str:
        return self._color

    def set_color(self, value: str):
        self._color = value or "#FFFFFF"
        self._refresh()


class SettingsDialog(QDialog):
    def __init__(self, options: ProcessingOptions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuracoes")
        self.resize(480, 560)
        self.options = options

        tabs = QTabWidget()
        tabs.addTab(self._build_video_tab(), "Video")
        tabs.addTab(self._build_caption_tab(), "Legenda")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        self._load(options)

    # --- abas ---------------------------------------------------------
    def _build_video_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        self.zoom = QDoubleSpinBox()
        self.zoom.setRange(1.0, 3.0)
        self.zoom.setSingleStep(0.05)
        self.zoom.setDecimals(2)
        form.addRow("Zoom do video", self.zoom)

        self.blur = QDoubleSpinBox()
        self.blur.setRange(0.0, 50.0)
        self.blur.setSingleStep(0.5)
        self.blur.setDecimals(1)
        form.addRow("Desfoque do fundo", self.blur)

        self.bg_brightness = QDoubleSpinBox()
        self.bg_brightness.setRange(-0.5, 0.5)
        self.bg_brightness.setSingleStep(0.02)
        self.bg_brightness.setDecimals(2)
        form.addRow("Brilho do fundo", self.bg_brightness)

        self.resolution = QComboBox()
        for label, width, height in RESOLUTIONS:
            self.resolution.addItem(label, (width, height))
        form.addRow("Resolucao", self.resolution)

        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        form.addRow("Qualidade (CRF/CQ)", self.crf)

        self.preset = QComboBox()
        self.preset.addItems(
            ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"]
        )
        form.addRow("Preset (CPU)", self.preset)

        self.encoder = QComboBox()
        self.encoder.addItems(
            ["auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf"]
        )
        form.addRow("Encoder", self.encoder)

        return widget

    def _build_caption_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        self.caption_preset = QComboBox()
        self.caption_preset.addItems(list(PRESETS.keys()))
        form.addRow("Preset", self.caption_preset)

        preset_row = QHBoxLayout()
        apply_preset = QPushButton("Aplicar preset")
        apply_preset.clicked.connect(self._apply_preset)
        preset_row.addWidget(apply_preset)
        preset_row.addStretch(1)
        form.addRow("", self._wrap(preset_row))

        self.caption_font = QComboBox()
        self.caption_font.setEditable(True)
        self.caption_font.addItems(["Arial", "Segoe UI", "Verdana", "DejaVu Sans"])
        form.addRow("Fonte", self.caption_font)

        self.caption_font_size = QSpinBox()
        self.caption_font_size.setRange(24, 180)
        form.addRow("Tamanho da fonte", self.caption_font_size)

        self.caption_text_color = ColorButton()
        form.addRow("Cor do texto", self.caption_text_color)

        self.caption_highlight_color = ColorButton()
        form.addRow("Cor do destaque", self.caption_highlight_color)

        self.caption_highlight_opacity = QDoubleSpinBox()
        self.caption_highlight_opacity.setRange(0.0, 1.0)
        self.caption_highlight_opacity.setSingleStep(0.05)
        self.caption_highlight_opacity.setDecimals(2)
        form.addRow("Opacidade do bloco", self.caption_highlight_opacity)

        self.caption_box_padding = QSpinBox()
        self.caption_box_padding.setRange(0, 60)
        form.addRow("Padding do bloco", self.caption_box_padding)

        self.caption_corner_radius = QSpinBox()
        self.caption_corner_radius.setRange(0, 80)
        form.addRow("Cantos arredondados (px)", self.caption_corner_radius)

        self.caption_word_spacing = QDoubleSpinBox()
        self.caption_word_spacing.setRange(0.5, 1.5)
        self.caption_word_spacing.setSingleStep(0.05)
        self.caption_word_spacing.setDecimals(2)
        form.addRow("Espaco entre palavras", self.caption_word_spacing)

        self.caption_outline_color = ColorButton()
        form.addRow("Cor do contorno", self.caption_outline_color)

        self.caption_outline_width = QSpinBox()
        self.caption_outline_width.setRange(0, 20)
        form.addRow("Contorno do texto", self.caption_outline_width)

        self.caption_max_words_per_line = QSpinBox()
        self.caption_max_words_per_line.setRange(1, 8)
        form.addRow("Palavras por linha", self.caption_max_words_per_line)

        self.caption_max_lines = QSpinBox()
        self.caption_max_lines.setRange(1, 3)
        form.addRow("Linhas", self.caption_max_lines)

        self.caption_margin_bottom = QSpinBox()
        self.caption_margin_bottom.setRange(0, 1200)
        self.caption_margin_bottom.setSingleStep(10)
        form.addRow("Margem do rodape (px)", self.caption_margin_bottom)

        self.caption_uppercase = QCheckBox("Texto em MAIUSCULAS")
        form.addRow("", self.caption_uppercase)

        self.caption_transcribe_mode = QComboBox()
        self.caption_transcribe_mode.addItems(["full", "clip"])
        form.addRow("Modo de transcricao", self.caption_transcribe_mode)

        hint = QLabel(
            "Margens altas colocam a legenda na faixa desfocada do rodape."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        form.addRow("", hint)

        return widget

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    # --- carga/gravacao ----------------------------------------------
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

        self.caption_font.setCurrentText(options.caption_font)
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
        self.caption_transcribe_mode.setCurrentText(
            options.caption_transcribe_mode or "full"
        )

    def _apply_preset(self):
        name = self.caption_preset.currentText()
        if name not in PRESETS:
            return
        highlight, text = PRESETS[name]
        self.caption_highlight_color.set_color(highlight)
        self.caption_text_color.set_color(text)

    def _apply(self):
        options = self.options
        options.zoom = self.zoom.value()
        options.blur_sigma = self.blur.value()
        options.bg_brightness = self.bg_brightness.value()
        options.crf = self.crf.value()
        options.preset = self.preset.currentText()
        options.encoder = "" if self.encoder.currentText() == "auto" else self.encoder.currentText()
        options.width, options.height = self.resolution.currentData()

        options.caption_font = self.caption_font.currentText().strip() or "Arial"
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
        options.caption_transcribe_mode = self.caption_transcribe_mode.currentText()

    def accept(self):
        self._apply()
        super().accept()
