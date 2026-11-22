"""Card de corte pronto, usado em Resultados e em Projetos.

Acao principal: "Postar" (abre as paginas de envio no navegador e mostra o
arquivo na pasta). As demais acoes ficam no menu "⋯".
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.widgets import label

POST_TOOLTIP = (
    "Abre o YouTube Studio e o TikTok Studio no navegador e mostra o arquivo "
    "na pasta, pronto para arrastar"
)


def clip_duration_text(clip: dict) -> str:
    from utils.timefmt import hhmmss_to_seconds

    start = clip.get("cut_start") or clip.get("start")
    end = clip.get("cut_end") or clip.get("end")
    try:
        secs = int(round(hhmmss_to_seconds(str(end)) - hhmmss_to_seconds(str(start))))
    except Exception:  # noqa: BLE001
        return ""
    if secs <= 0:
        return ""
    return f"{secs // 60}:{secs % 60:02d}"


def elide_lines(text: str, fm, width: int, lines: int = 2) -> str:
    """Quebra o texto em ate `lines` linhas; a ultima termina com reticencias."""
    words = text.split()
    if width <= 10 or not words:
        return text
    out: list[str] = []
    cur = ""
    i = 0
    while i < len(words) and len(out) < lines:
        cand = f"{cur} {words[i]}".strip()
        if fm.horizontalAdvance(cand) <= width or not cur:
            cur = cand
            i += 1
        else:
            out.append(cur)
            cur = ""
    if len(out) < lines and cur:
        out.append(cur)
        cur = ""
    if i < len(words) or cur:
        rest = " ".join([out[-1], *words[i:]]) if out else text
        out[-1] = fm.elidedText(rest, Qt.ElideRight, width)
    else:
        out[-1] = fm.elidedText(out[-1], Qt.ElideRight, width)
    return "\n".join(out)


def resolve_clip_file(clip: dict, path: str = "", report_path: str = "") -> str:
    """Caminho absoluto do MP4 do corte (ou '' se desconhecido)."""
    file_path = str(path or clip.get("file") or "")
    if file_path and not Path(file_path).is_absolute() and report_path:
        file_path = str((Path(report_path).parent / file_path).resolve())
    return file_path


class ClipCard(QFrame):
    """Card vertical de um corte com 'Postar' como acao principal."""

    posted = Signal(str, int)
    published_changed = Signal(int, bool)

    def __init__(
        self,
        clip: dict,
        path: str,
        index: int,
        thumb_requester=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ClipCard")
        self.setProperty("posted", "false")
        self.clip = dict(clip)
        self.path = str(path or "")
        self.index = index
        self._published = bool(clip.get("published", False))
        self._just_posted = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(8)

        # --- Miniatura vertical centralizada
        thumb_area = QFrame()
        thumb_area.setObjectName("ClipThumbArea")
        thumb_area.setFixedHeight(150)
        ta = QHBoxLayout(thumb_area)
        ta.setContentsMargins(0, 8, 0, 8)
        self.thumb = QPushButton(f"▶\n#{index + 1}")
        self.thumb.setObjectName("ResultMedia")
        self.thumb.setFixedSize(76, 134)
        self.thumb.setCursor(Qt.PointingHandCursor)
        self.file_exists = bool(self.path) and Path(self.path).is_file()
        if self.file_exists:
            self.thumb.setToolTip("Assistir")
            self.thumb.clicked.connect(self.watch)
            if thumb_requester is not None:
                thumb_requester(self.thumb, self.path, f"#{index + 1}")
        else:
            self.thumb.setEnabled(False)
            self.thumb.setToolTip("Arquivo do corte não encontrado")
        ta.addStretch(1)
        ta.addWidget(self.thumb)
        ta.addStretch(1)
        root.addWidget(thumb_area)

        body = QVBoxLayout()
        body.setContentsMargins(12, 0, 12, 0)
        body.setSpacing(6)

        tags = QHBoxLayout()
        tags.setSpacing(6)
        score_val = clip.get("viral_score", "—")
        score = label(f"{score_val}/10", "ClipScore")
        try:
            if float(score_val) < 8.0:
                score.setProperty("tier", "mid")
        except (TypeError, ValueError):
            pass
        tags.addWidget(score)
        tags.addWidget(label(str(clip.get("category") or "CORTE").upper(), "ClipCat"))
        tags.addStretch(1)
        self.pub_chip = label("✓ Publicado", "PubChip")
        tags.addWidget(self.pub_chip)
        body.addLayout(tags)

        self._title = str(clip.get("title") or f"Corte #{index + 1}")
        self.title_lbl = label(self._title, "ClipTitle")
        self.title_lbl.setToolTip(self._title)
        self.title_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        fm = self.title_lbl.fontMetrics()
        self.title_lbl.setFixedHeight(fm.lineSpacing() * 2 + 2)
        self.title_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        body.addWidget(self.title_lbl)

        from gui.projects_dialog import format_clip_interval

        meta = format_clip_interval(
            clip.get("cut_start") or clip.get("start", "—"),
            clip.get("cut_end") or clip.get("end", "—"),
        )
        if self.path and not self.file_exists:
            meta += "  ·  arquivo não encontrado"
        body.addWidget(label(meta, "ClipTime"))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.post_button = QPushButton()
        self.post_button.setCursor(Qt.PointingHandCursor)
        self.post_button.clicked.connect(self._on_primary)
        actions.addWidget(self.post_button)
        actions.addStretch(1)

        self.more_button = QToolButton()
        self.more_button.setObjectName("MoreBtn")
        self.more_button.setText("⋯")
        self.more_button.setToolTip("Mais ações")
        self.more_button.setCursor(Qt.PointingHandCursor)
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        self.menu = QMenu(self.more_button)
        self.act_watch = self.menu.addAction("▶  Assistir", self.watch)
        self.act_copy_meta = self.menu.addAction(
            "Copiar título + descrição", self.copy_title_description
        )
        self.act_copy_path = self.menu.addAction(
            "Copiar caminho do arquivo", self.copy_path
        )
        self.act_reveal = self.menu.addAction("Mostrar na pasta", self.reveal)
        self.menu.addSeparator()
        self.act_publish = self.menu.addAction("", self._toggle_published_from_menu)
        self.more_button.setMenu(self.menu)
        actions.addWidget(self.more_button)
        body.addLayout(actions)
        root.addLayout(body)

        for act in (self.act_watch, self.act_copy_path, self.act_reveal):
            act.setEnabled(self.file_exists)
        from gui.review_dialog import format_clip_share_text

        self._share_text = format_clip_share_text(clip)
        self.act_copy_meta.setEnabled(bool(self._share_text))
        self._sync()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.title_lbl.setText(
            elide_lines(self._title, self.title_lbl.fontMetrics(), self.title_lbl.width(), 2)
        )

    # --- Estado ------------------------------------------------------
    def is_published(self) -> bool:
        return self._published

    def set_published(self, published: bool, emit: bool = True):
        self._published = bool(published)
        self._just_posted = False
        self._sync()
        if emit:
            self.published_changed.emit(self.index, self._published)

    def _sync(self):
        self.pub_chip.setVisible(self._published)
        self.act_publish.setText(
            "Desmarcar publicado" if self._published else "✓  Marcar como publicado"
        )
        if self._just_posted and not self._published:
            self.post_button.setText("✓ Marcar como publicado")
            self.post_button.setObjectName("MarkPublished")
            self.post_button.setToolTip("Clique depois de postar o corte")
        elif self._published:
            self.post_button.setText("Postar de novo ↗")
            self.post_button.setObjectName("Ghost")
            self.post_button.setToolTip(POST_TOOLTIP)
        else:
            self.post_button.setText("Postar ↗")
            self.post_button.setObjectName("PostButton")
            self.post_button.setToolTip(POST_TOOLTIP)
        self.setProperty("posted", "true" if self._just_posted else "false")
        for widget in (self, self.post_button):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    # --- Acoes -------------------------------------------------------
    def _on_primary(self):
        if self._just_posted and not self._published:
            self.set_published(True)
            return
        self.post()

    def post(self):
        from gui.projects_dialog import open_upload_pages

        target = self.path if self.file_exists else ""
        open_upload_pages(target)
        if not self._published:
            self._just_posted = True
            self._sync()
        self.posted.emit(self.path, self.index)

    def _toggle_published_from_menu(self):
        self.set_published(not self._published)

    def watch(self):
        if self.file_exists:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))

    def copy_title_description(self):
        if self._share_text:
            QApplication.clipboard().setText(self._share_text)
            self._notify("Título e descrição copiados")

    def copy_path(self):
        if self.path:
            QApplication.clipboard().setText(self.path)
            self._notify("Caminho do arquivo copiado")

    def reveal(self):
        from gui.projects_dialog import reveal_in_explorer

        if self.path:
            reveal_in_explorer(self.path)

    def _notify(self, text: str):
        host = self.window()
        toast = getattr(host, "toast", None)
        if toast is not None:
            toast.show_message(text, icon="✓", ms=2500)


def make_thumb_requester(owner: QWidget):
    """Gera thumbnails com um FrameLoader proprio (quando nao ha janela principal)."""
    from gui.thumbnails import FrameLoader, poster_pixmap

    loader = FrameLoader(owner)
    targets: dict[str, list] = {}

    def done(key, jpg):
        for button, text in targets.pop(key, []):
            if not jpg:
                continue
            try:
                button.setIcon(QIcon(poster_pixmap(
                    jpg, button.width(), button.height(), text, button.devicePixelRatioF()
                )))
                button.setIconSize(button.size())
                button.setText("")
            except RuntimeError:
                pass

    loader.loaded.connect(done)

    def request(button, clip_path: str, text: str):
        targets.setdefault("clip:" + clip_path, []).append((button, text))
        loader.request_clip_thumb(clip_path)

    return request
