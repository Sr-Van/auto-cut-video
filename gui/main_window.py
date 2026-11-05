from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
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
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.captions.presets import (
    VIRAL_PRESETS,
    apply_preset,
    detect_active_preset,
)
from core.config import BASE_DIR, OUTPUT_DIR
from core.options import ProcessingOptions
from gui.controllers.pipeline_controller import PipelineController
from gui.projects_dialog import (
    ProjectsDialog,
    format_clip_interval,
    open_upload_pages,
    update_published_button_ui,
)
from gui.settings_dialog import RESOLUTIONS, SettingsDialog
from gui.widgets import (
    Panel,
    PhonePreviewWidget,
    PipeStep,
    Segmented,
    Switch,
    label,
    separator,
)
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
        self.resize(1260, 840)
        self.setMinimumSize(980, 660)
        self.video_path = None
        self.worker = None
        self.clip_paths: list[str] = []
        self.report_path: str | None = None
        self._syncing_quick = False

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

        # --- Pilha principal de navegação (Cortar | Projetos | Ajustes)
        self.main_stack = QStackedWidget()
        self.workspace_view = self._build_workspace_view()
        self.projects_view = ProjectsDialog(self, embedded=True)
        self.projects_view.project_deleted.connect(
            self._on_project_deleted_in_dialog
        )
        self.projects_view.clip_published_changed.connect(
            self._on_clip_published_changed_in_dialog
        )

        self.settings_view = SettingsDialog(self.options, self, embedded=True)
        self.settings_view.options_changed.connect(
            self._on_embedded_settings_changed
        )

        self.main_stack.addWidget(self.workspace_view)  # 0
        self.main_stack.addWidget(self.projects_view)   # 1
        self.main_stack.addWidget(self.settings_view)   # 2
        root_layout.addWidget(self.main_stack, 1)

        self.setCentralWidget(root)
        self._refresh_summary()

    # ------------------------------------------------------------------
    # Barra superior com navegação integrada
    # ------------------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        mark = QLabel("▶")
        mark.setObjectName("BrandMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(24, 24)
        layout.addWidget(mark)

        brand = QLabel("AutoCortes")
        brand.setObjectName("Brand")
        layout.addWidget(brand)
        layout.addWidget(label("BR", "BrandTag"))

        layout.addSpacing(18)

        # Navegação integrada por abas (Cortar | Projetos | Ajustes)
        nav_bar = QFrame()
        nav_bar.setObjectName("NavBar")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(3, 3, 3, 3)
        nav_layout.setSpacing(2)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.workspace_button = QPushButton("Cortar")
        self.workspace_button.setObjectName("NavTab")
        self.workspace_button.setCheckable(True)
        self.workspace_button.setChecked(True)
        self.workspace_button.setCursor(Qt.PointingHandCursor)

        self.projects_button = QPushButton("Projetos")
        self.projects_button.setObjectName("NavTab")
        self.projects_button.setCheckable(True)
        self.projects_button.setCursor(Qt.PointingHandCursor)

        self.settings_button = QPushButton("Ajustes")
        self.settings_button.setObjectName("NavTab")
        self.settings_button.setCheckable(True)
        self.settings_button.setCursor(Qt.PointingHandCursor)

        for idx, btn in (
            (0, self.workspace_button),
            (1, self.projects_button),
            (2, self.settings_button),
        ):
            self.nav_group.addButton(btn, idx)
            nav_layout.addWidget(btn)

        self.nav_group.idToggled.connect(self._on_nav_changed)
        layout.addWidget(nav_bar)

        layout.addStretch(1)

        self.header_status_pill = label("Status: Pronto", "StatusPill")
        self.header_status_pill.setProperty("state", "idle")
        layout.addWidget(self.header_status_pill)
        return header

    def _on_nav_changed(self, index: int, checked: bool):
        if not checked:
            return
        if index == 1:
            self.projects_view.refresh_projects()
        elif index == 2:
            self.settings_view.reload_options(self.options)
        self.main_stack.setCurrentIndex(index)

    def _set_header_status(self, text: str, state: str = "idle"):
        self.header_status_pill.setText(f"Status: {text}")
        self.header_status_pill.setProperty("state", state)
        self.header_status_pill.style().unpolish(self.header_status_pill)
        self.header_status_pill.style().polish(self.header_status_pill)

    # ------------------------------------------------------------------
    # Visão 0: Workspace Principal ("Cortar")
    # ------------------------------------------------------------------
    def _build_workspace_view(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        grid = QGridLayout(page)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 19)
        grid.setColumnStretch(1, 31)

        # Coluna Esquerda: Entrada + Ajustes Rápidos/Prévia + Botão Processar
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.addWidget(self._build_source_panel())
        left_col.addWidget(self._build_quick_config_panel(), 1)
        left_col.addLayout(self._build_action_bar())

        # Coluna Direita: Progresso/Etapas + Painel de Cortes/Log
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.addWidget(self._build_progress_panel())
        right_col.addWidget(self._build_output_panel(), 1)

        grid.addLayout(left_col, 0, 0)
        grid.addLayout(right_col, 0, 1)
        return page

    def _build_source_panel(self) -> QWidget:
        panel = Panel("Vídeo de origem e destino", "Entrada", compact=True)

        self.source_tabs = Segmented(["Link", "Arquivo"])
        self.source_tabs.changed.connect(self._on_source_changed)
        panel.add_head_widget(self.source_tabs)

        self.source_stack = QStackedWidget()

        # --- Aba Link
        link_page = QWidget()
        link_layout = QVBoxLayout(link_page)
        link_layout.setContentsMargins(0, 0, 0, 0)
        link_layout.setSpacing(5)
        link_layout.addWidget(label("URL do vídeo (YouTube, etc.)", "FieldLabel"))
        self.video_link = QLineEdit()
        self.video_link.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.video_link.setClearButtonEnabled(True)
        self.video_link.textChanged.connect(self._on_link_edited)
        link_layout.addWidget(self.video_link)
        self.source_stack.addWidget(link_page)

        # --- Aba Arquivo
        file_page = QWidget()
        file_layout = QVBoxLayout(file_page)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(6)

        self.select_button = QPushButton(
            "Selecionar arquivo de vídeo local (MP4, MKV, MOV, AVI)"
        )
        self.select_button.setObjectName("Dropzone")
        self.select_button.setCursor(Qt.PointingHandCursor)
        self.select_button.clicked.connect(self.select_video)
        file_layout.addWidget(self.select_button)

        self.file_selected_card = QFrame()
        self.file_selected_card.setObjectName("FileSelected")
        sel_row = QHBoxLayout(self.file_selected_card)
        sel_row.setContentsMargins(10, 8, 10, 8)
        sel_row.setSpacing(8)

        badge = QLabel("MP4")
        badge.setObjectName("FileSelectedBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(34, 26)
        sel_row.addWidget(badge)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        self.path_label = label(
            "Nenhum video selecionado", "FieldLabel", wrap=True
        )
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

        # --- Foco da análise
        focus_box = QVBoxLayout()
        focus_box.setSpacing(4)
        focus_head = QHBoxLayout()
        focus_head.addWidget(label("Direcionamento da IA (opcional)", "FieldLabel"))
        focus_head.addStretch(1)
        focus_head.addWidget(label("regra extra", "FieldHint"))
        focus_box.addLayout(focus_head)

        self.focus_input = QPlainTextEdit()
        self.focus_input.setPlaceholderText(
            "Ex.: Focar em partes engraçadas · Priorizar polêmicas · Extrair dicas práticas diretas"
        )
        self.focus_input.setPlainText(self.options.focus_instruction)
        self.focus_input.setFixedHeight(52)
        self.focus_input.setTabChangesFocus(True)
        self.focus_input.textChanged.connect(self._on_focus_edited)
        focus_box.addWidget(self.focus_input)
        panel.body.addLayout(focus_box)

        # --- Pasta de saída
        out_box = QVBoxLayout()
        out_box.setSpacing(4)
        out_box.addWidget(label("Pasta de saída", "FieldLabel"))
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        self.output_label = QLineEdit(self.output_dir)
        self.output_label.setObjectName("MonoInput")
        self.output_label.textEdited.connect(self._on_output_edited)
        out_row.addWidget(self.output_label, 1)

        self.output_button = QPushButton("Escolher...")
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
        panel.body.addLayout(out_box)
        return panel

    def _build_quick_config_panel(self) -> QWidget:
        panel = Panel("Legenda, cortes e prévia", "Configuração rápida", compact=True)

        edit = QPushButton("Ajustes avançados →")
        edit.setObjectName("Link")
        edit.setToolTip("Abrir todos os ajustes de vídeo, legenda e IA")
        edit.setCursor(Qt.PointingHandCursor)
        edit.clicked.connect(self.open_settings)
        self.summary_edit_button = edit
        panel.add_head_widget(edit)

        body_row = QHBoxLayout()
        body_row.setSpacing(14)

        # Subcoluna Esquerda: controles rápidos diretos
        controls_col = QVBoxLayout()
        controls_col.setSpacing(10)

        self.captions_checkbox = Switch("Legendas dinâmicas")
        self.captions_checkbox.setChecked(self.options.captions_enabled)
        self.captions_checkbox.toggled.connect(self.on_captions_toggled)
        controls_col.addWidget(self.captions_checkbox)

        # Seletor rápido de Preset de Legenda
        preset_box = QVBoxLayout()
        preset_box.setSpacing(4)
        preset_box.addWidget(label("Estilo da legenda (Preset)", "FieldLabel"))
        self.quick_preset_combo = QComboBox()
        for pid, preset in VIRAL_PRESETS.items():
            self.quick_preset_combo.addItem(f"{preset.name} ({preset.tag})", pid)
        self.quick_preset_combo.addItem("Personalizado (Custom)", "__custom__")
        self.quick_preset_combo.currentIndexChanged.connect(
            self._on_quick_preset_changed
        )
        preset_box.addWidget(self.quick_preset_combo)
        controls_col.addLayout(preset_box)

        # Grade 2x2 de parâmetros rápidos
        qgrid = QGridLayout()
        qgrid.setHorizontalSpacing(8)
        qgrid.setVerticalSpacing(8)

        # Máximo de clipes
        mc_box = QVBoxLayout()
        mc_box.setSpacing(3)
        mc_box.addWidget(label("Máx. cortes", "FieldLabel"))
        self.quick_max_clips = QSpinBox()
        self.quick_max_clips.setRange(1, 50)
        self.quick_max_clips.setValue(self.options.max_clips)
        self.quick_max_clips.valueChanged.connect(self._on_quick_params_changed)
        mc_box.addWidget(self.quick_max_clips)
        qgrid.addLayout(mc_box, 0, 0)

        # Nota mínima
        ms_box = QVBoxLayout()
        ms_box.setSpacing(3)
        ms_box.addWidget(label("Nota mín. (1-10)", "FieldLabel"))
        self.quick_min_score = QSpinBox()
        self.quick_min_score.setRange(1, 10)
        self.quick_min_score.setValue(self.options.min_viral_score)
        self.quick_min_score.valueChanged.connect(self._on_quick_params_changed)
        ms_box.addWidget(self.quick_min_score)
        qgrid.addLayout(ms_box, 0, 1)

        # Modelo Whisper
        wm_box = QVBoxLayout()
        wm_box.setSpacing(3)
        wm_box.addWidget(label("Whisper", "FieldLabel"))
        self.quick_whisper_combo = QComboBox()
        for w_label, w_val in (
            ("large", "large"),
            ("turbo", "turbo"),
            ("medium", "medium"),
            ("small", "small"),
            ("base", "base"),
            ("tiny", "tiny"),
        ):
            self.quick_whisper_combo.addItem(w_label, w_val)
        self.quick_whisper_combo.currentIndexChanged.connect(
            self._on_quick_params_changed
        )
        wm_box.addWidget(self.quick_whisper_combo)
        qgrid.addLayout(wm_box, 1, 0)

        # Resolução
        res_box = QVBoxLayout()
        res_box.setSpacing(3)
        res_box.addWidget(label("Resolução", "FieldLabel"))
        self.quick_res_combo = QComboBox()
        for _res_label, w, h in RESOLUTIONS:
            self.quick_res_combo.addItem(f"{w}×{h}", (w, h))
        self.quick_res_combo.currentIndexChanged.connect(
            self._on_quick_params_changed
        )
        res_box.addWidget(self.quick_res_combo)
        qgrid.addLayout(res_box, 1, 1)

        controls_col.addLayout(qgrid)
        controls_col.addWidget(separator())

        self.config_summary = label("", "FieldHint", wrap=True)
        controls_col.addWidget(self.config_summary)
        controls_col.addStretch(1)

        # Mantém dicionário summary_values atualizado para inspeção e testes
        self.summary_values = {
            k: label("", "SummaryValue")
            for k in (
                "resolution",
                "zoom",
                "blur",
                "crf",
                "encoder",
                "caption",
                "transcribe",
                "cuts",
            )
        }

        body_row.addLayout(controls_col, 1)

        # Subcoluna Direita: Prévia 9:16 ao vivo
        preview_col = QVBoxLayout()
        preview_col.setSpacing(6)
        preview_head = QHBoxLayout()
        preview_head.addWidget(label("PRÉVIA", "SectionTitle"))
        preview_head.addStretch(1)
        self.preview_ratio = label("9:16", "MiniPill")
        preview_head.addWidget(self.preview_ratio)
        preview_col.addLayout(preview_head)

        self.phone_preview = PhonePreviewWidget(phone_width=132)
        preview_col.addWidget(self.phone_preview, 0, Qt.AlignHCenter)

        self.preview_resolution = label("1080 × 1920", "FieldHint")
        self.preview_resolution.setAlignment(Qt.AlignCenter)
        preview_col.addWidget(self.preview_resolution)

        self.preview_caption_state = label("Legendas ativas", "FieldHint")
        self.preview_caption_state.setAlignment(Qt.AlignCenter)
        preview_col.addWidget(self.preview_caption_state)
        preview_col.addStretch(1)

        body_row.addLayout(preview_col, 0)
        panel.body.addLayout(body_row)
        return panel

    def _build_action_bar(self) -> QHBoxLayout:
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)

        self.process_button = QPushButton("▶   Processar vídeo")
        self.process_button.setObjectName("ProcessButton")
        self.process_button.setCursor(Qt.PointingHandCursor)
        self.process_button.clicked.connect(self.process)
        buttons_row.addWidget(self.process_button, 1)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.setVisible(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        buttons_row.addWidget(self.cancel_button)
        return buttons_row

    def _build_progress_panel(self) -> QWidget:
        panel = Panel("Etapas do pipeline", "Progresso", compact=True)

        status = QHBoxLayout()
        status.setContentsMargins(0, 0, 0, 0)
        status.setSpacing(10)
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
        return panel

    def _build_output_panel(self) -> QWidget:
        panel = Panel("", "Saída e Resultados", compact=True)

        # Abas para alternar entre Cortes Gerados e Log de Execução
        self.output_tabs = Segmented(["Cortes gerados", "Log de execução"])
        self.output_tabs.changed.connect(self._on_output_tab_changed)
        panel.add_head_widget(self.output_tabs)

        self.output_stack = QStackedWidget()

        # --- Página 0: Cortes Gerados
        self.results_section = self._build_results_section()
        self.output_stack.addWidget(self.results_section)

        # --- Página 1: Log de Execução
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)

        log_head = QHBoxLayout()
        log_head.addWidget(
            label("Saída detalhada do processamento em tempo real", "Faint")
        )
        log_head.addStretch(1)
        clear_log = QPushButton("Limpar log")
        clear_log.setObjectName("Link")
        clear_log.setCursor(Qt.PointingHandCursor)
        log_head.addWidget(clear_log)
        log_layout.addLayout(log_head)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(LOG_MAX_LINES)
        self.log_view.setPlainText("Aguardando um vídeo para processar.")
        clear_log.clicked.connect(self.log_view.clear)
        log_layout.addWidget(self.log_view, 1)

        self.output_stack.addWidget(log_page)

        # Inicia mostrando o estado vazio dos cortes (ou log quando processar)
        self.output_tabs.set_current(0)
        self.output_stack.setCurrentIndex(0)

        panel.body.addWidget(self.output_stack, 1)
        return panel

    def _build_results_section(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.result_count = label("0 cortes", "MiniPill")
        head.addWidget(self.result_count)

        self.result_path = label(
            "Nenhum corte gerado nesta sessão.", "FieldHint", wrap=True
        )
        head.addWidget(self.result_path, 1)

        self.report_button = QPushButton("Abrir relatório")
        self.report_button.setObjectName("Ghost")
        self.report_button.setCursor(Qt.PointingHandCursor)
        self.report_button.clicked.connect(self._open_report)
        head.addWidget(self.report_button)

        self.open_folder_button = QPushButton("Abrir pasta")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.setCursor(Qt.PointingHandCursor)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        head.addWidget(self.open_folder_button)

        layout.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        self.results_grid_host = QWidget()
        self.results_grid_host.setObjectName("Root")
        self.results_grid = QGridLayout(self.results_grid_host)
        self.results_grid.setContentsMargins(0, 0, 4, 0)
        self.results_grid.setHorizontalSpacing(10)
        self.results_grid.setVerticalSpacing(10)

        empty = label(
            "Os cortes gerados aparecerão aqui assim que o processamento terminar.\n"
            "Para consultar cortes de vídeos anteriores, acesse a aba 'Projetos' no topo.",
            "ResultsEmpty",
            wrap=True,
        )
        empty.setAlignment(Qt.AlignCenter)
        self.results_grid.addWidget(empty, 0, 0)

        scroll.setWidget(self.results_grid_host)
        layout.addWidget(scroll, 1)
        return section

    # ------------------------------------------------------------------
    # Sincronização e ações
    # ------------------------------------------------------------------
    def _on_output_tab_changed(self, index: int):
        self.output_stack.setCurrentIndex(index)

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
            self, "Selecionar vídeo", "", "Vídeos (*.mp4 *.mkv *.mov *.avi)"
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

    def on_captions_toggled(self, checked: bool):
        if self._syncing_quick:
            return
        self.options.captions_enabled = bool(checked)
        self._save_options()
        self._refresh_summary()

    def _on_quick_preset_changed(self, index: int):
        if self._syncing_quick or index < 0:
            return
        preset_id = self.quick_preset_combo.itemData(index)
        if preset_id and preset_id in VIRAL_PRESETS:
            apply_preset(self.options, preset_id)
            self.options.captions_enabled = True
            self._save_options()
            self._refresh_summary()

    def _on_quick_params_changed(self, *_args):
        if self._syncing_quick:
            return
        self.options.max_clips = self.quick_max_clips.value()
        self.options.min_viral_score = self.quick_min_score.value()
        w_val = self.quick_whisper_combo.currentData()
        if w_val:
            self.options.whisper_model = w_val
        res_val = self.quick_res_combo.currentData()
        if res_val:
            self.options.width, self.options.height = res_val
        self._save_options()
        self._refresh_summary()

    def _on_embedded_settings_changed(self, updated_options: ProcessingOptions):
        self.options = updated_options
        self._save_options()
        self._refresh_summary()

    def open_settings(self):
        self.settings_button.setChecked(True)

    def open_projects(self):
        self.projects_button.setChecked(True)

    def _on_project_deleted_in_dialog(self, project_dir: str):
        cur_folder = self._result_folder()
        if (
            cur_folder
            and str(Path(cur_folder).resolve()).lower()
            == str(Path(project_dir).resolve()).lower()
        ):
            self._clear_results_grid()
            self.clip_paths = []
            self.report_path = None
            self.result_count.setText("0 cortes")
            self.result_path.setText("Projeto excluído.")

    def _on_clip_published_changed_in_dialog(
        self, report_path: str, _clip_idx: int, _published: bool
    ):
        if self.report_path and Path(self.report_path).exists():
            if (
                str(Path(self.report_path).resolve()).lower()
                == str(Path(report_path).resolve()).lower()
            ):
                updated_clips = load_report(self.report_path)
                self._render_results(
                    updated_clips, self.clip_paths, self.report_path
                )

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
                f"{preset_name} · {o.caption_font} {o.caption_font_size}px"
                if preset_name
                else f"Custom · {o.caption_font} {o.caption_font_size}px"
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
            if key in self.summary_values:
                self.summary_values[key].setText(value)

        self.config_summary.setText(
            f"Duração: {o.min_clip_duration}–{o.max_clip_duration}s  ·  "
            f"Zoom: {o.zoom:.2f}×  ·  "
            f"Encoder: {o.encoder or 'auto'} (CRF {o.crf})"
        )

        # Sincroniza controles rápidos sem disparar sinais recursivos
        self._syncing_quick = True
        try:
            self.captions_checkbox.setChecked(o.captions_enabled)
            target_pid = active_preset_id if active_preset_id in VIRAL_PRESETS else "__custom__"
            for idx in range(self.quick_preset_combo.count()):
                if self.quick_preset_combo.itemData(idx) == target_pid:
                    self.quick_preset_combo.setCurrentIndex(idx)
                    break

            self.quick_max_clips.setValue(o.max_clips)
            self.quick_min_score.setValue(o.min_viral_score)

            for idx in range(self.quick_whisper_combo.count()):
                if self.quick_whisper_combo.itemData(idx) == o.whisper_model:
                    self.quick_whisper_combo.setCurrentIndex(idx)
                    break

            for idx in range(self.quick_res_combo.count()):
                if self.quick_res_combo.itemData(idx) == (o.width, o.height):
                    self.quick_res_combo.setCurrentIndex(idx)
                    break
        finally:
            self._syncing_quick = False

        # Atualiza prévia 9:16
        self.phone_preview.set_options(o)
        self.preview_resolution.setText(f"{o.width} × {o.height}")
        self.preview_ratio.setText(
            "1:1"
            if o.width == o.height
            else ("16:9" if o.width > o.height else "9:16")
        )
        self.preview_caption_state.setText(
            f"{preset_name or 'Personalizado'}"
            if o.captions_enabled
            else "Sem legenda"
        )

    def _on_progress_updated(self, value: int):
        self.progress_bar.setValue(value)

    def process(self):
        self.set_busy(True)
        self.progress_bar.setValue(0)
        self.log_view.clear()
        self.output_tabs.set_current(1)
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
        if not self.worker:
            self.set_busy(False)

    def cancel_processing(self):
        if self.controller.cancel_pipeline():
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelando...")
            self.stage_label.setText("Cancelando...")
            self._set_header_status("Cancelando...", "busy")
            self.log_view.appendPlainText(
                "Solicitando cancelamento do pipeline..."
            )

    def set_busy(self, busy: bool):
        self.select_button.setEnabled(not busy)
        self.clear_file_button.setEnabled(not busy)
        self.process_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setText("Cancelar")
        self.output_button.setEnabled(not busy)
        self.reset_output_button.setEnabled(not busy)
        self.output_label.setEnabled(not busy)
        self.projects_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.summary_edit_button.setEnabled(not busy)
        self.captions_checkbox.setEnabled(not busy)
        self.quick_preset_combo.setEnabled(not busy)
        self.quick_max_clips.setEnabled(not busy)
        self.quick_min_score.setEnabled(not busy)
        self.quick_whisper_combo.setEnabled(not busy)
        self.quick_res_combo.setEnabled(not busy)
        self.video_link.setEnabled(not busy)
        self.focus_input.setReadOnly(busy)
        self.source_tabs.setEnabled(not busy)
        self.process_button.setText(
            "Processando..." if busy else "▶   Processar vídeo"
        )
        if busy:
            self._set_header_status("Processando...", "busy")

    def on_stage(self, stage: str):
        stage_text = STAGE_LABELS.get(stage, stage)
        self.stage_label.setText(stage_text)
        if stage == "concluido":
            self._set_header_status("Concluído", "done")
            for step in self.pipe_steps:
                step.set_state("done")
            return
        self._set_header_status(stage_text, "busy")
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

    def on_log(self, line: str):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def on_finished(self, result: dict):
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
            justification = clip.get("justification") or clip.get(
                "analysis", ""
            )
            self.log_view.appendPlainText(f"  Justificativa: {justification}")
        self.log_view.appendPlainText(
            f"\nClipes salvos: {len(self.clip_paths)}"
        )

        self.progress_bar.setValue(100)
        for step in self.pipe_steps:
            step.set_state("done")
        self.stage_label.setText("Concluído")
        self._set_header_status("Concluído", "done")
        self._render_results(clips, self.clip_paths, self.report_path)
        self.output_tabs.set_current(0)

    def on_cancelled(self, message: str):
        self.set_busy(False)
        self.stage_label.setText("Cancelado")
        self._set_header_status("Cancelado", "idle")
        for step in self.pipe_steps:
            if step.property("state") == "active":
                step.set_state("idle")
        self.log_view.appendPlainText(f"[CANCELADO] {message}")

    def on_failed(self, error: str):
        self.set_busy(False)
        self.stage_label.setText("Erro")
        self._set_header_status("Erro", "error")
        for step in self.pipe_steps:
            if step.property("state") == "active":
                step.set_state("error")
        self.log_view.appendPlainText(f"[ERRO] {error}")
        QMessageBox.critical(self, "Erro", error)

    # ------------------------------------------------------------------
    # Mostragem dos Cortes Gerados
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
        total = len(clips)
        self.result_count.setText(
            f"{total} corte" if total == 1 else f"{total} cortes"
        )
        self.result_path.setText(
            str(report_path or self._result_folder() or "—")
        )

        if not clips:
            empty = label(
                "Nenhum corte atingiu os critérios configurados. Confira o log de execução ou reduza a nota mínima.",
                "ResultsEmpty",
                wrap=True,
            )
            empty.setAlignment(Qt.AlignCenter)
            self.results_grid.addWidget(empty, 0, 0)
            return

        for idx, clip in enumerate(clips):
            path = paths[idx] if idx < len(paths) else str(clip.get("file") or "")
            card = self._build_result_card(clip, path, clip_index=idx)
            self.results_grid.addWidget(card, idx, 0)

        self.results_grid.setRowStretch(len(clips), 1)

    def _build_result_card(
        self, clip: dict, path: str, clip_index: int = 0
    ) -> QWidget:
        card = QFrame()
        card.setObjectName("ResultCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)

        media = QPushButton(f"▶\n#{clip_index + 1}")
        media.setObjectName("ResultMedia")
        media.setFixedSize(68, 116)
        media.setCursor(Qt.PointingHandCursor)
        if path:
            media.setToolTip(f"Assistir {path}")
            media.clicked.connect(
                lambda _=False, p=path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(p))
                )
            )
        else:
            media.setEnabled(False)
        row.addWidget(media, 0, Qt.AlignTop)

        body = QVBoxLayout()
        body.setSpacing(5)

        kicker = QHBoxLayout()
        kicker.setSpacing(6)
        score_val = clip.get("viral_score", "—")
        score_lbl = label(f"Nota {score_val}/10", "ClipScore")
        try:
            if float(score_val) < 8.0:
                score_lbl.setProperty("tier", "mid")
        except (TypeError, ValueError):
            pass
        kicker.addWidget(score_lbl)
        kicker.addWidget(label(str(clip.get("category") or "CORTE"), "ClipCat"))
        kicker.addStretch(1)
        kicker.addWidget(
            label(
                format_clip_interval(
                    clip.get("start", "—"), clip.get("end", "—")
                ),
                "ClipTime",
            )
        )
        body.addLayout(kicker)

        body.addWidget(
            label(
                clip.get("title") or f"Corte #{clip_index + 1}",
                "ClipTitle",
                wrap=True,
            )
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
            open_btn = QPushButton("▶ Assistir MP4")
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

        target_path = path or (
            str(self._result_folder()) if self._result_folder() else ""
        )
        post_btn = QPushButton("Postar")
        post_btn.setObjectName("Ghost")
        post_btn.setCursor(Qt.PointingHandCursor)
        post_btn.setToolTip(
            "Abre YouTube e TikTok Studio no navegador, copia o caminho e abre a pasta do corte para arrastar"
        )
        post_btn.clicked.connect(
            lambda _=False, p=target_path: open_upload_pages(p)
        )
        actions.addWidget(post_btn)

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
