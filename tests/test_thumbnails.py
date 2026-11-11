import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from gui import thumbnails


class ThumbnailPathsTest(unittest.TestCase):
    def test_clip_thumb_fica_no_cache_oculto_do_projeto(self):
        path = thumbnails.clip_thumb_path("C:/saida/proj/corte 1.mp4")
        self.assertEqual(path.parent.name, "thumbs")
        self.assertEqual(path.parent.parent.name, ".cache")
        self.assertEqual(path.name, "corte 1.jpg")

    def test_preview_frame_fica_no_temp_do_sistema(self):
        path = thumbnails.preview_frame_path("C:/nao/existe.mp4")
        self.assertEqual(path.parent, thumbnails.PREVIEW_CACHE_DIR)
        self.assertEqual(path.suffix, ".jpg")

    def test_extract_frame_falha_sem_arquivo(self):
        self.assertFalse(
            thumbnails.extract_frame("C:/nao/existe.mp4", Path("x.jpg"), 1.0, 100)
        )


class PosterPixmapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_poster_tem_tamanho_do_card(self):
        img = QImage(64, 36, QImage.Format_RGB32)
        img.fill(QColor("#336699"))
        tmp = Path(os.environ.get("TEMP", ".")) / "autocortes_test_frame.jpg"
        img.save(str(tmp))
        try:
            pm = thumbnails.poster_pixmap(str(tmp), 54, 96, "#1")
            self.assertEqual((pm.width(), pm.height()), (54, 96))
        finally:
            tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
