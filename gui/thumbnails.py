"""Frames reais do video para a previa 9:16 e miniaturas dos cortes.

A extracao roda em segundo plano (QThreadPool) com um unico `ffmpeg` por
imagem e fica em cache em disco, entao a interface nunca trava esperando.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

PREVIEW_CACHE_DIR = Path(tempfile.gettempdir()) / "autocortes_preview"


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def extract_frame(video_path: str, out_path: Path, at_s: float, max_width: int) -> bool:
    """Grava um JPG do frame em `at_s` (cai para 0s se o video for mais curto)."""
    ffmpeg = _ffmpeg()
    if not ffmpeg or not Path(video_path).is_file():
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for seek in (at_s, 0.0) if at_s > 0 else (0.0,):
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{seek:.2f}", "-i", str(video_path),
            "-frames:v", "1",
            "-vf", f"scale='min({max_width},iw)':-2",
            "-q:v", "4",
            str(out_path),
        ]
        try:
            subprocess.run(
                cmd, capture_output=True, timeout=30, creationflags=_NO_WINDOW
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if out_path.is_file() and out_path.stat().st_size > 0:
            return True
    return False


def _fresh(cache: Path, source: Path) -> bool:
    try:
        return cache.is_file() and cache.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def preview_frame_path(video_path: str) -> Path:
    """Cache da previa fora da pasta do usuario (temp do sistema)."""
    p = Path(video_path)
    try:
        stamp = f"{p.resolve()}|{p.stat().st_size}|{p.stat().st_mtime_ns}"
    except OSError:
        stamp = str(p)
    digest = hashlib.sha1(stamp.encode("utf-8")).hexdigest()[:16]
    return PREVIEW_CACHE_DIR / f"{digest}.jpg"


def clip_thumb_path(clip_path: str) -> Path:
    """Miniatura ao lado do corte, na pasta oculta .cache que o pipeline ja usa."""
    p = Path(clip_path)
    return p.parent / ".cache" / "thumbs" / f"{p.stem}.jpg"


class _Job(QRunnable):
    def __init__(self, loader: "FrameLoader", key: str, video: str, out: Path,
                 at_s: float, max_width: int):
        super().__init__()
        self.loader, self.key, self.video = loader, key, video
        self.out, self.at_s, self.max_width = out, at_s, max_width

    def run(self):
        ok = _fresh(self.out, Path(self.video)) or extract_frame(
            self.video, self.out, self.at_s, self.max_width
        )
        try:
            self.loader.loaded.emit(self.key, str(self.out) if ok else "")
        except RuntimeError:  # loader destruido ao fechar a janela
            pass


class FrameLoader(QObject):
    """Dispara extracoes em paralelo e avisa via `loaded(key, jpg_path)`."""

    loaded = Signal(str, str)

    def __init__(self, parent=None, max_threads: int = 2):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max_threads)
        self._pending: set[str] = set()
        self.loaded.connect(lambda key, _p: self._pending.discard(key))

    def request(self, key: str, video: str, out: Path, at_s: float, max_width: int):
        if _fresh(out, Path(video)):
            self.loaded.emit(key, str(out))
            return
        if key in self._pending:
            return
        self._pending.add(key)
        self.pool.start(_Job(self, key, video, out, at_s, max_width))

    def request_preview(self, video: str):
        self.request("preview:" + video, video, preview_frame_path(video), 8.0, 720)

    def request_clip_thumb(self, clip: str):
        self.request("clip:" + clip, clip, clip_thumb_path(clip), 3.0, 360)


def poster_pixmap(jpg_path: str, width: int, height: int, label: str = "",
                  dpr: float = 1.0) -> QPixmap:
    """Recorte 'cover' do frame no tamanho do card, com selo de play e numero."""
    image = QImage(jpg_path)
    pm = QPixmap(int(width * dpr), int(height * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, width, height), 6, 6)
    painter.setClipPath(clip)
    if not image.isNull():
        scaled = image.scaled(
            int(width * dpr), int(height * dpr),
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
        )
        sx = (scaled.width() - width * dpr) / 2
        sy = (scaled.height() - height * dpr) / 2
        painter.drawImage(
            QRectF(0, 0, width, height),
            scaled,
            QRectF(sx, sy, width * dpr, height * dpr),
        )
    else:
        painter.fillRect(QRectF(0, 0, width, height), QColor("#1A1A1A"))
    # Escurece levemente para o selo ficar legivel
    painter.fillRect(QRectF(0, 0, width, height), QColor(0, 0, 0, 70))
    r = min(width, height) * 0.2
    cx, cy = width / 2, height / 2
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(245, 196, 0, 235))
    painter.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
    tri = QPainterPath()
    tri.moveTo(cx - r * 0.32, cy - r * 0.45)
    tri.lineTo(cx - r * 0.32, cy + r * 0.45)
    tri.lineTo(cx + r * 0.5, cy)
    tri.closeSubpath()
    painter.setBrush(QColor("#121212"))
    painter.drawPath(tri)
    if label:
        font = QFont()
        font.setPixelSize(max(9, int(height * 0.09)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#F5F5F4"))
        painter.drawText(
            QRectF(0, height - font.pixelSize() * 1.9, width, font.pixelSize() * 1.6),
            Qt.AlignCenter, label,
        )
    painter.end()
    return pm


__all__ = [
    "FrameLoader",
    "clip_thumb_path",
    "extract_frame",
    "poster_pixmap",
    "preview_frame_path",
]
