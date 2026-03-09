"""
gui-app/ui/dashboard_page.py
─────────────────────────────
SERVICE CALL SEQUENCE (the contract with assessment_service.py)
───────────────────────────────────────────────────────────────
Step 1 — User drops / browses a file:
    result = load_file(path)            ← utils/data_loader.py  (pure parse, no DB)
    taxa   = result["taxa"]             ← dict[str, float], values sum to 1.0
    store on app state for later

Step 2 — User clicks GET AD RISK %:
    mb = store_microbiome_upload(       ← assessment_service  (writes MicrobiomeData row)
        project_id = app.current_project_id,
        file_path  = path,
        taxa       = taxa,              ← the dict from step 1
    )
    # mb["microbiome_id"] is now in the DB

    result = compute_and_store_risk(    ← assessment_service  (reads latest microbiome,
        project_id = app.current_project_id,   runs model_fn, writes RiskAssessment)
        model_fn   = stub_model_fn,
    )
    # result["risk_probability"] → float 0-100
    # result["risk_label"]       → "Low" | "Moderate" | "High"

Note: store_microbiome_upload and compute_and_store_risk are separate calls
because the service reads the *latest* microbiome from the DB.  Always call
store first, then compute.

FALLBACK (no DB / no project_id set yet)
─────────────────────────────────────────
If ServiceError or ImportError is raised the page falls back to
_compute_risk_stub() which runs the model directly on the in-memory taxa.
This lets the GUI work during development without a live database.
"""
from __future__ import annotations

import os
from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QTextEdit, QPushButton, QFileDialog,
    QSizePolicy, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QFont

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np


