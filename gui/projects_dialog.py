"""Projetos finalizados: lista à esquerda, cortes do projeto à direita.

Suporta uso embarcado na janela principal (`embedded=True`) e uso como
diálogo autônomo (`ProjectsDialog(registry_path=...)`).
"""

from __future__ import annotations

import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.widgets import ElidedLabel, FlowGrid, Segmented, label, separator
from utils.report import (
    delete_project,
    load_projects_registry,
    load_report,
    project_folder_missing,
    remove_missing_projects,
    update_clip_published,
)
from utils.timefmt import hhmmss_to_seconds

YOUTUBE_UPLOAD_URL = "https://www.youtube.com/upload"
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video"

FILTER_ALL, FILTER_PENDING, FILTER_PUBLISHED = 0, 1, 2


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
    """Abre YouTube e TikTok Studio no navegador e mostra o corte na pasta.

    Não mexe na área de transferência: o usuário pode ter acabado de copiar
    o título e a descrição do corte.
    """
    if path and reveal:
        try:
            resolved_path = Path(path).resolve()
            if resolved_path.exists():
                reveal_in_explorer(resolved_path)
            elif resolved_path.parent.exists():
                reveal_in_explorer(resolved_path.parent)
        except Exception:
            pass
    webbrowser.open_new_tab(YOUTUBE_UPLOAD_URL)
    webbrowser.open_new_tab(TIKTOK_UPLOAD_URL)


def _format_created_at(iso_str: str, short: bool = False) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso_str))
        return dt.strftime("%d/%m" if short else "%d/%m/%Y · %H:%M")
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


def _report_path_of(project: dict) -> str:
    report_path = str(project.get("report_path") or "")
    project_dir = str(project.get("project_dir") or "")
    if not report_path and project_dir:
        report_path = str(Path(project_dir) / "relatorio.json")
    return report_path


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class ProjectRow(QFrame):
    """Linha compacta da lista de projetos."""

    clicked = Signal(object)

    def __init__(self, project: dict, clips: list[dict], parent=None):
        super().__init__(parent)
        self.project = dict(project)
        self.clips = clips
        self.missing = project_folder_missing(project)
        self.published = sum(1 for c in clips if c.get("published"))
        self.total = len(clips) or int(project.get("clips_count", 0) or 0)
        self.setObjectName("ProjectRow")
        self.setProperty("selected", "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        col = QVBoxLayout(self)
        col.setContentsMargins(14, 9, 12, 9)
        col.setSpacing(3)
        name = str(project.get("video_name") or "Projeto sem nome")
        self.title = ElidedLabel(name, "ProjectRowTitle")
        col.addWidget(self.title)
        date = _format_created_at(str(project.get("created_at") or ""), short=True)
        meta = (
            f"{date} · {_plural(self.total, 'corte', 'cortes')} · "
            f"{self.published} de {self.total} publicados"
        )
        if self.missing:
            meta = f"{date} · pasta não encontrada"
        meta_lbl = label(meta, "ProjectRowMeta")
        if self.missing:
            meta_lbl.setProperty("missing", "true")
        col.addWidget(meta_lbl)

    def has_pending(self) -> bool:
        return not self.missing and self.published < self.total

    def is_fully_published(self) -> bool:
        return not self.missing and self.total > 0 and self.published >= self.total

    def set_selected(self, selected: bool):
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self)
            event.accept()
            return
        super().keyPressEvent(event)


