from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QLineEdit
)

from core.config import OUTPUT_DIR
from gui.workers import PipelineWorker

LOG_MAX_LINES = 500


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoCortesBR")
        self.resize(720, 560)
        self.video_path = None
        self.worker = None

        self.settings = QSettings("AutoCortesBR", "AutoCortesBR")
        self.output_dir = self.settings.value("last_output_dir", str(OUTPUT_DIR))

        self.video_link = QLineEdit()
        self.video_link.setPlaceholderText("Cole o link do video aqui")

        self.select_button = QPushButton("Selecionar video")
        self.select_button.clicked.connect(self.select_video)

        self.process_button = QPushButton("Processar")
        #self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.process)

        self.output_button = QPushButton("Escolher pasta")
        self.output_button.clicked.connect(self.select_output_dir)

        self.path_label = QLabel("Nenhum video selecionado")
        self.path_label.setWordWrap(True)

        self.output_label = QLabel(self.output_dir)
        self.output_label.setWordWrap(True)

        self.stage_label = QLabel("Pronto")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(LOG_MAX_LINES)

        button_row = QHBoxLayout()
        button_row.addWidget(self.video_link)
        button_row.addWidget(self.select_button)
        button_row.addWidget(self.process_button)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_button)
        output_row.addWidget(self.output_label, 1)

        layout = QVBoxLayout()
        layout.addLayout(button_row)
        layout.addWidget(self.path_label)
        layout.addLayout(output_row)
        layout.addWidget(self.stage_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar video", "", "Videos (*.mp4 *.mkv *.mov *.avi)"
        )
        if file_path:
            self.video_path = file_path
            self.path_label.setText(file_path)
            #self.process_button.setEnabled(True)

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Escolher pasta de destino", self.output_dir
        )
        if folder:
            self.output_dir = folder
            self.output_label.setText(folder)
            self.settings.setValue("last_output_dir", folder)

    def process(self):
        self.set_busy(True)
        self.progress_bar.setValue(0)
        self.log_view.clear()

        self.worker = PipelineWorker(yt_link=self.video_link.text(), video_path=self.video_path, output_dir=self.output_dir)
        self.worker.stage_changed.connect(self.on_stage)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.message.connect(self.on_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def set_busy(self, busy):
        self.select_button.setEnabled(not busy)
        self.process_button.setEnabled(not busy)
        self.output_button.setEnabled(not busy)

    def on_stage(self, stage):
        self.stage_label.setText(stage)

    def on_log(self, line):
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def on_finished(self, result):
        self.set_busy(False)
        clips = result.get("clips", [])
        for clip in clips:
            self.log_view.appendPlainText(
                f"[{clip.get('start')} - {clip.get('end')}] "
                f"{clip.get('category', '')} ({clip.get('viral_score')}) "
                f"{clip.get('title', '')}"
            )
            self.log_view.appendPlainText(
                f"  Justificativa: {clip.get('justification', '')}"
            )
        self.log_view.appendPlainText(
            f"\nClipes salvos: {len(result.get('clip_paths', []))}"
        )
        self.stage_label.setText("Concluido")

    def on_failed(self, error):
        self.set_busy(False)
        self.stage_label.setText("Erro")
        self.log_view.appendPlainText(f"[ERRO] {error}")
        QMessageBox.critical(self, "Erro", error)
