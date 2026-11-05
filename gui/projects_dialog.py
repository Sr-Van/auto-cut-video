"""Painel e diálogo de Projetos finalizados, exibidos em formato sanfona (accordion).

Suporta uso embarcado na janela principal (`embedded=True`) e uso como
diálogo autônomo (`ProjectsDialog(registry_path=...)`).
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.widgets import label, separator
from utils.report import (
    delete_project,
    load_projects_registry,
    load_report,
    update_clip_published,
)
from utils.timefmt import hhmmss_to_seconds


def reveal_in_explorer(path: str | Path) -> None:
    """Abre a pasta onde o corte está no gerenciador de arquivos nativo do sistema."""
    try:
        p = Path(path).resolve()
        folder = p.parent if p.is_file() else p
        if not folder.exists() and p.parent.exists():
            folder = p.parent
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
    except Exception:
        pass


def open_upload_pages(path: str = "", reveal: bool = True) -> None:
    """Abre YouTube e TikTok Studio no navegador padrão, copia o caminho do corte e abre a pasta onde o vídeo está."""
    if path:
        try:
            resolved_path = Path(path).resolve()
            if resolved_path.exists():
                QApplication.clipboard().setText(str(resolved_path))
                if reveal:
                    reveal_in_explorer(resolved_path)
            elif resolved_path.parent.exists():
                QApplication.clipboard().setText(str(resolved_path))
                if reveal:
                    reveal_in_explorer(resolved_path.parent)
        except Exception:
            pass
    webbrowser.open_new_tab("https://www.youtube.com/upload")
    webbrowser.open_new_tab(
        "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video"
    )


def _format_created_at(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso_str))
        return dt.strftime("%d/%m/%Y · %H:%M")
    except ValueError:
        return str(iso_str)


def format_clip_interval(start: str, end: str) -> str:
    s_txt = str(start or "—")
    e_txt = str(end or "—")
    try:
        dur = int(round(hhmmss_to_seconds(e_txt) - hhmmss_to_seconds(s_txt)))
        if dur > 0:
            return f"{s_txt} → {e_txt} · {dur}s"
    except Exception:
        pass
    return f"{s_txt} → {e_txt}"


def update_published_button_ui(button: QPushButton, published: bool) -> None:
    is_pub = bool(published)
    button.setProperty("published", "true" if is_pub else "false")
    if button.isCheckable() and button.isChecked() != is_pub:
        button.blockSignals(True)
        button.setChecked(is_pub)
        button.blockSignals(False)
    button.setText("✓ Publicado" if is_pub else "Marcar publicado")
    button.style().unpolish(button)
    button.style().polish(button)


class ProjectAccordionItem(QFrame):
    """Item sanfona (accordion) representando um projeto finalizado."""

    project_deleted = Signal(str)
    clip_published_changed = Signal(str, int, bool)

    def __init__(
        self,
        project: dict,
        expanded: bool = False,
        registry_path: str | Path | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.project = dict(project)
        self.registry_path = registry_path
        self._expanded = bool(expanded)
        self.setObjectName("ProjectAccordion")

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # --- Botão cabeçalho da sanfona
        self.header_button = QPushButton()
        self.header_button.setObjectName("ProjectHeaderBtn")
        self.header_button.setCursor(Qt.PointingHandCursor)
        self.header_button.clicked.connect(self.toggle)
        self.root_layout.addWidget(self.header_button)

        # --- Área de conteúdo expansível
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(16, 0, 16, 14)
        self.content_layout.setSpacing(10)
        self.root_layout.addWidget(self.content_area)

        self._build_content()
        self._sync_ui()

    def _build_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.content_layout.addWidget(separator())

        project_dir = str(self.project.get("project_dir") or "")
        report_path = str(self.project.get("report_path") or "")
        if not report_path and project_dir:
            report_path = str(Path(project_dir) / "relatorio.json")

        clips = load_report(report_path) if report_path else []
        published_count = sum(1 for c in clips if c.get("published"))

        # --- Barra de metadados e ações do projeto
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)

        meta_info = QVBoxLayout()
        meta_info.setSpacing(2)
        created_str = _format_created_at(
            str(self.project.get("created_at") or "")
        )
        avg_score = float(self.project.get("average_viral_score", 0.0) or 0.0)
        clips_count = int(self.project.get("clips_count", len(clips)) or 0)
        summary_txt = (
            f"Concluído em {created_str}  ·  "
            f"{clips_count} cortes  ·  "
            f"Nota média: {avg_score:.1f}/10  ·  "
            f"Publicados: {published_count}/{len(clips)}"
        )
        self.meta_summary_label = label(summary_txt, "FieldLabel", wrap=True)
        meta_info.addWidget(self.meta_summary_label)

        dir_lbl = label(project_dir or "—", "FieldHint", wrap=True)
        meta_info.addWidget(dir_lbl)
        meta_row.addLayout(meta_info, 1)

        self.open_folder_button = QPushButton("Abrir pasta")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.setCursor(Qt.PointingHandCursor)
        self.open_folder_button.clicked.connect(self.open_folder)
        meta_row.addWidget(self.open_folder_button, 0, Qt.AlignVCenter)

        self.delete_project_button = QPushButton("Excluir projeto")
        self.delete_project_button.setObjectName("Danger")
        self.delete_project_button.setCursor(Qt.PointingHandCursor)
        self.delete_project_button.clicked.connect(self.confirm_and_delete)
        meta_row.addWidget(self.delete_project_button, 0, Qt.AlignVCenter)

        meta_holder = QWidget()
        meta_holder.setLayout(meta_row)
        self.content_layout.addWidget(meta_holder)

        # --- Lista de cortes
        self.clips_container = QWidget()
        self.clips_layout = QVBoxLayout(self.clips_container)
        self.clips_layout.setContentsMargins(0, 2, 0, 0)
        self.clips_layout.setSpacing(6)

        if not clips:
            empty_lbl = label(
                "Nenhum corte registrado no relatório deste projeto.",
                "ResultsEmpty",
                wrap=True,
            )
            empty_lbl.setAlignment(Qt.AlignCenter)
            self.clips_layout.addWidget(empty_lbl)
        else:
            for idx, clip in enumerate(clips):
                self.clips_layout.addWidget(
                    self._build_clip_row(idx, clip, report_path)
                )

        self.content_layout.addWidget(self.clips_container)

    def _build_clip_row(
        self, index: int, clip: dict, report_path: str
    ) -> QWidget:
        card = QFrame()
        card.setObjectName("ProjectClipCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(3)

        kicker = QHBoxLayout()
        kicker.setSpacing(6)
        score_val = clip.get("viral_score", "—")
        score_lbl = label(f"{score_val}/10", "ClipScore")
        try:
            if float(score_val) < 8.0:
                score_lbl.setProperty("tier", "mid")
        except (TypeError, ValueError):
            pass
        kicker.addWidget(score_lbl)
        kicker.addWidget(label(str(clip.get("category") or "CORTE"), "ClipCat"))
        kicker.addWidget(
            label(
                format_clip_interval(
                    clip.get("start", "—"), clip.get("end", "—")
                ),
                "ClipTime",
            )
        )
        kicker.addStretch(1)
        left.addLayout(kicker)

        title_lbl = label(
            clip.get("title") or f"Corte #{index + 1}", "ClipTitle", wrap=True
        )
        left.addWidget(title_lbl)

        file_path = str(clip.get("file") or "")
        if file_path and not Path(file_path).is_absolute() and report_path:
            file_path = str((Path(report_path).parent / file_path).resolve())
        elif not file_path and report_path:
            file_path = str(Path(report_path).parent.resolve())

        if file_path:
            fname = label(Path(file_path).name, "ClipPath")
            fname.setToolTip(file_path)
            left.addWidget(fname)

        row.addLayout(left, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)

        if file_path and Path(file_path).is_file():
            open_mp4 = QPushButton("▶ Assistir")
            open_mp4.setObjectName("Ghost")
            open_mp4.setCursor(Qt.PointingHandCursor)
            open_mp4.clicked.connect(
                lambda _=False, p=file_path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(p))
                )
            )
            actions.addWidget(open_mp4)

            copy_btn = QPushButton("Copiar caminho")
            copy_btn.setObjectName("Ghost")
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.clicked.connect(
                lambda _=False, p=file_path: QApplication.clipboard().setText(
                    str(p)
                )
            )
            actions.addWidget(copy_btn)

        post_btn = QPushButton("Postar")
        post_btn.setObjectName("Ghost")
        post_btn.setCursor(Qt.PointingHandCursor)
        post_btn.setToolTip(
            "Abre YouTube e TikTok Studio no navegador, copia o caminho e abre a pasta do corte para arrastar"
        )
        post_btn.clicked.connect(
            lambda _=False, p=file_path: open_upload_pages(p)
        )
        actions.addWidget(post_btn)

        pub_btn = QPushButton()
        pub_btn.setObjectName("PublishedBtn")
        pub_btn.setCheckable(True)
        pub_btn.setCursor(Qt.PointingHandCursor)
        update_published_button_ui(pub_btn, bool(clip.get("published", False)))
        pub_btn.clicked.connect(
            lambda checked, i=index, b=pub_btn, rp=report_path: self._on_toggle_published(
                rp, i, checked, b
            )
        )
        actions.addWidget(pub_btn)

        row.addLayout(actions)
        return card

    def _on_toggle_published(
        self,
        report_path: str,
        clip_index: int,
        published: bool,
        button: QPushButton,
    ) -> None:
        rows = update_clip_published(report_path, clip_index, published)
        update_published_button_ui(button, published)

        published_count = sum(1 for c in rows if c.get("published"))
        created_str = _format_created_at(
            str(self.project.get("created_at") or "")
        )
        avg_score = float(self.project.get("average_viral_score", 0.0) or 0.0)
        clips_count = int(self.project.get("clips_count", len(rows)) or 0)
        self.meta_summary_label.setText(
            f"Concluído em {created_str}  ·  "
            f"{clips_count} cortes  ·  "
            f"Nota média: {avg_score:.1f}/10  ·  "
            f"Publicados: {published_count}/{len(rows)}"
        )
        self.clip_published_changed.emit(
            report_path, clip_index, bool(published)
        )

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self._sync_ui()

    def is_expanded(self) -> bool:
        return self._expanded

    def _sync_ui(self) -> None:
        arrow = "▾" if self._expanded else "▸"
        video_name = str(self.project.get("video_name") or "Projeto sem nome")
        clips_count = int(self.project.get("clips_count", 0) or 0)
        avg_score = float(self.project.get("average_viral_score", 0.0) or 0.0)
        self.header_button.setText(
            f"{arrow}   {video_name}     ·     {clips_count} cortes     ·     Nota média: {avg_score:.1f}/10"
        )
        self.content_area.setVisible(self._expanded)
        self.setProperty("expanded", "true" if self._expanded else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def open_folder(self) -> None:
        project_dir = str(self.project.get("project_dir") or "")
        if project_dir and Path(project_dir).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(project_dir))
        else:
            QMessageBox.warning(
                self,
                "Pasta não encontrada",
                f"A pasta do projeto não existe mais no disco:\n{project_dir}",
            )

    def confirm_and_delete(self, skip_confirm: bool = False) -> bool:
        project_dir = str(self.project.get("project_dir") or "")
        video_name = str(self.project.get("video_name") or project_dir)
        if not skip_confirm:
            reply = QMessageBox.question(
                self,
                "Excluir projeto",
                f"Tem certeza que deseja excluir o projeto “{video_name}”?\n\n"
                f"Isso excluirá TODA A PASTA e todos os clipes em:\n{project_dir}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False

        try:
            delete_project(project_dir, registry_path=self.registry_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erro ao excluir",
                f"Não foi possível excluir a pasta do projeto:\n{exc}",
            )
            return False

        self.project_deleted.emit(project_dir)
        return True


class ProjectsDialog(QDialog):
    """Biblioteca de projetos finalizados ordenados do mais recente ao mais antigo."""

    project_deleted = Signal(str)
    clip_published_changed = Signal(str, int, bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        registry_path: str | Path | None = None,
        embedded: bool = False,
    ):
        super().__init__(parent)
        self.embedded = bool(embedded)
        if self.embedded:
            self.setWindowFlags(Qt.Widget)
        else:
            self.setWindowTitle("Projetos")
            self.resize(880, 680)
            self.setMinimumSize(700, 520)

        self.registry_path = registry_path
        self.accordion_items: list[ProjectAccordionItem] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Barra superior com filtro e contador
        head = QFrame()
        head.setObjectName("SettingsHead")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(20, 14, 20, 14)
        head_layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Projetos finalizados", "PanelTitle"))
        titles.addWidget(
            label(
                "Expanda um projeto para assistir aos cortes, marcar como publicado ou abrir a pasta.",
                "Faint",
            )
        )
        head_layout.addLayout(titles, 1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filtrar por nome do vídeo...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self._apply_filter)
        head_layout.addWidget(self.search_input, 0, Qt.AlignVCenter)

        self.count_pill = label("0 projetos", "MiniPill")
        head_layout.addWidget(self.count_pill, 0, Qt.AlignVCenter)

        refresh_btn = QPushButton("Atualizar")
        refresh_btn.setObjectName("Ghost")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh_projects)
        head_layout.addWidget(refresh_btn, 0, Qt.AlignVCenter)

        root.addWidget(head)

        # --- Lista rolável
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        self.list_host = QWidget()
        self.list_host.setObjectName("Root")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(20, 16, 20, 18)
        self.list_layout.setSpacing(10)
        scroll.setWidget(self.list_host)
        root.addWidget(scroll, 1)

        # --- Rodapé apenas quando aberto como modal independente
        if not self.embedded:
            foot = QFrame()
            foot.setObjectName("Footer")
            foot_layout = QHBoxLayout(foot)
            foot_layout.setContentsMargins(20, 12, 20, 12)
            foot_layout.addStretch(1)

            close_btn = QPushButton("Fechar")
            close_btn.setObjectName("Primary")
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.clicked.connect(self.accept)
            foot_layout.addWidget(close_btn)
            root.addWidget(foot)

        self.refresh_projects()

    def refresh_projects(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.accordion_items.clear()

        projects = load_projects_registry(self.registry_path)
        total = len(projects)
        self.count_pill.setText(
            f"{total} projeto" if total == 1 else f"{total} projetos"
        )

        if not projects:
            empty = label(
                "Nenhum projeto finalizado ainda. Assim que você concluir um processamento, ele aparecerá aqui.",
                "ResultsEmpty",
                wrap=True,
            )
            empty.setAlignment(Qt.AlignCenter)
            self.list_layout.addWidget(empty)
            self.list_layout.addStretch(1)
            return

        for idx, proj in enumerate(projects):
            item = ProjectAccordionItem(
                proj,
                expanded=(idx == 0),
                registry_path=self.registry_path,
                parent=self.list_host,
            )
            item.project_deleted.connect(self._on_project_deleted)
            item.clip_published_changed.connect(self.clip_published_changed)
            self.accordion_items.append(item)
            self.list_layout.addWidget(item)

        self.list_layout.addStretch(1)
        if hasattr(self, "search_input") and self.search_input.text().strip():
            self._apply_filter(self.search_input.text())

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        for item in self.accordion_items:
            name = str(item.project.get("video_name") or "").lower()
            item.setVisible(not q or q in name)

    def _on_project_deleted(self, project_dir: str) -> None:
        self.project_deleted.emit(project_dir)
        self.refresh_projects()
