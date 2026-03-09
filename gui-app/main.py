"""
gui-app/main.py
────────────────
Entry point for the Alzheimer's Risk Assessment GUI.

CRITICAL IMPORT ORDER
─────────────────────
path_setup must be imported FIRST.  It patches sys.path so that both
    from utils.data_loader import load_file
    from src.services.assessment_service import ...
resolve correctly from anywhere you run the script.
"""
import sys

# ── 1. Fix sys.path before ANY local imports ──────────────────────────────────
import path_setup   # noqa: F401  (side-effect import — must stay first)

# ── 2. Now safe to import Qt and local modules ────────────────────────────────
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Alzheimer's Risk Assessment")

    try:
        with open("assets/styles.qss", "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        pass  # styles are cosmetic — missing file should not crash the app

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()