"""
Dashboard Page  (Figure 1)
─────────────────────────
Layout:
  Top-left  : Risk of AD  (big % badge)
  Top-right : Phylogeny of Microbiome Taxa  (tree canvas)
  Bot-left  : Uploaded Data  (text + drag-drop)
  Bot-right : Taxa Abundance  (bar chart)
"""
import os, random
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QTextEdit, QPushButton, QFileDialog,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QMimeData, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QFont

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np


# ── Phylogeny Tree Widget ────────────────────────────────────
class PhylogenyCanvas(QWidget):
    """Minimal cladogram rendered with QPainter."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.taxa = list("ABCDEFGH")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#1a2a4a"), 2)
        p.setPen(pen)

        w, h = self.width(), self.height()
        margin_right = 30
        margin_top   = 20
        n = len(self.taxa)
        row_h = (h - margin_top * 2) / (n - 1)

        # leaf y positions
        leaf_x = w - margin_right - 10
        leaf_ys = [margin_top + i * row_h for i in range(n)]

        # Simple symmetric bifurcating tree
        # We'll draw horizontal lines to a ladder structure
        levels = [
            (0, 1), (2, 3), (4, 5), (6, 7),
            (0, 3), (4, 7),
            (0, 7),
        ]
        current_mid_x = {}

        # draw leaf labels
        font = QFont("Segoe UI", 9)
        p.setFont(font)
        for i, taxon in enumerate(self.taxa):
            p.drawText(int(leaf_x) + 4, int(leaf_ys[i]) + 4, taxon)

        # horizontal lines from leaf to a step
        step = (w - margin_right - 60) / 4
        for i in range(n):
            x_conn = leaf_x - step
            p.drawLine(int(x_conn), int(leaf_ys[i]), int(leaf_x), int(leaf_ys[i]))
            current_mid_x[i] = x_conn

        # pair up repeatedly
        nodes = {i: (current_mid_x[i], leaf_ys[i]) for i in range(n)}
        node_id = n
        pairs = [(0,1),(2,3),(4,5),(6,7),(8,9),(10,11),(12,13)]
        active = list(range(n))
        level_dx = step

        while len(active) > 1:
            new_active = []
            i = 0
            while i < len(active) - 1:
                a, b = active[i], active[i+1]
                ax, ay = nodes[a]
                bx, by = nodes[b]
                parent_x = min(ax, bx) - level_dx
                parent_y = (ay + by) / 2
                # vertical connector
                p.drawLine(int(ax), int(ay), int(ax), int(by))
                # horizontal lines to parent
                p.drawLine(int(parent_x), int(parent_y), int(ax), int(ay))
                p.drawLine(int(parent_x), int(parent_y), int(ax), int(by))
                nodes[node_id] = (parent_x, parent_y)
                new_active.append(node_id)
                node_id += 1
                i += 2
            if len(active) % 2 == 1:
                new_active.append(active[-1])
            active = new_active
            level_dx = max(level_dx - 5, 5)

        p.end()


# ── Drag-and-drop Upload Widget ──────────────────────────────
class UploadDropArea(QLabel):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setText("📂  Drag-and-drop Data Here...")
        self.setObjectName("UploadHint")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(100)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            self.file_dropped.emit(url.toLocalFile())
            break


# ── Taxa Abundance bar chart ─────────────────────────────────
class TaxaAbundanceChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 3), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._draw_placeholder()

    def _draw_placeholder(self):
        ax = self.fig.add_subplot(111)
        categories = [
            "Prepreg.", "Pregnancy", "Birth", "Postnatal",
            "Infancy", "Childhood", "Other"
        ]
        colours = ["#e07070","#e09050","#e0c050","#70c080",
                   "#7090e0","#9070c0","#c0c0c0"]
        for i, (cat, col) in enumerate(zip(categories, colours)):
            vals = np.random.uniform(20, 80, 14)
            ax.bar(np.arange(14) + i * 0.12, vals, width=0.12,
                   color=col, label=cat, alpha=0.8)

        ax.set_ylabel("Coverage (%)", fontsize=8)
        ax.set_xticks([])
        ax.tick_params(labelsize=7)
        ax.legend(fontsize=6, loc="upper right", ncol=2)
        self.fig.patch.set_facecolor("white")
        ax.set_facecolor("white")
        self.draw()

    def update_data(self, data: dict):
        """Redraw with real uploaded data."""
        self.fig.clear()
        self._draw_placeholder()


# ── Dashboard Page ───────────────────────────────────────────
class DashboardPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app = app_state
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)

        # ── Top-left: Risk of AD ──────────────────────────────
        risk_card = self._card("Risk of AD")
        self.risk_label = QLabel("15%")
        self.risk_label.setObjectName("RiskDisplay")
        self.risk_label.setAlignment(Qt.AlignCenter)
        risk_card.layout().addWidget(self.risk_label)
        grid.addWidget(risk_card, 0, 0)

        # ── Top-right: Phylogeny ──────────────────────────────
        phylo_card = self._card("Phylogeny of Microbiome Taxa", toggle=True)
        self.phylo_canvas = PhylogenyCanvas()
        phylo_card.layout().addWidget(self.phylo_canvas)
        grid.addWidget(phylo_card, 0, 1)

        # ── Bottom-left: Uploaded Data ────────────────────────
        data_card = self._card("Uploaded Data")
        self.data_text = QTextEdit()
        self.data_text.setObjectName("DataDisplay")
        self.data_text.setReadOnly(True)
        self.data_text.setPlaceholderText("summary statistics about microbiome will appear here")
        self.data_text.setMaximumHeight(80)

        self.drop_area = UploadDropArea()
        self.drop_area.file_dropped.connect(self._load_file)

        browse_btn = QPushButton("Browse File…")
        browse_btn.setObjectName("ActionBtn")
        browse_btn.setMaximumWidth(120)
        browse_btn.clicked.connect(self.open_file_dialog)

        data_card.layout().addWidget(self.data_text)
        data_card.layout().addWidget(self.drop_area)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(browse_btn)
        data_card.layout().addLayout(btn_row)

        grid.addWidget(data_card, 1, 0)

        # ── Bottom-right: Taxa Abundance ──────────────────────
        taxa_card = self._card("Taxa Abundance")
        self.taxa_chart = TaxaAbundanceChart()
        taxa_card.layout().addWidget(self.taxa_chart)
        grid.addWidget(taxa_card, 1, 1)

        # Equal column widths, equal row heights
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        outer.addLayout(grid)

    # ── Card helper ──────────────────────────────────────────
    @staticmethod
    def _card(title: str, toggle: bool = False) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(8, 6, 8, 8)
        vbox.setSpacing(4)

        header = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setObjectName("CardTitle")
        header.addWidget(lbl)
        header.addStretch()

        if toggle:
            tog = QPushButton("☀")
            tog.setObjectName("ToggleBtn")
            tog.setCheckable(True)
            header.addWidget(tog)

        vbox.addLayout(header)
        return card

    # ── File handling ────────────────────────────────────────
    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Microbiome Data",
            "", "Data Files (*.csv *.tsv *.json *.txt);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            size = os.path.getsize(path)
            name = os.path.basename(path)
            summary = (
                f"File: {name}\n"
                f"Size: {size / 1024:.1f} KB\n"
                f"Path: {path}\n\n"
                "Processing… (plug in your parser here)"
            )
            self.data_text.setPlainText(summary)
            self.app.uploaded_data = {"path": path, "name": name}
            self.drop_area.setText(f"✓ Loaded: {name}")
        except Exception as e:
            self.data_text.setPlainText(f"Error loading file:\n{e}")

    # ── Risk computation ─────────────────────────────────────
    def compute_risk(self):
        """
        Placeholder model – replace with your real ML inference call.
        """
        if not self.app.uploaded_data:
            self.risk_label.setText("No Data")
            return
        risk = round(random.uniform(5, 85), 1)
        self.app.ad_risk = risk
        self.risk_label.setText(f"{risk}%")

    # ── Reset ─────────────────────────────────────────────────
    def reset(self):
        self.risk_label.setText("0%")
        self.data_text.clear()
        self.drop_area.setText("📂  Drag-and-drop Data Here...")
        self.app.ad_risk = 0.0
