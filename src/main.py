"""
GutSeq – entry point.

Run:
    python main.py
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore    import Qt
from ui.main_window  import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("GutSeq")
    #app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()