# ── Phylogeny Tree Widget ─────────────────────────────────────────────────────
class PhylogenyCanvas(QWidget):
    """Cladogram rendered with QPainter. Taxa names update after file upload."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.taxa: list[str] = list("ABCDEFGH")

    def set_taxa(self, names: list[str]):
        self.taxa = [t[:18] for t in names[:12]]
        self.repaint()

    def paintEvent(self, event):
        if len(self.taxa) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#1a2a4a"), 2))

        w, h = self.width(), self.height()
        n = len(self.taxa)
        margin_top   = 20
        margin_right = 12
        row_h = (h - margin_top * 2) / max(n - 1, 1)

        max_label_px = max(len(t) for t in self.taxa) * 7 + 8
        leaf_x  = w - margin_right - max_label_px
        leaf_ys = [margin_top + i * row_h for i in range(n)]

        font = QFont("Segoe UI", 8)
        p.setFont(font)
        for i, taxon in enumerate(self.taxa):
            p.drawText(int(leaf_x) + 4, int(leaf_ys[i]) + 4, taxon)

        step = max((leaf_x - 20) / 4, 10)
        for i in range(n):
            p.drawLine(int(leaf_x - step), int(leaf_ys[i]),
                       int(leaf_x),         int(leaf_ys[i]))

        nodes   = {i: (leaf_x - step, leaf_ys[i]) for i in range(n)}
        node_id = n
        active  = list(range(n))
        level_dx = step

        while len(active) > 1:
            new_active = []
            i = 0
            while i < len(active) - 1:
                a, b   = active[i], active[i + 1]
                ax_, ay = nodes[a]
                bx_, by = nodes[b]
                px = min(ax_, bx_) - level_dx
                py = (ay + by) / 2
                p.drawLine(int(ax_), int(ay), int(ax_), int(by))
                p.drawLine(int(px),  int(py), int(ax_), int(ay))
                p.drawLine(int(px),  int(py), int(ax_), int(by))
                nodes[node_id] = (px, py)
                new_active.append(node_id)
                node_id += 1
                i += 2
            if len(active) % 2 == 1:
                new_active.append(active[-1])
            active   = new_active
            level_dx = max(level_dx - 5, 5)

        p.end()


# ── Drag-and-drop Upload Widget ───────────────────────────────────────────────
class UploadDropArea(QLabel):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setText("📂  Drag-and-drop Data Here...")
        self.setObjectName("UploadHint")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(80)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            self.file_dropped.emit(url.toLocalFile())
            break


# ── Taxa Abundance bar chart ──────────────────────────────────────────────────
class TaxaAbundanceChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 3), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._draw_placeholder()

    def _draw_placeholder(self):
        ax = self.fig.add_subplot(111)
        ax.text(0.5, 0.5, "Upload data to view taxa abundance",
                ha="center", va="center", color="#aaa", fontsize=10,
                transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_facecolor("white")
        self.fig.patch.set_facecolor("white")
        for spine in ax.spines.values():
            spine.set_visible(False)
        self.draw()

    def update_data(self, taxa: dict[str, float]):
        """Redraw with real taxa proportions (values are 0-1 proportions)."""
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        sorted_taxa = sorted(taxa.items(), key=lambda x: x[1], reverse=True)[:20]
        names  = [t[0] for t in sorted_taxa]
        values = [t[1] * 100 for t in sorted_taxa]

        palette = [
            "#e07070","#e09050","#e0c050","#70c080","#7090e0",
            "#9070c0","#c0c0c0","#50b0c0","#d08040","#80c060",
            "#c06080","#6080d0","#a0a040","#40c090","#d06060",
            "#7060a0","#b09030","#509070","#c07050","#6090b0",
        ]
        colours = [palette[i % len(palette)] for i in range(len(names))]

        ax.barh(names, values, color=colours, alpha=0.85)
        ax.set_xlabel("Relative Abundance (%)", fontsize=8)
        ax.tick_params(axis="y", labelsize=7)
        ax.tick_params(axis="x", labelsize=7)
        ax.set_facecolor("white")
        self.fig.patch.set_facecolor("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self.draw()


# ── Dashboard Page ────────────────────────────────────────────────────────────
class DashboardPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app = app_state
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)

        # Top-left – Risk badge
        risk_card = self._card("Risk of AD")
        self.risk_label = QLabel("—")
        self.risk_label.setObjectName("RiskDisplay")
        self.risk_label.setAlignment(Qt.AlignCenter)
        self.risk_label.setToolTip(
            "Upload data and click 'GET AD RISK %' to compute.")
        risk_card.layout().addWidget(self.risk_label)
        grid.addWidget(risk_card, 0, 0)

        # Top-right – Phylogeny
        phylo_card = self._card("Phylogeny of Microbiome Taxa", toggle=True)
        self.phylo_canvas = PhylogenyCanvas()
        phylo_card.layout().addWidget(self.phylo_canvas)
        grid.addWidget(phylo_card, 0, 1)

        # Bottom-left – Uploaded Data
        data_card = self._card("Uploaded Data")
        self.data_text = QTextEdit()
        self.data_text.setObjectName("DataDisplay")
        self.data_text.setReadOnly(True)
        self.data_text.setPlaceholderText(
            "Summary statistics about microbiome will appear here after upload.")
        self.data_text.setMaximumHeight(100)

        self.drop_area = UploadDropArea()
        self.drop_area.file_dropped.connect(self._load_file)

        browse_btn = QPushButton("Browse File…")
        browse_btn.setObjectName("ActionBtn")
        browse_btn.setMaximumWidth(130)
        browse_btn.clicked.connect(self.open_file_dialog)

        data_card.layout().addWidget(self.data_text)
        data_card.layout().addWidget(self.drop_area)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(browse_btn)
        data_card.layout().addLayout(btn_row)
        grid.addWidget(data_card, 1, 0)

        # Bottom-right – Taxa Abundance chart
        taxa_card = self._card("Taxa Abundance")
        self.taxa_chart = TaxaAbundanceChart()
        taxa_card.layout().addWidget(self.taxa_chart)
        grid.addWidget(taxa_card, 1, 1)

        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1);    grid.setRowStretch(1, 1)
        outer.addLayout(grid)

    @staticmethod
    def _card(title: str, toggle: bool = False) -> QFrame:
        card  = QFrame()
        card.setObjectName("Card")
        vbox  = QVBoxLayout(card)
        vbox.setContentsMargins(8, 6, 8, 8)
        vbox.setSpacing(4)
        header = QHBoxLayout()
        lbl    = QLabel(title)
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

    # ── Step 1: parse file with data_loader (no DB) ───────────────────────────
    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Microbiome Data", "",
            "Data Files (*.csv *.tsv *.json *.txt);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        # Import here (not at top of module) so the file can be imported
        # even if the utils package path isn't set up yet during testing.
        from utils.data_loader import load_file

        result = load_file(path)

        # Always display whatever the loader produced (summary or error message)
        self.data_text.setPlainText(result["summary"])

        if result["error"]:
            QMessageBox.warning(self, "Parse Error", result["summary"])
            self.drop_area.setText("⚠  Parse failed – try another file")
            return

        taxa = result["taxa"]
        if not taxa:
            QMessageBox.warning(self, "Empty File",
                                "No valid taxa/abundance data found in this file.")
            return

        # Store parsed taxa on shared app state.
        # This is what compute_risk() and the intervention page read.
        self.app.uploaded_data = {
            "path":  path,
            "name":  result["name"],
            "taxa":  taxa,   # dict[str, float] — ready to pass to store_microbiome_upload
        }

        self.drop_area.setText(
            f"✓  Loaded: {result['name']}  ({result['size_kb']} KB)")
        self.taxa_chart.update_data(taxa)
        self.phylo_canvas.set_taxa(list(taxa.keys()))

    # ── Step 2: store upload → compute risk via service layer ─────────────────
    def compute_risk(self):
        if not self.app.uploaded_data or not self.app.uploaded_data.get("taxa"):
            QMessageBox.information(self, "No Data",
                                    "Please upload microbiome data first.")
            return

        if self.app.current_project_id is None:
            QMessageBox.information(
                self, "No Project",
                "No project is loaded.\n"
                "Click 'SET PROJECT' in the sidebar and enter a project ID."
            )
            return

        try:
            # Lazy import — only resolves once path_setup has patched sys.path
            from src.services.assessment_service import (
                store_microbiome_upload,
                compute_and_store_risk,
                ServiceError,
            )
            from utils.model import stub_model_fn

            taxa      = self.app.uploaded_data["taxa"]
            file_path = self.app.uploaded_data.get("path")
            proj_id   = self.app.current_project_id

            # ── Step 2a: persist the upload so the DB has microbiome data ─────
            # store_microbiome_upload auto-computes shannon + alpha_diversity
            # if you don't pass them; the loader already computed them but
            # letting the service recompute is fine and keeps the call simple.
            store_microbiome_upload(
                project_id=proj_id,
                file_path=file_path,
                taxa=taxa,
                # shannon_index and alpha_diversity are optional — service computes them
            )

            # ── Step 2b: run the model on the just-stored microbiome ──────────
            # compute_and_store_risk reads the latest microbiome from the DB
            # (the one we just wrote above), calls model_fn(taxa) → risk %,
            # stores a RiskAssessment row, and returns a plain dict.
            result = compute_and_store_risk(
                project_id=proj_id,
                model_fn=stub_model_fn,   # swap for Emma's model when ready
            )

            self._apply_risk_result(result["risk_probability"], result["risk_label"])
            self.app.last_risk_result = result

        except Exception as exc:
            # Covers ServiceError, ImportError (src not on path), OperationalError, etc.
            # Always fall back to the stub so the UI stays usable during development.
            self._compute_risk_stub()
            # Only surface unexpected errors (not "no project" during dev)
            if "ServiceError" not in type(exc).__name__ and not isinstance(exc, ImportError):
                QMessageBox.warning(self, "DB Unavailable",
                                    f"Running in stub mode (no DB connection):\n{exc}")

    def _compute_risk_stub(self):
        """Offline fallback — runs model directly on in-memory taxa, no DB."""
        from utils.model import stub_model_fn, risk_label
        taxa  = self.app.uploaded_data.get("taxa", {})
        risk  = stub_model_fn(taxa)
        label = risk_label(risk)
        self.app.ad_risk = risk
        self._apply_risk_result(risk, label)

    def _apply_risk_result(self, risk: float, label: str):
        """Update the risk badge colour and text. Called by both live and stub paths."""
        self.app.ad_risk = risk
        self.risk_label.setText(f"{risk:.1f}%")
        colour_map = {"Low": "#2a7a2a", "Moderate": "#c07000", "High": "#a02020"}
        bg = colour_map.get(label, "#2357b5")
        self.risk_label.setStyleSheet(
            f"background-color:{bg}; color:white; font-size:64px; "
            f"font-weight:bold; border-radius:8px;"
        )

    # ── Reset ─────────────────────────────────────────────────────────────────
    def reset(self):
        self.risk_label.setText("—")
        self.risk_label.setStyleSheet("")
        self.data_text.clear()
        self.drop_area.setText("📂  Drag-and-drop Data Here...")
        self.taxa_chart.fig.clear()
        self.taxa_chart._draw_placeholder()
        self.phylo_canvas.taxa = list("ABCDEFGH")
        self.phylo_canvas.repaint()
        self.app.ad_risk      = 0.0
        self.app.uploaded_data = {}