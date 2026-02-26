"""
Export Page  (Figure 3)
───────────────────────
Left  : Export Settings (Report Type, File Type, Include) + Generate button
Right : Preview panel with microbiome summary, phylogeny, and charts
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QFrame, QComboBox, QPushButton, QTextEdit,
    QSizePolicy, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPen, QColor, QFont

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np


# ── Mini Phylogeny (reused, compact) ────────────────────────
class MiniPhylogenyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.taxa = list("ABCDEFGH")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#1a2a4a"), 1.5))

        w, h = self.width(), self.height()
        n = len(self.taxa)
        margin_top   = 15
        margin_right = 24
        row_h = (h - margin_top * 2) / (n - 1)
        leaf_x = w - margin_right - 8
        leaf_ys = [margin_top + i * row_h for i in range(n)]

        font = QFont("Segoe UI", 8)
        p.setFont(font)
        for i, taxon in enumerate(self.taxa):
            p.drawText(int(leaf_x) + 2, int(leaf_ys[i]) + 4, taxon)

        step = (w - margin_right - 50) / 4
        nodes = {i: (leaf_x - step, leaf_ys[i]) for i in range(n)}
        for i in range(n):
            p.drawLine(int(nodes[i][0]), int(leaf_ys[i]),
                       int(leaf_x), int(leaf_ys[i]))

        node_id = n
        active = list(range(n))
        level_dx = step
        while len(active) > 1:
            new_active = []
            i = 0
            while i < len(active) - 1:
                a, b = active[i], active[i+1]
                ax_, ay = nodes[a]; bx_, by = nodes[b]
                px = min(ax_, bx_) - level_dx
                py = (ay + by) / 2
                p.drawLine(int(ax_), int(ay), int(ax_), int(by))
                p.drawLine(int(px), int(py), int(ax_), int(ay))
                p.drawLine(int(px), int(py), int(ax_), int(by))
                nodes[node_id] = (px, py)
                new_active.append(node_id); node_id += 1; i += 2
            if len(active) % 2 == 1:
                new_active.append(active[-1])
            active = new_active
            level_dx = max(level_dx - 4, 4)
        p.end()


# ── Mini Perturbation Chart ──────────────────────────────────
class MiniSimChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(3.5, 2.2), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._draw([35, 48, 41, 43, 58, 50, 70])  # placeholder

    def _draw(self, data):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.plot(range(1, len(data)+1), data, marker="o",
                color="#2979d4", linewidth=1.5, markersize=5)
        ax.set_ylim(0, 80)
        ax.tick_params(labelsize=7)
        ax.set_facecolor("white")
        self.fig.patch.set_facecolor("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self.draw()

    def update_data(self, history: list):
        if history:
            self._draw(history)


# ── Mini Taxa Abundance ───────────────────────────────────────
class MiniTaxaChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(4, 2.5), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._draw()

    def _draw(self):
        ax = self.fig.add_subplot(111)
        colours = ["#e07070","#e09050","#e0c050","#70c080",
                   "#7090e0","#9070c0","#c0c0c0"]
        for i, col in enumerate(colours):
            vals = np.random.uniform(15, 70, 14)
            ax.bar(np.arange(14) + i * 0.12, vals, width=0.12,
                   color=col, alpha=0.8)
        ax.set_ylabel("Coverage (%)", fontsize=7)
        ax.set_xticks([])
        ax.tick_params(labelsize=6)
        ax.set_facecolor("white")
        self.fig.patch.set_facecolor("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        self.draw()


# ── Labelled ComboBox ────────────────────────────────────────
def _labelled_combo(title: str, options: list) -> tuple:
    """Returns (container_widget, combo_box)."""
    w = QWidget()
    vbox = QVBoxLayout(w)
    vbox.setContentsMargins(0, 4, 0, 4)
    lbl = QLabel(title)
    lbl.setObjectName("SliderLabel")
    lbl.setAlignment(Qt.AlignCenter)
    combo = QComboBox()
    combo.addItems(options)
    vbox.addWidget(lbl)
    vbox.addWidget(combo)
    return w, combo


# ── Export Page ──────────────────────────────────────────────
class ExportPage(QWidget):
    def __init__(self, app_state):
        super().__init__()
        self.app = app_state
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        # ── Left: Export Settings ─────────────────────────────
        left = QFrame()
        left.setObjectName("Card")
        left.setFixedWidth(200)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 16, 12, 16)
        left_layout.setSpacing(6)

        title = QLabel("Export\nSettings")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title)
        left_layout.addSpacing(8)

        report_w, self.report_combo = _labelled_combo(
            "Report Type", ["Option A", "Option B", "Option C"])
        file_w,   self.file_combo   = _labelled_combo(
            "File Type",   ["PDF", "HTML", "DOCX", "CSV"])
        include_w, self.include_combo = _labelled_combo(
            "Include",     ["All Sections", "Risk Only", "Charts Only", "Raw Data"])

        left_layout.addWidget(report_w)
        left_layout.addWidget(file_w)
        left_layout.addWidget(include_w)
        left_layout.addStretch(1)

        gen_btn = QPushButton("GENERATE\nREPORT")
        gen_btn.setObjectName("ActionBtn")
        gen_btn.clicked.connect(self._generate_report)
        left_layout.addWidget(gen_btn)

        outer.addWidget(left)

        # ── Right: Preview ────────────────────────────────────
        right = QFrame()
        right.setObjectName("Card")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 10, 12, 10)
        right_layout.setSpacing(8)

        # header
        header_row = QHBoxLayout()
        preview_title = QLabel("Preview")
        preview_title.setStyleSheet("font-size:18px; font-weight:bold; color:#1a4fa3;")
        header_row.addWidget(preview_title)
        header_row.addStretch()
        tog = QPushButton("☀")
        tog.setObjectName("ToggleBtn")
        tog.setCheckable(True)
        header_row.addWidget(tog)
        right_layout.addLayout(header_row)

        # Summary text
        self.summary_text = QTextEdit()
        self.summary_text.setObjectName("DataDisplay")
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText("summary statistics about microbiome")
        self.summary_text.setMaximumHeight(70)
        right_layout.addWidget(self.summary_text)

        # Charts row
        charts_row = QHBoxLayout()
        charts_row.setSpacing(10)

        # left mini-charts column
        left_charts = QVBoxLayout()
        left_charts.setSpacing(6)

        phylo_title = QLabel("Phrenology of Microbiome Taxa")
        phylo_title.setObjectName("CardTitle")
        left_charts.addWidget(phylo_title)
        self.mini_phylo = MiniPhylogenyWidget()
        left_charts.addWidget(self.mini_phylo)

        perturb_title = QLabel("Perturbation Trajectories")
        perturb_title.setObjectName("CardTitle")
        left_charts.addWidget(perturb_title)
        self.mini_sim = MiniSimChart()
        left_charts.addWidget(self.mini_sim)

        charts_row.addLayout(left_charts, 1)

        # right taxa abundance
        right_charts = QVBoxLayout()
        right_charts.setSpacing(6)
        taxa_title = QLabel("Taxa Abundance")
        taxa_title.setObjectName("CardTitle")
        right_charts.addWidget(taxa_title)
        self.mini_taxa = MiniTaxaChart()
        right_charts.addWidget(self.mini_taxa)
        right_charts.addStretch(1)

        charts_row.addLayout(right_charts, 1)
        right_layout.addLayout(charts_row, 1)

        outer.addWidget(right, stretch=1)

    # ── Refresh preview from current app state ───────────────
    def refresh_preview(self):
        if self.app.uploaded_data:
            name = self.app.uploaded_data.get("name", "unknown")
            text = (
                f"File: {name}\n"
                f"AD Risk: {self.app.ad_risk}%\n"
                f"Simulations run: {len(self.app.simulation_history)}"
            )
            self.summary_text.setPlainText(text)
        if self.app.simulation_history:
            self.mini_sim.update_data(self.app.simulation_history)

    # ── Report generation stub ───────────────────────────────
    def _generate_report(self):
        self.refresh_preview()

        file_type = self.file_combo.currentText().lower()
        ext_map = {"pdf": "*.pdf", "html": "*.html", "docx": "*.docx", "csv": "*.csv"}
        filter_str = f"{file_type.upper()} Files ({ext_map.get(file_type, '*.*')})"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", f"AD_Risk_Report.{file_type}", filter_str
        )
        if not path:
            return

        # Minimal HTML export as proof-of-concept
        try:
            html = self._build_html_report()
            if file_type == "html":
                with open(path, "w") as f:
                    f.write(html)
            else:
                # For other types you'd integrate a real library (e.g. weasyprint for PDF)
                with open(path, "w") as f:
                    f.write(html)

            QMessageBox.information(self, "Export Complete",
                                    f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _build_html_report(self) -> str:
        name = self.app.uploaded_data.get("name", "N/A")
        risk = self.app.ad_risk
        n_sim = len(self.app.simulation_history)
        history_str = ", ".join(str(x) for x in self.app.simulation_history) or "No simulations"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Alzheimer's Risk Assessment Report</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; margin: 40px; color: #1a2a4a; }}
    h1   {{ color: #2357b5; }}
    h2   {{ color: #2979d4; border-bottom: 1px solid #c0dcf0; padding-bottom: 4px; }}
    .risk-badge {{
      display: inline-block; padding: 16px 32px;
      background: #2357b5; color: white; font-size: 36px;
      font-weight: bold; border-radius: 8px; margin: 12px 0;
    }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #c0dcf0; padding: 8px 12px; text-align: left; }}
    th {{ background: #ddeeff; }}
  </style>
</head>
<body>
  <h1>Alzheimer's Risk Assessment Report</h1>
  <p>Generated on: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

  <h2>Patient Data Summary</h2>
  <table>
    <tr><th>Data File</th><td>{name}</td></tr>
    <tr><th>Simulations Run</th><td>{n_sim}</td></tr>
  </table>

  <h2>AD Risk Score</h2>
  <div class="risk-badge">{risk}%</div>

  <h2>Simulation History</h2>
  <p>{history_str}</p>

  <hr>
  <p><em>This report was generated by the Alzheimer's Risk Assessment Tool.
  It is for research purposes only and does not constitute medical advice.</em></p>
</body>
</html>"""
