"""
GutSeq – page panels (one class per sidebar item).

Each panel is a self-contained QWidget that:
  • builds its own horizontal layout on construction
  • exposes a load(**kwargs) or set_run(label) method
  • never imports from main_window or other panels
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QComboBox,
    QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QSizePolicy, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal

from resources.styles import (
    GENUS_COLORS, BG_PAGE, BORDER,
    TEXT_H, TEXT_M, TEXT_HINT,
    DANGER_FG, SUCCESS_FG,
)
from models.example_data import (
    PROJECT, GENERA, GENUS_ABUNDANCE, ASV_FEATURES,
    ALPHA_DIVERSITY, BETA_BRAY_CURTIS, BETA_UNIFRAC,
    PCOA_BRAY_CURTIS, PCOA_UNIFRAC, PHYLO_TREE_TEXT, ALZHEIMER_RISK,
)
from ui.widgets import (
    BarChartWidget, StackedBarWidget, BoxPlotWidget,
    PCoAWidget, HeatmapWidget, RiskMeterWidget,
)
from ui.helpers import (
    card, card_flat, page_title, section_title,
    label_muted, label_hint, stat_card,
    btn_primary, btn_outline,
    PillSwitcher, hdivider, vdivider, banner, vstretch,
)


# ── Colours mapped to runs ────────────────────────────────────────────────────
RUN_COLORS = {
    "R1": "#10B981",   # emerald
    "R2": "#6366F1",   # indigo
    "R3": "#F59E0B",   # amber
    "R4": "#EF4444",   # red
}


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 1 – Overview  (Fetch + Project Stats)
# ═════════════════════════════════════════════════════════════════════════════

class OverviewPage(QWidget):
    """
    Top section: BioProject fetch form.
    Bottom section: project summary stat cards.
    """

    fetch_requested = pyqtSignal(str, str, int)   # bioproject, run_acc, n_runs

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()
        self._populate_with_example()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)

        root.addWidget(page_title("Overview"))

        # ── Fetch card ──
        fetch_card = card()
        root.addWidget(fetch_card)

        fetch_card.layout().addWidget(section_title("Fetch data from NCBI"))
        fetch_card.layout().addWidget(
            label_hint("BioProject accession required · Run accession optional")
        )

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(12)

        # BioProject
        col1 = QVBoxLayout(); col1.setSpacing(4)
        bp_lbl = QLabel("BioProject accession <span style='color:#EF4444'>*</span>")
        bp_lbl.setTextFormat(Qt.TextFormat.RichText)
        bp_lbl.setObjectName("label_muted")
        self._bp_input = QLineEdit(PROJECT["bioproject_id"])
        self._bp_input.setProperty("state", "ok")
        col1.addWidget(bp_lbl)
        col1.addWidget(self._bp_input)
        input_row.addLayout(col1, 3)

        # Run accession
        col2 = QVBoxLayout(); col2.setSpacing(4)
        run_lbl = QLabel("Run accession <span style='font-size:11px;color:#9CA3AF'>(filter to single run)</span>")
        run_lbl.setTextFormat(Qt.TextFormat.RichText)
        run_lbl.setObjectName("label_muted")
        self._run_input = QLineEdit()
        self._run_input.setPlaceholderText("e.g. SRR98765")
        col2.addWidget(run_lbl)
        col2.addWidget(self._run_input)
        input_row.addLayout(col2, 3)

        # Runs to fetch
        col3 = QVBoxLayout(); col3.setSpacing(4)
        col3.addWidget(label_muted("Runs to fetch"))
        self._run_count = QComboBox()
        for n in ["1", "2", "3", "4"]:
            self._run_count.addItem(n)
        self._run_count.setCurrentIndex(3)
        col3.addWidget(self._run_count)
        input_row.addLayout(col3, 1)

        # Fetch button
        self._fetch_btn = btn_primary("Fetch →")
        self._fetch_btn.clicked.connect(self._on_fetch)
        input_row.addWidget(self._fetch_btn, 0, Qt.AlignmentFlag.AlignBottom)

        fetch_card.layout().addLayout(input_row)
        fetch_card.layout().addWidget(
            label_hint(
                "BioProject groups all runs from one study.  Run Accession "
                "(SRR…/ERR…) lets you drill into a single sequencing file.  "
                "Fetched runs appear as R1–R4 throughout the dashboard."
            )
        )

        # ── Stats card ──
        stats_card = card()
        root.addWidget(stats_card)
        stats_card.layout().addWidget(section_title("Project overview"))

        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(10)
        stats_card.layout().addLayout(self._stats_row)

        root.addStretch()

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate_with_example(self) -> None:
        """Fill stat cards from example data."""
        while self._stats_row.count():
            item = self._stats_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        p = PROJECT
        run_labels = "  ".join(p["runs"])
        uploaded   = sum(p["uploaded"].values())

        cards = [
            stat_card(p["project_id"],         "Project ID"),
            stat_card(str(len(p["runs"])),      "Runs",   run_labels),
            stat_card(f"{p['asv_count']:,}",    "ASVs",   "unique sequences"),
            stat_card(str(p["genus_count"]),     "Genera", "bacterial genera"),
            stat_card(p["library"],              "Library"),
            stat_card(f"{uploaded} / {len(p['runs'])}", "Upload status",
                      "1 pending" if uploaded < len(p["runs"]) else "all uploaded"),
        ]
        for c in cards:
            self._stats_row.addWidget(c)

    # ── Slot ──────────────────────────────────────────────────────────────────

    def _on_fetch(self) -> None:
        bp  = self._bp_input.text().strip()
        run = self._run_input.text().strip()
        n   = int(self._run_count.currentText())
        if bp:
            self.fetch_requested.emit(bp, run, n)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 2 – Upload Runs
# ═════════════════════════════════════════════════════════════════════════════

class UploadRunsPage(QWidget):
    """FASTQ upload zone + per-run status."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addWidget(page_title("Upload Runs"))

        # Top info card
        info = card()
        info.layout().addWidget(section_title("Upload .fastq or .fastq.gz files"))
        info.layout().addWidget(label_hint(
            "Validates 4-line FASTQ format: @SEQID · sequence (ACTG) · + · Phred scores\n"
            "3 of 4 runs uploaded · R4 pending"
        ))
        root.addWidget(info)

        # Per-run upload rows
        runs_card = card()
        runs_card.layout().addWidget(section_title("Run files"))
        root.addWidget(runs_card)

        for run in PROJECT["runs"]:
            row = QHBoxLayout()
            row.setSpacing(12)

            lbl = QLabel(f"<b>{run}</b>  {PROJECT['run_accessions'][run]}")
            lbl.setObjectName("label_muted")
            lbl.setFixedWidth(160)
            row.addWidget(lbl)

            status = PROJECT["uploaded"][run]
            status_lbl = QLabel("✓  Uploaded" if status else "Pending")
            status_lbl.setStyleSheet(
                f"color: {'#065F46' if status else '#9CA3AF'}; font-size: 12px;"
            )
            row.addWidget(status_lbl)
            row.addStretch()

            browse_btn = btn_outline(f"Browse file for {run}…")
            browse_btn.clicked.connect(lambda _, r=run: self._browse(r))
            row.addWidget(browse_btn)

            runs_card.layout().addLayout(row)
            if run != PROJECT["runs"][-1]:
                runs_card.layout().addWidget(hdivider())

        # QIIME2 error banner
        for run, msg in PROJECT.get("qiime_errors", {}).items():
            root.addWidget(banner(f"{run} — {msg}", kind="err"))

        root.addStretch()

    def _browse(self, run: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select FASTQ for {run}", "",
            "FASTQ files (*.fastq *.fastq.gz);;All files (*)"
        )
        # In production: validate + hand off to service layer


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 3 – Diversity
# ═════════════════════════════════════════════════════════════════════════════

