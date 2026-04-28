"""
Axis – entry point.

Run:
    python main.py
"""

import path_setup   # must be first — adds project root to sys.path

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore    import Qt
from ui.main_window  import MainWindow
from src.pipeline.install_dependencies import ensure_env


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Axis")
    #app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()