from PySide6.QtCore import QThread, Signal

from core.pipeline import run


class PipelineWorker(QThread):
    progress = Signal(int)
    stage_changed = Signal(str)
    message = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, yt_link, video_path, output_dir=None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.output_dir = output_dir
        self.yt_link = yt_link

    def run(self):
        try:
            def on_progress(stage, percent, msg):
                self.stage_changed.emit(stage)
                self.progress.emit(percent)
                self.message.emit(f"[{percent:3d}%] {stage}: {msg}")

            result = run(self.yt_link, self.video_path, output_dir=self.output_dir, progress_callback=on_progress)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