class ProjectDetail(QWidget):
    """Detalhe de um projeto: metadados, ações e galeria de cortes."""

    project_deleted = Signal(str)
    clip_published_changed = Signal(str, int, bool)
    counts_changed = Signal()

    def __init__(self, registry_path=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Root")
        self.registry_path = registry_path
        self.project: dict | None = None
        self.report_path = ""
        self.clip_cards = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        self.title = label("", "DetailTitle", wrap=True)
        root.addWidget(self.title)
        self.meta = label("", "Muted")
        root.addWidget(self.meta)
        self.path = ElidedLabel("", "ClipPath")
        root.addWidget(self.path)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.open_folder_button = QPushButton("Abrir pasta")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.setCursor(Qt.PointingHandCursor)
        self.open_folder_button.clicked.connect(self.open_folder)
        actions.addWidget(self.open_folder_button)
        actions.addStretch(1)
        self.delete_button = QPushButton("Excluir projeto…")
        self.delete_button.setObjectName("DangerLink")
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.clicked.connect(self.confirm_and_delete)
        actions.addWidget(self.delete_button)
        root.addLayout(actions)

        root.addWidget(separator())
        self.count_line = label("", "SectionTitle")
        root.addWidget(self.count_line)

        self.notice = label("", "ResultsEmpty", wrap=True)
        self.notice.setAlignment(Qt.AlignCenter)
        self.notice.setVisible(False)
        root.addWidget(self.notice)

        self.grid = FlowGrid(min_col_width=240)
        root.addWidget(self.grid)
        root.addStretch(1)

    def show_project(self, project: dict | None, empty_text: str = ""):
        self.project = dict(project) if project else None
        self.grid.clear()
        self.clip_cards = []
        has = project is not None
        for w in (self.open_folder_button, self.delete_button, self.path, self.meta):
            w.setVisible(has)
        if not has:
            self.title.setText("Nenhum projeto selecionado")
            self.count_line.setText("")
            self.notice.setText(empty_text or "Escolha um projeto na lista ao lado.")
            self.notice.setVisible(True)
            return

        self.report_path = _report_path_of(project)
        clips = load_report(self.report_path) if self.report_path else []
        name = str(project.get("video_name") or "Projeto sem nome")
        self.title.setText(name)
        avg = float(project.get("average_viral_score", 0.0) or 0.0)
        self.meta.setText(
            f"Concluído em {_format_created_at(str(project.get('created_at') or ''))}"
            f"  ·  Nota média {avg:.1f}/10"
        )
        project_dir = str(project.get("project_dir") or "")
        self.path.setText(project_dir or "—")

        if project_folder_missing(project):
            self.count_line.setText("")
            self.notice.setText(
                "A pasta deste projeto não existe mais no disco (foi movida ou apagada). "
                "Use “Remover da lista” à esquerda para limpar projetos assim."
            )
            self.notice.setVisible(True)
            self.open_folder_button.setEnabled(False)
            return
        self.open_folder_button.setEnabled(True)

        if not clips:
            self.count_line.setText("")
            self.notice.setText("Nenhum corte registrado no relatório deste projeto.")
            self.notice.setVisible(True)
            return
        self.notice.setVisible(False)

        from gui.clip_card import ClipCard, make_thumb_requester, resolve_clip_file

        host = self.window()
        requester = getattr(host, "request_clip_thumb", None)
        if requester is None:
            requester = getattr(self, "_own_requester", None)
            if requester is None:
                requester = self._own_requester = make_thumb_requester(self)
        for idx, clip in enumerate(clips):
            path = resolve_clip_file(clip, report_path=self.report_path)
            card = ClipCard(clip, path, idx, thumb_requester=requester)
            card.published_changed.connect(self._on_published_changed)
            self.clip_cards.append(card)
            self.grid.add(card)
        self._update_count_line()

    def _update_count_line(self):
        total = len(self.clip_cards)
        pub = sum(1 for c in self.clip_cards if c.is_published())
        self.count_line.setText(
            f"{_plural(total, 'corte', 'cortes')}  ·  {pub} publicado"
            f"{'s' if pub != 1 else ''}  ·  {total - pub} aguardando publicação"
        )

    def _on_published_changed(self, index: int, published: bool):
        if self.report_path:
            update_clip_published(self.report_path, index, published)
        self._update_count_line()
        self.clip_published_changed.emit(self.report_path, index, published)
        self.counts_changed.emit()

    def open_folder(self) -> None:
        project_dir = str((self.project or {}).get("project_dir") or "")
        if project_dir and Path(project_dir).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(project_dir))
        else:
            QMessageBox.warning(
                self,
                "Pasta não encontrada",
                f"A pasta do projeto não existe mais no disco:\n{project_dir}",
            )

    def confirm_and_delete(self, skip_confirm: bool = False) -> bool:
        if not self.project:
            return False
        project_dir = str(self.project.get("project_dir") or "")
        video_name = str(self.project.get("video_name") or project_dir)
        if not skip_confirm:
            reply = QMessageBox.question(
                self,
                "Excluir projeto",
                f"Excluir o projeto “{video_name}”?\n\n"
                f"Isso apaga A PASTA INTEIRA e todos os cortes em:\n{project_dir}\n\n"
                "Não dá para desfazer.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
        try:
            delete_project(project_dir, registry_path=self.registry_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Erro ao excluir",
                f"Não foi possível excluir a pasta do projeto:\n{exc}",
            )
            return False
        self.project_deleted.emit(project_dir)
        return True


class ProjectsDialog(QDialog):
    """Biblioteca de projetos finalizados (lista + detalhe)."""

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
            self.resize(1100, 700)
            self.setMinimumSize(820, 520)

        self.registry_path = registry_path
        self.project_rows: list[ProjectRow] = []
        self._selected_dir: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # --- Coluna da lista
        side = QFrame()
        side.setObjectName("ProjectsSide")
        side.setFixedWidth(360)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(14, 14, 0, 0)
        side_l.setSpacing(10)

        top = QVBoxLayout()
        top.setContentsMargins(0, 0, 14, 0)
        top.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar projeto…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_filter)
        top.addWidget(self.search_input)

        self.filter_seg = Segmented(["Todos", "A publicar", "Publicados"])
        self.filter_seg.setObjectName("FilterSeg")
        self.filter_seg.changed.connect(lambda _i: self._apply_filter())
        top.addWidget(self.filter_seg)

        self.missing_row = QFrame()
        mr = QHBoxLayout(self.missing_row)
        mr.setContentsMargins(0, 0, 0, 0)
        mr.setSpacing(8)
        self.missing_label = label("", "WarnText")
        mr.addWidget(self.missing_label, 1)
        self.clean_button = QPushButton("Remover da lista")
        self.clean_button.setObjectName("Ghost")
        self.clean_button.setCursor(Qt.PointingHandCursor)
        self.clean_button.setToolTip(
            "Tira da lista os projetos cuja pasta não existe mais. Nada é apagado do disco."
        )
        self.clean_button.clicked.connect(self.remove_missing)
        mr.addWidget(self.clean_button)
        top.addWidget(self.missing_row)
        side_l.addLayout(top)

        list_scroll = QScrollArea()
        list_scroll.setWidgetResizable(True)
        list_scroll.setFrameShape(QScrollArea.NoFrame)
        list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_host.setObjectName("ProjectsSideList")
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 12)
        self.list_layout.setSpacing(0)
        list_scroll.setWidget(self.list_host)
        side_l.addWidget(list_scroll, 1)
        body.addWidget(side)

        # --- Detalhe
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QScrollArea.NoFrame)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail = ProjectDetail(registry_path=registry_path)
        self.detail.project_deleted.connect(self._on_project_deleted)
        self.detail.clip_published_changed.connect(self.clip_published_changed)
        self.detail.counts_changed.connect(self._refresh_counts_soft)
        detail_scroll.setWidget(self.detail)
        body.addWidget(detail_scroll, 1)
        root.addLayout(body, 1)

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

    # --- Dados ---------------------------------------------------------
    def refresh_projects(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.project_rows = []

        for proj in load_projects_registry(self.registry_path):
            rp = _report_path_of(proj)
            clips = load_report(rp) if rp and Path(rp).is_file() else []
            row = ProjectRow(proj, clips, parent=self.list_host)
            row.clicked.connect(self._on_row_clicked)
            self.project_rows.append(row)
            self.list_layout.addWidget(row)

        self.empty_list = label("", "ListEmpty", wrap=True)
        self.empty_list.setAlignment(Qt.AlignCenter)
        self.list_layout.addWidget(self.empty_list)
        self.list_layout.addStretch(1)
        self._update_filter_labels()
        self._apply_filter()

    def _update_filter_labels(self):
        rows = self.project_rows
        self.filter_seg.set_label(0, f"Todos {len(rows)}")
        self.filter_seg.set_label(
            1, f"A publicar {sum(1 for r in rows if r.has_pending())}"
        )
        self.filter_seg.set_label(
            2, f"Publicados {sum(1 for r in rows if r.is_fully_published())}"
        )
        missing = sum(1 for r in rows if r.missing)
        self.missing_row.setVisible(missing > 0)
        self.missing_label.setText(
            f"⚠ {missing} sem pasta no disco"
        )

    def _refresh_counts_soft(self):
        """Atualiza contadores sem reconstruir a lista (apos marcar publicado)."""
        if not self.detail.project:
            return
        target = str(self.detail.project.get("project_dir") or "")
        for row in self.project_rows:
            if str(row.project.get("project_dir") or "") == target:
                row.published = sum(1 for c in self.detail.clip_cards if c.is_published())
        self._update_filter_labels()

    def _matches(self, row: ProjectRow, query: str, mode: int) -> bool:
        name = str(row.project.get("video_name") or "").lower()
        if query and query not in name:
            return False
        if mode == FILTER_PENDING:
            return row.has_pending()
        if mode == FILTER_PUBLISHED:
            return row.is_fully_published()
        return True

    def _apply_filter(self, *_args) -> None:
        q = self.search_input.text().strip().lower()
        mode = max(0, self.filter_seg.current())
        visible = []
        for row in self.project_rows:
            ok = self._matches(row, q, mode)
            row.setVisible(ok)
            if ok:
                visible.append(row)

        if not self.project_rows:
            msg = (
                "Nenhum projeto ainda. Quando você gerar cortes de um vídeo, "
                "o projeto aparece aqui."
            )
        elif not visible:
            msg = (
                f"Nenhum projeto encontrado para “{self.search_input.text().strip()}”."
                if q
                else "Nenhum projeto neste filtro."
            )
        else:
            msg = ""
        self.empty_list.setText(msg)
        self.empty_list.setVisible(bool(msg))

        current = next(
            (r for r in visible
             if str(r.project.get("project_dir") or "") == self._selected_dir),
            None,
        )
        if current is None and visible:
            current = next((r for r in visible if not r.missing), visible[0])
        self._select_row(current)

    def _on_row_clicked(self, row: ProjectRow):
        self._select_row(row)

    def _select_row(self, row: ProjectRow | None):
        self._selected_dir = str(row.project.get("project_dir") or "") if row else None
        for r in self.project_rows:
            r.set_selected(r is row)
        if row is None:
            self.detail.show_project(
                None,
                "Nenhum projeto ainda." if not self.project_rows
                else "Nenhum projeto neste filtro.",
            )
        elif self.detail.project is None or str(
            self.detail.project.get("project_dir") or ""
        ) != self._selected_dir:
            self.detail.show_project(row.project)

    def select_project(self, index: int):
        visible = [r for r in self.project_rows if not r.isHidden()]
        if 0 <= index < len(visible):
            self._select_row(visible[index])

    def remove_missing(self) -> int:
        removed = remove_missing_projects(self.registry_path)
        self._selected_dir = None
        self.detail.project = None
        self.refresh_projects()
        return removed

    def _on_project_deleted(self, project_dir: str) -> None:
        self.project_deleted.emit(project_dir)
        self._selected_dir = None
        self.detail.project = None
        self.refresh_projects()
