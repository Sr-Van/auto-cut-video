from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.captions.presets import VIRAL_PRESETS, detect_active_preset
from core.config import BASE_DIR, OUTPUT_DIR
from core.options import ProcessingOptions
from gui.controllers.pipeline_controller import PipelineController
from gui.projects_dialog import ProjectsDialog, update_published_button_ui
from gui.settings_dialog import SettingsDialog
from gui.widgets import (
    Panel,
    PhonePreviewWidget,
    PipeStep,
    Segmented,
    Switch,
    eyebrow,
    label,
    separator,
)
from gui.workers import PipelineWorker
from utils.report import load_report, update_clip_published

LOG_MAX_LINES = 500

PIPE_STEPS = [
    ("Entrada", "download / áudio", {"baixando", "audio", "iniciando", "upload"}),
    ("Transcrição", "Whisper", {"transcricao"}),
    ("Análise", "IA", {"analise", "normalizacao"}),
    ("Corte", "9:16 + legendas", {"corte", "clipes"}),
    ("Relatório", "JSON + CSV", {"relatorio"}),
]

STAGE_LABELS = {
    "pronto": "Pronto",
    "iniciando": "Iniciando",
    "baixando": "Baixando vídeo",
    "audio": "Extraindo áudio",
    "transcricao": "Transcrevendo",
    "analise": "Analisando com IA",
    "normalizacao": "Ajustando duração",
    "corte": "Cortando clipes",
    "clipes": "Renderizando clipes",
    "relatorio": "Gerando relatório",
    "concluido": "Concluído",
}

