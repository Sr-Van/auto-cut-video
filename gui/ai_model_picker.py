"""Seletor do modelo de IA, montado a partir das API keys configuradas.

Mostra na hora os modelos do catalogo de cada provedor das chaves do .env e,
em segundo plano, consulta `/models` de cada provedor para listar o que a
chave realmente enxerga. O valor e "provedor:modelo" ("" = automatico).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QWidget

from core.config import API_KEYS
from core.providers import list_available_models

AUTO_LABEL = "Automático · alterna modelos e chaves"


class _Signals(QObject):
    done = Signal(object)


class _FetchJob(QRunnable):
    def __init__(self, keys: list[str]):
        super().__init__()
        self.keys = list(keys)
        self.signals = _Signals()

    def run(self):  # noqa: D401 - roda no pool
        try:
            groups = list_available_models(self.keys, live=True)
        except Exception:
            groups = None
        self.signals.done.emit(groups)


class AIModelPicker(QWidget):
    changed = Signal()

    def __init__(self, keys: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._keys = list(API_KEYS if keys is None else keys)
        self._value = ""
        self._pool = QThreadPool(self)
        self._job: _FetchJob | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.combo = QComboBox()
        self.combo.setMaxVisibleItems(16)
        self.combo.currentIndexChanged.connect(self._on_index_changed)
        layout.addWidget(self.combo, 1)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Buscar a lista de modelos de cada provedor")
        self.refresh_btn.setFixedWidth(36)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_btn)

        self._populate(list_available_models(self._keys, live=False))
        if self._keys:
            self.refresh()
        else:
            self.combo.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.combo.setToolTip("Nenhuma API key no .env")

    # --- valor -----------------------------------------------------------
    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = (value or "").strip()
        self._select_value()

    # --- lista -----------------------------------------------------------
    def refresh(self) -> None:
        if self._job is not None:
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("…")
        self._job = _FetchJob(self._keys)
        self._job.signals.done.connect(self._on_fetched)
        self._pool.start(self._job)

    def _on_fetched(self, groups) -> None:
        self._job = None
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("↻")
        if groups:
            self._populate(groups)

    def _populate(self, groups) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(AUTO_LABEL, "")
        model = self.combo.model()
        for provider_id, name, models in groups:
            header = QStandardItem(f"── {name} ──")
            header.setFlags(Qt.NoItemFlags)
            model.appendRow(header)
            for m in models:
                self.combo.addItem(f"   {m}", f"{provider_id}:{m}")
        self.combo.blockSignals(False)
        self._select_value()

    def _select_value(self) -> None:
        self.combo.blockSignals(True)
        idx = self.combo.findData(self._value) if self._value else 0
        if idx < 0:
            # modelo salvo que a lista atual nao trouxe: mantem visivel
            self.combo.addItem(f"   {self._value}", self._value)
            idx = self.combo.count() - 1
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)

    def _on_index_changed(self, _idx: int) -> None:
        data = self.combo.currentData()
        if data is None:  # cabecalho
            return
        self._value = str(data)
        self.changed.emit()
