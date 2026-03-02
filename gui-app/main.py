"""
Alzheimer's Risk Assessment Tool
Entry point
"""
import sys
import os
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Alzheimer's Risk Assessment")
    
    # Load global stylesheet
    with open("assets/styles.qss", "r") as f:
        app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