class DiversityPage(QWidget):
    """Alpha + Beta diversity (PCoA & heatmap) with shared metric switcher."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._alpha_metric  = "shannon"
        self._beta_metric   = "bray_curtis"
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addWidget(page_title("Diversity"))

        # ── Alpha diversity ──
        alpha_card = card()
        root.addWidget(alpha_card)

        hdr = QHBoxLayout()
        hdr.addWidget(section_title("Alpha diversity"))
        self._alpha_switch = PillSwitcher(["Shannon", "Simpson"], obj_name="metric_pill")
        self._alpha_switch.on_changed(self._on_alpha_metric)
        hdr.addStretch()
        hdr.addWidget(self._alpha_switch)
        alpha_card.layout().addLayout(hdr)
        alpha_card.layout().addWidget(
            label_hint("Each box = one run. Shows diversity within a single sample.")
        )

        self._boxplot = BoxPlotWidget(
            data={r: ALPHA_DIVERSITY[r]["shannon"] for r in PROJECT["runs"]},
            colors=[RUN_COLORS[r] for r in PROJECT["runs"]],
        )
        self._boxplot.setFixedHeight(130)
        alpha_card.layout().addWidget(self._boxplot)

        # ── Beta diversity header row (shared metric switcher) ──
        beta_hdr = QHBoxLayout()
        beta_hdr.addWidget(section_title("Beta diversity"))
        self._beta_switch = PillSwitcher(["Bray-Curtis", "UniFrac"], obj_name="metric_pill")
        self._beta_switch.on_changed(self._on_beta_metric)
        beta_hdr.addStretch()
        beta_hdr.addWidget(self._beta_switch)

        # Beta card row: PCoA left, heatmap right
        beta_row = QHBoxLayout()
        beta_row.setSpacing(12)

        # PCoA card
        pcoa_card = card()
        pcoa_hdr = QHBoxLayout()
        pcoa_hdr.addWidget(section_title("PCoA"))
        pcoa_card.layout().addLayout(pcoa_hdr)
        pcoa_card.layout().addWidget(
            label_hint("Runs plotted by community similarity. Closer = more similar microbiomes.")
        )
        self._pcoa = PCoAWidget(
            coords=PCOA_BRAY_CURTIS,
            colors=RUN_COLORS,
        )
        pcoa_card.layout().addWidget(self._pcoa)
        beta_row.addWidget(pcoa_card, 3)

        # Heatmap card
        hm_card = card()
        hm_card.layout().addWidget(section_title("Heatmap"))
        hm_card.layout().addWidget(
            label_hint("Pairwise dissimilarity between runs. Darker = more similar.")
        )
        self._heatmap = HeatmapWidget(
            labels=PROJECT["runs"],
            values=BETA_BRAY_CURTIS,
        )
        hm_card.layout().addWidget(self._heatmap, 0, Qt.AlignmentFlag.AlignLeft)

        # Colour scale hint
        scale_row = QHBoxLayout()
        from PyQt6.QtWidgets import QSizePolicy as SP
        grad_lbl = label_hint("similar → dissimilar")
        scale_row.addWidget(grad_lbl)
        hm_card.layout().addLayout(scale_row)
        beta_row.addWidget(hm_card, 2)

        # Pack beta section into root
        beta_widget = QWidget()
        beta_layout = QVBoxLayout(beta_widget)
        beta_layout.setContentsMargins(0, 0, 0, 0)
        beta_layout.setSpacing(10)
        beta_layout.addLayout(beta_hdr)
        beta_layout.addLayout(beta_row)

        root.addWidget(beta_widget)
        root.addStretch()

    # ── Metric switching ──────────────────────────────────────────────────────

    def _on_alpha_metric(self, label: str) -> None:
        metric = "shannon" if label.lower() == "shannon" else "simpson"
        self._alpha_metric = metric
        self._boxplot.set_data(
            {r: ALPHA_DIVERSITY[r][metric] for r in PROJECT["runs"]}
        )

    def _on_beta_metric(self, label: str) -> None:
        """Both PCoA and heatmap switch simultaneously."""
        if "bray" in label.lower():
            matrix = BETA_BRAY_CURTIS
            coords  = PCOA_BRAY_CURTIS
        else:
            matrix = BETA_UNIFRAC
            coords  = PCOA_UNIFRAC
        self._pcoa.set_data(coords)
        self._heatmap.set_data(PROJECT["runs"], matrix)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 4 – Taxonomy
# ═════════════════════════════════════════════════════════════════════════════

class TaxonomyPage(QWidget):
    """Genus abundance bar chart + ASV taxonomy donut + stacked composition."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_run = "R1"
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # Header row with run switcher
        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Taxonomy"))
        self._run_sw = PillSwitcher(PROJECT["runs"], obj_name="pill")
        self._run_sw.on_changed(self._on_run)
        hdr.addStretch()
        hdr.addWidget(self._run_sw)
        root.addLayout(hdr)

        # ── Two-column row ──
        cols = QHBoxLayout()
        cols.setSpacing(12)

        # Left: bar chart
        bar_card = card()
        bar_card.layout().addWidget(section_title("Top 10 genera — relative abundance"))
        self._bar = BarChartWidget(
            data=list(zip(GENERA, GENUS_ABUNDANCE["R1"])),
            colors=GENUS_COLORS,
        )
        self._bar.setFixedHeight(150)
        bar_card.layout().addWidget(self._bar)
        cols.addWidget(bar_card, 3)

        # Right: taxonomy donut (legend only — full SVG donut is a stretch goal)
        tax_card = card()
        tax_card.layout().addWidget(section_title("ASV → taxonomy map"))
        tax_card.layout().addWidget(label_hint(
            "outer = ASVs · inner = genera · width ∝ count"
        ))
        self._legend_layout = QVBoxLayout()
        self._legend_layout.setSpacing(4)
        tax_card.layout().addLayout(self._legend_layout)
        self._build_legend("R1")
        cols.addWidget(tax_card, 2)

        root.addLayout(cols)

        # ── Stacked composition bar ──
        comp_card = card()
        comp_card.layout().addWidget(section_title("Genus composition — all runs"))
        stacked_data = {
            run: list(zip(GENERA, GENUS_ABUNDANCE[run]))
            for run in PROJECT["runs"]
        }
        self._stacked = StackedBarWidget(data=stacked_data, colors=GENUS_COLORS)
        comp_card.layout().addWidget(self._stacked)

        # Legend
        leg_row = QHBoxLayout()
        leg_row.setSpacing(10)
        for i, g in enumerate(GENERA[:6]):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {GENUS_COLORS[i]}; font-size: 10px;")
            lbl = label_muted(g)
            lbl.setStyleSheet("font-size: 10px;")
            sub = QHBoxLayout(); sub.setSpacing(3)
            sub.addWidget(dot); sub.addWidget(lbl)
            leg_row.addLayout(sub)
        leg_row.addStretch()
        comp_card.layout().addLayout(leg_row)
        root.addWidget(comp_card)
        root.addStretch()

    def _build_legend(self, run: str) -> None:
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        vals = GENUS_ABUNDANCE[run]
        total = sum(vals) or 1.0
        top5  = sorted(zip(GENERA, vals), key=lambda x: -x[1])[:5]
        other = total - sum(v for _, v in top5)

        for i, (g, v) in enumerate(top5):
            row = QHBoxLayout(); row.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {GENUS_COLORS[i]}; font-size: 11px;")
            txt = label_muted(f"{g}   {v:.1f}%")
            row.addWidget(dot); row.addWidget(txt); row.addStretch()
            self._legend_layout.addLayout(row)

        row = QHBoxLayout(); row.setSpacing(6)
        dot = QLabel("●"); dot.setStyleSheet("color: #D1D5DB; font-size: 11px;")
        txt = label_muted(f"Other genera   {other:.1f}%")
        row.addWidget(dot); row.addWidget(txt); row.addStretch()
        self._legend_layout.addLayout(row)

    def _on_run(self, run: str) -> None:
        self._active_run = run
        self._bar.set_data(list(zip(GENERA, GENUS_ABUNDANCE[run])))
        self._build_legend(run)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 5 – ASV Table
