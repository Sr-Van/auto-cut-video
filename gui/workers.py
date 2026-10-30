from threading import Event

from PySide6.QtCore import QThread, Signal

from core.exceptions import PipelineCancelledError
from core.options import ProcessingOptions
from core.pipeline import run


class PipelineWorker(QThread):
    progress = Signal(int)
    stage_changed = Signal(str)
    message = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(
        self,
        yt_link,
        video_path,
        output_dir=None,
        options=None,
        cancel_event: Event | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.video_path = video_path
        self.output_dir = output_dir
        self.yt_link = yt_link
        self.options = options or ProcessingOptions.from_env_or_config()
        self.cancel_event = cancel_event or Event()

    def cancel(self) -> None:
        """Sinaliza cancelamento cooperativo para o pipeline em execucao."""
        self.cancel_event.set()

    def run(self):
        try:
            def on_progress(stage, percent, msg):
                self.stage_changed.emit(stage)
                self.progress.emit(percent)
                self.message.emit(f"[{percent:3d}%] {stage}: {msg}")

            result = run(
                self.yt_link,
                self.video_path,
                output_dir=self.output_dir,
                progress_callback=on_progress,
                options=self.options,
                cancel_event=self.cancel_event,
            )
            if self.cancel_event.is_set():
                self.cancelled.emit("Processamento cancelado pelo usuário.")
                return
            self.finished.emit(result)
        except PipelineCancelledError as exc:
            self.cancelled.emit(str(exc))
        except Exception as exc:
            if self.cancel_event.is_set():
                self.cancelled.emit("Processamento cancelado pelo usuário.")
            else:
                self.failed.emit(str(exc))
