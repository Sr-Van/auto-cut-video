"""Dialogo de revisao pre-render para aprovar e ajustar tempos dos cortes."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from utils.timefmt import hhmmss_to_seconds, seconds_to_hhmmss


def format_clip_share_text(clip: dict) -> str:
    """Formata titulo e descricao/resumo do corte para colar em YouTube/TikTok/Reels."""
    title = str(clip.get("title") or "").strip()
    desc = str(clip.get("description") or clip.get("reason") or "").strip()
    if title and desc:
        return f"{title}\n\n{desc}"
    return title or desc


class ClipReviewDialog(QDialog):
    """Permite aprovar/descartar cortes e ajustar inicio/fim antes da renderizacao."""

    def __init__(self, clips: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revisar cortes antes de renderizar")
        self.setMinimumSize(680, 440)
        self._clips = [dict(c) for c in clips]
        self._rows: list[tuple[QCheckBox, QDoubleSpinBox, QDoubleSpinBox, dict]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        intro = QLabel(
            "Desmarque os cortes que deseja descartar ou ajuste fino de início/fim (em segundos) "
            "antes de iniciar a renderização."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(10)

        for idx, clip in enumerate(self._clips, 1):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(10)

            cb = QCheckBox(f"#{idx} · {clip.get('title', f'Corte {idx}')}")
            cb.setChecked(True)
            row_layout.addWidget(cb, 1)

            score_lbl = QLabel(f"★ {clip.get('viral_score', '-')}")
            row_layout.addWidget(score_lbl)

            start_s = self._to_seconds(clip.get("start", "00:00:00"))
            end_s = self._to_seconds(clip.get("end", "00:00:30"))

            start_spin = QDoubleSpinBox()
            start_spin.setRange(0.0, 86400.0)
            start_spin.setDecimals(1)
            start_spin.setSingleStep(1.0)
            start_spin.setSuffix("s")
            start_spin.setValue(start_s)
            start_spin.setToolTip("Início do corte em segundos")
            row_layout.addWidget(QLabel("Início:"))
            row_layout.addWidget(start_spin)

            end_spin = QDoubleSpinBox()
            end_spin.setRange(0.5, 86400.0)
            end_spin.setDecimals(1)
            end_spin.setSingleStep(1.0)
            end_spin.setSuffix("s")
            end_spin.setValue(max(start_s + 1.0, end_s))
            end_spin.setToolTip("Fim do corte em segundos")
            row_layout.addWidget(QLabel("Fim:"))
            row_layout.addWidget(end_spin)

            self._rows.append((cb, start_spin, end_spin, clip))
            body_layout.addWidget(row_widget)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        confirm_btn = QPushButton("Renderizar selecionados")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(self.accept)
        footer.addWidget(confirm_btn)
        root.addLayout(footer)

    @staticmethod
    def _to_seconds(val) -> float:
        try:
            return float(hhmmss_to_seconds(str(val)))
        except Exception:
            return 0.0

    def selected_clips(self) -> list[dict]:
        """Retorna os cortes marcados com start/end atualizados."""
        result: list[dict] = []
        for cb, start_spin, end_spin, clip in self._rows:
            if not cb.isChecked():
                continue
            s = float(start_spin.value())
            e = float(end_spin.value())
            if e <= s:
                e = s + 1.0
            updated = dict(clip)
            updated["start"] = seconds_to_hhmmss(s)
            updated["end"] = seconds_to_hhmmss(e)
            result.append(updated)
        return result
