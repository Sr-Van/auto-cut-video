from PySide6.QtCore import QThread, Signal

from core.pipeline import run


class PipelineWorker(QThread):
    progress = Signal(int)
    stage_changed = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self.video_path = video_path

    def run(self):
        try:
            def on_progress(stage, percent, message):
                self.stage_changed.emit(stage)
                self.progress.emit(percent)

            result = run(self.video_path, progress_callback=on_progress)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
