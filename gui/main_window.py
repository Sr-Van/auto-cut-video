import copy
import re
import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
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
from core.layouts import LAYOUTS, get_layout, missing_requirements
from core.options import ProcessingOptions
from gui import theme
from gui.clip_card import ClipCard
from gui.controllers.pipeline_controller import PipelineController
from gui.projects_dialog import ProjectsDialog
from gui.settings_dialog import SettingsDialog
from gui.thumbnails import FrameLoader, poster_pixmap
from gui.widgets import (
    CollapsibleBox,
    CompactPresetCard,
    ElidedLabel,
    FlowGrid,
    FormatOption,
    PhonePreviewWidget,
    Segmented,
    StepRow,
    Switch,
    Toast,
    label,
    separator,
)
from utils.report import load_report, update_clip_published

LOG_MAX_LINES = 500

PAGE_CONFIG, PAGE_RUN, PAGE_RESULTS = 0, 1, 2

# (titulo, dica, etapas do pipeline que pertencem a esta linha)
PIPE_STEPS = [
    ("Preparando o vídeo", "download e extração do áudio", {"baixando", "audio", "iniciando", "upload"}),
    ("Transcrevendo", "transformando a fala em texto", {"transcricao"}),
    ("Analisando com IA", "escolhendo os melhores momentos", {"analise", "normalizacao", "revisao"}),
    ("Renderizando cortes", "vídeo vertical 9:16", {"corte", "clipes"}),
    ("Relatório", "títulos e descrições", {"relatorio"}),
]

STAGE_LABELS = {
    "pronto": "Pronto",
    "iniciando": "Iniciando",
    "upload": "Preparando o vídeo",
    "baixando": "Baixando vídeo",
    "audio": "Extraindo áudio",
    "transcricao": "Transcrevendo",
    "analise": "Analisando com IA",
    "normalizacao": "Ajustando duração",
    "revisao": "Aguardando sua revisão",
    "corte": "Cortando clipes",
    "clipes": "Renderizando cortes",
    "relatorio": "Gerando relatório",
    "concluido": "Concluído",
}

# Escolhas em linguagem simples da tela Cortar -> valores tecnicos.
DURATION_CHOICES = [("Curto", 15, 40), ("Médio", 40, 90), ("Longo", 90, 120)]
RIGOR_CHOICES = [("Mais cortes", 6), ("Equilibrado", 8), ("Só os melhores", 9)]

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
VIDEO_FILTER = "Vídeos (*.mp4 *.mkv *.mov *.avi *.webm *.m4v)"

QUICK_PRESETS_SHOWN = 4
PREVIEW_COL_WIDTH = 220

_ERROR_HINTS = (
    ("api key", "Verifique as chaves de IA em Ajustes → Contas e IA."),
    ("ffmpeg", "Confira se o FFmpeg está instalado e no PATH."),
    ("informe yt_link", "Cole um link ou escolha um arquivo antes de gerar os cortes."),
    ("falha ao baixar", "Não foi possível baixar o vídeo. Confira o link e a conexão."),
    ("quota", "A cota gratuita do provedor de IA acabou. Tente outra chave ou mais tarde."),
    ("429", "O provedor de IA limitou as requisições. Aguarde um pouco e tente de novo."),
    ("cuda", "Falha na GPU ao transcrever. Tente o modelo Whisper 'small' em Ajustes → Avançado."),
    (
        "expecting value",
        "A IA respondeu em um formato inesperado. Tente de novo ou escolha outro "
        "modelo em Ajustes → Contas e IA.",
    ),
    (
        "json",
        "A IA respondeu em um formato inesperado. Tente de novo ou escolha outro "
        "modelo em Ajustes → Contas e IA.",
    ),
)


def friendly_error(error: str) -> str:
    """Orientacao em linguagem simples seguida do detalhe tecnico."""
    text = str(error or "Erro desconhecido.")
    low = text.lower()
    for needle, hint in _ERROR_HINTS:
        if needle in low:
            return f"{hint}\n\nDetalhe técnico:\n{text}"
    return (
        "Algo deu errado durante o processamento. Tente de novo; se repetir, "
        f"veja o log abaixo.\n\nDetalhe técnico:\n{text}"
    )


def link_state(text: str) -> str:
    """'empty', 'ok' ou 'invalid' para o texto do campo de link."""
    t = (text or "").strip()
    if not t:
        return "empty"
    if re.match(r"^https?://[^\s/]+\.[^\s]+", t, re.I):
        return "ok"
    if re.match(r"^(www\.|m\.)?(youtube\.com|youtu\.be)/\S+", t, re.I):
        return "ok"
    return "invalid"


def normalize_link(text: str) -> str:
    t = (text or "").strip()
    if t and not re.match(r"^https?://", t, re.I):
        t = "https://" + t
    return t


