"""Controlador responsavel por persistir opcoes e orquestrar o PipelineWorker."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, QSettings, Signal

from core.config import OUTPUT_DIR
from core.options import ProcessingOptions
from gui.workers import PipelineWorker


class PipelineController(QObject):
    progress = Signal(int)
    stage_changed = Signal(str)
    message = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, parent: QObject | None = None, settings: QSettings | None = None):
        super().__init__(parent)
        self.settings = settings or QSettings("AutoCortesBR", "AutoCortesBR")
        self.worker: PipelineWorker | None = None
        self.cancel_event: Event | None = None

    def load_output_dir(self) -> str:
        return str(self.settings.value("last_output_dir", str(OUTPUT_DIR)))

    def save_output_dir(self, folder: str) -> None:
        folder = (folder or "").strip()
        if folder:
            self.settings.setValue("last_output_dir", folder)

    def reset_output_dir(self) -> str:
        default_dir = str(OUTPUT_DIR)
        self.settings.setValue("last_output_dir", default_dir)
        return default_dir

    def load_options(self) -> ProcessingOptions:
        raw = self.settings.value("processing_options", "")
        return ProcessingOptions.from_json(raw)

    def save_options(self, options: ProcessingOptions) -> None:
        self.settings.setValue("processing_options", options.to_json())

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def start_pipeline(
        self,
        *,
        yt_link: str,
        video_path: str | None,
        output_dir: str,
        options: ProcessingOptions,
    ) -> PipelineWorker:
        self.save_options(options)
        self.save_output_dir(output_dir)

        self.cancel_event = Event()
        self.worker = PipelineWorker(
            yt_link=yt_link,
            video_path=video_path,
            output_dir=output_dir,
            options=options,
            cancel_event=self.cancel_event,
            parent=self,
        )
        self.worker.stage_changed.connect(self.stage_changed)
        self.worker.progress.connect(self.progress)
        self.worker.message.connect(self.message)
        self.worker.finished.connect(self.finished)
        self.worker.failed.connect(self.failed)
        self.worker.cancelled.connect(self.cancelled)
        self.worker.start()
        return self.worker

    def cancel_pipeline(self) -> bool:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            return True
        return False

