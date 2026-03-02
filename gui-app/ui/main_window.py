"""
Main application window – hosts the sidebar and stacked pages.
"""
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QSizePolicy
)
from PyQt5.QtCore import Qt

from ui.dashboard_page import DashboardPage
from ui.intervention_page import InterventionPage
from ui.export_page import ExportPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alzheimer's Risk Assessment")
        self.setMinimumSize(1100, 700)
        self.resize(1200, 760)

        # ── Shared state ──────────────────────────────────────
        self.uploaded_data: dict = {}   # populated after file upload
        self.ad_risk: float = 15.0      # last computed risk %
        self.simulation_history: list = []

        # ── Root layout ───────────────────────────────────────
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────
        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        # ── Page stack ───────────────────────────────────────
        self.stack = QStackedWidget()
        self.dashboard_page = DashboardPage(self)
        self.intervention_page = InterventionPage(self)
        self.export_page = ExportPage(self)

        self.stack.addWidget(self.dashboard_page)    # index 0
        self.stack.addWidget(self.intervention_page) # index 1
        self.stack.addWidget(self.export_page)       # index 2

        root_layout.addWidget(self.stack, stretch=1)

    # ── Sidebar builder ──────────────────────────────────────
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(175)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setSpacing(4)

        buttons = [
            # ("UPLOAD DATA",           self._on_upload_data),
            ("GET AD RISK %",         self._on_get_risk),
            ("SIMULATE INTERVENTION", self._on_simulate),
            ("CLEAR ALL",             self._on_clear_all),
            # ("CLEAR LAST",            self._on_clear_last),
            ("HELP",                  self._on_help),
        ]

        for label, slot in buttons:
            btn = QPushButton(label)
            btn.setObjectName("SidebarBtn")
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        layout.addStretch(1)

        title = QLabel("Alzheimers\nRisk\nAssessment")
        title.setObjectName("AppTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        return sidebar

    # ── Sidebar actions ──────────────────────────────────────
    def _on_upload_data(self):
        """Delegate file upload to dashboard page."""
        self.stack.setCurrentIndex(0)
        self.dashboard_page.open_file_dialog()

    def _on_get_risk(self):
        self.stack.setCurrentIndex(0)
        self.dashboard_page.compute_risk()

    def _on_simulate(self):
        self.stack.setCurrentIndex(1)

    def _on_clear_all(self):
        self.uploaded_data = {}
        self.ad_risk = 0.0
        self.simulation_history = []
        self.dashboard_page.reset()
        self.intervention_page.reset()

    def _on_clear_last(self):
        if self.simulation_history:
            self.simulation_history.pop()
            self.intervention_page.refresh_chart()

    def _on_help(self):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Help",
            "1. Upload microbiome data via 'UPLOAD DATA'.\n"
            "2. Click 'GET AD RISK %' to compute your Alzheimer's risk score.\n"
            "3. Use 'SIMULATE INTERVENTION' to explore lifestyle changes.\n"
            "4. Visit the Export page to generate a report.\n\n"
            "Supported file formats: CSV, TSV, JSON."
        )
