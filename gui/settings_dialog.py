"""Painel e diálogo de configurações (vídeo vertical, legendas e IA), persistido via QSettings.

Suporta execução embarcada na navegação principal (`embedded=True`) e uso
como diálogo autônomo (`SettingsDialog(options)`).
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
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.captions import (
    PRECONFIGURED_FONTS,
    PRESETS,
    VIRAL_PRESETS,
    apply_preset,
    detect_active_preset,
    list_available_fonts,
)
from core.options import ProcessingOptions
from gui import theme
from gui.widgets import (
    CollapsibleBox,
    PhonePreviewWidget,
    PresetGrid,
    Switch,
    UnderlineTabs,
    label,
    separator,
)

RESOLUTIONS = [
    ("1080 × 1920 · Full HD (9:16)", 1080, 1920),
    ("720 × 1280 · HD (9:16)", 720, 1280),
    ("1440 × 2560 · 2K (9:16)", 1440, 2560),
]


class ColorButton(QWidget):
    """Seletor de cor enxuto: amostra clicável + campo hexadecimal."""

    changed = Signal(str)

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = (color or "#FFFFFF").upper()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.swatch = QPushButton()
        self.swatch.setFixedSize(32, 32)
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
            f"border: 1px solid {theme.LINE_STRONG}; border-radius: 5px;"
        )
        if self.hex_edit.text().upper() != self._color:
            self.hex_edit.setText(self._color)

    def _choose(self):
        chosen = QColorDialog.getColor(
            QColor(self._color), self, "Escolher cor"
        )
        if chosen.isValid():
            self.set_color(chosen.name())
            self.changed.emit(self._color)

    def _on_hex_edited(self, text: str):
        value = text.strip().upper()
        if re.fullmatch(r"#[0-9A-F]{6}", value):
            self._color = value
            self.swatch.setStyleSheet(
                f"background-color: {self._color}; "
                f"border: 1px solid {theme.LINE_STRONG}; border-radius: 5px;"
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
    layout.setSpacing(5)

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
    """Configurações completas de Vídeo, Legenda e Cortes/IA."""

    options_changed = Signal(object)

    def __init__(
        self,
        options: ProcessingOptions,
        parent=None,
        embedded: bool = False,
    ):
        super().__init__(parent)
        self.embedded = bool(embedded)
        if self.embedded:
            self.setWindowFlags(Qt.Widget)
        else:
            self.setWindowTitle("Ajustes")
            self.resize(840, 680)
            self.setMinimumSize(680, 540)

        self.options = options
        self._syncing_preset = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Cabeçalho (apenas quando aberto como diálogo isolado)
        if not self.embedded:
            head = QFrame()
            head.setObjectName("SettingsHead")
            head_layout = QVBoxLayout(head)
            head_layout.setContentsMargins(20, 16, 20, 14)
            head_layout.setSpacing(4)
            head_layout.addWidget(
                label("Ajustes do processamento", "PanelTitle")
            )
            sub = QLabel(
                "Parâmetros de vídeo vertical, estilo de legendas e critérios de corte por IA."
            )
            sub.setObjectName("Faint")
            head_layout.addWidget(sub)
            root.addWidget(head)

        # --- Sub-abas (Vídeo | Legenda | Cortes & IA)
        self.tabs = UnderlineTabs(["Vídeo", "Legenda", "Cortes & IA"])
        root.addWidget(self.tabs)

        # --- Corpo rolável
        self.stack = QStackedWidget()
        self.stack.addWidget(self._wrap_scroll(self._build_video_tab()))
        # A aba Legenda tem rolagem propria: a previa 9:16 fica fixa ao lado.
        self.stack.addWidget(self._build_caption_tab())
        self.stack.addWidget(self._wrap_scroll(self._build_cuts_tab()))
        self.tabs.changed.connect(self.stack.setCurrentIndex)
        root.addWidget(self.stack, 1)

        # --- Rodapé
        foot = QFrame()
        foot.setObjectName("Footer")
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(20, 12, 20, 12)

        restore_btn = QPushButton("Restaurar padrões")
        restore_btn.setObjectName("Ghost")
        restore_btn.setCursor(Qt.PointingHandCursor)
        restore_btn.clicked.connect(self._restore_defaults)
        foot_layout.addWidget(restore_btn)
        foot_layout.addStretch(1)

        if self.embedded:
            self.status_hint = label(
                "As alterações são aplicadas e salvas automaticamente.",
                "Faint",
            )
            foot_layout.addWidget(self.status_hint)
        else:
            cancel_btn = QPushButton("Cancelar")
            cancel_btn.setObjectName("Ghost")
            cancel_btn.setCursor(Qt.PointingHandCursor)
            cancel_btn.clicked.connect(self.reject)

            save_btn = QPushButton("Salvar ajustes")
            save_btn.setObjectName("Primary")
            save_btn.setCursor(Qt.PointingHandCursor)
            save_btn.clicked.connect(self.accept)

            foot_layout.addWidget(cancel_btn)
            foot_layout.addWidget(save_btn)

        root.addWidget(foot)

        self._load(options)
        self._connect_live_preview()
        self._refresh_preview()

    def set_active_tab(self, index: int):
        self.tabs.set_current(index)
        self.stack.setCurrentIndex(index)

    def reload_options(self, options: ProcessingOptions):
        self.options = options
        self._load(options)
        self._refresh_preview(emit_change=False)

    @staticmethod
    def _wrap_scroll(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content)
        return scroll

    # --- Abas ---------------------------------------------------------
    def _build_video_tab(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("Root")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        layout.addWidget(label("ENQUADRAMENTO VERTICAL", "SectionTitle"))

        grid1 = QGridLayout()
        grid1.setHorizontalSpacing(14)
        grid1.setVerticalSpacing(12)

        self.zoom = QDoubleSpinBox()
        self.zoom.setRange(1.0, 3.0)
        self.zoom.setSingleStep(0.05)
        self.zoom.setDecimals(2)
        grid1.addWidget(_field_box("Zoom do vídeo", self.zoom, "1.0 – 3.0"), 0, 0)

        self.blur = QDoubleSpinBox()
        self.blur.setRange(0.0, 50.0)
        self.blur.setSingleStep(0.5)
        self.blur.setDecimals(1)
        grid1.addWidget(
            _field_box("Desfoque do fundo", self.blur, "0 – 50"), 0, 1
        )

        self.bg_brightness = QDoubleSpinBox()
        self.bg_brightness.setRange(-0.5, 0.5)
        self.bg_brightness.setSingleStep(0.02)
        self.bg_brightness.setDecimals(2)
        grid1.addWidget(
            _field_box("Brilho do fundo", self.bg_brightness, "-0.5 – 0.5"),
            0,
            2,
        )

        self.resolution = QComboBox()
        for res_label, width, height in RESOLUTIONS:
            self.resolution.addItem(res_label, (width, height))
        grid1.addWidget(_field_box("Resolução de saída", self.resolution), 1, 0)

        layout.addLayout(grid1)
        layout.addWidget(separator())
        layout.addWidget(label("CODIFICAÇÃO DE VÍDEO", "SectionTitle"))

        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(14)
        grid2.setVerticalSpacing(12)

        self.crf = QSpinBox()
        self.crf.setRange(0, 51)
        grid2.addWidget(
            _field_box("Qualidade (CRF)", self.crf, "0 – 51"), 0, 0
        )

        self.preset = QComboBox()
        self.preset.addItems(
            ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"]
        )
        grid2.addWidget(_field_box("Preset de CPU", self.preset), 0, 1)

        self.encoder = QComboBox()
        self.encoder.addItems(
            ["auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf"]
        )
        grid2.addWidget(_field_box("Encoder H.264", self.encoder), 0, 2)

        layout.addLayout(grid2)

        note = label(
            "O modo 'auto' utiliza aceleração por placa de vídeo (NVENC/QSV/AMF) quando disponível "
            "e recorre ao libx264 como fallback. Valores menores de CRF produzem maior qualidade visual.",
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
        outer.setContentsMargins(20, 18, 8, 18)
        outer.setSpacing(20)

        # --- Coluna principal de controles (rolavel)
        left_holder = QWidget()
        left_holder.setObjectName("Root")
        left = QVBoxLayout(left_holder)
        left.setContentsMargins(0, 0, 8, 0)
        left.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)
        self.captions_enabled_toggle = Switch("Gerar legendas dinâmicas")
        top_bar.addWidget(self.captions_enabled_toggle)
        top_bar.addStretch(1)
        self.preset_status_badge = label("Preset: TikTok Studio", "MiniPill")
        top_bar.addWidget(self.preset_status_badge)
        left.addLayout(top_bar)

        left.addWidget(separator())
        left.addWidget(label("ESTILOS PRONTOS (PRESETS)", "SectionTitle"))

        self.preset_grid = PresetGrid(VIRAL_PRESETS, columns=3, parent=pane)
        self.preset_grid.preset_selected.connect(self._on_preset_card_selected)
        left.addWidget(self.preset_grid)

        left.addWidget(separator())

        # --- Seção retrátil: Configurações Avançadas
        self.advanced_box = CollapsibleBox(
            "Configurações Avançadas de Tipografia e Bloco",
            expanded=False,
            parent=pane,
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        self.caption_preset = QComboBox()
        self.caption_preset.addItems(list(PRESETS.keys()))
        self.caption_preset.setVisible(False)

        self.caption_font = QComboBox()
        self.caption_font.setEditable(False)
        self.caption_font.setMaxVisibleItems(16)
        self._populate_font_combo()
        grid.addWidget(_field_box("Fonte", self.caption_font), 0, 0)

        self.caption_font_size = QSpinBox()
        self.caption_font_size.setRange(24, 180)
        grid.addWidget(
            _field_box("Tamanho (px)", self.caption_font_size, "24 – 180"),
            0,
            1,
        )

        self.caption_text_color = ColorButton()
        grid.addWidget(
            _field_box("Cor do texto base", self.caption_text_color), 1, 0
        )

        self.caption_highlight_color = ColorButton()
        grid.addWidget(
            _field_box("Cor da palavra ativa", self.caption_highlight_color),
            1,
            1,
        )

        self.caption_highlight_opacity = QDoubleSpinBox()
        self.caption_highlight_opacity.setRange(0.0, 1.0)
        self.caption_highlight_opacity.setSingleStep(0.05)
        self.caption_highlight_opacity.setDecimals(2)
        grid.addWidget(
            _field_box(
                "Opacidade da caixa", self.caption_highlight_opacity, "0 – 1"
            ),
            2,
            0,
        )

        self.caption_box_padding = QSpinBox()
        self.caption_box_padding.setRange(0, 60)
        grid.addWidget(
            _field_box("Padding da caixa", self.caption_box_padding), 2, 1
        )

        self.caption_corner_radius = QSpinBox()
        self.caption_corner_radius.setRange(0, 80)
        grid.addWidget(
            _field_box("Arredondamento da caixa", self.caption_corner_radius),
            3,
            0,
        )

        self.caption_word_spacing = QDoubleSpinBox()
        self.caption_word_spacing.setRange(0.5, 1.5)
        self.caption_word_spacing.setSingleStep(0.05)
        self.caption_word_spacing.setDecimals(2)
        grid.addWidget(
            _field_box(
                "Espaço entre palavras", self.caption_word_spacing, "0.5 – 1.5"
            ),
            3,
            1,
        )

        self.caption_outline_color = ColorButton()
        grid.addWidget(
            _field_box("Cor do contorno", self.caption_outline_color), 4, 0
        )

        self.caption_outline_width = QSpinBox()
        self.caption_outline_width.setRange(0, 20)
        grid.addWidget(
            _field_box("Espessura do contorno", self.caption_outline_width, "0 – 20"),
            4,
            1,
        )

        self.caption_max_words_per_line = QSpinBox()
        self.caption_max_words_per_line.setRange(1, 8)
        grid.addWidget(
            _field_box("Palavras por linha", self.caption_max_words_per_line),
            5,
            0,
        )

        self.caption_max_lines = QSpinBox()
        self.caption_max_lines.setRange(1, 3)
        grid.addWidget(_field_box("Máximo de linhas", self.caption_max_lines), 5, 1)

        self.caption_margin_bottom = QSpinBox()
        self.caption_margin_bottom.setRange(0, 1200)
        self.caption_margin_bottom.setSingleStep(10)
        grid.addWidget(
            _field_box("Margem inferior", self.caption_margin_bottom, "px"),
            6,
            0,
        )

        self.caption_transcribe_mode = QComboBox()
        self.caption_transcribe_mode.addItem("Por clipe · mais preciso", "clip")
        self.caption_transcribe_mode.addItem("Completa · mais rápido", "full")
        grid.addWidget(
            _field_box("Modo de transcrição", self.caption_transcribe_mode),
            6,
            1,
        )

        self.caption_animation = QComboBox()
        self.caption_animation.addItem("Pop / Padrão", "pop")
        self.caption_animation.addItem("Subir e Aparecer (Rise)", "rise")
        grid.addWidget(
            _field_box("Animação de entrada", self.caption_animation), 7, 0
        )

        self.advanced_box.set_content_layout(grid)

        toggles = QHBoxLayout()
        toggles.setSpacing(20)
        self.caption_uppercase = Switch("Forçar maiúsculas")
        toggles.addWidget(self.caption_uppercase)
        self.caption_glow = Switch("Efeito Glow (halo)")
        toggles.addWidget(self.caption_glow)
        toggles.addStretch(1)
        self.advanced_box.set_content_layout(toggles)

        left.addWidget(self.advanced_box)
        left.addStretch(1)
        left_scroll = self._wrap_scroll(left_holder)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(left_scroll, 1)

        # --- Coluna lateral de prévia 9:16
        preview_box = QFrame()
        preview_box.setObjectName("SettingsPreviewBox")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(label("PRÉVIA 9:16", "SectionTitle"))
        self.preview_widget = PhonePreviewWidget(
            phone_width=156, in_settings=True
        )
        preview_layout.addWidget(self.preview_widget, 0, Qt.AlignHCenter)
        outer.addWidget(preview_box, 0, Qt.AlignTop)

        return pane

    def _build_cuts_tab(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("Root")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        layout.addWidget(label("CRITÉRIOS DE SELEÇÃO E IA", "SectionTitle"))

        grid1 = QGridLayout()
        grid1.setHorizontalSpacing(14)
        grid1.setVerticalSpacing(12)

        self.max_clips = QSpinBox()
        self.max_clips.setRange(1, 50)
        grid1.addWidget(
            _field_box("Máximo de clipes", self.max_clips, "1 – 50"), 0, 0
        )

        self.min_viral_score = QSpinBox()
        self.min_viral_score.setRange(1, 10)
        grid1.addWidget(
            _field_box("Nota mínima viral", self.min_viral_score, "1 – 10"),
            0,
            1,
        )

        self.whisper_model = QComboBox()
        for w_label, w_val in (
            ("large · máxima precisão", "large"),
            ("turbo · rápido e preciso", "turbo"),
            ("medium · equilibrado", "medium"),
            ("small · leve", "small"),
            ("base · muito leve", "base"),
            ("tiny · ultra rápido", "tiny"),
        ):
            self.whisper_model.addItem(w_label, w_val)
        grid1.addWidget(
            _field_box("Modelo Whisper", self.whisper_model), 0, 2
        )

        layout.addLayout(grid1)
        layout.addWidget(separator())
        layout.addWidget(label("DURAÇÃO E RECORTE", "SectionTitle"))

        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(14)
        grid2.setVerticalSpacing(12)

        self.min_clip_duration = QSpinBox()
        self.min_clip_duration.setRange(10, 180)
        self.min_clip_duration.setSingleStep(5)
        self.min_clip_duration.valueChanged.connect(
            self._on_min_duration_changed
        )
        grid2.addWidget(
            _field_box("Duração mínima", self.min_clip_duration, "10 – 180s"),
            0,
            0,
        )

        self.max_clip_duration = QSpinBox()
        self.max_clip_duration.setRange(15, 300)
        self.max_clip_duration.setSingleStep(5)
        self.max_clip_duration.valueChanged.connect(
            self._on_max_duration_changed
        )
        grid2.addWidget(
            _field_box("Duração máxima", self.max_clip_duration, "15 – 300s"),
            0,
            1,
        )

        self.pause_gap = QDoubleSpinBox()
        self.pause_gap.setRange(0.2, 10.0)
        self.pause_gap.setSingleStep(0.1)
        self.pause_gap.setDecimals(1)
        grid2.addWidget(
            _field_box("Pausa natural para corte", self.pause_gap, "0.2 – 10s"),
            0,
            2,
        )

        self.padding_s = QDoubleSpinBox()
        self.padding_s.setRange(0.0, 30.0)
        self.padding_s.setSingleStep(0.5)
        self.padding_s.setDecimals(1)
        grid2.addWidget(
            _field_box("Margem de segurança (padding)", self.padding_s, "0 – 30s"),
            1,
            0,
        )

        self.max_workers = QSpinBox()
        self.max_workers.setRange(1, 8)
        grid2.addWidget(
            _field_box("Workers de renderização", self.max_workers, "1 – 8"),
            1,
            1,
        )

        layout.addLayout(grid2)

        note = label(
            "A IA seleciona trechos independentes que atinjam a nota mínima até o limite configurado. "
            "Os cortes são ajustados automaticamente em pausas naturais da fala.",
            "Note",
            wrap=True,
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return pane

    def _on_min_duration_changed(self, value: int):
        if (
            hasattr(self, "max_clip_duration")
            and value > self.max_clip_duration.value()
        ):
            self.max_clip_duration.setValue(value)

    def _on_max_duration_changed(self, value: int):
        if (
            hasattr(self, "min_clip_duration")
            and value < self.min_clip_duration.value()
        ):
            self.min_clip_duration.setValue(value)

    def _populate_font_combo(self):
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
            self.max_clips,
            self.min_viral_score,
            self.min_clip_duration,
            self.max_clip_duration,
            self.pause_gap,
            self.padding_s,
            self.max_workers,
        ):
            spin.valueChanged.connect(self._refresh_preview)
        for combo in (
            self.resolution,
            self.preset,
            self.encoder,
            self.caption_font,
            self.caption_transcribe_mode,
            self.caption_animation,
            self.whisper_model,
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
        self.caption_glow.toggled.connect(self._refresh_preview)

    def _draft_options(self) -> ProcessingOptions:
        draft = ProcessingOptions.from_dict(self.options.to_dict())
        self._write_into(draft)
        return draft

    def _refresh_preview(self, *_args, emit_change: bool = True):
        if self._syncing_preset:
            return
        draft = self._draft_options()
        if hasattr(self, "preview_widget"):
            self.preview_widget.set_options(draft)
        self._update_preset_status(draft)
        if self.embedded and emit_change:
            self._apply()
            self.options_changed.emit(self.options)

    def _update_preset_status(self, options: ProcessingOptions):
        active_id = detect_active_preset(options)
        if hasattr(self, "preset_grid"):
            self.preset_grid.select_preset(active_id)
        if hasattr(self, "preset_status_badge"):
            if active_id and active_id in VIRAL_PRESETS:
                self.preset_status_badge.setText(
                    f"Preset: {VIRAL_PRESETS[active_id].name}"
                )
            else:
                self.preset_status_badge.setText("Personalizado (Custom)")

    def _on_preset_card_selected(self, preset_id: str):
        draft = self._draft_options()
        apply_preset(draft, preset_id)
        draft.captions_enabled = True
        self._syncing_preset = True
        try:
            self._load_caption_fields(draft)
        finally:
            self._syncing_preset = False
        self._refresh_preview()

    def _restore_defaults(self):
        answer = QMessageBox.question(
            self,
            "Restaurar padrões",
            "Substituir todos os ajustes de vídeo, legenda e IA pelos valores padrão?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._load(ProcessingOptions())
        if getattr(self, "status_hint", None) is not None:
            self.status_hint.setText("Padrões restaurados e salvos.")
        self._refresh_preview()

    def _load_caption_fields(self, options: ProcessingOptions):
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
        self.caption_highlight_opacity.setValue(
            options.caption_highlight_opacity
        )
        self.caption_box_padding.setValue(options.caption_box_padding)
        self.caption_corner_radius.setValue(options.caption_corner_radius)
        self.caption_word_spacing.setValue(options.caption_word_spacing)
        self.caption_outline_color.set_color(options.caption_outline_color)
        self.caption_outline_width.setValue(options.caption_outline_width)
        self.caption_max_words_per_line.setValue(
            options.caption_max_words_per_line
        )
        self.caption_max_lines.setValue(options.caption_max_lines)
        self.caption_margin_bottom.setValue(options.caption_margin_bottom)
        self.caption_uppercase.setChecked(options.caption_uppercase)
        self.caption_glow.setChecked(
            bool(getattr(options, "caption_glow", False))
        )

        mode = options.caption_transcribe_mode or "clip"
        for idx in range(self.caption_transcribe_mode.count()):
            if self.caption_transcribe_mode.itemData(idx) == mode:
                self.caption_transcribe_mode.setCurrentIndex(idx)
                break

        anim = options.caption_animation or "pop"
        if anim == "rise_swing":
            anim = "rise"
        for idx in range(self.caption_animation.count()):
            if self.caption_animation.itemData(idx) == anim:
                self.caption_animation.setCurrentIndex(idx)
                break

    def _load(self, options: ProcessingOptions):
        self._syncing_preset = True
        try:
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

            self._load_caption_fields(options)

            self.max_clips.setValue(options.max_clips)
            self.min_viral_score.setValue(options.min_viral_score)
            self.min_clip_duration.setValue(options.min_clip_duration)
            self.max_clip_duration.setValue(
                max(options.min_clip_duration, options.max_clip_duration)
            )
            self.pause_gap.setValue(options.pause_gap)
            self.padding_s.setValue(options.padding_s)
            self.max_workers.setValue(options.max_workers)

            w_model = (options.whisper_model or "large").strip()
            w_found = False
            for idx in range(self.whisper_model.count()):
                if self.whisper_model.itemData(idx) == w_model:
                    self.whisper_model.setCurrentIndex(idx)
                    w_found = True
                    break
            if not w_found:
                self.whisper_model.insertItem(0, w_model, w_model)
                self.whisper_model.setCurrentIndex(0)
        finally:
            self._syncing_preset = False
        self._update_preset_status(options)

    def _apply_preset(self):
        name = self.caption_preset.currentText()
        self._on_preset_card_selected(name)

    def _write_into(self, options: ProcessingOptions):
        options.zoom = self.zoom.value()
        options.blur_sigma = self.blur.value()
        options.bg_brightness = self.bg_brightness.value()
        options.crf = self.crf.value()
        options.preset = self.preset.currentText()
        options.encoder = (
            ""
            if self.encoder.currentText() == "auto"
            else self.encoder.currentText()
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
        options.caption_highlight_opacity = (
            self.caption_highlight_opacity.value()
        )
        options.caption_box_padding = self.caption_box_padding.value()
        options.caption_corner_radius = self.caption_corner_radius.value()
        options.caption_word_spacing = self.caption_word_spacing.value()
        options.caption_outline_color = self.caption_outline_color.color()
        options.caption_outline_width = self.caption_outline_width.value()
        options.caption_max_words_per_line = (
            self.caption_max_words_per_line.value()
        )
        options.caption_max_lines = self.caption_max_lines.value()
        options.caption_margin_bottom = self.caption_margin_bottom.value()
        options.caption_uppercase = self.caption_uppercase.isChecked()
        options.caption_glow = self.caption_glow.isChecked()
        options.caption_transcribe_mode = (
            self.caption_transcribe_mode.currentData()
            or self.caption_transcribe_mode.currentText()
        )
        options.caption_animation = (
            self.caption_animation.currentData()
            or self.caption_animation.currentText()
            or "pop"
        )
        options.max_clips = self.max_clips.value()
        options.min_viral_score = self.min_viral_score.value()
        options.min_clip_duration = self.min_clip_duration.value()
        options.max_clip_duration = max(
            options.min_clip_duration, self.max_clip_duration.value()
        )
        options.pause_gap = self.pause_gap.value()
        options.padding_s = self.padding_s.value()
        options.max_workers = self.max_workers.value()
        options.whisper_model = (
            self.whisper_model.currentData()
            or self.whisper_model.currentText().strip()
            or "large"
        )

    def _apply(self):
        self._write_into(self.options)

    def accept(self):
        self._apply()
        self.options_changed.emit(self.options)
        super().accept()
