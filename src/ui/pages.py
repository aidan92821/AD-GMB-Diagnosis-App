"""
Axis – page panels.

Every page has a  load(state: AppState)  method called by MainWindow
whenever the shared state changes.  No page imports from example_data.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QComboBox,
    QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QSizePolicy, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal

from models.app_state import AppState
from resources.styles import (
    GENUS_COLORS, BG_PAGE, BORDER,
    TEXT_H, TEXT_M, TEXT_HINT,
    DANGER_FG, SUCCESS_FG,
)
from models.example_data import ALZHEIMER_RISK   # risk only still uses example
from ui.widgets import (
    BarChartWidget, StackedBarWidget, BoxPlotWidget,
    PCoAWidget, HeatmapWidget, RiskMeterWidget,
)
from ui.helpers import (
    card, page_title, section_title,
    label_muted, label_hint, stat_card,
    btn_primary, btn_outline,
    PillSwitcher, hdivider, vdivider,
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


def _placeholder(msg: str) -> QLabel:
    lbl = QLabel(msg)
    lbl.setObjectName("label_hint")
    lbl.setWordWrap(True)
    return lbl


def _info_banner(msg: str, kind: str = "info") -> QFrame:
    """Inline banner used for download / pipeline status messages."""
    obj = {"ok": "banner_ok", "warn": "banner_warn", "err": "banner_err"}.get(kind, "banner_warn")
    txt_obj = {"ok": "banner_text_ok", "warn": "banner_text_warn", "err": "banner_text_err"}.get(kind, "banner_text_warn")
    frame = QFrame()
    frame.setObjectName(obj)
    lay = QHBoxLayout(frame)
    lay.setContentsMargins(12, 8, 12, 8)
    lbl = QLabel(msg)
    lbl.setObjectName(txt_obj)
    lbl.setWordWrap(True)
    lay.addWidget(lbl)
    return frame


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 1 – Overview
# ═════════════════════════════════════════════════════════════════════════════

class OverviewPage(QWidget):
    fetch_requested = pyqtSignal(str, str, int)

    _BP_RE  = __import__("re").compile(r"^PRJ(NA|EA|DA|EB|DB|NB)\d+$",
                                        __import__("re").IGNORECASE)
    _RUN_RE = __import__("re").compile(r"^[SED]RR\d+$",
                                        __import__("re").IGNORECASE)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._show_empty_stats()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)
        root.addWidget(page_title("Overview"))

        fetch_card = card()
        root.addWidget(fetch_card)
        lay = fetch_card.layout()
        lay.addWidget(section_title("Fetch data from NCBI"))
        lay.addWidget(label_hint(
            "Enter a BioProject accession to load all runs for that study.  "
            "Optionally filter to a single run by entering its Run accession."
        ))

        input_row = QHBoxLayout(); input_row.setSpacing(12)

        col_bp = QVBoxLayout(); col_bp.setSpacing(4)
        bp_lbl = QLabel("BioProject accession <span style='color:#EF4444;font-weight:700'>*</span>")
        bp_lbl.setTextFormat(Qt.TextFormat.RichText)
        bp_lbl.setObjectName("label_muted")
        self._bp_input = QLineEdit()
        self._bp_input.setPlaceholderText("e.g. PRJNA743840")
        self._bp_input.setToolTip("Required. Format: PRJNA/PRJEB/PRJDB + digits")
        self._bp_input.textChanged.connect(self._validate_inputs)
        col_bp.addWidget(bp_lbl); col_bp.addWidget(self._bp_input)
        input_row.addLayout(col_bp, 3)

        col_run = QVBoxLayout(); col_run.setSpacing(4)
        run_lbl = QLabel("Run accession <span style='color:#9CA3AF;font-size:11px'>(optional)</span>")
        run_lbl.setTextFormat(Qt.TextFormat.RichText)
        run_lbl.setObjectName("label_muted")
        self._run_input = QLineEdit()
        self._run_input.setPlaceholderText("e.g. SRR001001  —  leave blank for all runs")
        self._run_input.textChanged.connect(self._validate_inputs)
        col_run.addWidget(run_lbl); col_run.addWidget(self._run_input)
        input_row.addLayout(col_run, 3)

        col_n = QVBoxLayout(); col_n.setSpacing(4)
        col_n.addWidget(label_muted("Max runs to fetch"))
        self._run_count = QComboBox()
        for n in ["1", "2", "3", "4", "5", "6", "8", "10", "12", "16", "20"]:
            self._run_count.addItem(n)
        self._run_count.setCurrentIndex(3)   # default = 4
        col_n.addWidget(self._run_count)
        input_row.addLayout(col_n, 1)
        lay.addLayout(input_row)

        action_row = QHBoxLayout(); action_row.setSpacing(12)
        self._validation_lbl = QLabel("")
        self._validation_lbl.setStyleSheet(f"font-size:11px; color:{DANGER_FG};")
        self._validation_lbl.setWordWrap(True)
        action_row.addWidget(self._validation_lbl, 1)

        self._fetch_btn = btn_primary("  ⬇  Fetch data  →")
        self._fetch_btn.setFixedHeight(42)
        self._fetch_btn.setMinimumWidth(160)
        self._fetch_btn.setStyleSheet("""
            QPushButton { background-color:#4F46E5; color:#FFFFFF; border:none;
              border-radius:8px; font-size:14px; font-weight:700; padding:0 22px; }
            QPushButton:hover   { background-color:#4338CA; }
            QPushButton:pressed { background-color:#3730A3; }
            QPushButton:disabled { background-color:#C7D2FE; color:#818CF8; }
        """)
        self._fetch_btn.clicked.connect(self._on_fetch_clicked)
        action_row.addWidget(self._fetch_btn, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(action_row)
        lay.addWidget(label_hint(
            "BioProject = study-level ID (e.g. PRJNA743840).  "
            "Run accession = one sequencing file (e.g. SRR001001).  "
            "Fetched runs appear as R1–R4 throughout the dashboard."
        ))

        # Status banner
        self._status_bar = QFrame()
        self._status_bar.setStyleSheet(
            "background:#EEF2FF; border:1px solid #C7D2FE; border-radius:6px;")
        self._status_bar.hide()
        sb_lay = QHBoxLayout(self._status_bar); sb_lay.setContentsMargins(12, 8, 12, 8)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:12px; color:#4338CA;")
        sb_lay.addWidget(self._status_lbl)
        root.addWidget(self._status_bar)

        # Stats card
        self._stats_card = card()
        root.addWidget(self._stats_card)
        self._stats_card.layout().addWidget(section_title("Project overview"))
        self._stats_row = QHBoxLayout(); self._stats_row.setSpacing(10)
        self._stats_card.layout().addLayout(self._stats_row)

        # Runs card
        self._runs_card = card()
        root.addWidget(self._runs_card)
        self._runs_card.layout().addWidget(section_title("Fetched runs"))
        self._runs_body = QVBoxLayout(); self._runs_body.setSpacing(0)
        self._runs_card.layout().addLayout(self._runs_body)

        root.addStretch()

    def _validate_inputs(self):
        bp  = self._bp_input.text().strip()
        run = self._run_input.text().strip()
        bp_ok  = bool(bp) and bool(self._BP_RE.match(bp))
        run_ok = (not run) or bool(self._RUN_RE.match(run))

        self._bp_input.setStyleSheet(
            f"border:1.5px solid {'#10B981' if bp_ok else '#EF4444' if bp else '#E5E7EB'};"
            "border-radius:6px; padding:7px 10px; font-size:13px; background:white;")
        if run:
            self._run_input.setStyleSheet(
                f"border:1.5px solid {'#10B981' if run_ok else '#EF4444'};"
                "border-radius:6px; padding:7px 10px; font-size:13px; background:white;")
        else:
            self._run_input.setStyleSheet("")

        if bp and not bp_ok:
            self._validation_lbl.setText(
                f"⚠  '{bp}' is not a valid BioProject accession (PRJNA/PRJEB/PRJDB + digits).")
        elif run and not run_ok:
            self._validation_lbl.setText(
                f"⚠  '{run}' is not a valid Run accession (SRR/ERR/DRR + digits).")
        else:
            self._validation_lbl.setText("")

        self._fetch_btn.setEnabled(bp_ok and run_ok)

    def _on_fetch_clicked(self):
        bp  = self._bp_input.text().strip()
        run = self._run_input.text().strip()
        n   = int(self._run_count.currentText())
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("  ⟳  Fetching…")
        self._bp_input.setEnabled(False)
        self._run_input.setEnabled(False)
        self._run_count.setEnabled(False)
        self._status_lbl.setText(
            f"⟳  Fetching data for  {bp}"
            + (f"  ·  run {run}" if run else "") + "  …")
        self._status_bar.setStyleSheet(
            "background:#EEF2FF; border:1px solid #C7D2FE; border-radius:6px;")
        self._status_lbl.setStyleSheet("font-size:12px; color:#4338CA;")
        self._status_bar.show()
        self.fetch_requested.emit(bp, run, n)

    # ── called by MainWindow ──────────────────────────────────────────────────

    def load(self, state: AppState):
        """Populate overview from live AppState."""
        self._fetch_btn.setEnabled(True)
        self._fetch_btn.setText("  ⬇  Fetch data  →")
        self._bp_input.setEnabled(True)
        self._run_input.setEnabled(True)
        self._run_count.setEnabled(True)

        self._status_lbl.setText(
            f"✓  Loaded  {state.bioproject_id}  —  "
            f"{state.run_count} run{'s' if state.run_count != 1 else ''} fetched successfully.")
        self._status_bar.setStyleSheet(
            "background:#ECFDF5; border:1px solid #A7F3D0; border-radius:6px;")
        self._status_lbl.setStyleSheet("font-size:12px; color:#065F46;")
        self._status_bar.show()
        self._rebuild_stat_cards(state)
        self._rebuild_runs_list(state)

    def show_fetch_error(self, message: str):
        self._fetch_btn.setEnabled(True)
        self._fetch_btn.setText("  ⬇  Fetch data  →")
        self._bp_input.setEnabled(True)
        self._run_input.setEnabled(True)
        self._run_count.setEnabled(True)
        self._status_lbl.setText(f"✗  {message}")
        self._status_bar.setStyleSheet(
            "background:#FEF2F2; border:1px solid #FECACA; border-radius:6px;")
        self._status_lbl.setStyleSheet("font-size:12px; color:#991B1B;")
        self._status_bar.show()

    def _show_empty_stats(self):
        _clear(self._stats_row)
        self._stats_row.addWidget(_placeholder(
            "Enter a BioProject accession above and click  Fetch data →  to load statistics."))
        _clear(self._runs_body)
        self._runs_body.addWidget(_placeholder("No runs loaded yet."))

    def _rebuild_stat_cards(self, state: AppState):
        _clear(self._stats_row)
        asv_val   = f"{state.asv_count:,}" if state.asv_count else "—"
        genus_val = str(state.genus_count)  if state.genus_count else "—"
        asv_sub   = "unique sequences"      if state.asv_count else "upload FASTQ to compute"
        genus_sub = "bacterial genera"      if state.genus_count else "upload FASTQ to compute"
        for value, label, sub in [
            (state.project_id or state.bioproject_id, "Project ID",    ""),
            (state.bioproject_id,                     "BioProject ID", "NCBI accession"),
            (str(state.run_count),                    "Runs",          "  ".join(state.run_labels)),
            (asv_val,                                 "ASVs",          asv_sub),
            (genus_val,                               "Genera",        genus_sub),
            (state.library_layout,                    "Library",       "sequencing type"),
            (f"{state.uploaded_count} / {state.run_count}", "Uploaded",
             "FASTQ files ready"),
        ]:
            self._stats_row.addWidget(stat_card(value, label, sub))

    def _rebuild_runs_list(self, state: AppState):
        _clear(self._runs_body)
        header = QHBoxLayout()
        for col_text, fw in [("Run",0),("Accession",1),("Reads",1),("Layout",1),("Status",1),("QIIME2",2)]:
            lbl = QLabel(col_text)
            lbl.setStyleSheet(f"font-size:11px;font-weight:600;color:{TEXT_M};padding-bottom:4px;")
            if fw: header.addWidget(lbl, fw)
            else: lbl.setFixedWidth(36); header.addWidget(lbl)
        self._runs_body.addLayout(header)
        rule = QFrame(); rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(f"background:{BORDER}; max-height:1px;")
        self._runs_body.addWidget(rule)

        for run in state.runs:
            row = QHBoxLayout(); row.setContentsMargins(0, 6, 0, 6)
            badge = QLabel(run.label)
            badge.setFixedWidth(36)
            badge.setStyleSheet(
                "font-size:11px;font-weight:700;color:#6366F1;"
                "background:#EEF2FF;border-radius:4px;padding:2px 4px;")
            row.addWidget(badge)

            acc = QLabel(run.accession)
            acc.setStyleSheet("font-size:11px;color:#6B7280;font-family:monospace;")
            row.addWidget(acc, 1)

            reads = QLabel(f"{run.read_count:,}" if run.read_count else "—")
            reads.setStyleSheet(f"font-size:12px;color:{TEXT_M};")
            row.addWidget(reads, 1)

            layout_lbl = QLabel(run.layout.title())
            layout_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_M};")
            row.addWidget(layout_lbl, 1)

            status_text  = "✓  Uploaded" if run.uploaded else "○  Pending"
            status_color = SUCCESS_FG    if run.uploaded else TEXT_HINT
            st = QLabel(status_text)
            st.setStyleSheet(f"font-size:11px;color:{status_color};")
            row.addWidget(st, 1)

            if run.qiime_error:
                qiime_lbl = QLabel(f"⚠  {run.qiime_error[:60]}")
                qiime_lbl.setStyleSheet(f"font-size:10px;color:{DANGER_FG};")
            else:
                qiime_lbl = QLabel("—")
                qiime_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_HINT};")
            row.addWidget(qiime_lbl, 2)
            self._runs_body.addLayout(row)

            div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
            div.setStyleSheet(f"background:{BORDER}; max-height:1px;")
            self._runs_body.addWidget(div)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 2 – Upload Runs
# ═════════════════════════════════════════════════════════════════════════════

class UploadRunsPage(QWidget):
    file_selected = pyqtSignal(str, str)   # (run_label, file_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._row_widgets: dict[str, dict] = {}
        self._build()

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(28, 24, 28, 24)
        self._root.setSpacing(16)
        self._root.addWidget(page_title("Upload Runs"))

        info = card()
        info.layout().addWidget(section_title("Upload .fastq or .fastq.gz files"))
        info.layout().addWidget(label_hint(
            "Validates 4-line FASTQ format: @SEQID · sequence (ACTG) · + · Phred scores\n"
            "Fetch a project first to see the run list below."))
        self._root.addWidget(info)

        self._runs_card = card()
        self._runs_card.layout().addWidget(section_title("Run files"))
        self._runs_body = QVBoxLayout()
        self._runs_body.setSpacing(0)
        self._runs_card.layout().addLayout(self._runs_body)
        self._runs_body.addWidget(_placeholder("No runs loaded — fetch a project first."))
        self._root.addWidget(self._runs_card)

        self._error_area = QVBoxLayout()
        self._root.addLayout(self._error_area)
        self._root.addStretch()

    def load(self, state: AppState):
        self._state = state
        self._row_widgets = {}
        _clear(self._runs_body)
        _clear(self._error_area)

        for run in state.runs:
            row = QHBoxLayout(); row.setSpacing(12)
            lbl = QLabel(f"<b>{run.label}</b>  {run.accession}")
            lbl.setObjectName("label_muted"); lbl.setFixedWidth(180)
            row.addWidget(lbl)

            status_lbl = QLabel("✓  Uploaded" if run.uploaded else "○  Pending")
            status_lbl.setStyleSheet(
                f"color:{'#065F46' if run.uploaded else '#9CA3AF'}; font-size:12px;")
            row.addWidget(status_lbl); row.addStretch()

            browse_btn = btn_outline(f"Browse file for {run.label}…")
            browse_btn.clicked.connect(
                lambda _, r=run.label: self._browse(r))
            row.addWidget(browse_btn)

            self._runs_body.addLayout(row)
            self._row_widgets[run.label] = {"status": status_lbl}
            if run != state.runs[-1]:
                self._runs_body.addWidget(hdivider())

        for run in state.runs:
            if run.qiime_error:
                b = QFrame(); b.setObjectName("banner_err")
                bl = QHBoxLayout(b); bl.setContentsMargins(12, 8, 12, 8)
                l = QLabel(f"{run.label} — {run.qiime_error}")
                l.setObjectName("banner_text_err"); l.setWordWrap(True)
                bl.addWidget(l); self._error_area.addWidget(b)

    def update_run_status(self, run_label: str, uploaded: bool, error: str = ""):
        """Called by MainWindow after FASTQ validation."""
        if run_label not in self._row_widgets:
            return
        lbl = self._row_widgets[run_label]["status"]
        if error:
            lbl.setText(f"✗  Error")
            lbl.setStyleSheet(f"color:{DANGER_FG}; font-size:12px;")
        else:
            lbl.setText("✓  Uploaded" if uploaded else "○  Pending")
            lbl.setStyleSheet(
                f"color:{'#065F46' if uploaded else '#9CA3AF'}; font-size:12px;")

    def _browse(self, run_label: str):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select FASTQ for {run_label}", "",
            "FASTQ files (*.fastq *.fastq.gz);;All files (*)")
        if path:
            self.file_selected.emit(run_label, path)

    def show_run_pipeline_btn(self, ready: bool, callback) -> None:
        """
        Show the Run Pipeline button once at least one FASTQ is uploaded.
        'ready' = True means ALL runs have files (button fully enabled).
        'callback' = function to call when user clicks.
        """
        if not hasattr(self, "_pipeline_btn"):
            from ui.helpers import btn_primary, hdivider
            self._runs_card.layout().addWidget(hdivider())

            row = QHBoxLayout(); row.setSpacing(12)
            hint = QLabel("Upload all run files then click Run Pipeline to start QIIME2 preprocessing.")
            hint.setObjectName("label_hint"); hint.setWordWrap(True)
            row.addWidget(hint, 1)

            self._pipeline_btn = btn_primary("  ▶  Run Pipeline")
            self._pipeline_btn.setFixedHeight(40)
            self._pipeline_btn.setStyleSheet("""
                QPushButton { background:#10B981; color:white; border:none;
                  border-radius:8px; font-size:13px; font-weight:700; padding:0 20px; }
                QPushButton:hover   { background:#059669; }
                QPushButton:disabled { background:#D1FAE5; color:#6EE7B7; }
            """)
            row.addWidget(self._pipeline_btn)
            self._runs_card.layout().addLayout(row)

        self._pipeline_btn.setEnabled(ready)
        self._pipeline_btn.setText(
            "  ▶  Run Pipeline" if ready else "  ▶  Run Pipeline  (waiting for all files)")
        # Reconnect to the callback (disconnect old first to avoid double-fire)
        try:
            self._pipeline_btn.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._pipeline_btn.clicked.connect(callback)

    def auto_mark_uploaded(self, state: "AppState") -> None:
        """
        Called by MainWindow after fasterq-dump downloads complete.
        Refreshes the run list (showing ✓ Uploaded for downloaded runs)
        and shows the Run Pipeline button ready to fire.
        """
        self.load(state)
        uploaded = [r for r in state.runs if r.uploaded]
        if uploaded:
            self.show_download_status(
                f"✓  {len(uploaded)} of {state.run_count} run"
                f"{'s' if state.run_count != 1 else ''} downloaded automatically "
                f"to  data/{state.bioproject_id}/fastq/",
                kind="ok",
            )

    def show_pipeline_error(self, message: str) -> None:
        """Show a red error banner on the upload page after pipeline failure."""
        if hasattr(self, "_dl_info_banner"):
            self._dl_info_banner.deleteLater()
            del self._dl_info_banner
        if hasattr(self, "_pipeline_err_banner"):
            self._pipeline_err_banner.deleteLater()
        self._pipeline_err_banner = _info_banner(f"Pipeline error: {message[:200]}", kind="err")
        self._root.insertWidget(self._root.count() - 1, self._pipeline_err_banner)

    def show_download_status(self, message: str, kind: str = "info") -> None:
        """Show a non-blocking info/ok/warn banner about download state."""
        if hasattr(self, "_dl_info_banner"):
            try:
                self._dl_info_banner.deleteLater()
            except RuntimeError:
                pass
        self._dl_info_banner = _info_banner(message, kind=kind)
        self._root.insertWidget(self._root.count() - 1, self._dl_info_banner)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 3 – Diversity
# ═════════════════════════════════════════════════════════════════════════════

class DiversityPage(QWidget):
    """Alpha boxplots + Beta PCoA & heatmap — all driven by live AppState."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._alpha_metric = "shannon"
        self._beta_metric  = "bray_curtis"
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addWidget(page_title("Diversity"))

        # ── Alpha card ──────────────────────────────────────────────────────
        alpha_card = card()
        root.addWidget(alpha_card)

        hdr = QHBoxLayout()
        hdr.addWidget(section_title("Alpha diversity"))
        hdr.addWidget(label_hint("Each box = one run · shows within-sample species richness"))
        self._alpha_sw = PillSwitcher(["Shannon", "Simpson"], obj_name="metric_pill")
        self._alpha_sw.on_changed(self._on_alpha_metric)
        hdr.addStretch(); hdr.addWidget(self._alpha_sw)
        alpha_card.layout().addLayout(hdr)

        self._boxplot = BoxPlotWidget(data={}, colors=[])
        self._boxplot.setFixedHeight(150)
        alpha_card.layout().addWidget(self._boxplot)
        self._alpha_placeholder = _placeholder(
            "Fetch a project and upload FASTQ files to compute alpha diversity.")
        alpha_card.layout().addWidget(self._alpha_placeholder)

        # ── Beta card ────────────────────────────────────────────────────────
        beta_hdr = QHBoxLayout()
        beta_hdr.addWidget(section_title("Beta diversity"))
        self._beta_sw = PillSwitcher(["Bray-Curtis", "UniFrac"], obj_name="metric_pill")
        self._beta_sw.on_changed(self._on_beta_metric)
        beta_hdr.addStretch(); beta_hdr.addWidget(self._beta_sw)

        beta_row = QHBoxLayout(); beta_row.setSpacing(12)

        # PCoA
        pcoa_card = card()
        pcoa_card.layout().addWidget(section_title("PCoA scatter"))
        pcoa_card.layout().addWidget(
            label_hint("Runs plotted by community similarity. Closer = more similar microbiomes."))
        self._pcoa = PCoAWidget(coords={}, colors={})
        self._pcoa.setMinimumHeight(180)
        pcoa_card.layout().addWidget(self._pcoa)
        self._pcoa_placeholder = _placeholder(
            "Upload FASTQ files to compute beta diversity PCoA.")
        pcoa_card.layout().addWidget(self._pcoa_placeholder)
        beta_row.addWidget(pcoa_card, 3)

        # Heatmap
        hm_card = card()
        hm_card.layout().addWidget(section_title("Dissimilarity heatmap"))
        hm_card.layout().addWidget(
            label_hint("Pairwise dissimilarity between runs.  Darker = more similar."))
        self._heatmap = HeatmapWidget(labels=[], values=[])
        hm_card.layout().addWidget(self._heatmap, 0, Qt.AlignmentFlag.AlignLeft)
        hm_card.layout().addWidget(label_hint("similar ←──────→ dissimilar"))
        self._hm_placeholder = _placeholder(
            "Upload FASTQ files to compute dissimilarity heatmap.")
        hm_card.layout().addWidget(self._hm_placeholder)
        beta_row.addWidget(hm_card, 2)

        beta_w = QWidget()
        beta_l = QVBoxLayout(beta_w)
        beta_l.setContentsMargins(0, 0, 0, 0); beta_l.setSpacing(10)
        beta_l.addLayout(beta_hdr); beta_l.addLayout(beta_row)
        root.addWidget(beta_w)
        root.addStretch()

    def load(self, state: AppState):
        """Update all charts from live AppState."""
        self._state = state
        self._refresh_alpha()
        self._refresh_beta()

    def _refresh_alpha(self):
        if not self._state or not self._state.alpha_diversity:
            self._boxplot.hide()
            self._alpha_placeholder.show()
            return

        data   = {lbl: self._state.alpha_diversity[lbl][self._alpha_metric]
                  for lbl in self._state.run_labels
                  if lbl in self._state.alpha_diversity}
        colors = list(self._state.run_colors().values())

        self._boxplot.set_data(data)
        self._boxplot._colors = colors
        self._boxplot.update()
        self._boxplot.show()
        self._alpha_placeholder.hide()

    def _refresh_beta(self):
        if not self._state or not self._state.beta_bray_curtis:
            self._pcoa.hide()
            self._pcoa_placeholder.show()
            self._heatmap.hide()
            self._hm_placeholder.show()
            return

        if self._beta_metric == "bray_curtis":
            matrix = self._state.beta_bray_curtis
            coords  = self._state.pcoa_bray_curtis
        else:
            matrix = self._state.beta_unifrac
            coords  = self._state.pcoa_unifrac

        self._pcoa.set_data(coords)
        self._pcoa._colors = self._state.run_colors()
        self._pcoa.update()
        self._pcoa.show()
        self._pcoa_placeholder.hide()

        self._heatmap.set_data(self._state.run_labels, matrix)
        self._heatmap.show()
        self._hm_placeholder.hide()

    def _on_alpha_metric(self, label: str):
        self._alpha_metric = "shannon" if "shannon" in label.lower() else "simpson"
        self._refresh_alpha()

    def _on_beta_metric(self, label: str):
        self._beta_metric = "bray_curtis" if "bray" in label.lower() else "unifrac"
        self._refresh_beta()


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 4 – Taxonomy
# ═════════════════════════════════════════════════════════════════════════════

class TaxonomyPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._active_run = "R1"
        self._build()

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(28, 24, 28, 24)
        self._root.setSpacing(16)

        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Taxonomy"))
        self._run_sw = PillSwitcher(["—"], obj_name="pill")
        hdr.addStretch(); hdr.addWidget(self._run_sw)
        self._root.addLayout(hdr)

        # Two-column row
        cols = QHBoxLayout(); cols.setSpacing(12)

        bar_card = card()
        bar_card.layout().addWidget(section_title("Top genera — relative abundance"))
        self._bar = BarChartWidget(data=[], colors=GENUS_COLORS)
        self._bar.setFixedHeight(160)
        bar_card.layout().addWidget(self._bar)
        self._bar_placeholder = _placeholder("Upload FASTQ files to compute taxonomy.")
        bar_card.layout().addWidget(self._bar_placeholder)
        cols.addWidget(bar_card, 3)

        tax_card = card()
        tax_card.layout().addWidget(section_title("Genus abundance breakdown"))
        self._legend_layout = QVBoxLayout(); self._legend_layout.setSpacing(4)
        tax_card.layout().addLayout(self._legend_layout)
        self._legend_placeholder = _placeholder("No data yet.")
        self._legend_layout.addWidget(self._legend_placeholder)
        cols.addWidget(tax_card, 2)
        self._root.addLayout(cols)

        # Stacked bar
        comp_card = card()
        comp_card.layout().addWidget(section_title("Genus composition — all runs"))
        self._stacked = StackedBarWidget(data={}, colors=GENUS_COLORS)
        comp_card.layout().addWidget(self._stacked)
        self._stacked_placeholder = _placeholder(
            "Upload FASTQ files to see composition across all runs.")
        comp_card.layout().addWidget(self._stacked_placeholder)
        self._root.addWidget(comp_card)
        self._root.addStretch()

    def load(self, state: AppState):
        self._state = state

        # Rebuild run switcher if run labels changed
        old_active = self._active_run
        labels = state.run_labels or ["—"]

        # Reconnect switcher
        new_sw = PillSwitcher(labels, obj_name="pill")
        new_sw.on_changed(self._on_run)
        hdr_lay = self._root.itemAt(0).layout()
        # Replace old switcher widget
        old_sw_item = hdr_lay.itemAt(hdr_lay.count() - 1)
        if old_sw_item and old_sw_item.widget():
            old_sw_item.widget().deleteLater()
        hdr_lay.addWidget(new_sw)
        self._run_sw = new_sw

        self._active_run = labels[0] if labels else "R1"
        self._refresh(self._active_run)

        # Stacked bar
        if state.genus_abundances:
            self._stacked.set_data(state.genus_abundances)
            self._stacked.show()
            self._stacked_placeholder.hide()
        else:
            self._stacked.hide()
            self._stacked_placeholder.show()

    def _refresh(self, run: str):
        if not self._state or not self._state.genus_abundances:
            self._bar.hide(); self._bar_placeholder.show()
            return

        genera = self._state.genus_abundances.get(run, [])
        if not genera:
            self._bar.hide(); self._bar_placeholder.show()
            return

        self._bar.set_data(genera[:10])
        self._bar.show(); self._bar_placeholder.hide()
        self._build_legend(genera)

    def _build_legend(self, genera: list[tuple[str, float]]):
        _clear(self._legend_layout)
        top5  = genera[:5]
        other = sum(p for _, p in genera[5:])
        for i, (g, v) in enumerate(top5):
            row = QHBoxLayout(); row.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{GENUS_COLORS[i % len(GENUS_COLORS)]}; font-size:11px;")
            txt = label_muted(f"{g}   {v:.1f}%")
            row.addWidget(dot); row.addWidget(txt); row.addStretch()
            self._legend_layout.addLayout(row)
        if other > 0:
            row = QHBoxLayout(); row.setSpacing(6)
            dot = QLabel("●"); dot.setStyleSheet("color:#D1D5DB; font-size:11px;")
            txt = label_muted(f"Other   {other:.1f}%")
            row.addWidget(dot); row.addWidget(txt); row.addStretch()
            self._legend_layout.addLayout(row)

    def _on_run(self, run: str):
        self._active_run = run
        self._refresh(run)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 5 – ASV Table
# ═════════════════════════════════════════════════════════════════════════════

class AsvTablePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._active_run = "R1"
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.addWidget(page_title("ASV Table"))
        self._run_sw = PillSwitcher(["—"], obj_name="pill")
        hdr.addStretch(); hdr.addWidget(self._run_sw)
        root.addLayout(hdr)

        ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        ctrl.addWidget(label_muted("Sort:"))
        self._sort_id  = btn_outline("Feature ID ↕")
        self._sort_cnt = btn_outline("Count ↓")
        self._sort_id.clicked.connect(lambda: self._table.sortItems(0))
        self._sort_cnt.clicked.connect(lambda: self._table.sortItems(2))
        ctrl.addWidget(self._sort_id); ctrl.addWidget(self._sort_cnt)

        # Summary label
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_M};")
        ctrl.addStretch(); ctrl.addWidget(self._summary_lbl)
        root.addLayout(ctrl)

        tbl_card = card()
        root.addWidget(tbl_card, 1)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Feature ID", "Taxonomy", "Count", "Rel. %"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        tbl_card.layout().addWidget(self._table)

        self._placeholder = _placeholder(
            "Fetch a project and upload FASTQ files to populate the ASV table.")
        tbl_card.layout().addWidget(self._placeholder)
        self._table.hide()

    def load(self, state: AppState):
        self._state = state
        labels = state.run_labels or ["—"]

        new_sw = PillSwitcher(labels, obj_name="pill")
        new_sw.on_changed(self._on_run)
        hdr_lay = self.layout().itemAt(0).layout()
        old = hdr_lay.itemAt(hdr_lay.count() - 1)
        if old and old.widget(): old.widget().deleteLater()
        hdr_lay.addWidget(new_sw)
        self._run_sw = new_sw

        self._active_run = labels[0] if labels else "R1"
        self._populate(self._active_run)

    def _populate(self, run: str):
        if not self._state or not self._state.asv_features:
            self._table.hide(); self._placeholder.show()
            self._summary_lbl.setText("")
            return

        rows = self._state.asv_features.get(run, [])
        if not rows:
            self._table.hide(); self._placeholder.show()
            self._summary_lbl.setText("")
            return

        self._table.setRowCount(len(rows))
        for r, feat in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(feat["id"]))
            self._table.setItem(r, 1, QTableWidgetItem(feat["genus"]))
            count_item = QTableWidgetItem()
            count_item.setData(Qt.ItemDataRole.DisplayRole, f"{feat['count']:,}")
            count_item.setData(Qt.ItemDataRole.UserRole, feat["count"])
            self._table.setItem(r, 2, count_item)
            self._table.setItem(r, 3, QTableWidgetItem(f"{feat['pct']:.2f}"))

        self._summary_lbl.setText(
            f"{len(rows)} ASVs  ·  {run}  ·  "
            f"{sum(f['count'] for f in rows):,} total reads")
        self._table.show(); self._placeholder.hide()

    def _on_run(self, run: str):
        self._active_run = run
        self._populate(run)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 6 – Phylogeny
# ═════════════════════════════════════════════════════════════════════════════

class PhylogenyPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Phylogenetic Tree"))
        hdr.addWidget(label_hint("derived from ASV sequences"))
        self._run_sw = PillSwitcher(["—"], obj_name="pill")
        hdr.addStretch(); hdr.addWidget(self._run_sw)
        root.addLayout(hdr)

        tree_card = card()
        root.addWidget(tree_card, 1)
        self._tree_lbl = QLabel("Fetch a project and upload FASTQ files to see the phylogenetic tree.")
        self._tree_lbl.setObjectName("tree_text")
        self._tree_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._tree_lbl.setWordWrap(True)
        tree_card.layout().addWidget(self._tree_lbl, 1)
        root.addStretch()

    def load(self, state: AppState):
        self._state = state
        labels = state.run_labels or ["—"]

        new_sw = PillSwitcher(labels, obj_name="pill")
        new_sw.on_changed(self._on_run)
        hdr_lay = self.layout().itemAt(0).layout()
        old = hdr_lay.itemAt(hdr_lay.count() - 1)
        if old and old.widget(): old.widget().deleteLater()
        hdr_lay.addWidget(new_sw)
        self._run_sw = new_sw

        first = labels[0] if labels else "—"
        self._on_run(first)

    def _on_run(self, run: str):
        if not self._state or not self._state.phylo_tree:
            self._tree_lbl.setText("No tree data yet. Upload FASTQ files to compute.")
            return
        self._tree_lbl.setText(
            self._state.phylo_tree.get(run, "No tree for this run."))


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 7 – Alzheimer Risk
# ═════════════════════════════════════════════════════════════════════════════

class AlzheimerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # ── Page header (static) ──────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Alzheimer Risk"))
        hdr.addStretch()
        hdr.addWidget(label_hint("Based on gut-brain axis biomarkers"))
        root.addLayout(hdr)

        # ── Summary card (mutable labels stored as instance vars) ─────────────
        summary = card()
        root.addWidget(summary)
        sum_row = QHBoxLayout(); sum_row.setSpacing(24)

        pct_col = QVBoxLayout(); pct_col.setSpacing(2)
        pct_col.addWidget(label_muted("Predicted risk"))
        self._pct_lbl = QLabel("—")
        self._pct_lbl.setObjectName("risk_number")
        pct_col.addWidget(self._pct_lbl)
        self._lvl_lbl = QLabel("—")
        self._lvl_lbl.setObjectName("risk_level")
        pct_col.addWidget(self._lvl_lbl)
        sum_row.addLayout(pct_col)
        sum_row.addWidget(vdivider())

        meter_col = QVBoxLayout(); meter_col.setSpacing(6)
        meter_col.addWidget(label_muted("Risk spectrum"))
        self._meter_widget = RiskMeterWidget(0)
        meter_col.addWidget(self._meter_widget)
        scale = QHBoxLayout()
        for t in ("Low", "Moderate", "High"):
            scale.addWidget(label_hint(t))
            if t != "High": scale.addStretch()
        meter_col.addLayout(scale)
        sum_row.addLayout(meter_col, 1)
        sum_row.addWidget(vdivider())

        conf_col = QVBoxLayout(); conf_col.setSpacing(2)
        conf_col.addWidget(label_muted("Confidence"))
        self._conf_lbl = QLabel("—")
        self._conf_lbl.setObjectName("conf_number")
        conf_col.addWidget(self._conf_lbl)
        conf_col.addWidget(label_hint("model certainty"))
        sum_row.addLayout(conf_col)
        summary.layout().addLayout(sum_row)

        # ── Scrollable biomarker area ─────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setObjectName("content_scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self._scroll, 1)

        # Initial render with example data
        self._render(ALZHEIMER_RISK)

    def load(self, state: AppState):
        d = state.risk_result if (state and state.risk_result) else ALZHEIMER_RISK
        self._render(d)

    def _render(self, d: dict):
        pct   = d.get("predicted_pct", 0)
        conf  = d.get("confidence_pct", 0)
        level = d.get("risk_level", "unknown").capitalize()

        self._pct_lbl.setText(f"{pct:.0f}%")
        self._lvl_lbl.setText(level)
        self._conf_lbl.setText(f"{conf:.0f}%")
        self._meter_widget.set_pct(pct)

        # Build a fresh inner widget — avoids stale child widget accumulation
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(12)

        # ── Biomarker grid ────────────────────────────────────────────────────
        bm_section = card()
        bm_section.layout().addWidget(section_title("Key biomarkers"))

        biomarkers = d.get("biomarkers", [])
        cols = 3
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        for idx, bm in enumerate(biomarkers):
            row, col = divmod(idx, cols)
            f = QFrame()
            f.setObjectName("bm_card")
            f.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            lay = QVBoxLayout(f)
            lay.setContentsMargins(12, 10, 12, 10)
            lay.setSpacing(4)

            nm = QLabel(bm["name"])
            nm.setObjectName("bm_name")
            nm.setWordWrap(True)
            lay.addWidget(nm)

            arrow  = {"low": "↓", "high": "↑", "normal": "✓"}.get(bm["status"], "")
            # map "normal" → "ok" to match the QSS object name
            style_key = "ok" if bm["status"] == "normal" else bm["status"]
            vl = QLabel(f"{arrow} {bm['value']:.1f}{bm['unit']}")
            vl.setObjectName(f"bm_val_{style_key}")
            lay.addWidget(vl)

            rf = QLabel(f"Normal: {bm['normal']}  ·  {bm['role']}")
            rf.setObjectName("bm_ref")
            rf.setWordWrap(True)
            lay.addWidget(rf)

            grid.addWidget(f, row, col)

        bm_section.layout().addLayout(grid)
        inner_lay.addWidget(bm_section)

        # ── Disclaimer ────────────────────────────────────────────────────────
        disc = label_hint(
            "⚠  Research-grade estimate only — NOT a clinical diagnosis. "
            "Consult a physician for clinical assessment.")
        disc.setWordWrap(True)
        inner_lay.addWidget(disc)
        inner_lay.addStretch()

        self._scroll.setWidget(inner)