# ═════════════════════════════════════════════════════════════════════════════

class AsvTablePage(QWidget):
    """Sortable / filterable ASV feature-count table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_run = "R1"
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.addWidget(page_title("ASV Table"))
        self._run_sw = PillSwitcher(PROJECT["runs"], obj_name="pill")
        self._run_sw.on_changed(self._on_run)
        hdr.addStretch()
        hdr.addWidget(self._run_sw)
        root.addLayout(hdr)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        ctrl.addWidget(label_muted("Sort:"))
        self._sort_id  = btn_outline("Feature ID ↕")
        self._sort_cnt = btn_outline("Count ↓")
        self._sort_id.clicked.connect(lambda: self._sort("id"))
        self._sort_cnt.clicked.connect(lambda: self._sort("count"))
        ctrl.addWidget(self._sort_id)
        ctrl.addWidget(self._sort_cnt)
        ctrl.addStretch()
        root.addLayout(ctrl)

        # Table
        tbl_card = card()
        root.addWidget(tbl_card, 1)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Feature ID", "Genus", "Count", "Rel. %"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        tbl_card.layout().addWidget(self._table)

        self._populate("R1")

    def _populate(self, run: str) -> None:
        rows = ASV_FEATURES[run]
        self._table.setRowCount(len(rows))
        for r, feat in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(feat["id"]))
            self._table.setItem(r, 1, QTableWidgetItem(feat["genus"]))
            self._table.setItem(r, 2, QTableWidgetItem(f"{feat['count']:,}"))
            self._table.setItem(r, 3, QTableWidgetItem(f"{feat['pct']:.1f}"))

    def _on_run(self, run: str) -> None:
        self._active_run = run
        self._populate(run)

    def _sort(self, key: str) -> None:
        col = {"id": 0, "count": 2}[key]
        self._table.sortItems(col)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 6 – Phylogeny
# ═════════════════════════════════════════════════════════════════════════════

class PhylogenyPage(QWidget):
    """Text-based phylogenetic tree (IQ-TREE output), switchable per run."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Phylogenetic Tree"))
        hdr.addWidget(label_hint("IQ-TREE · tree.nwk"))
        self._run_sw = PillSwitcher(PROJECT["runs"], obj_name="pill")
        self._run_sw.on_changed(self._on_run)
        hdr.addStretch()
        hdr.addWidget(self._run_sw)
        root.addLayout(hdr)

        tree_card = card()
        root.addWidget(tree_card, 1)

        self._tree_lbl = QLabel(PHYLO_TREE_TEXT["R1"])
        self._tree_lbl.setObjectName("tree_text")
        self._tree_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        tree_card.layout().addWidget(self._tree_lbl, 1)

        root.addStretch()

    def _on_run(self, run: str) -> None:
        self._tree_lbl.setText(PHYLO_TREE_TEXT[run])


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 7 – Alzheimer Risk
# ═════════════════════════════════════════════════════════════════════════════