def _fmt_secs(secs: float) -> str:
    secs = max(0, int(secs))
    return f"{secs // 60}:{secs % 60:02d}"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoCortesBR")
        self.resize(1280, 840)
        self.setMinimumSize(980, 660)
        self.video_path = None
        self.worker = None
        self.clip_paths: list[str] = []
        self.report_path: str | None = None
        self.last_clips: list[dict] = []
        self._syncing_quick = False
        self._run_started = 0.0
        self._step_started: dict[int, float] = {}
        self._active_step = -1
        self._stage_text = ""

        self.frames = FrameLoader(self)
        self.frames.loaded.connect(self._on_frame_loaded)
        self._thumb_targets: dict[str, list] = {}
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
        self.controller.review_requested.connect(self._on_review_requested)

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
        self.log_box = self._build_log_box()
        self.workspace_view = self._build_workspace_view()
        self.projects_view = ProjectsDialog(self, embedded=True)
        self.projects_view.project_deleted.connect(self._on_project_deleted_in_dialog)
        self.projects_view.clip_published_changed.connect(
            self._on_clip_published_changed_in_dialog
        )

        self.settings_view = SettingsDialog(self.options, self, embedded=True)
        self.settings_view.api_keys_changed.connect(self._refresh_env_status)
        self.settings_view.options_changed.connect(self._on_embedded_settings_changed)

        self.main_stack.addWidget(self.workspace_view)  # 0
        self.main_stack.addWidget(self.projects_view)   # 1
        self.main_stack.addWidget(self.settings_view)   # 2
        root_layout.addWidget(self.main_stack, 1)

        self.setCentralWidget(root)
        self.toast = Toast(root)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)

        self._refresh_summary()
        self.setAcceptDrops(True)
        self._install_shortcuts()
        self._refresh_env_status()
        self._update_process_enabled()
        self._show_page(PAGE_CONFIG)

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
        layout.addSpacing(18)

        nav_bar = QFrame()
        nav_bar.setObjectName("NavBar")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(3, 3, 3, 3)
        nav_layout.setSpacing(2)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.workspace_button = QPushButton("Cortar")
        self.projects_button = QPushButton("Projetos")
        self.settings_button = QPushButton("Ajustes")
        for idx, (btn, key) in enumerate(
            (
                (self.workspace_button, "Ctrl+1"),
                (self.projects_button, "Ctrl+2"),
                (self.settings_button, "Ctrl+3"),
            )
        ):
            btn.setObjectName("NavTab")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(key)
            self.nav_group.addButton(btn, idx)
            nav_layout.addWidget(btn)
        self.workspace_button.setChecked(True)

        self.nav_group.idToggled.connect(self._on_nav_changed)
        layout.addWidget(nav_bar)
        layout.addStretch(1)

        self.header_status_pill = QPushButton("Pronto")
        self.header_status_pill.setObjectName("StatusPill")
        self.header_status_pill.setProperty("state", "idle")
        self.header_status_pill.setCursor(Qt.PointingHandCursor)
        self.header_status_pill.setToolTip("Ir para a tela Cortar")
        self.header_status_pill.clicked.connect(
            lambda: self.workspace_button.setChecked(True)
        )
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
        self.header_status_pill.setText(text)
        self.header_status_pill.setProperty("state", state)
        self.header_status_pill.style().unpolish(self.header_status_pill)
        self.header_status_pill.style().polish(self.header_status_pill)

    # ------------------------------------------------------------------
    # Visão 0: Cortar (configurar -> processando -> resultados)
    # ------------------------------------------------------------------
    def _build_workspace_view(self) -> QWidget:
        self.workspace_stack = QStackedWidget()
        config = QWidget()
        config.setObjectName("Root")
        cl = QVBoxLayout(config)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._centered_scroll(self._build_config_page(), 1120), 1)
        cl.addWidget(self._build_config_footer())
        self.workspace_stack.addWidget(config)
        self.workspace_stack.addWidget(self._centered_scroll(self._build_run_page(), 960))
        self.workspace_stack.addWidget(self._build_results_page())
        return self.workspace_stack

    @staticmethod
    def _centered_scroll(content: QWidget, max_width: int) -> QScrollArea:
        holder = QWidget()
        holder.setObjectName("Root")
        row = QHBoxLayout(holder)
        row.setContentsMargins(24, 18, 24, 24)
        row.setSpacing(0)
        row.addStretch(1)
        content.setMaximumWidth(max_width)
        row.addWidget(content, 100)
        row.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        return scroll

    def _show_page(self, page: int):
        """Troca o estado da tela Cortar; o log acompanha a pagina visivel."""
        slot = {PAGE_RUN: self.run_log_slot, PAGE_RESULTS: self.results_log_slot}.get(page)
        if slot is not None and self.log_box.parentWidget() is not None:
            slot.addWidget(self.log_box)
        self.workspace_stack.setCurrentIndex(page)

    # --- Passos da configuração ---------------------------------------
    def _step(self, number: int, title: str, hint: str = ""):
        frame = QFrame()
        frame.setObjectName("StepSection")
        col = QVBoxLayout(frame)
        col.setContentsMargins(0, 0, 0, 16)
        col.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(10)
        badge = label(str(number), "StepNum")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(24, 24)
        badge.setProperty("state", "idle")
        head.addWidget(badge)
        head.addWidget(label(title, "StepTitleBig"))
        if hint:
            head.addWidget(label(hint, "Faint"))
        head.addStretch(1)
        col.addLayout(head)
        return frame, col, head, badge

    @staticmethod
    def _set_badge(badge: QLabel, number: int, state: str):
        badge.setText("✓" if state == "done" else str(number))
        badge.setProperty("state", state)
        badge.style().unpolish(badge)
        badge.style().polish(badge)

    def _build_config_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(14)
        title_row.addWidget(label("Novo corte", "PageTitle"))
        title_row.addWidget(
            label("Escolha o vídeo e o formato, decida se quer legendas e gere os cortes", "Muted")
        )
        title_row.addStretch(1)
        outer.addLayout(title_row)

        self.config_banner = label("", "InfoBanner", wrap=True)
        self.config_banner.setVisible(False)
        outer.addWidget(self.config_banner)

        grid = QHBoxLayout()
        grid.setSpacing(32)
        steps = QVBoxLayout()
        steps.setSpacing(0)
        steps.addWidget(self._build_source_step())
        steps.addWidget(separator())
        steps.addSpacing(14)
        steps.addWidget(self._build_format_step())
        steps.addWidget(separator())
        steps.addSpacing(14)
        steps.addWidget(self._build_caption_step())
        steps.addWidget(separator())
        steps.addSpacing(14)
        steps.addWidget(self._build_cuts_step())
        steps.addStretch(1)
        grid.addLayout(steps, 1)
        preview_holder = QWidget()
        preview_holder.setFixedWidth(PREVIEW_COL_WIDTH)
        preview_holder.setLayout(self._build_preview_column())
        grid.addWidget(preview_holder, 0, Qt.AlignTop)
        outer.addLayout(grid, 1)
        return page

    def _build_config_footer(self) -> QWidget:
        """Barra fixa com o botao principal: sempre visivel, sem rolar."""
        footer = QFrame()
        footer.setObjectName("ActionFooter")
        row = QHBoxLayout(footer)
        row.setContentsMargins(24, 12, 24, 12)
        row.addStretch(1)
        inner = QWidget()
        inner.setMaximumWidth(1120)
        il = QHBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(32)
        il.addLayout(self._build_action_bar(), 1)
        il.addSpacing(PREVIEW_COL_WIDTH)
        row.addWidget(inner, 100)
        row.addStretch(1)
        return footer

    def _build_source_step(self) -> QWidget:
        frame, col, _head, self.source_badge = self._step(1, "Vídeo", "link ou arquivo · um por vez")

        self.source_drop = QFrame()
        self.source_drop.setObjectName("SourceDrop")
        self.source_drop.setProperty("drag", "false")
        drop = QVBoxLayout(self.source_drop)
        drop.setContentsMargins(14, 14, 14, 12)
        drop.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.video_link = QLineEdit()
        self.video_link.setPlaceholderText(
            "Cole aqui o link do YouTube — ou arraste um arquivo de vídeo para a janela"
        )
        self.video_link.setClearButtonEnabled(True)
        self.video_link.textChanged.connect(self._on_link_edited)
        self.video_link.returnPressed.connect(self._run_process_shortcut)
        row.addWidget(self.video_link, 1)
        self.select_button = QPushButton("Procurar arquivo")
        self.select_button.setObjectName("Ghost")
        self.select_button.setCursor(Qt.PointingHandCursor)
        self.select_button.setToolTip("Ctrl+O")
        self.select_button.clicked.connect(self.select_video)
        row.addWidget(self.select_button)
        drop.addLayout(row)
        self.source_hint = label(
            "Links do YouTube ou arquivos MP4, MKV, MOV, AVI, WEBM, M4V  ·  "
            "Ctrl+O procura um arquivo  ·  Enter gera os cortes",
            "SourceHint",
            wrap=True,
        )
        self.source_hint.setProperty("state", "idle")
        drop.addWidget(self.source_hint)
        col.addWidget(self.source_drop)

        self.file_selected_card = QFrame()
        self.file_selected_card.setObjectName("FileSelected")
        sel_row = QHBoxLayout(self.file_selected_card)
        sel_row.setContentsMargins(12, 10, 12, 10)
        sel_row.setSpacing(12)
        self.file_badge = QLabel("MP4")
        self.file_badge.setObjectName("FileSelectedBadge")
        self.file_badge.setAlignment(Qt.AlignCenter)
        self.file_badge.setFixedSize(42, 34)
        sel_row.addWidget(self.file_badge)
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self.path_label = ElidedLabel("Nenhum vídeo selecionado", "FileName")
        self.file_size_label = ElidedLabel("—", "Faint")
        info_col.addWidget(self.path_label)
        info_col.addWidget(self.file_size_label)
        sel_row.addLayout(info_col, 1)
        self.change_file_button = QPushButton("Trocar")
        self.change_file_button.setObjectName("Ghost")
        self.change_file_button.setCursor(Qt.PointingHandCursor)
        self.change_file_button.clicked.connect(self.select_video)
        sel_row.addWidget(self.change_file_button)
        self.clear_file_button = QPushButton("✕")
        self.clear_file_button.setObjectName("IconBtn")
        self.clear_file_button.setCursor(Qt.PointingHandCursor)
        self.clear_file_button.setToolTip("Remover arquivo e usar um link")
        self.clear_file_button.clicked.connect(self.clear_video)
        sel_row.addWidget(self.clear_file_button)
        self.file_selected_card.setVisible(False)
        col.addWidget(self.file_selected_card)

        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(label("Salvar em", "Faint"))
        self.output_label = ElidedLabel(self.output_dir, "OutputPath")
        out_row.addWidget(self.output_label, 1)
        self.output_button = QPushButton("Alterar…")
        self.output_button.setObjectName("Link")
        self.output_button.setCursor(Qt.PointingHandCursor)
        self.output_button.clicked.connect(self.select_output_dir)
        out_row.addWidget(self.output_button)
        self.reset_output_button = QPushButton("Usar padrão")
        self.reset_output_button.setObjectName("Link")
        self.reset_output_button.setCursor(Qt.PointingHandCursor)
        self.reset_output_button.setToolTip("Usar a pasta padrão do projeto")
        self.reset_output_button.clicked.connect(self.reset_output_dir)
        out_row.addWidget(self.reset_output_button)
        col.addLayout(out_row)
        return frame

    def _build_format_step(self) -> QWidget:
        frame, col, _head, self.format_badge = self._step(
            2, "Formato", "como o vídeo é enquadrado no 9:16"
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.format_cards: dict[str, FormatOption] = {}
        for idx, (lid, lay) in enumerate(LAYOUTS.items()):
            card = FormatOption(lay)
            card.clicked.connect(self._on_format_clicked)
            self.format_cards[lid] = card
            grid.addWidget(card, idx // 3, idx % 3)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        col.addLayout(grid)

        warn_row = QHBoxLayout()
        warn_row.setSpacing(8)
        self.format_warning = label("", "WarnText", wrap=True)
        warn_row.addWidget(self.format_warning, 1)
        self.format_warning_button = QPushButton("Escolher em Ajustes → Formato")
        self.format_warning_button.setObjectName("Link")
        self.format_warning_button.setCursor(Qt.PointingHandCursor)
        self.format_warning_button.clicked.connect(
            lambda: self.open_settings(SettingsDialog.PAGE_FORMAT)
        )
        warn_row.addWidget(self.format_warning_button)
        self.format_warning_holder = QWidget()
        self.format_warning_holder.setLayout(warn_row)
        self.format_warning_holder.setVisible(False)
        col.addWidget(self.format_warning_holder)
        return frame

    def _build_caption_step(self) -> QWidget:
        frame, col, head, self.caption_badge = self._step(3, "Legendas", "opcional")
        self.captions_checkbox = Switch("Usar legendas")
        self.captions_checkbox.setChecked(self.options.captions_enabled)
        self.captions_checkbox.toggled.connect(self.on_captions_toggled)
        head.addWidget(self.captions_checkbox)

        self.caption_body = QWidget()
        body = QVBoxLayout(self.caption_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        self.preset_row = QHBoxLayout()
        self.preset_row.setSpacing(8)
        body.addLayout(self.preset_row)
        self.preset_cards: dict[str, CompactPresetCard] = {}
        self._shown_presets: list[str] = []
        self.more_presets_button = QPushButton(f"Ver todos ({len(VIRAL_PRESETS)}) →")
        self.more_presets_button.setObjectName("MoreCard")
        self.more_presets_button.setCursor(Qt.PointingHandCursor)
        self.more_presets_button.setFixedHeight(76)
        self.more_presets_button.setToolTip("Todos os estilos e ajustes finos de fonte, cor e posição")
        self.more_presets_button.clicked.connect(
            lambda: self.open_settings(SettingsDialog.PAGE_CAPTION)
        )
        self.custom_preset_note = label(
            "Estilo personalizado em uso (ajustado em Ajustes → Legenda).", "Faint"
        )
        body.addWidget(self.custom_preset_note)
        col.addWidget(self.caption_body)

        self.caption_off_note = label(
            "Os cortes saem sem legenda. Ligue “Usar legendas” para escolher um estilo.",
            "Faint",
        )
        col.addWidget(self.caption_off_note)
        self._build_preset_strip(list(VIRAL_PRESETS)[:QUICK_PRESETS_SHOWN])
        return frame

    def _build_preset_strip(self, preset_ids: list[str]):
        while self.preset_row.count():
            item = self.preset_row.takeAt(0)
            w = item.widget()
            if w is not None and w is not self.more_presets_button:
                w.deleteLater()
        self.preset_cards = {}
        for pid in preset_ids:
            card = CompactPresetCard(VIRAL_PRESETS[pid])
            card.clicked.connect(self.select_quick_preset)
            self.preset_cards[pid] = card
            self.preset_row.addWidget(card, 1)
        self.preset_row.addWidget(self.more_presets_button, 1)
        self._shown_presets = list(preset_ids)

    def _build_cuts_step(self) -> QWidget:
        frame, col, head, self.cuts_badge = self._step(4, "Cortes", "quantos e de que tipo")
        self.focus_toggle = QPushButton("+ Instrução para a IA (opcional)")
        self.focus_toggle.setObjectName("DashedButton")
        self.focus_toggle.setCursor(Qt.PointingHandCursor)
        self.focus_toggle.clicked.connect(self._toggle_focus_input)
        head.addWidget(self.focus_toggle)

        row = QHBoxLayout()
        row.setSpacing(18)

        box = QVBoxLayout()
        box.setSpacing(5)
        box.addWidget(label("Quantos cortes", "FieldLabel"))
        self.quick_max_clips = QSpinBox()
        self.quick_max_clips.setRange(1, 50)
        self.quick_max_clips.setMinimumWidth(90)
        self.quick_max_clips.valueChanged.connect(self._on_quick_params_changed)
        box.addWidget(self.quick_max_clips)
        box.addStretch(1)
        row.addLayout(box)

        box = QVBoxLayout()
        box.setSpacing(5)
        box.addWidget(label("Duração", "FieldLabel"))
        self.duration_seg = Segmented([name for name, _lo, _hi in DURATION_CHOICES])
        self.duration_seg.setToolTip(
            "  ·  ".join(f"{name}: {lo}–{hi}s" for name, lo, hi in DURATION_CHOICES)
        )
        self.duration_seg.setObjectName("ChoiceSeg")
        self.duration_seg.changed.connect(self._on_duration_choice)
        box.addWidget(self.duration_seg)
        self.duration_hint = label("", "Faint")
        box.addWidget(self.duration_hint)
        box.addStretch(1)
        row.addLayout(box)

        box = QVBoxLayout()
        box.setSpacing(5)
        box.addWidget(label("Rigor da IA", "FieldLabel"))
        self.rigor_seg = Segmented([name for name, _ in RIGOR_CHOICES])
        self.rigor_seg.setToolTip(
            "Mais cortes = nota mínima 6 · Equilibrado = 8 · Só os melhores = 9"
        )
        self.rigor_seg.setObjectName("ChoiceSeg")
        self.rigor_seg.changed.connect(self._on_rigor_choice)
        box.addWidget(self.rigor_seg)
        self.rigor_hint = label("", "Faint")
        box.addWidget(self.rigor_hint)
        box.addStretch(1)
        row.addLayout(box)
        row.addStretch(1)
        col.addLayout(row)

        self.focus_input = QPlainTextEdit()
        self.focus_input.setPlaceholderText(
            "Ex.: foque em polêmicas entre jogadores e técnicos · priorize dicas práticas"
        )
        self.focus_input.setPlainText(self.options.focus_instruction)
        self.focus_input.setFixedHeight(60)
        self.focus_input.setTabChangesFocus(True)
        self.focus_input.textChanged.connect(self._on_focus_edited)
        self.focus_input.setVisible(False)
        col.addWidget(self.focus_input)
        self._sync_focus_toggle()

        self.review_checkbox = Switch("Revisar cortes antes de renderizar")
        self.review_checkbox.setChecked(self.options.review_before_render)
        self.review_checkbox.setToolTip(
            "Pausa após a análise de IA para aprovar cortes e ajustar início/fim antes de renderizar"
        )
        self.review_checkbox.toggled.connect(self.on_review_toggled)
        col.addWidget(self.review_checkbox)
        return frame

    def _build_action_bar(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        self.process_button = QPushButton("Gerar cortes")
        self.process_button.setObjectName("ProcessButton")
        self.process_button.setCursor(Qt.PointingHandCursor)
        self.process_button.clicked.connect(self.process)
        col.addWidget(self.process_button)

        sum_row = QHBoxLayout()
        sum_row.setSpacing(6)
        self.config_summary = label("", "Faint")
        sum_row.addWidget(self.config_summary)
        self.summary_edit_button = QPushButton("alterar em Ajustes")
        self.summary_edit_button.setObjectName("LinkUnderline")
        self.summary_edit_button.setCursor(Qt.PointingHandCursor)
        self.summary_edit_button.clicked.connect(
            lambda: self.open_settings(SettingsDialog.PAGE_ADVANCED)
        )
        sum_row.addWidget(self.summary_edit_button)
        sum_row.addStretch(1)
        col.addLayout(sum_row)

        self.env_status_label = label("", "FieldHint", wrap=True)
        self.env_status_label.setTextFormat(Qt.RichText)
        col.addWidget(self.env_status_label)
        return col

    def _build_preview_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(label("Prévia", "StepTitleBig"))
        head.addStretch(1)
        self.preview_ratio = label("9:16", "MiniPill")
        head.addWidget(self.preview_ratio)
        col.addLayout(head)
        self.phone_preview = PhonePreviewWidget(phone_width=180)
        col.addWidget(self.phone_preview, 0, Qt.AlignHCenter)
        self.preview_caption_state = label("", "Muted", wrap=True)
        self.preview_caption_state.setAlignment(Qt.AlignCenter)
        col.addWidget(self.preview_caption_state)
        self.preview_resolution = label("1080 × 1920", "Faint")
        self.preview_resolution.setAlignment(Qt.AlignCenter)
        col.addWidget(self.preview_resolution)
        col.addStretch(1)
        holder = QVBoxLayout()
        holder.addLayout(col)
        return holder

    # --- Página de processamento ---------------------------------------
    def _build_run_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)

        src = QVBoxLayout()
        src.setSpacing(2)
        self.run_source_title = ElidedLabel("", "FileName")
        self.run_source_meta = label("", "Faint")
        src.addWidget(self.run_source_title)
        src.addWidget(self.run_source_meta)
        col.addLayout(src)

        prog = QFrame()
        prog.setObjectName("Panel")
        pl = QVBoxLayout(prog)
        pl.setContentsMargins(20, 16, 20, 16)
        pl.setSpacing(10)
        top = QHBoxLayout()
        self.percent_label = label("0%", "BigPercent")
        top.addWidget(self.percent_label)
        top.addStretch(1)
        self.eta_label = label("calculando tempo…", "EtaLabel")
        top.addWidget(self.eta_label)
        pl.addLayout(top)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.valueChanged.connect(
            lambda value: self.percent_label.setText(f"{value}%")
        )
        pl.addWidget(self.progress_bar)
        bottom = QHBoxLayout()
        self.stage_label = label("Pronto", "StageLabel")
        bottom.addWidget(self.stage_label)
        bottom.addStretch(1)
        self.elapsed_label = label("", "Faint")
        bottom.addWidget(self.elapsed_label)
        pl.addLayout(bottom)
        col.addWidget(prog)

        steps = QFrame()
        steps.setObjectName("Panel")
        sl = QVBoxLayout(steps)
        sl.setContentsMargins(8, 8, 8, 8)
        sl.setSpacing(2)
        self.pipe_steps: list[StepRow] = []
        for i, (title, hint, _stages) in enumerate(PIPE_STEPS):
            step = StepRow(i + 1, title, hint)
            sl.addWidget(step)
            self.pipe_steps.append(step)
        col.addWidget(steps)

        self.error_banner = QFrame()
        self.error_banner.setObjectName("ErrorBanner")
        el = QVBoxLayout(self.error_banner)
        el.setContentsMargins(16, 14, 16, 14)
        el.setSpacing(8)
        el.addWidget(label("Não foi possível concluir", "ErrorTitle"))
        self.error_text = label("", "ErrorText", wrap=True)
        self.error_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        el.addWidget(self.error_text)
        eb = QHBoxLayout()
        eb.setSpacing(8)
        back = QPushButton("Voltar e ajustar")
        back.setObjectName("Ghost")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(lambda: self._show_page(PAGE_CONFIG))
        eb.addWidget(back)
        self.retry_button = QPushButton("Tentar de novo")
        self.retry_button.setObjectName("Primary")
        self.retry_button.setCursor(Qt.PointingHandCursor)
        self.retry_button.clicked.connect(self.process)
        eb.addWidget(self.retry_button)
        eb.addStretch(1)
        el.addLayout(eb)
        self.error_banner.setVisible(False)
        col.addWidget(self.error_banner)

        self.run_log_slot = QVBoxLayout()
        self.run_log_slot.addWidget(self.log_box)
        col.addLayout(self.run_log_slot)

        foot = QHBoxLayout()
        foot.setSpacing(12)
        foot.addStretch(1)
        self.run_hint = label(
            "Você pode usar Projetos e Ajustes enquanto isso — avisamos quando terminar.",
            "Faint",
        )
        foot.addWidget(self.run_hint)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.setToolTip("Esc")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)
        foot.addWidget(self.cancel_button)
        col.addLayout(foot)
        col.addStretch(1)
        return page

    def _build_log_box(self) -> CollapsibleBox:
        box = CollapsibleBox("Ver detalhes técnicos (log)", expanded=False)
        head = QHBoxLayout()
        head.addWidget(label("Saída detalhada do processamento", "Faint"))
        head.addStretch(1)
        clear_log = QPushButton("Limpar log")
        clear_log.setObjectName("Link")
        clear_log.setCursor(Qt.PointingHandCursor)
        head.addWidget(clear_log)
        box.set_content_layout(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(LOG_MAX_LINES)
        self.log_view.setMinimumHeight(220)
        self.log_view.setPlainText("Aguardando um vídeo para processar.")
        clear_log.clicked.connect(self.log_view.clear)
        box.add_widget(self.log_view)
        return box

    # --- Página de resultados ------------------------------------------
    def _build_results_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 18, 24, 0)
        outer.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.results_title = label("0 cortes prontos", "PageTitle")
        self.result_count = self.results_title
        titles.addWidget(self.results_title)
        self.result_path = ElidedLabel("", "ClipPath")
        titles.addWidget(self.result_path)
        head.addLayout(titles, 1)
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
        self.new_video_button = QPushButton("Novo vídeo")
        self.new_video_button.setObjectName("Primary")
        self.new_video_button.setCursor(Qt.PointingHandCursor)
        self.new_video_button.clicked.connect(self.start_new_video)
        head.addWidget(self.new_video_button)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("Root")
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 6, 18)
        hl.setSpacing(12)

        self.results_empty = QFrame()
        self.results_empty.setObjectName("ResultsEmptyBox")
        rel = QVBoxLayout(self.results_empty)
        rel.setContentsMargins(20, 22, 20, 22)
        rel.setSpacing(10)
        self.results_empty_text = label(
            "Nenhum corte atingiu os critérios. Tente “Rigor da IA: Mais cortes” "
            "ou mude a instrução para a IA — a transcrição fica em cache, então a "
            "próxima tentativa é mais rápida.",
            "Muted",
            wrap=True,
        )
        self.results_empty_text.setAlignment(Qt.AlignCenter)
        rel.addWidget(self.results_empty_text)
        retry = QPushButton("Ajustar e tentar de novo")
        retry.setObjectName("Primary")
        retry.setCursor(Qt.PointingHandCursor)
        retry.clicked.connect(lambda: self._show_page(PAGE_CONFIG))
        rr = QHBoxLayout()
        rr.addStretch(1)
        rr.addWidget(retry)
        rr.addStretch(1)
        rel.addLayout(rr)
        self.results_empty.setVisible(False)
        hl.addWidget(self.results_empty)

        self.results_grid = FlowGrid(min_col_width=250)
        hl.addWidget(self.results_grid)
        self.results_log_slot = QVBoxLayout()
        hl.addLayout(self.results_log_slot)
        hl.addStretch(1)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)
        return page

    # ------------------------------------------------------------------
    # Fonte (link ou arquivo)
    # ------------------------------------------------------------------
    def _on_link_edited(self, _text: str = ""):
        state = link_state(self.video_link.text())
        if state == "invalid":
            self.source_hint.setText(
                "Isso não parece um link. Cole um endereço como https://www.youtube.com/watch?v=…"
            )
        elif state == "ok":
            self.source_hint.setText("✓ Link reconhecido. Pressione Enter para gerar os cortes.")
        else:
            self.source_hint.setText(
                "Links do YouTube ou arquivos MP4, MKV, MOV, AVI, WEBM, M4V  ·  "
                "Ctrl+O procura um arquivo  ·  Enter gera os cortes"
            )
        self.source_hint.setProperty(
            "state", {"invalid": "error", "ok": "ok"}.get(state, "idle")
        )
        self.source_hint.style().unpolish(self.source_hint)
        self.source_hint.style().polish(self.source_hint)
        self._update_process_enabled()

    def _active_source(self) -> tuple[str | None, str | None]:
        """Retorna (yt_link, video_path): o arquivo escolhido tem prioridade."""
        if self.video_path:
            return None, self.video_path
        if link_state(self.video_link.text()) == "ok":
            return normalize_link(self.video_link.text()), None
        return None, None

    def _update_process_enabled(self):
        link, path = self._active_source()
        ready = bool(link) or bool(path)
        busy = self.worker is not None
        self.process_button.setEnabled(ready and not busy)
        if busy:
            text = "Processando…"
        elif ready:
            text = "Gerar cortes   ·   Ctrl+Enter"
        elif link_state(self.video_link.text()) == "invalid":
            text = "Confira o link do vídeo"
        else:
            text = "Escolha um vídeo para começar"
        self.process_button.setText(text)
        self._set_badge(self.source_badge, 1, "done" if ready else "active")
        for b, n in ((self.format_badge, 2), (self.caption_badge, 3), (self.cuts_badge, 4)):
            self._set_badge(b, n, "idle")

    @staticmethod
    def _configured_keys() -> tuple[list[str], list[str]]:
        try:
            from core import config as core_config

            keys = [k for k in core_config.API_KEYS if k and k.strip()]
            providers = sorted({core_config.detect_provider(k)[0] for k in keys})
        except Exception:  # noqa: BLE001
            return [], []
        return keys, providers

    def _environment_issues(self) -> list[str]:
        issues = []
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            issues.append(
                "FFmpeg/ffprobe não encontrados no PATH. Instale o FFmpeg e reinicie o app."
            )
        keys, _providers = self._configured_keys()
        if not keys:
            issues.append(
                "Nenhuma chave de IA configurada. Adicione uma em Ajustes → Contas e IA."
            )
        return issues

    def _refresh_env_status(self):
        ff_ok = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
        keys, providers = self._configured_keys()
        ok, bad = theme.SUCCESS, theme.DANGER
        ff = (
            f'<span style="color:{ok}">✓ FFmpeg</span>'
            if ff_ok
            else f'<span style="color:{bad}">✕ FFmpeg ausente</span>'
        )
        if keys:
            ia = (
                f'<span style="color:{ok}">✓ {len(keys)} chave(s) de IA</span>'
                f" ({', '.join(providers)})"
            )
        else:
            ia = f'<span style="color:{bad}">✕ Sem chave de IA — adicione em Ajustes → Contas e IA</span>'
        self.env_status_label.setText(f"{ff} &nbsp;·&nbsp; {ia}")

    # --- Arrastar e soltar video na janela
    VIDEO_EXTS = VIDEO_EXTS

    def _dropped_video(self, event) -> str | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in VIDEO_EXTS:
                return local
        return None

    def _set_drag_highlight(self, on: bool):
        self.source_drop.setProperty("drag", "true" if on else "false")
        self.source_drop.style().unpolish(self.source_drop)
        self.source_drop.style().polish(self.source_drop)

    def dragEnterEvent(self, event):  # noqa: N802
        if self.worker is None and self._dropped_video(event):
            self._set_drag_highlight(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):  # noqa: N802
        self._set_drag_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        self._set_drag_highlight(False)
        path = self._dropped_video(event)
        if path and self.worker is None:
            self.workspace_button.setChecked(True)
            self._show_page(PAGE_CONFIG)
            self._set_selected_video(path)
            event.acceptProposedAction()

    def closeEvent(self, event):  # noqa: N802
        if self.worker is not None:
            answer = QMessageBox.question(
                self,
                "Processamento em andamento",
                "Um vídeo ainda está sendo processado. Cancelar e sair?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.controller.cancel_pipeline()
            wait = getattr(self.worker, "wait", None)
            if callable(wait):
                wait(5000)
        super().closeEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if getattr(self, "toast", None) is not None and self.toast.isVisible():
            self.toast._reposition()

    # --- Frames reais (previa e miniaturas)
    def _set_preview_frame(self, image):
        self.phone_preview.set_frame(image)
        if hasattr(self.settings_view, "set_preview_frame"):
            self.settings_view.set_preview_frame(image)

    def _on_frame_loaded(self, key: str, jpg_path: str):
        if key.startswith("preview:"):
            if self.video_path and key == "preview:" + self.video_path and jpg_path:
                self._set_preview_frame(QImage(jpg_path))
            return
        if not jpg_path:
            return
        for button, label_text in self._thumb_targets.pop(key, []):
            try:
                size = button.size()
                button.setIcon(QIcon(poster_pixmap(
                    jpg_path, size.width(), size.height(), label_text,
                    button.devicePixelRatioF(),
                )))
                button.setIconSize(size)
                button.setText("")
            except RuntimeError:  # card ja removido da tela
                pass

    def request_clip_thumb(self, button, clip_path: str, label_text: str):
        key = "clip:" + clip_path
        self._thumb_targets.setdefault(key, []).append((button, label_text))
        self.frames.request_clip_thumb(clip_path)

    def _run_process_shortcut(self):
        if (
            self.main_stack.currentIndex() == 0
            and self.workspace_stack.currentIndex() == PAGE_CONFIG
            and self.process_button.isEnabled()
        ):
            self.process()

    def _install_shortcuts(self):
        def nav(i):
            btn = self.nav_group.button(i)
            if btn is not None and btn.isEnabled():
                btn.setChecked(True)

        def run_select():
            if self.worker is None:
                self.workspace_button.setChecked(True)
                self._show_page(PAGE_CONFIG)
                self.select_video()

        def run_cancel():
            if self.cancel_button.isEnabled():
                self.cancel_processing()

        bindings = [
            ("Ctrl+Return", self._run_process_shortcut),
            ("Ctrl+Enter", self._run_process_shortcut),
            ("Ctrl+O", run_select),
            ("Escape", run_cancel),
            ("Ctrl+1", lambda: nav(0)),
            ("Ctrl+2", lambda: nav(1)),
            ("Ctrl+3", lambda: nav(2)),
        ]
        self._shortcuts = []
        for seq, fn in bindings:
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Escolher vídeo", "", VIDEO_FILTER)
        if file_path:
            self._set_selected_video(file_path)

    def _set_selected_video(self, file_path: str):
        self.video_path = file_path
        p = Path(file_path)
        self.path_label.setText(p.name)
        try:
            size_mb = p.stat().st_size / (1024 * 1024)
            self.file_size_label.setText(f"{size_mb:.1f} MB  ·  {p.parent}")
        except OSError:
            self.file_size_label.setText(str(p.parent))
        self.frames.request_preview(file_path)
        ext = p.suffix.lstrip(".").upper() or "VID"
        self.file_badge.setText(ext[:4])
        # Um arquivo escolhido substitui qualquer link digitado: uma origem por vez.
        self.video_link.blockSignals(True)
        self.video_link.clear()
        self.video_link.blockSignals(False)
        self._on_link_edited()
        self.source_drop.setVisible(False)
        self.file_selected_card.setVisible(True)
        self._update_process_enabled()

    def clear_video(self):
        self.video_path = None
        self.path_label.setText("Nenhum vídeo selecionado")
        self.file_size_label.setText("—")
        self.file_selected_card.setVisible(False)
        self.source_drop.setVisible(True)
        self._set_preview_frame(None)
        self._update_process_enabled()
        self.video_link.setFocus()

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

    # ------------------------------------------------------------------
    # Controles rápidos
    # ------------------------------------------------------------------
    def on_captions_toggled(self, checked: bool):
        if self._syncing_quick:
            return
        self.options.captions_enabled = bool(checked)
        self._save_options()
        self._refresh_summary()

    def on_review_toggled(self, checked: bool):
        if self._syncing_quick:
            return
        self.options.review_before_render = bool(checked)
        self._save_options()
        self._refresh_summary()

    def select_quick_preset(self, preset_id: str):
        if preset_id not in VIRAL_PRESETS:
            return
        apply_preset(self.options, preset_id)
        self._save_options()
        self._refresh_summary()

    def _on_format_clicked(self, layout_id: str):
        if self._syncing_quick or layout_id not in LAYOUTS:
            return
        self.options.layout_id = layout_id
        self._save_options()
        self._refresh_summary()

    def _on_duration_choice(self, index: int):
        if self._syncing_quick or not (0 <= index < len(DURATION_CHOICES)):
            return
        _name, lo, hi = DURATION_CHOICES[index]
        self.options.min_clip_duration = lo
        self.options.max_clip_duration = hi
        self._save_options()
        self._refresh_summary()

    def _on_rigor_choice(self, index: int):
        if self._syncing_quick or not (0 <= index < len(RIGOR_CHOICES)):
            return
        self.options.min_viral_score = RIGOR_CHOICES[index][1]
        self._save_options()
        self._refresh_summary()

    def _on_quick_params_changed(self, *_args):
        if self._syncing_quick:
            return
        self.options.max_clips = self.quick_max_clips.value()
        self._save_options()
        self._refresh_summary()

    def _toggle_focus_input(self):
        show = self.focus_input.isHidden()
        self.focus_input.setVisible(show)
        if show:
            self.focus_input.setFocus()
        self._sync_focus_toggle()

    def _sync_focus_toggle(self):
        text = self.focus_input.toPlainText().strip()
        self.focus_toggle.setToolTip(text or "Diga à IA que tipo de momento procurar")
        if not self.focus_input.isHidden():
            self.focus_toggle.setText("− Ocultar instrução para a IA")
        elif text:
            self.focus_toggle.setText("✎ Instrução para a IA (ativa)")
        else:
            self.focus_toggle.setText("+ Instrução para a IA (opcional)")

    def _on_embedded_settings_changed(self, updated_options: ProcessingOptions):
        self.options = updated_options
        self._save_options()
        self._refresh_summary()

    def open_settings(self, page: int | None = None):
        self.settings_button.setChecked(True)
        if page is not None:
            self.settings_view.set_active_tab(page)

    def open_projects(self):
        self.projects_button.setChecked(True)

    def _on_project_deleted_in_dialog(self, project_dir: str):
        cur_folder = self._result_folder()
        if (
            cur_folder
            and str(Path(cur_folder).resolve()).lower()
            == str(Path(project_dir).resolve()).lower()
        ):
            self.results_grid.clear()
            self.clip_paths = []
            self.report_path = None
            self.last_clips = []
            if self.workspace_stack.currentIndex() == PAGE_RESULTS:
                self._show_page(PAGE_CONFIG)

    def _on_clip_published_changed_in_dialog(
        self, report_path: str, _clip_idx: int, _published: bool
    ):
        if self.report_path and Path(self.report_path).exists() and report_path:
            if (
                str(Path(self.report_path).resolve()).lower()
                == str(Path(report_path).resolve()).lower()
            ):
                self._render_results(
                    load_report(self.report_path), self.clip_paths, self.report_path
                )

    def _on_focus_edited(self):
        self.options.focus_instruction = self.focus_input.toPlainText().strip()
        self._save_options()
        if self.focus_input.isHidden():
            self._sync_focus_toggle()

    def _save_options(self):
        self.controller.save_options(self.options)

    def _refresh_summary(self):
        o = self.options
        active_preset_id = detect_active_preset(o)
        is_preset = active_preset_id in VIRAL_PRESETS
        preset_name = VIRAL_PRESETS[active_preset_id].name if is_preset else None
        layout_name = get_layout(o.layout_id).name
        caption_txt = (preset_name or "legenda personalizada") if o.captions_enabled else "sem legenda"
        ai_txt = "IA automática" if not o.ai_model else f"IA {o.ai_model.split(':', 1)[-1]}"
        self.config_summary.setText(
            f"{_plural(o.max_clips, 'corte', 'cortes')} · {layout_name} · {caption_txt} · "
            f"{o.width}×{o.height} · Whisper {o.whisper_model} · {ai_txt} —"
        )

        # Estilos visiveis: garante que o estilo em uso aparece na faixa.
        if is_preset and active_preset_id not in self._shown_presets:
            shown = list(VIRAL_PRESETS)[: QUICK_PRESETS_SHOWN - 1] + [active_preset_id]
            self._build_preset_strip(shown)

        self._syncing_quick = True
        try:
            self.captions_checkbox.setChecked(o.captions_enabled)
            self.review_checkbox.setChecked(o.review_before_render)
            self.quick_max_clips.setValue(o.max_clips)
            for lid, card in self.format_cards.items():
                card.set_selected(lid == o.layout_id)
            for pid, card in self.preset_cards.items():
                card.set_selected(pid == active_preset_id)

            d_idx = next(
                (i for i, (_n, lo, hi) in enumerate(DURATION_CHOICES)
                 if lo == o.min_clip_duration and hi == o.max_clip_duration),
                -1,
            )
            if d_idx >= 0:
                self.duration_seg.set_current(d_idx)
                self.duration_hint.setText(f"{o.min_clip_duration}–{o.max_clip_duration}s por corte")
            else:
                self.duration_seg.clear_selection()
                self.duration_hint.setText(
                    f"Atual: {o.min_clip_duration}–{o.max_clip_duration}s (personalizado)"
                )


            r_idx = next(
                (i for i, (_n, score) in enumerate(RIGOR_CHOICES) if score == o.min_viral_score),
                -1,
            )
            if r_idx >= 0:
                self.rigor_seg.set_current(r_idx)
            else:
                self.rigor_seg.clear_selection()
                self.rigor_hint.setText(f"Atual: nota mínima {o.min_viral_score} (personalizado)")
            self.rigor_hint.setVisible(r_idx < 0)
        finally:
            self._syncing_quick = False

        self.caption_body.setVisible(o.captions_enabled)
        self.caption_off_note.setVisible(not o.captions_enabled)
        self.custom_preset_note.setVisible(o.captions_enabled and not is_preset)

        missing = missing_requirements(get_layout(o.layout_id), o.aux_image_path)
        self.format_warning_holder.setVisible(bool(missing))
        if missing:
            self.format_warning.setText(
                f"⚠ “{layout_name}” precisa de uma imagem auxiliar antes de gerar os cortes."
            )

        self.phone_preview.set_options(o)
        self.preview_resolution.setText(f"{o.width} × {o.height}")
        self.preview_ratio.setText(
            "1:1" if o.width == o.height else ("16:9" if o.width > o.height else "9:16")
        )
        self.preview_caption_state.setText(f"{layout_name} · {caption_txt}")
        self._update_process_enabled()

    # ------------------------------------------------------------------
    # Processamento
    # ------------------------------------------------------------------
    def _on_progress_updated(self, value: int):
        self.progress_bar.setValue(value)
        self._update_eta()
        if self.worker is not None and self._stage_text and self._stage_text != STAGE_LABELS["revisao"]:
            self._set_header_status(f"{self._stage_text} · {value}%", "busy")

    def _update_eta(self):
        if not self._run_started:
            return
        elapsed = time.monotonic() - self._run_started
        value = self.progress_bar.value()
        if value >= 100:
            self.eta_label.setText("concluído")
        elif value >= 8 and elapsed > 8:
            remaining = elapsed * (100 - value) / max(1, value)
            if remaining < 60:
                self.eta_label.setText("≈ menos de 1 min restante")
            else:
                mins = int(round(remaining / 60))
                self.eta_label.setText(f"≈ {_plural(mins, 'min restante', 'min restantes')}")
        else:
            self.eta_label.setText("calculando tempo…")

    def _tick(self):
        if not self._run_started:
            return
        self.elapsed_label.setText(
            f"Tempo decorrido {_fmt_secs(time.monotonic() - self._run_started)}"
        )
        self._update_eta()

    def _start_new_run_ui(self, yt_link, video_path):
        self.error_banner.setVisible(False)
        self.config_banner.setVisible(False)
        self.progress_bar.setValue(0)
        self.log_view.clear()
        self.log_box.set_expanded(False)
        self._step_started = {}
        self._active_step = -1
        for step in self.pipe_steps:
            step.set_state("idle")
        caption_hint = "vídeo vertical 9:16" + (
            " + legendas" if self.options.captions_enabled else ""
        )
        self.pipe_steps[3].set_hint(caption_hint)
        if video_path:
            self.run_source_title.setText(Path(video_path).name)
        else:
            self.run_source_title.setText(yt_link or "")
        active_preset_id = detect_active_preset(self.options)
        cap = (
            VIRAL_PRESETS[active_preset_id].name
            if self.options.captions_enabled and active_preset_id in VIRAL_PRESETS
            else ("legenda personalizada" if self.options.captions_enabled else "sem legenda")
        )
        self.run_source_meta.setText(
            f"{get_layout(self.options.layout_id).name} · {cap} · "
            f"até {_plural(self.options.max_clips, 'corte', 'cortes')}"
        )
        self.stage_label.setText("Etapa 1 de 5 · Iniciando")
        self.eta_label.setText("calculando tempo…")
        self.elapsed_label.setText("")
        self._run_started = time.monotonic()
        self._clock.start()
        self._show_page(PAGE_RUN)

    def process(self):
        if self.worker is not None:
            return
        yt_link, video_path = self._active_source()
        if not yt_link and not video_path:
            QMessageBox.information(
                self,
                "Nada para processar",
                "Cole o link de um vídeo ou escolha um arquivo no passo 1.",
            )
            return
        if video_path and not Path(video_path).is_file():
            QMessageBox.warning(
                self, "Arquivo não encontrado", f"O vídeo não existe mais:\n{video_path}"
            )
            self.clear_video()
            return
        issues = self._environment_issues()
        issues += missing_requirements(
            get_layout(self.options.layout_id), self.options.aux_image_path
        )
        if self.options.aux_audio_path and not Path(self.options.aux_audio_path).is_file():
            issues.append("A música de fundo escolhida não existe mais (Ajustes → Formato).")
        if issues:
            self._refresh_env_status()
            QMessageBox.warning(
                self,
                "Falta pouco",
                "Antes de gerar os cortes, resolva:\n\n• " + "\n• ".join(issues),
            )
            return

        self.options.captions_enabled = self.captions_checkbox.isChecked()
        self.options.review_before_render = self.review_checkbox.isChecked()
        self.options.focus_instruction = self.focus_input.toPlainText().strip()

        self._start_new_run_ui(yt_link, video_path)
        self.set_busy(True)
        # Copia: mudar Ajustes durante o processamento não afeta o vídeo em andamento.
        self.worker = self.controller.start_pipeline(
            yt_link=yt_link,
            video_path=video_path,
            output_dir=self.output_dir,
            options=copy.deepcopy(self.options),
        )
        if not self.worker:
            self.worker = None
            self.set_busy(False)
            self._clock.stop()
            self._run_started = 0.0
            self._show_page(PAGE_CONFIG)
            self._update_process_enabled()

    def cancel_processing(self):
        if self.controller.cancel_pipeline():
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Cancelando…")
            self.stage_label.setText("Cancelando…")
            self._set_header_status("Cancelando…", "busy")
            self.log_view.appendPlainText("Solicitando cancelamento do pipeline...")

    def set_busy(self, busy: bool):
        self.select_button.setEnabled(not busy)
        self.clear_file_button.setEnabled(not busy)
        self.change_file_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setText("Cancelar")
        self.run_hint.setVisible(busy)
        self.output_button.setEnabled(not busy)
        self.reset_output_button.setEnabled(not busy)
        self.video_link.setEnabled(not busy)
        if busy:
            self._set_header_status("Processando…", "busy")
        else:
            self.worker = None
        self._update_process_enabled()

    def _step_index(self, stage: str) -> int | None:
        return next(
            (i for i, (_, _, stages) in enumerate(PIPE_STEPS) if stage in stages), None
        )

    def on_stage(self, stage: str):
        stage_text = STAGE_LABELS.get(stage, stage)
        if stage == "concluido":
            self._set_header_status("Concluído", "done")
            self._finish_steps()
            self.stage_label.setText("Concluído")
            return
        active = self._step_index(stage)
        if active is None:
            self.stage_label.setText(stage_text)
            self._set_header_status(stage_text, "busy")
            return
        now = time.monotonic()
        if active != self._active_step:
            for index in range(len(self.pipe_steps)):
                if index < active and self.pipe_steps[index].property("state") != "done":
                    started = self._step_started.get(index)
                    took = f"concluído · {_fmt_secs(now - started)}" if started else "concluído"
                    self.pipe_steps[index].set_state("done", took)
            self._step_started.setdefault(active, now)
            self._active_step = active
        status = "aguardando você" if stage == "revisao" else "em andamento"
        self.pipe_steps[active].set_state("active", status)
        for index in range(active + 1, len(self.pipe_steps)):
            self.pipe_steps[index].set_state("idle")
        self._stage_text = stage_text
        self.stage_label.setText(f"Etapa {active + 1} de {len(PIPE_STEPS)} · {stage_text}")
        pill = stage_text if stage == "revisao" else f"{stage_text} · {self.progress_bar.value()}%"
        self._set_header_status(pill, "busy")

    def _finish_steps(self):
        now = time.monotonic()
        for index, step in enumerate(self.pipe_steps):
            if step.property("state") != "done":
                started = self._step_started.get(index)
                took = f"concluído · {_fmt_secs(now - started)}" if started else "concluído"
                step.set_state("done", took)

    def on_log(self, line: str):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def _notify_if_away(self, title: str, body: str, action_text: str):
        away = self.main_stack.currentIndex() != 0 or not self.isActiveWindow()
        if away:
            self.toast.show_message(
                title,
                body,
                icon="✓",
                action_text=action_text,
                action=lambda: self.workspace_button.setChecked(True),
            )
            QApplication.alert(self)

    def on_finished(self, result: dict):
        self.set_busy(False)
        self._clock.stop()
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
        self._finish_steps()
        self.stage_label.setText("Concluído")
        n = len(clips)
        self._set_header_status(
            f"Concluído · {_plural(n, 'corte', 'cortes')}", "done"
        )
        self._run_started = 0.0
        self._render_results(clips, self.clip_paths, self.report_path)
        self.log_box.set_expanded(False)
        self._show_page(PAGE_RESULTS)
        self.report_button.setEnabled(bool(self.report_path))
        self.open_folder_button.setEnabled(bool(self.clip_paths or self.report_path))
        if not clips:
            self.log_view.appendPlainText(
                "Nenhum corte atingiu a nota mínima. Tente 'Rigor da IA: Mais cortes' "
                "ou mude a instrução para a IA e gere de novo (a transcrição fica em cache)."
            )
        self._notify_if_away(
            "Cortes prontos" if n else "Processamento concluído",
            f"{_plural(n, 'corte gerado', 'cortes gerados')}.",
            "Ver cortes",
        )

    def _on_review_requested(self, clips):
        from PySide6.QtWidgets import QDialog

        from gui.review_dialog import ClipReviewDialog

        self.workspace_button.setChecked(True)
        QApplication.alert(self)
        dialog = ClipReviewDialog(list(clips or []), self)
        if dialog.exec() == QDialog.Accepted:
            self.controller.submit_review(dialog.selected_clips())
        else:
            self.controller.submit_review([])

    def on_cancelled(self, message: str):
        self.set_busy(False)
        self._clock.stop()
        self._run_started = 0.0
        self.eta_label.setText("")
        self.stage_label.setText("Cancelado")
        self._set_header_status("Cancelado", "idle")
        for step in self.pipe_steps:
            if step.property("state") == "active":
                step.set_state("idle", "cancelado")
        self.log_view.appendPlainText(f"[CANCELADO] {message}")
        self.config_banner.setText(
            "Processamento cancelado. Ajuste o que quiser e clique em “Gerar cortes” para tentar de novo."
        )
        self.config_banner.setVisible(True)
        self._show_page(PAGE_CONFIG)

    def on_failed(self, error: str):
        self.set_busy(False)
        self._clock.stop()
        self._run_started = 0.0
        self.eta_label.setText("")
        if 0 <= self._active_step < len(PIPE_STEPS):
            self.stage_label.setText(
                f"Parou na etapa {self._active_step + 1} de {len(PIPE_STEPS)} · "
                f"{PIPE_STEPS[self._active_step][0]}"
            )
        else:
            self.stage_label.setText("Erro")
        self._set_header_status("Erro", "error")
        for step in self.pipe_steps:
            if step.property("state") == "active":
                step.set_state("error")
        self.log_view.appendPlainText(f"[ERRO] {error}")
        self.error_text.setText(friendly_error(error))
        self.error_banner.setVisible(True)
        self.log_box.set_expanded(True)
        self._show_page(PAGE_RUN)
        self.cancel_button.setVisible(False)
        self._notify_if_away("Não foi possível concluir", "Veja o motivo na tela Cortar.", "Ver")

    def start_new_video(self):
        self.clear_video()
        self.video_link.clear()
        self.config_banner.setVisible(False)
        self._set_header_status("Pronto", "idle")
        self._show_page(PAGE_CONFIG)
        self.video_link.setFocus()

    # ------------------------------------------------------------------
    # Cortes gerados
    # ------------------------------------------------------------------
    def _render_results(self, clips, paths, report_path):
        self.results_grid.clear()
        self.last_clips = list(clips)
        total = len(clips)
        self.results_title.setText(
            f"{total} corte pronto" if total == 1 else f"{total} cortes prontos"
        )
        self.result_path.setText(str(self._result_folder() or report_path or "—"))
        self.results_empty.setVisible(not clips)
        self.results_grid.setVisible(bool(clips))
        for idx, clip in enumerate(clips):
            path = paths[idx] if idx < len(paths) else str(clip.get("file") or "")
            card = ClipCard(clip, path, idx, thumb_requester=self.request_clip_thumb)
            card.posted.connect(self._on_clip_posted)
            card.published_changed.connect(self._on_result_published_changed)
            self.results_grid.add(card)

    def _on_clip_posted(self, path: str, index: int):
        body = (
            f"O arquivo do corte #{index + 1} está selecionado na pasta — é só arrastar "
            "para a página de envio. Depois de postar, clique em “Marcar como publicado”."
            if path and Path(path).is_file()
            else "O arquivo deste corte não foi encontrado; envie manualmente."
        )
        self.toast.show_message(
            "Abrimos o YouTube Studio e o TikTok Studio no navegador.", body, icon="↗"
        )

    def _on_result_published_changed(self, index: int, published: bool):
        if self.report_path and Path(self.report_path).exists():
            update_clip_published(self.report_path, index, published)

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
