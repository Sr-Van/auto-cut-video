import sys

from PySide6.QtWidgets import QApplication

from core.captions.fonts import register_bundled_fonts
from gui.main_window import MainWindow
from gui.theme import apply_theme


def main():
    app = QApplication(sys.argv)
    register_bundled_fonts()
    apply_theme(app)
    app.setProperty("theme_applied", True)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
