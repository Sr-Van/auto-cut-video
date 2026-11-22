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
    review_requested = Signal(object)

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
        self._review_event = Event()
        self._reviewed_clips: list[dict] | None = None

    def cancel(self) -> None:
        """Sinaliza cancelamento cooperativo para o pipeline em execucao."""
        self.cancel_event.set()
        self._review_event.set()

    def submit_review(self, clips: list[dict] | None) -> None:
        """Entrega os cortes aprovados pela GUI e libera a thread do pipeline."""
        self._reviewed_clips = clips
        self._review_event.set()

    def _on_review_needed(self, clips: list[dict]) -> list[dict] | None:
        self._review_event.clear()
        self._reviewed_clips = None
        self.review_requested.emit(clips)
        while not self._review_event.is_set() and not self.cancel_event.is_set():
            self._review_event.wait(timeout=0.2)
        if self.cancel_event.is_set():
            return None
        return self._reviewed_clips

    def run(self):
        try:
            def on_progress(stage, percent, msg):
                self.stage_changed.emit(stage)
                self.progress.emit(percent)
                self.message.emit(f"[{percent:3d}%] {stage}: {msg}")

            review_cb = (
                self._on_review_needed
                if getattr(self.options, "review_before_render", False)
                else None
            )

            result = run(
                self.yt_link,
                self.video_path,
                output_dir=self.output_dir,
                progress_callback=on_progress,
                options=self.options,
                cancel_event=self.cancel_event,
                review_callback=review_cb,
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