class AlzheimerPage(QWidget):
    """Risk score + biomarker grid."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Alzheimer Risk"))
        hdr.addStretch()
        hdr.addWidget(label_hint("Based on gut-brain axis biomarkers · R1"))
        root.addLayout(hdr)

        d = ALZHEIMER_RISK

        # ── Summary card ──
        summary = card()
        root.addWidget(summary)

        sum_row = QHBoxLayout()
        sum_row.setSpacing(24)

        # Big % number
        pct_col = QVBoxLayout(); pct_col.setSpacing(2)
        pct_col.addWidget(label_muted("Predicted risk"))
        pct_lbl = QLabel(f"{d['predicted_pct']:.0f}%")
        pct_lbl.setObjectName("risk_number")
        pct_col.addWidget(pct_lbl)
        lvl = QLabel(d["risk_level"])
        lvl.setObjectName("risk_level")
        pct_col.addWidget(lvl)
        sum_row.addLayout(pct_col)

        sum_row.addWidget(vdivider())

        # Risk meter
        meter_col = QVBoxLayout(); meter_col.setSpacing(6)
        meter_col.addWidget(label_muted("Risk spectrum — gut-brain axis score"))
        meter = RiskMeterWidget(d["predicted_pct"])
        meter_col.addWidget(meter)
        scale_row = QHBoxLayout()
        for txt in ("Low", "Moderate", "High"):
            l = label_hint(txt)
            scale_row.addWidget(l)
            if txt != "High":
                scale_row.addStretch()
        meter_col.addLayout(scale_row)
        sum_row.addLayout(meter_col, 1)

        sum_row.addWidget(vdivider())

        # Confidence
        conf_col = QVBoxLayout(); conf_col.setSpacing(2)
        conf_col.addWidget(label_muted("Confidence"))
        conf_lbl = QLabel(f"{d['confidence_pct']:.0f}%")
        conf_lbl.setObjectName("conf_number")
        conf_col.addWidget(conf_lbl)
        conf_col.addWidget(label_hint("model certainty"))
        sum_row.addLayout(conf_col)

        summary.layout().addLayout(sum_row)

        # ── Biomarker grid ──
        bm_card = card()
        bm_card.layout().addWidget(section_title("Key biomarkers driving this prediction"))
        root.addWidget(bm_card)

        grid = QGridLayout()
        grid.setSpacing(10)
        bm_card.layout().addLayout(grid)

        for idx, bm in enumerate(d["biomarkers"]):
            tile = self._make_bm_tile(bm)
            row, col = divmod(idx, 3)
            grid.addWidget(tile, row, col)

        # Disclaimer
        disc = label_hint(
            "⚠  This prediction is a research-grade estimate based on published "
            "gut-brain axis literature. It is NOT a clinical diagnosis. "
            "Biomarker thresholds are derived from population studies and may not "
            "apply to individual cases. Consult a physician for clinical assessment."
        )
        disc.setWordWrap(True)
        root.addWidget(disc)
        root.addStretch()

    @staticmethod
    def _make_bm_tile(bm: dict) -> QFrame:
        f = QFrame()
        f.setObjectName("bm_card")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)

        name = QLabel(bm["name"])
        name.setObjectName("bm_name")
        name.setWordWrap(True)
        lay.addWidget(name)

        status = bm["status"]
        arrow  = {"low": "↓", "high": "↑", "normal": "✓"}.get(status, "")
        val_lbl = QLabel(f"{arrow} {bm['value']:.1f}{bm['unit']}")
        val_lbl.setObjectName(f"bm_val_{status}")
        lay.addWidget(val_lbl)

        ref = QLabel(f"Normal: {bm['normal']} · {bm['role']}")
        ref.setObjectName("bm_ref")
        ref.setWordWrap(True)
        lay.addWidget(ref)

        return f