TRANSCRIBE_LABELS = {"clip": "Por clipe", "full": "Completa"}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoCortesBR")
        self.resize(1240, 880)
        self.setMinimumSize(980, 660)
        self.video_path = None
        self.worker = None
        self.clip_paths: list[str] = []
        self.report_path: str | None = None

        self.controller = PipelineController(self)
        self.settings = self.controller.settings
        self.output_dir = self.controller.load_output_dir()
        self.options = self.controller.load_options()
        self.controller.stage_changed.connect(self.on_stage)
        self.controller.progress.connect(self._on_progress_updated)
        self.controller.message.connect(self.on_log)
        self.controller.finished.connect(self.on_finished)
        self.controller.failed.connect(self.on_failed)
        self.controller.cancelled.connect(self.on_cancelled)

        root = QWidget()
        root.setObjectName("Root")
        if QApplication.instance() is not None and not QApplication.instance().property("theme_applied"):
            from gui.theme import apply_theme
            apply_theme(QApplication.instance())
            QApplication.instance().setProperty("theme_applied", True)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self._build_studio())
        root_layout.addWidget(scroll, 1)

        self.setCentralWidget(root)
        self._refresh_summary()

    # ------------------------------------------------------------------
    # Construção da interface (espelha site/index.html)
    # ------------------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 14, 28, 14)
        layout.setSpacing(10)

        mark = QLabel("▶")
        mark.setObjectName("BrandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(28, 28)
        layout.addWidget(mark)

        brand = QLabel('autocortes<span style="color:#c9ff4f">.</span>')
        brand.setObjectName("Brand")
        brand.setTextFormat(Qt.RichText)
        layout.addWidget(brand)
        layout.addWidget(label("BR", "BrandTag"))
        layout.addStretch(1)

        self.projects_button = QPushButton("▣  Projetos")
        self.projects_button.setObjectName("Ghost")
        self.projects_button.setCursor(Qt.PointingHandCursor)
        self.projects_button.clicked.connect(self.open_projects)
        layout.addWidget(self.projects_button)

        self.settings_button = QPushButton("⚙  Configurações")
        self.settings_button.setObjectName("Ghost")
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button)
        return header

    def _build_studio(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 30, 28, 24)
        layout.setSpacing(22)

        # --- page-intro
        intro_row = QHBoxLayout()
        intro_col = QVBoxLayout()
        intro_col.setSpacing(6)
        intro_col.addWidget(eyebrow("Estúdio local"))
        serif = self._serif_family()
        title = QLabel(
            "Do vídeo longo ao corte "
            f'<span style="font-family:\'{serif}\'; font-style:italic; '
            'font-weight:400; color:#c9ff4f;">pronto.</span>'
        )
        title.setObjectName("Title")
        title.setTextFormat(Qt.RichText)
        intro_col.addWidget(title)
        intro_col.addWidget(
            label(
                "Cole um link ou envie um arquivo. As preferências ficam salvas neste computador.",
                "Subtitle",
                wrap=True,
            )
        )
        intro_row.addLayout(intro_col, 1)

        note = QLabel(
            '<span style="color:#c9ff4f;">🔒</span>&nbsp;&nbsp;Configurações salvas localmente'
        )
        note.setObjectName("LocalNote")
        note.setTextFormat(Qt.RichText)
        intro_row.addWidget(note, 0, Qt.AlignBottom)
        layout.addLayout(intro_row)

        # --- workspace-grid (main_column + side_column)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        grid.setColumnStretch(0, 31)
        grid.setColumnStretch(1, 15)

        main_col = QVBoxLayout()
        main_col.setSpacing(16)
        main_col.addWidget(self._build_source_panel())
        main_col.addWidget(self._build_progress_panel(), 1)

        side_col = QVBoxLayout()
        side_col.setSpacing(16)
        side_col.addWidget(self._build_preview_panel())
        side_col.addWidget(self._build_summary_panel())
        side_col.addWidget(self._build_help_panel())
        side_col.addStretch(1)

        grid.addLayout(main_col, 0, 0)
        grid.addLayout(side_col, 0, 1)
        layout.addLayout(grid)

        # --- results-section
        self.results_section = self._build_results_section()
        self.results_section.setVisible(False)
        layout.addWidget(self.results_section)

        # --- studio-footer
        footer = QFrame()
        footer.setObjectName("StudioFooter")
        foot_row = QHBoxLayout(footer)
        foot_row.setContentsMargins(0, 16, 0, 4)
        foot_row.addWidget(label("AutoCortesBR", "Faint"))
        foot_row.addStretch(1)
        foot_row.addWidget(
            label("Pipeline local · as configurações ficam salvas neste app", "Faint")
        )
        layout.addWidget(footer)
        return page

    def _build_source_panel(self) -> QWidget:
        panel = Panel("Entrada", "O que processar", source_accent=True)

        self.source_tabs = Segmented(["Link", "Arquivo"])
        self.source_tabs.changed.connect(self._on_source_changed)
        panel.add_head_widget(self.source_tabs)

        self.source_stack = QStackedWidget()

        # --- aba Link
        link_page = QWidget()
        link_layout = QVBoxLayout(link_page)
        link_layout.setContentsMargins(0, 0, 0, 0)
        link_layout.setSpacing(7)
        link_layout.addWidget(label("Link do vídeo", "FieldLabel"))
        self.video_link = QLineEdit()
        self.video_link.setPlaceholderText("https://...")
        self.video_link.setClearButtonEnabled(True)
        self.video_link.textChanged.connect(self._on_link_edited)
        link_layout.addWidget(self.video_link)
        self.source_stack.addWidget(link_page)

        # --- aba Arquivo (dropzone + file-selected)
        file_page = QWidget()
        file_layout = QVBoxLayout(file_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(8)

        self.select_button = QPushButton(
            "⤓   Arraste um vídeo ou clique para escolher\nMP4, MKV, MOV ou AVI"
        )
        self.select_button.setObjectName("Dropzone")
        self.select_button.setCursor(Qt.PointingHandCursor)
        self.select_button.clicked.connect(self.select_video)
        file_layout.addWidget(self.select_button)

        self.file_selected_card = QFrame()
        self.file_selected_card.setObjectName("FileSelected")
        sel_row = QHBoxLayout(self.file_selected_card)
        sel_row.setContentsMargins(12, 10, 12, 10)
        sel_row.setSpacing(10)

        badge = QLabel("▣")
        badge.setObjectName("FileSelectedBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(32, 32)
        sel_row.addWidget(badge)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self.path_label = label("Nenhum video selecionado", "FieldLabel", wrap=True)
        self.file_size_label = label("—", "Faint")
        info_col.addWidget(self.path_label)
        info_col.addWidget(self.file_size_label)
        sel_row.addLayout(info_col, 1)

        change_btn = QPushButton("Trocar")
        change_btn.setObjectName("Ghost")
        change_btn.setCursor(Qt.PointingHandCursor)
        change_btn.clicked.connect(self.select_video)
        sel_row.addWidget(change_btn)

        self.clear_file_button = QPushButton("✕")
        self.clear_file_button.setObjectName("IconBtn")
        self.clear_file_button.setCursor(Qt.PointingHandCursor)
        self.clear_file_button.setToolTip("Remover arquivo")
        self.clear_file_button.clicked.connect(self.clear_video)
        sel_row.addWidget(self.clear_file_button)

        self.file_selected_card.setVisible(False)
        file_layout.addWidget(self.file_selected_card)
        self.source_stack.addWidget(file_page)

        panel.body.addWidget(self.source_stack)

        # --- regra extra (foco da analise)
        focus_box = QVBoxLayout()
        focus_box.setSpacing(6)
        focus_box.addWidget(label("Foco da análise (opcional)", "FieldLabel"))
        self.focus_input = QPlainTextEdit()
        self.focus_input.setPlaceholderText(
            "Ex.: Quero focar nas partes engraçadas · Quero polêmica e discussão · "
            "O tema é educação financeira, foque em mensagens diretas e instrutivas"
        )
        self.focus_input.setPlainText(self.options.focus_instruction)
        self.focus_input.setFixedHeight(64)
        self.focus_input.setTabChangesFocus(True)
        self.focus_input.textChanged.connect(self._on_focus_edited)
        focus_box.addWidget(self.focus_input)
        focus_box.addWidget(
            label(
                "Vira uma REGRA EXTRA para a IA: ela prioriza trechos alinhados, "
                "se existirem no vídeo.",
                "Faint",
                wrap=True,
            )
        )
        panel.body.addLayout(focus_box)

        # --- pasta de saída
        out_box = QVBoxLayout()
        out_box.setSpacing(6)
        out_box.addWidget(label("Pasta de saída", "FieldLabel"))
        out_row = QHBoxLayout()
        out_row.setSpacing(7)
        self.output_label = QLineEdit(self.output_dir)
        self.output_label.setObjectName("MonoInput")
        self.output_label.textEdited.connect(self._on_output_edited)
        out_row.addWidget(self.output_label, 1)

        self.output_button = QPushButton("Escolher pasta")
        self.output_button.setObjectName("Ghost")
        self.output_button.setCursor(Qt.PointingHandCursor)
        self.output_button.clicked.connect(self.select_output_dir)
        out_row.addWidget(self.output_button)

        self.reset_output_button = QPushButton("Padrão")
        self.reset_output_button.setObjectName("Ghost")
        self.reset_output_button.setCursor(Qt.PointingHandCursor)
        self.reset_output_button.setToolTip("Usar a pasta padrão do projeto")
        self.reset_output_button.clicked.connect(self.reset_output_dir)
        out_row.addWidget(self.reset_output_button)

        out_box.addLayout(out_row)
        out_box.addWidget(
            label("O pipeline cria uma subpasta com o nome do vídeo.", "Faint")
        )
        panel.body.addLayout(out_box)

        panel.body.addWidget(separator())

        # --- action-row (switch de legendas + resumo compacto)
        action_row = QHBoxLayout()
        self.captions_checkbox = Switch("Legendas dinâmicas")
        self.captions_checkbox.setChecked(self.options.captions_enabled)
        self.captions_checkbox.toggled.connect(self.on_captions_toggled)
        action_row.addWidget(self.captions_checkbox)
        action_row.addStretch(1)
        self.config_summary = label("", "FieldHint")
        action_row.addWidget(self.config_summary)
        panel.body.addLayout(action_row)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)

        self.process_button = QPushButton("▶   Processar vídeo")
        self.process_button.setObjectName("ProcessButton")
        self.process_button.setCursor(Qt.PointingHandCursor)
        self.process_button.clicked.connect(self.process)
        buttons_row.addWidget(self.process_button, 1)

        self.cancel_button = QPushButton("✕   Cancelar")
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        buttons_row.addWidget(self.cancel_button)

        panel.body.addLayout(buttons_row)
        return panel

    def _build_progress_panel(self) -> QWidget:
        panel = Panel("Processamento", "Execução")

        status = QHBoxLayout()
        status.setContentsMargins(0, 0, 0, 0)
        status.setSpacing(12)
        self.stage_label = label("Pronto", "StageLabel")
        self.percent_label = label("0%", "Percent")
        status.addWidget(self.stage_label)
        status.addWidget(self.percent_label)
        status_holder = QWidget()
        status_holder.setLayout(status)
        panel.add_head_widget(status_holder)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.valueChanged.connect(
            lambda value: self.percent_label.setText(f"{value}%")
        )
        panel.body.addWidget(self.progress_bar)

        steps = QHBoxLayout()
        steps.setSpacing(6)
        self.pipe_steps: list[PipeStep] = []
        for title, hint, _stages in PIPE_STEPS:
            step = PipeStep(title, hint)
            steps.addWidget(step, 1)
            self.pipe_steps.append(step)
        panel.body.addLayout(steps)

        log_head = QHBoxLayout()
        log_head.addWidget(label("LOG", "SectionTitle"))
        log_head.addStretch(1)
        clear_log = QPushButton("Limpar")
        clear_log.setObjectName("Link")
        clear_log.setCursor(Qt.PointingHandCursor)
        log_head.addWidget(clear_log)
        panel.body.addLayout(log_head)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(LOG_MAX_LINES)
        self.log_view.setMinimumHeight(175)
        self.log_view.setPlainText("Aguardando um vídeo para processar.")
        clear_log.clicked.connect(self.log_view.clear)
        panel.body.addWidget(self.log_view, 1)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = Panel("Prévia", "Legenda e enquadramento", compact=True)
        self.preview_ratio = label("9:16", "MiniPill")
        panel.add_head_widget(self.preview_ratio)

        self.phone_preview = PhonePreviewWidget(phone_width=196)
        panel.body.addWidget(self.phone_preview, 0, Qt.AlignHCenter)

        foot = QHBoxLayout()
        self.preview_resolution = label("1080 × 1920", "FieldHint")
        self.preview_caption_state = label("Legendas desligadas", "FieldHint")
        foot.addWidget(self.preview_resolution)
        foot.addStretch(1)
        foot.addWidget(self.preview_caption_state)
        panel.body.addLayout(foot)
        return panel

    def _build_summary_panel(self) -> QWidget:
        panel = Panel("Configuração atual", "Ajustes do pipeline", compact=True)
        edit = QPushButton("☰")
        edit.setObjectName("IconBtn")
        edit.setToolTip("Editar configurações")
        edit.setCursor(Qt.PointingHandCursor)
        edit.clicked.connect(self.open_settings)
        self.summary_edit_button = edit
        panel.add_head_widget(edit)

        self.summary_values = {}
        rows = [
            ("resolution", "Resolução"),
            ("zoom", "Zoom"),
            ("blur", "Desfoque"),
            ("crf", "CRF / preset"),
            ("encoder", "Encoder"),
            ("caption", "Legenda"),
            ("transcribe", "Transcrição"),
            ("cuts", "Cortes"),
        ]
        for index, (key, title) in enumerate(rows):
            if index:
                panel.body.addWidget(separator())
            row = QHBoxLayout()
            row.addWidget(label(title, "SummaryKey"))
            row.addStretch(1)
            value = label("", "SummaryValue")
            row.addWidget(value)
            self.summary_values[key] = value
            panel.body.addLayout(row)
        panel.body.setSpacing(8)
        return panel

    def _build_help_panel(self) -> QWidget:
        panel = Panel("Ambiente", "Como processar", compact=True)
        panel.body.addWidget(
            label(
                "Pipeline conectado diretamente ao Python e às chaves configuradas no .env.",
                "Muted",
                wrap=True,
            )
        )
        panel.body.addWidget(separator())

        for title, val in (
            ("Projeto", str(BASE_DIR)),
            ("Saída padrão", str(OUTPUT_DIR)),
        ):
            row = QHBoxLayout()
            row.addWidget(label(title, "SummaryKey"))
            row.addStretch(1)
            v_lbl = label(val, "SummaryValue")
            v_lbl.setToolTip(val)
            row.addWidget(v_lbl)
            panel.body.addLayout(row)
        panel.body.setSpacing(8)
        return panel

    def _build_results_section(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(separator())

        head = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(eyebrow("Resultado"))

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(label("Cortes gerados", "PanelTitle"))
        self.result_count = label("0", "MiniPill")
        title_row.addWidget(self.result_count)
        title_row.addStretch(1)
        left.addLayout(title_row)

        self.result_path = label("—", "FieldHint", wrap=True)
        left.addWidget(self.result_path)
        head.addLayout(left, 1)

        self.report_button = QPushButton("Abrir relatório")
        self.report_button.setObjectName("Ghost")
        self.report_button.setCursor(Qt.PointingHandCursor)
        self.report_button.clicked.connect(self._open_report)
        head.addWidget(self.report_button, 0, Qt.AlignBottom)

        self.open_folder_button = QPushButton("Abrir pasta")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.setCursor(Qt.PointingHandCursor)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        head.addWidget(self.open_folder_button, 0, Qt.AlignBottom)

        layout.addLayout(head)

        self.results_grid_host = QWidget()
        self.results_grid = QGridLayout(self.results_grid_host)
        self.results_grid.setContentsMargins(0, 0, 0, 0)
        self.results_grid.setHorizontalSpacing(14)
        self.results_grid.setVerticalSpacing(14)
        layout.addWidget(self.results_grid_host)
        return section

    @staticmethod
    def _serif_family() -> str:
        app = QApplication.instance()
        return (app.property("serif_family") if app else None) or "Georgia"

    # ------------------------------------------------------------------
    # Ações e sincronização de estado
    # ------------------------------------------------------------------
    def _on_source_changed(self, index: int):
        self.source_stack.setCurrentIndex(index)

    def _on_link_edited(self, text: str):
        if text.strip() and self.source_tabs.current() != 0:
            self.source_tabs.set_current(0)

    def _on_output_edited(self, text: str):
        folder = text.strip()
        if folder:
            self.output_dir = folder
            self.controller.save_output_dir(folder)

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar video", "", "Videos (*.mp4 *.mkv *.mov *.avi)"
        )
        if file_path:
            self._set_selected_video(file_path)

    def _set_selected_video(self, file_path: str):
        self.video_path = file_path
        self.path_label.setText(file_path)
        p = Path(file_path)
        try:
            size_mb = p.stat().st_size / (1024 * 1024)
            self.file_size_label.setText(f"{p.name} · {size_mb:.1f} MB")
        except OSError:
            self.file_size_label.setText(p.name)
        self.select_button.setVisible(False)
        self.file_selected_card.setVisible(True)
        self.source_tabs.set_current(1)

    def clear_video(self):
        self.video_path = None
        self.path_label.setText("Nenhum video selecionado")
        self.file_size_label.setText("—")
        self.file_selected_card.setVisible(False)
        self.select_button.setVisible(True)

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Escolher pasta de destino", self.output_dir
        )
        if folder:
            self.output_dir = folder
            self.output_label.setText(folder)
            self.controller.save_output_dir(folder)

    def reset_output_dir(self):
        self.output_dir = self.controller.reset_output_dir()
        self.output_label.setText(self.output_dir)

    def on_captions_toggled(self, checked):
        self.options.captions_enabled = checked
        self._save_options()
        self._refresh_summary()

    def open_settings(self):
        dialog = SettingsDialog(self.options, self)
        if dialog.exec():
            self.options = dialog.options
            self.captions_checkbox.setChecked(self.options.captions_enabled)
            self._save_options()
            self._refresh_summary()

    def open_projects(self):
        dialog = ProjectsDialog(self)
        dialog.project_deleted.connect(self._on_project_deleted_in_dialog)
        dialog.clip_published_changed.connect(self._on_clip_published_changed_in_dialog)
        dialog.exec()

    def _on_project_deleted_in_dialog(self, project_dir: str):
        cur_folder = self._result_folder()
        if cur_folder and str(Path(cur_folder).resolve()).lower() == str(Path(project_dir).resolve()).lower():
            self._clear_results_grid()
            self.results_section.setVisible(False)
            self.clip_paths = []
            self.report_path = None

    def _on_clip_published_changed_in_dialog(self, report_path: str, _clip_idx: int, _published: bool):
        if self.report_path and Path(self.report_path).exists():
            if str(Path(self.report_path).resolve()).lower() == str(Path(report_path).resolve()).lower():
                updated_clips = load_report(self.report_path)
                self._render_results(updated_clips, self.clip_paths, self.report_path)

    def _on_focus_edited(self):
        self.options.focus_instruction = self.focus_input.toPlainText().strip()
        self._save_options()

    def _save_options(self):
        self.controller.save_options(self.options)

    def _refresh_summary(self):
        o = self.options
        active_preset_id = detect_active_preset(o)
        preset_name = (
            VIRAL_PRESETS[active_preset_id].name
            if active_preset_id in VIRAL_PRESETS
            else None
        )
        caption_summary = (
            (
                f"{preset_name} · {o.caption_font} {o.caption_font_size}"
                if preset_name
                else f"{o.caption_font} {o.caption_font_size} · {o.caption_max_words_per_line} palavras"
            )
            if o.captions_enabled
            else "desligada"
        )
        values = {
            "resolution": f"{o.width} × {o.height}",
            "zoom": f"{o.zoom:.2f}×",
            "blur": f"{o.blur_sigma:.1f}",
            "crf": f"{o.crf} · {o.preset}",
            "encoder": o.encoder or "auto",
            "caption": caption_summary,
            "transcribe": TRANSCRIBE_LABELS.get(
                o.caption_transcribe_mode, o.caption_transcribe_mode
            ),
            "cuts": (
                f"até {o.max_clips} · nota >= {o.min_viral_score} · "
                f"{o.min_clip_duration}–{o.max_clip_duration}s"
            ),
        }
        for key, value in values.items():
            self.summary_values[key].setText(value)
        self.config_summary.setText(
            f"{o.width}×{o.height} · zoom {o.zoom:.2f}× · CRF {o.crf}"
        )

        # Atualiza prévia lateral (.preview-panel)
        self.phone_preview.set_options(o)
        self.preview_resolution.setText(f"{o.width} × {o.height}")
        self.preview_ratio.setText(
            "1:1" if o.width == o.height else ("16:9" if o.width > o.height else "9:16")
        )
        self.preview_caption_state.setText(
            f"Legendas · {'por clipe' if o.caption_transcribe_mode == 'clip' else 'completas'}"
            if o.captions_enabled
            else "Legendas desligadas"
        )

    def _on_progress_updated(self, value: int):
        self.progress_bar.setValue(value)

    def process(self):
        self.set_busy(True)
        self.progress_bar.setValue(0)
        self.log_view.clear()
        self.results_section.setVisible(False)
        for step in self.pipe_steps:
            step.set_state("idle")

        self.options.captions_enabled = self.captions_checkbox.isChecked()
        self.options.focus_instruction = self.focus_input.toPlainText().strip()

        self.worker = self.controller.start_pipeline(
            yt_link=self.video_link.text().strip(),
            video_path=self.video_path,
            output_dir=self.output_dir,
            options=self.options,
        )

    def cancel_processing(self):
        if self.controller.cancel_pipeline():
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelando...")
            self.stage_label.setText("Cancelando...")
            self.log_view.appendPlainText("Solicitando cancelamento do pipeline...")

    def set_busy(self, busy):
        self.select_button.setEnabled(not busy)
        self.clear_file_button.setEnabled(not busy)
        self.process_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setText("✕   Cancelar")
        self.output_button.setEnabled(not busy)
        self.reset_output_button.setEnabled(not busy)
        self.output_label.setEnabled(not busy)
        self.projects_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.summary_edit_button.setEnabled(not busy)
        self.captions_checkbox.setEnabled(not busy)
        self.video_link.setEnabled(not busy)
        self.focus_input.setReadOnly(busy)
        self.source_tabs.setEnabled(not busy)
        self.process_button.setText(
            "Processando..." if busy else "▶   Processar vídeo"
        )

    def on_stage(self, stage):
        self.stage_label.setText(STAGE_LABELS.get(stage, stage))
        if stage == "concluido":
            for step in self.pipe_steps:
                step.set_state("done")
            return
        active = next(
            (i for i, (_, _, stages) in enumerate(PIPE_STEPS) if stage in stages),
            None,
        )
        if active is None:
            return
        for index, step in enumerate(self.pipe_steps):
            if index < active:
                step.set_state("done")
            elif index == active:
                step.set_state("active")
            else:
                step.set_state("idle")

    def on_log(self, line):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def on_finished(self, result):
        self.set_busy(False)
        clips = result.get("clips", [])
        self.clip_paths = result.get("clip_paths", []) or []
        self.report_path = result.get("report_path")

        for clip in clips:
            self.log_view.appendPlainText(
                f"[{clip.get('start')} - {clip.get('end')}] "
                f"{clip.get('category', '')} ({clip.get('viral_score')}) "
                f"{clip.get('title', '')}"
            )
            justification = clip.get("justification") or clip.get("analysis", "")
            self.log_view.appendPlainText(f"  Justificativa: {justification}")
        self.log_view.appendPlainText(f"\nClipes salvos: {len(self.clip_paths)}")

        self.progress_bar.setValue(100)
        for step in self.pipe_steps:
            step.set_state("done")
        self.stage_label.setText("Concluido")
        self._render_results(clips, self.clip_paths, self.report_path)

    def on_cancelled(self, message: str):
        self.set_busy(False)
        self.stage_label.setText("Cancelado")
        for step in self.pipe_steps:
            if step.property("state") == "active":
                step.set_state("idle")
        self.log_view.appendPlainText(f"[CANCELADO] {message}")

    def on_failed(self, error):
        self.set_busy(False)
        self.stage_label.setText("Erro")
        for step in self.pipe_steps:
            if step.property("state") == "active":
                step.set_state("error")
        self.log_view.appendPlainText(f"[ERRO] {error}")
        QMessageBox.critical(self, "Erro", error)

    # ------------------------------------------------------------------
    # Resultados (.results-section / .result-card)
    # ------------------------------------------------------------------
    def _clear_results_grid(self):
        while self.results_grid.count():
            item = self.results_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render_results(self, clips, paths, report_path):
        self._clear_results_grid()
        self.results_section.setVisible(True)
        self.result_count.setText(str(len(clips)))
        self.result_path.setText(str(report_path or self._result_folder() or "—"))

        if not clips:
            empty = label(
                "Nenhum corte passou nos critérios. Confira o log e tente outro vídeo.",
                "ResultsEmpty",
                wrap=True,
            )
            empty.setAlignment(Qt.AlignCenter)
            self.results_grid.addWidget(empty, 0, 0, 1, 2)
            return

        for idx, clip in enumerate(clips):
            path = paths[idx] if idx < len(paths) else ""
            card = self._build_result_card(clip, path, clip_index=idx)
            self.results_grid.addWidget(card, idx // 2, idx % 2)

    def _build_result_card(self, clip: dict, path: str, clip_index: int = 0) -> QWidget:
        card = QFrame()
        card.setObjectName("ResultCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 14, 14, 14)
        row.setSpacing(14)

        media = QPushButton("▶\n9:16")
        media.setObjectName("ResultMedia")
        media.setFixedSize(92, 162)
        media.setCursor(Qt.PointingHandCursor)
        if path:
            media.setToolTip(f"Abrir {path}")
            media.clicked.connect(
                lambda _=False, p=path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(p))
                )
            )
        else:
            media.setEnabled(False)
        row.addWidget(media, 0, Qt.AlignTop)

        body = QVBoxLayout()
        body.setSpacing(6)

        kicker = QHBoxLayout()
        kicker.setSpacing(6)
        kicker.addWidget(label(str(clip.get("category") or "CORTE"), "ClipCat"))
        kicker.addWidget(label(f"{clip.get('viral_score', '—')}/10", "ClipScore"))
        kicker.addStretch(1)
        kicker.addWidget(
            label(
                f"{clip.get('start', '—')} → {clip.get('end', '—')}", "ClipTime"
            )
        )
        body.addLayout(kicker)

        body.addWidget(
            label(clip.get("title") or "Corte sem título", "ClipTitle", wrap=True)
        )

        hook_text = clip.get("hook_text")
        if hook_text:
            body.addWidget(label(f"“{hook_text}”", "ClipHook", wrap=True))

        analysis = clip.get("analysis") or clip.get("justification")
        if analysis:
            body.addWidget(label(str(analysis), "ClipAnalysis", wrap=True))

        body.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        if path:
            open_btn = QPushButton("Abrir MP4")
            open_btn.setObjectName("Ghost")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.clicked.connect(
                lambda _=False, p=path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(p))
                )
            )
            actions.addWidget(open_btn)

            copy_btn = QPushButton("Copiar caminho")
            copy_btn.setObjectName("Ghost")
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.clicked.connect(
                lambda _=False, p=path: QApplication.clipboard().setText(str(p))
            )
            actions.addWidget(copy_btn)

        pub_btn = QPushButton()
        pub_btn.setObjectName("PublishedBtn")
        pub_btn.setCheckable(True)
        pub_btn.setCursor(Qt.PointingHandCursor)
        update_published_button_ui(pub_btn, bool(clip.get("published", False)))
        pub_btn.clicked.connect(
            lambda checked, idx=clip_index, b=pub_btn: self._toggle_result_clip_published(
                idx, checked, b
            )
        )
        actions.addWidget(pub_btn)

        actions.addStretch(1)
        if path:
            fname = label(Path(path).name, "ClipPath")
            fname.setToolTip(str(path))
            actions.addWidget(fname)
        body.addLayout(actions)

        row.addLayout(body, 1)
        return card

    def _toggle_result_clip_published(
        self, clip_index: int, published: bool, button: QPushButton
    ) -> None:
        if self.report_path and Path(self.report_path).exists():
            update_clip_published(self.report_path, clip_index, published)
        update_published_button_ui(button, published)

    def _result_folder(self):
        for path in self.clip_paths:
            if path:
                return Path(path).parent
        if self.report_path:
            return Path(self.report_path).parent
        return Path(self.output_dir) if self.output_dir else None

    def _open_report(self):
        if self.report_path and Path(self.report_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report_path)))
        else:
            self._open_output_folder()

    def _open_output_folder(self):
        folder = self._result_folder()
        if folder and Path(folder).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
