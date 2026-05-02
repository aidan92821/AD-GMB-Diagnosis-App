"""
Axis – page panels.

Every page has a  load(state: AppState)  method called by MainWindow
whenever the shared state changes.  No page imports from example_data.
"""

from __future__ import annotations
from pathlib import Path as _Path

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QComboBox,
    QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QSizePolicy, QScrollArea, QPlainTextEdit, QSlider, QSpinBox,
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QColor

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
    NumericSortItem, GenusTableWidget, _AlphaBarWidget
)
from ui.helpers import (
    card, page_title, section_title,
    label_muted, label_hint, stat_card,
    btn_primary, btn_outline,
    PillSwitcher, hdivider, vdivider,
)

from src.services.assessment_service import (ServiceError, get_feature_counts,
                                             get_genus_data, get_alpha_diversities,
                                             get_beta_diversity_matrix, get_pcoa)

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
    fetch_requested = pyqtSignal(str, str, int, str, object)

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
        self._run_input.textChanged.connect(self._on_run_input_changed)
        col_run.addWidget(run_lbl); col_run.addWidget(self._run_input)
        input_row.addLayout(col_run, 3)

        col_n = QVBoxLayout(); col_n.setSpacing(4)
        col_n.addWidget(label_muted("Max runs to fetch"))
        self._run_count = QComboBox()
        for n in ["1", "2", "3", "4"]:
            self._run_count.addItem(n)
        self._run_count.setCurrentIndex(0)   # default = 4
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

    def _on_run_input_changed(self, text: str) -> None:
        if text.strip():
            self._run_count.setCurrentIndex(0)
            self._run_count.setEnabled(False)
        else:
            self._run_count.setEnabled(True)

    _FETCH_BTN_STYLE = """
        QPushButton { background-color:#4F46E5; color:#FFFFFF; border:none;
          border-radius:8px; font-size:14px; font-weight:700; padding:0 22px; }
        QPushButton:hover   { background-color:#4338CA; }
        QPushButton:pressed { background-color:#3730A3; }
        QPushButton:disabled { background-color:#C7D2FE; color:#818CF8; }
    """
    _FETCH_CANCEL_STYLE = """
        QPushButton { background-color:#DC2626; color:#FFFFFF; border:none;
          border-radius:8px; font-size:14px; font-weight:700; padding:0 22px; }
        QPushButton:hover   { background-color:#B91C1C; }
        QPushButton:pressed { background-color:#991B1B; }
    """

    def set_cancel_callback(self, cb) -> None:
        self._cancel_callback = cb

    def _restore_fetch_btn(self) -> None:
        self._fetch_btn.setText("  ⬇  Fetch data  →")
        self._fetch_btn.setStyleSheet(self._FETCH_BTN_STYLE)
        self._fetch_btn.clicked.disconnect()
        self._fetch_btn.clicked.connect(self._on_fetch_clicked)
        self._fetch_btn.setEnabled(True)
        self._bp_input.setEnabled(True)
        self._run_input.setEnabled(True)
        self._run_count.setEnabled(not self._run_input.text().strip())

    def _on_fetch_clicked(self):
        bp  = self._bp_input.text().strip()
        run = self._run_input.text().strip()
        n   = int(self._run_count.currentText())
        email = 'emmanicolego@gmail.com'
        user = None

        # Transform button to Cancel
        self._fetch_btn.setText("  ✕  Cancel")
        self._fetch_btn.setStyleSheet(self._FETCH_CANCEL_STYLE)
        self._fetch_btn.clicked.disconnect()
        cb = getattr(self, '_cancel_callback', None)
        if cb:
            self._fetch_btn.clicked.connect(cb)

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
        self.fetch_requested.emit(bp, run, n, email, user)

    # ── called by MainWindow ──────────────────────────────────────────────────

    def load(self, state: AppState):
        """Populate overview from live AppState."""
        self._restore_fetch_btn()
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
        self._restore_fetch_btn()
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
        uploaded_runs = sum(1 for r in state.runs.values() if r['uploaded'])
        uploaded_sub  = (
            f"{state.uploaded_count} FASTQ files on disk"
            if uploaded_runs else "browse or fetch to upload"
        )
        for value, label, sub in [
            (state.project_uid or state.bioproject_id, "Project ID",    ""),
            (state.bioproject_id,                     "BioProject ID", "NCBI accession"),
            (str(state.run_count),                    "Runs",          "  ".join(state.run_labels)),
            (asv_val,                                 "ASVs",          asv_sub),
            (genus_val,                               "Genera",        genus_sub),
            (state.library_layout,                    "Library",       "sequencing type"),
            (f"{uploaded_runs} / {state.run_count}",  "Runs Uploaded", uploaded_sub),
        ]:
            self._stats_row.addWidget(stat_card(value, label, sub))

    def _rebuild_runs_list(self, state: AppState):
        _clear(self._runs_body)
        header = QHBoxLayout()
        for col_text, fw in [("Run", 0), ("Accession", 2), ("Reads", 1), ("Layout", 1), ("Status", 1)]:
            lbl = QLabel(col_text)
            lbl.setStyleSheet(f"font-size:11px;font-weight:600;color:{TEXT_M};padding-bottom:4px;")
            if fw:
                header.addWidget(lbl, fw)
            else:
                lbl.setFixedWidth(36); header.addWidget(lbl)
        self._runs_body.addLayout(header)
        rule = QFrame(); rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(f"background:{BORDER}; max-height:1px;")
        self._runs_body.addWidget(rule)

        for run in state.runs.values():
            row = QHBoxLayout(); row.setContentsMargins(0, 5, 0, 5)
            badge = QLabel(run['label'])
            badge.setFixedWidth(36)
            badge.setStyleSheet(
                "font-size:11px;font-weight:700;color:#6366F1;"
                "background:#EEF2FF;border-radius:4px;padding:2px 4px;")
            row.addWidget(badge)

            acc = QLabel(run['run_accession'])
            acc.setStyleSheet("font-size:11px;color:#6B7280;font-family:monospace;")
            row.addWidget(acc, 2)

            reads = QLabel(f"{run['read_count']:,}" if run['read_count'] else "—")
            reads.setStyleSheet(f"font-size:11px;color:{TEXT_M};")
            row.addWidget(reads, 1)

            layout_lbl = QLabel(run['library_layout'].title())
            layout_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_M};")
            row.addWidget(layout_lbl, 1)

            st = QLabel("✓  Uploaded" if run['uploaded'] else "○  Pending")
            st.setStyleSheet(
                f"font-size:11px;color:{SUCCESS_FG if run['uploaded'] else TEXT_HINT};")
            row.addWidget(st, 1)
            self._runs_body.addLayout(row)

            div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
            div.setStyleSheet(f"background:{BORDER}; max-height:1px;")
            self._runs_body.addWidget(div)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 2 – Upload Runs
# ═════════════════════════════════════════════════════════════════════════════

class UploadRunsPage(QWidget):
    file_selected   = pyqtSignal(str, str, str)  # (run_label, slot, file_path)  — for NCBI pending runs
    local_run_added = pyqtSignal(str, str, str)  # (layout, fwd_path, rev_or_empty)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._row_widgets: dict[str, dict] = {}
        self._build()

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(28, 24, 28, 24)
        self._root.setSpacing(12)
        self._root.addWidget(page_title("Upload Runs"))

        # ── Runs card: compact one-row-per-run table ───────────────────────────
        self._runs_card = card()
        self._runs_card.layout().setSpacing(6)
        self._runs_card.layout().addWidget(section_title("Sequencing Runs"))
        self._runs_body = QVBoxLayout()
        self._runs_body.setSpacing(0)
        self._runs_card.layout().addLayout(self._runs_body)
        self._runs_body.addWidget(_placeholder("No runs loaded — fetch a project first."))

        # Pipeline button (hidden until files ready)
        self._pipeline_divider = hdivider()
        self._runs_card.layout().addWidget(self._pipeline_divider)
        self._pipeline_divider.hide()

        self._pipeline_row_widget = QWidget()
        pr_lay = QHBoxLayout(self._pipeline_row_widget)
        pr_lay.setContentsMargins(0, 4, 0, 2)
        pr_lay.setSpacing(12)
        self._pipeline_hint = QLabel("Runs ready — click to start QIIME2 preprocessing.")
        self._pipeline_hint.setObjectName("label_hint")
        pr_lay.addWidget(self._pipeline_hint, 1)
        self._pipeline_btn = btn_primary("  ▶  Run Pipeline")
        self._pipeline_btn.setObjectName("btn_run_pipeline")
        self._pipeline_btn.setFixedHeight(40)
        self._pipeline_btn.setMinimumWidth(160)
        self._pipeline_btn.setStyleSheet(
            "background-color:#059669; color:white; border:none;"
            "border-radius:8px; font-size:13px; font-weight:700; padding:0 20px;"
        )
        pr_lay.addWidget(self._pipeline_btn)
        self._runs_card.layout().addWidget(self._pipeline_row_widget)
        self._pipeline_row_widget.hide()
        self._root.addWidget(self._runs_card)

        # ── Add Local FASTQ card ───────────────────────────────────────────────
        local_card = card()
        local_card.layout().setSpacing(8)
        local_card.layout().addWidget(section_title("Add Local FASTQ Files"))
        local_card.layout().addWidget(label_hint(
            "Upload your own FASTQ files from your computer. "
            "They will be included in the QIIME2 pipeline when you click Run Pipeline."))

        # Type toggle — two large, clearly visible buttons
        _SEL   = "background-color:#4F46E5; color:#FFFFFF; border:none; border-radius:8px; font-size:13px; font-weight:700; padding:8px 20px;"
        _UNSEL = "background-color:#F3F4F6; color:#374151; border:1.5px solid #D1D5DB; border-radius:8px; font-size:13px; font-weight:600; padding:8px 20px;"
        type_row = QHBoxLayout(); type_row.setSpacing(8)
        self._btn_paired = QPushButton("⬤  Paired-end")
        self._btn_paired.setFixedHeight(40)
        self._btn_paired.setStyleSheet(_SEL)
        self._btn_paired.clicked.connect(lambda: self._set_local_type("Paired-end"))
        self._btn_single = QPushButton("○  Single-end")
        self._btn_single.setFixedHeight(40)
        self._btn_single.setStyleSheet(_UNSEL)
        self._btn_single.clicked.connect(lambda: self._set_local_type("Single-end"))
        type_row.addWidget(self._btn_paired, 1)
        type_row.addWidget(self._btn_single, 1)
        type_row.addStretch()
        local_card.layout().addLayout(type_row)
        self._local_type_active = "Paired-end"

        # Paired-end file inputs
        self._local_paired_widget = QWidget()
        pw = QVBoxLayout(self._local_paired_widget)
        pw.setContentsMargins(0, 4, 0, 0); pw.setSpacing(8)
        self._local_fwd_path = QLineEdit()
        self._local_fwd_path.setReadOnly(True)
        self._local_fwd_path.setPlaceholderText("Forward reads  (_1.fastq / _R1.fastq)")
        self._local_rev_path = QLineEdit()
        self._local_rev_path.setReadOnly(True)
        self._local_rev_path.setPlaceholderText("Reverse reads  (_2.fastq / _R2.fastq)")
        for path_edit, row_lbl, tip in [
            (self._local_fwd_path, "Forward (_1)", "Select forward / R1 FASTQ file"),
            (self._local_rev_path, "Reverse (_2)", "Select reverse / R2 FASTQ file"),
        ]:
            fr = QHBoxLayout(); fr.setSpacing(8)
            lbl_w = QLabel(row_lbl)
            lbl_w.setFixedWidth(90)
            lbl_w.setStyleSheet("font-size:12px; color:#6B7280;")
            fr.addWidget(lbl_w)
            fr.addWidget(path_edit, 1)
            b = QPushButton("Browse…")
            b.setFixedHeight(34); b.setFixedWidth(90)
            b.setToolTip(tip)
            b.setStyleSheet(
                "background-color:#FFFFFF; color:#374151; border:1.5px solid #D1D5DB;"
                "border-radius:6px; font-size:12px; font-weight:600; padding:0 12px;")
            b.clicked.connect(lambda _, p=path_edit: self._browse_local_file(p))
            fr.addWidget(b)
            pw.addLayout(fr)
        local_card.layout().addWidget(self._local_paired_widget)

        # Single-end file input (hidden by default)
        self._local_single_widget = QWidget()
        sw = QHBoxLayout(self._local_single_widget)
        sw.setContentsMargins(0, 4, 0, 0); sw.setSpacing(8)
        lbl_sw = QLabel("FASTQ file")
        lbl_sw.setFixedWidth(90)
        lbl_sw.setStyleSheet("font-size:12px; color:#6B7280;")
        sw.addWidget(lbl_sw)
        self._local_single_path = QLineEdit()
        self._local_single_path.setReadOnly(True)
        self._local_single_path.setPlaceholderText("FASTQ file  (.fastq / .fastq.gz)")
        sw.addWidget(self._local_single_path, 1)
        b_s = QPushButton("Browse…")
        b_s.setFixedHeight(34); b_s.setFixedWidth(90)
        b_s.setStyleSheet(
            "background-color:#FFFFFF; color:#374151; border:1.5px solid #D1D5DB;"
            "border-radius:6px; font-size:12px; font-weight:600; padding:0 12px;")
        b_s.clicked.connect(lambda _: self._browse_local_file(self._local_single_path))
        sw.addWidget(b_s)
        local_card.layout().addWidget(self._local_single_widget)
        self._local_single_widget.hide()

        # Add Run button — large and green, full attention
        add_row = QHBoxLayout(); add_row.addStretch()
        self._add_local_btn = QPushButton("＋  Add Run")
        self._add_local_btn.setFixedHeight(42)
        self._add_local_btn.setMinimumWidth(140)
        self._add_local_btn.setStyleSheet(
            "background-color:#059669; color:white; border:none;"
            "border-radius:8px; font-size:14px; font-weight:700; padding:0 24px;")
        self._add_local_btn.clicked.connect(self._on_add_local_run)
        add_row.addWidget(self._add_local_btn)
        local_card.layout().addLayout(add_row)
        self._root.addWidget(local_card)

        # ── Log / terminal card (always visible) ──────────────────────────────
        log_card = card()
        log_card.layout().setSpacing(6)
        log_card.layout().setContentsMargins(14, 10, 14, 10)

        log_hdr = QHBoxLayout()
        log_hdr.setSpacing(8)
        log_hdr.addWidget(section_title("Log"))
        log_hdr.addStretch()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("font-size:10px; color:#9CA3AF;")
        log_hdr.addWidget(self._status_dot)
        self._status_step_lbl = QLabel("Idle")
        self._status_step_lbl.setStyleSheet("font-size:11px; color:#9CA3AF;")
        log_hdr.addWidget(self._status_step_lbl)
        log_card.layout().addLayout(log_hdr)

        self._terminal = QPlainTextEdit()
        self._terminal.setReadOnly(True)
        mono = QFont("Menlo")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._terminal.setFont(mono)
        self._terminal.setStyleSheet(
            "QPlainTextEdit {"
            "  background:#0D1117; color:#C9D1D9;"
            "  border:1px solid #30363D; border-radius:6px; padding:8px;"
            "}"
        )
        self._terminal.setMinimumHeight(70)
        # self._terminal.setMaximumHeight(140)
        self._terminal.setPlainText("Ready — fetch a project to begin.\n")
        log_card.layout().addWidget(self._terminal)

        # Hidden error container kept for API compatibility
        self._error_container = QWidget()
        self._error_container.hide()
        err_lay = QVBoxLayout(self._error_container)
        err_lay.setContentsMargins(0, 0, 0, 0)
        err_lay.setSpacing(4)
        self._error_area = err_lay
        log_card.layout().addWidget(self._error_container)

        self._root.addWidget(log_card)
        self._root.addStretch()

    def load(self, state: AppState):
        self._state = state
        self._row_widgets = {}
        _clear(self._runs_body)

        _pipeline_dir = _Path(__file__).parent.parent / "pipeline" / "data"

        for i, run in enumerate(state.runs.values(), start=1):
            srr       = run['run_accession']
            is_paired = run.get('library_layout', 'PAIRED').upper() == 'PAIRED'
            uploaded  = run.get('uploaded', False)

            row = QHBoxLayout()
            row.setContentsMargins(0, 6, 0, 6)
            row.setSpacing(10)

            # Label badge
            badge = QLabel(run['label'])
            badge.setFixedWidth(30)
            badge.setStyleSheet(
                "font-size:11px; font-weight:700; color:#6366F1;"
                "background:#EEF2FF; border-radius:4px; padding:2px 4px;")
            row.addWidget(badge)

            # Accession (monospace)
            acc = QLabel(srr)
            acc.setStyleSheet("font-size:11px; color:#6B7280; font-family:monospace;")
            row.addWidget(acc, 2)

            # Type tag
            tag = QLabel("PAIRED" if is_paired else "SINGLE")
            tag.setStyleSheet(
                f"font-size:10px; font-weight:700; padding:1px 5px; border-radius:3px;"
                f"background:{'#EDE9FE' if is_paired else '#D1FAE5'};"
                f"color:{'#6D28D9' if is_paired else '#065F46'};")
            row.addWidget(tag)

            # FASTQ file display — prefer stored path names, fall back to disk check
            if is_paired:
                stored_fwd = run.get('fastq_forward', '')
                stored_rev = run.get('fastq_reverse', '')
                disk_f1 = _pipeline_dir / state.bioproject_id / "fastq" / "paired" / f"{srr}_1.fastq"
                disk_f2 = _pipeline_dir / state.bioproject_id / "fastq" / "paired" / f"{srr}_2.fastq"
                fwd_ok   = bool(stored_fwd) or disk_f1.exists()
                rev_ok   = bool(stored_rev) or disk_f2.exists()
                fwd_name = _Path(stored_fwd).name if stored_fwd else (f"{srr}_1.fastq" if disk_f1.exists() else f"{srr}_1.fastq")
                rev_name = _Path(stored_rev).name if stored_rev else (f"{srr}_2.fastq" if disk_f2.exists() else f"{srr}_2.fastq")
                files_ok = fwd_ok and rev_ok
                files_text = (
                    f"{'✓' if fwd_ok else '○'}  {fwd_name}    "
                    f"{'✓' if rev_ok else '○'}  {rev_name}"
                )
            else:
                stored_s  = run.get('fastq_path', '')
                disk_f1   = _pipeline_dir / state.bioproject_id / "fastq" / "single" / f"{srr}.fastq"
                files_ok  = bool(stored_s) or disk_f1.exists()
                file_name = _Path(stored_s).name if stored_s else f"{srr}.fastq"
                files_text = f"{'✓' if files_ok else '○'}  {file_name}"
            files_lbl = QLabel(files_text)
            files_lbl.setStyleSheet(
                f"font-size:10px; font-family:monospace;"
                f"color:{'#059669' if files_ok else '#9CA3AF'};")
            row.addWidget(files_lbl, 3)

            # Upload status
            status_lbl = QLabel("✓  Uploaded" if uploaded else "○  Pending")
            status_lbl.setFixedWidth(84)
            status_lbl.setStyleSheet(
                f"font-size:11px; color:{'#065F46' if uploaded else '#9CA3AF'};")
            row.addWidget(status_lbl)

            # Browse buttons only for pending NCBI runs (not local and not already uploaded)
            is_local = srr.startswith("LOCAL_")
            if not uploaded and not is_local:
                if is_paired:
                    for slot, lbl_txt, tip in [
                        ('forward', 'Browse _1', 'Forward reads (SRR_1.fastq)'),
                        ('reverse', 'Browse _2', 'Reverse reads (SRR_2.fastq)'),
                    ]:
                        b = btn_outline(lbl_txt)
                        b.setFixedWidth(82); b.setToolTip(tip)
                        b.clicked.connect(lambda _, r=run['label'], s=slot: self._browse(r, s))
                        row.addWidget(b)
                else:
                    b = btn_outline("Browse")
                    b.setFixedWidth(82); b.setToolTip("Select FASTQ file")
                    b.clicked.connect(lambda _, r=run['label']: self._browse(r, 'single'))
                    row.addWidget(b)

            self._runs_body.addLayout(row)
            self._row_widgets[run['label']] = {"status": status_lbl}
            if i < state.run_count:
                self._runs_body.addWidget(hdivider())

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

    def _browse(self, run_label: str, slot: str) -> None:
        titles = {
            'forward': f"Select Forward reads (_1.fastq) for {run_label}",
            'reverse': f"Select Reverse reads (_2.fastq) for {run_label}",
            'single':  f"Select FASTQ file for {run_label}",
        }
        path, _ = QFileDialog.getOpenFileName(
            self, titles.get(slot, f"Select FASTQ for {run_label}"), "",
            "FASTQ files (*.fastq *.fastq.gz);;All files (*)")
        if path:
            self.file_selected.emit(run_label, slot, path)

    # ── Local file upload helpers ──────────────────────────────────────────────

    def _set_local_type(self, label: str) -> None:
        _SEL   = "background-color:#4F46E5; color:#FFFFFF; border:none; border-radius:8px; font-size:13px; font-weight:700; padding:8px 20px;"
        _UNSEL = "background-color:#F3F4F6; color:#374151; border:1.5px solid #D1D5DB; border-radius:8px; font-size:13px; font-weight:600; padding:8px 20px;"
        self._local_type_active = label
        is_paired = label == "Paired-end"
        self._btn_paired.setText("⬤  Paired-end  (2 files)" if is_paired else "○  Paired-end  (2 files)")
        self._btn_single.setText("⬤  Single-end  (1 file)" if not is_paired else "○  Single-end  (1 file)")
        self._btn_paired.setStyleSheet(_SEL if is_paired else _UNSEL)
        self._btn_single.setStyleSheet(_SEL if not is_paired else _UNSEL)
        self._local_paired_widget.setVisible(is_paired)
        self._local_single_widget.setVisible(not is_paired)

    def _on_local_type_changed(self, label: str) -> None:
        self._set_local_type(label)

    def _browse_local_file(self, target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FASTQ file", "",
            "FASTQ files (*.fastq *.fastq.gz);;All files (*)")
        if path:
            target.setText(path)

    def _on_add_local_run(self) -> None:
        is_paired = self._local_type_active == "Paired-end"
        if is_paired:
            fwd = self._local_fwd_path.text().strip()
            rev = self._local_rev_path.text().strip()
            if not fwd or not rev:
                self._log("Select both forward and reverse FASTQ files first.", "warn")
                return
            self.local_run_added.emit("PAIRED", fwd, rev)
            self._local_fwd_path.clear()
            self._local_rev_path.clear()
        else:
            single = self._local_single_path.text().strip()
            if not single:
                self._log("Select a FASTQ file first.", "warn")
                return
            self.local_run_added.emit("SINGLE", single, "")
            self._local_single_path.clear()

    _PIPELINE_BTN_STYLE = (
        "background-color:#059669; color:white; border:none;"
        "border-radius:8px; font-size:13px; font-weight:700; padding:0 20px;"
    )
    _CANCEL_BTN_STYLE = (
        "background-color:#DC2626; color:white; border:none;"
        "border-radius:8px; font-size:13px; font-weight:700; padding:0 20px;"
    )

    def show_run_pipeline_btn(self, ready: bool, callback, cancel_callback=None) -> None:
        """Show button as Run Pipeline; on click it transforms into a Cancel button."""
        self._pipeline_divider.show()
        self._pipeline_row_widget.show()
        self._pipeline_btn.setEnabled(ready)
        self._pipeline_btn.setText("  ▶  Run Pipeline")
        self._pipeline_btn.setStyleSheet(self._PIPELINE_BTN_STYLE)
        try:
            self._pipeline_btn.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass

        def _on_click():
            self._pipeline_btn.setText("  ✕  Cancel")
            self._pipeline_btn.setStyleSheet(self._CANCEL_BTN_STYLE)
            try:
                self._pipeline_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            if cancel_callback:
                self._pipeline_btn.clicked.connect(cancel_callback)
            callback()

        self._pipeline_btn.clicked.connect(_on_click)

    def reset_pipeline_btn(self, callback, cancel_callback=None) -> None:
        """Restore button to Run Pipeline state (call after complete, error, or cancel)."""
        self.show_run_pipeline_btn(ready=True, callback=callback,
                                   cancel_callback=cancel_callback)

    def auto_mark_uploaded(self, state: "AppState") -> None:
        self.load(state)  # refresh table; main_window logs status via update_pipeline_status

    def show_pipeline_error(self, message: str) -> None:
        self._log(f"✗  Pipeline error: {message[:200]}", "err")

    def show_download_status(self, message: str, kind: str = "info") -> None:
        self._log(message, kind)

    def update_pipeline_status(self, message: str, kind: str = "info") -> None:
        dot_colors = {
            "ok": "#10B981", "warn": "#F59E0B",
            "err": "#EF4444", "info": "#3B82F6", "run": "#8B5CF6",
        }
        text_colors = {
            "ok": "#065F46", "warn": "#78350F",
            "err": "#7F1D1D", "info": "#1E3A5F", "run": "#3B0764",
        }
        self._status_dot.setStyleSheet(
            f"font-size:10px; color:{dot_colors.get(kind, '#3B82F6')};")
        self._status_step_lbl.setStyleSheet(
            f"font-size:11px; color:{text_colors.get(kind, '#1E3A5F')};")
        self._status_step_lbl.setText(message)
        self._log(message, kind)

    def _log(self, text: str, kind: str = "info") -> None:
        prefixes = {"ok": "✓", "warn": "⚠", "err": "✗", "run": "▶", "info": "ℹ"}
        prefix = prefixes.get(kind, "ℹ")
        line = f"{prefix}  {text.strip()}"
        self._terminal.moveCursor(QTextCursor.MoveOperation.End)
        self._terminal.insertPlainText(line + "\n")
        self._terminal.moveCursor(QTextCursor.MoveOperation.End)

    def append_terminal_output(self, text: str) -> None:
        self._terminal.moveCursor(QTextCursor.MoveOperation.End)
        self._terminal.insertPlainText(text if text.endswith("\n") else text + "\n")
        self._terminal.moveCursor(QTextCursor.MoveOperation.End)

    def show_terminal(self, visible: bool = True) -> None:
        self._terminal.setVisible(visible)

    def clear_terminal(self) -> None:
        self._terminal.clear()


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 3 – Diversity
# ═════════════════════════════════════════════════════════════════════════════

class DiversityPage(QWidget):
    """
    Matplotlib-based Diversity page.
    Stat cards + alpha bar chart + beta PCoA scatter + dissimilarity heatmap.
    Only shows data after state.pipeline_complete is True.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state: AppState | None = None
        self._alpha_metric = "shannon"
        self._beta_metric  = "bray_curtis"
        self._alpha_cache: dict[int, dict[str, float]]                      = {}
        self._feat_cache:  dict[int, int]                                   = {}
        self._beta_cache:  dict[str, list[list[float]] | None]              = {}
        self._pcoa_cache:  dict[str, dict[str, tuple[float, float]] | None] = {}
        self._build()
 
    # ── Layout ────────────────────────────────────────────────────────────────
 
    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        import matplotlib.pyplot as plt

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner_w = QWidget()
        scroll.setWidget(inner_w)
        root = QVBoxLayout(inner_w)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Diversity"))
        hdr.addStretch()
        root.addLayout(hdr)

        # ── Stat cards ────────────────────────────────────────────────────
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        self._stat_asv     = self._make_stat_card("—", "ASVs detected",   "#6366F1")
        self._stat_shannon = self._make_stat_card("—", "Avg Shannon",     "#10B981")
        self._stat_simpson = self._make_stat_card("—", "Avg Simpson",     "#F59E0B")
        self._stat_genera  = self._make_stat_card("—", "Genera detected", "#8B5CF6")
        for w in (self._stat_asv, self._stat_shannon, self._stat_simpson, self._stat_genera):
            stat_row.addWidget(w)
        root.addLayout(stat_row)

        # ── Alpha chart card ──────────────────────────────────────────────
        alpha_card = card()
        root.addWidget(alpha_card)
        ah = QHBoxLayout()
        ah.addWidget(section_title("Alpha diversity — per run"))
        ah.addWidget(label_hint("Within-sample species richness and evenness"))
        ah.addStretch()
        self._alpha_sw = PillSwitcher(["Shannon", "Simpson"], obj_name="metric_pill")
        self._alpha_sw.on_changed(self._on_alpha_metric)
        ah.addWidget(self._alpha_sw)
        alpha_card.layout().addLayout(ah)

        self._alpha_fig, self._alpha_ax = plt.subplots(1, 1, figsize=(9, 3), facecolor="none")
        self._alpha_canvas = FigureCanvasQTAgg(self._alpha_fig)
        self._alpha_canvas.setMinimumHeight(200)
        alpha_card.layout().addWidget(self._alpha_canvas)
        self._alpha_placeholder = _placeholder(
            "Run the QIIME2 pipeline to compute alpha diversity."
        )
        alpha_card.layout().addWidget(self._alpha_placeholder)
        self._alpha_canvas.hide()

        # ── Beta section ──────────────────────────────────────────────────
        beta_hdr = QHBoxLayout()
        beta_hdr.addWidget(section_title("Beta diversity — between runs"))
        beta_hdr.addStretch()
        self._beta_sw = PillSwitcher(["Bray-Curtis", "UniFrac"], obj_name="metric_pill")
        self._beta_sw.on_changed(self._on_beta_metric)
        beta_hdr.addWidget(QLabel("Metric:"))
        beta_hdr.addWidget(self._beta_sw)
        root.addLayout(beta_hdr)

        beta_row = QHBoxLayout()
        beta_row.setSpacing(16)

        pcoa_card = card()
        pcoa_card.layout().addWidget(section_title("PCoA scatter"))
        pcoa_card.layout().addWidget(
            label_hint("Runs projected by dissimilarity — closer = more similar")
        )
        self._pcoa_fig = plt.figure(figsize=(5, 4), facecolor="none")
        self._pcoa_ax  = self._pcoa_fig.add_subplot(111)
        self._pcoa_canvas = FigureCanvasQTAgg(self._pcoa_fig)
        self._pcoa_canvas.setMinimumHeight(280)
        pcoa_card.layout().addWidget(self._pcoa_canvas)
        self._pcoa_placeholder = _placeholder("Run the pipeline with ≥2 runs to compute PCoA.")
        self._pcoa_no_unifrac  = _placeholder(
            "UniFrac requires a phylogenetic tree — run phylogeny first."
        )
        pcoa_card.layout().addWidget(self._pcoa_placeholder)
        pcoa_card.layout().addWidget(self._pcoa_no_unifrac)
        self._pcoa_canvas.hide()
        self._pcoa_no_unifrac.hide()
        beta_row.addWidget(pcoa_card, 3)

        hm_card = card()
        hm_card.layout().addWidget(section_title("Dissimilarity heatmap"))
        hm_card.layout().addWidget(label_hint("0.0 = identical  ·  1.0 = maximally different"))
        self._hm_fig = plt.figure(figsize=(4, 4), facecolor="none")
        self._hm_ax  = self._hm_fig.add_subplot(111)
        self._hm_colorbar = None
        self._hm_canvas = FigureCanvasQTAgg(self._hm_fig)
        self._hm_canvas.setMinimumHeight(280)
        hm_card.layout().addWidget(self._hm_canvas)
        self._hm_placeholder = _placeholder("Run the pipeline with ≥2 runs.")
        self._hm_no_unifrac  = _placeholder("UniFrac requires a phylogenetic tree.")
        hm_card.layout().addWidget(self._hm_placeholder)
        hm_card.layout().addWidget(self._hm_no_unifrac)
        self._hm_canvas.hide()
        self._hm_no_unifrac.hide()
        beta_row.addWidget(hm_card, 2)

        self._single_run_notice = _placeholder(
            "Beta diversity requires ≥2 runs. Add more runs to this project."
        )
        beta_w = QWidget()
        beta_l = QVBoxLayout(beta_w)
        beta_l.setContentsMargins(0, 0, 0, 0)
        beta_l.setSpacing(10)
        beta_l.addLayout(beta_row)
        beta_l.addWidget(self._single_run_notice)
        root.addWidget(beta_w)
        root.addStretch()

    @staticmethod
    def _make_stat_card(value: str, label: str, accent: str) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        f.setMinimumWidth(130)
        l = QVBoxLayout(f)
        l.setContentsMargins(16, 14, 16, 14)
        l.setSpacing(4)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(f"font-size:26px;font-weight:700;color:{accent};")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lbl = QLabel(label)
        lbl.setObjectName("label_hint")
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        l.addWidget(val_lbl)
        l.addWidget(lbl)
        f._val_lbl = val_lbl
        return f

    @staticmethod
    def _set_stat(frame: QFrame, value: str) -> None:
        frame._val_lbl.setText(value)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, state: AppState) -> None:
        self._state = state
        self._alpha_cache.clear()
        self._feat_cache.clear()
        self._beta_cache.clear()
        self._pcoa_cache.clear()

        if not state.pipeline_complete:
            self._reset_to_pending()
            return

        self._refresh_stats()
        self._refresh_alpha()
        self._refresh_beta()

    def _reset_to_pending(self) -> None:
        for c in (self._stat_asv, self._stat_shannon, self._stat_simpson, self._stat_genera):
            self._set_stat(c, "—")
        self._alpha_canvas.hide()
        self._alpha_placeholder.setText("Run the QIIME2 pipeline to compute diversity metrics.")
        self._alpha_placeholder.show()
        self._pcoa_canvas.hide()
        self._pcoa_placeholder.setText("Run the QIIME2 pipeline to compute beta diversity.")
        self._pcoa_placeholder.show()
        self._pcoa_no_unifrac.hide()
        self._hm_canvas.hide()
        self._hm_placeholder.setText("Run the QIIME2 pipeline to compute beta diversity.")
        self._hm_placeholder.show()
        self._hm_no_unifrac.hide()
        self._single_run_notice.hide()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def _refresh_stats(self) -> None:
        if not self._state or not self._state.lbs:
            return
        total_asvs   = 0
        total_genera = 0
        shannon_vals: list[float] = []
        simpson_vals: list[float] = []

        for label in self._state.run_labels:
            run_id = self._state.lbs.get(label)
            if run_id is None:
                continue
            if run_id not in self._feat_cache:
                try:
                    rows = get_feature_counts(run_id)
                    self._feat_cache[run_id] = len(rows)
                except ServiceError:
                    self._feat_cache[run_id] = 0
            total_asvs += self._feat_cache[run_id]

            alpha = self._fetch_alpha(run_id)
            if "shannon" in alpha:
                shannon_vals.append(alpha["shannon"])
            if "simpson" in alpha:
                simpson_vals.append(alpha["simpson"])

            try:
                genera = get_genus_data(run_id)
                total_genera += len(genera)
            except ServiceError:
                pass

        self._set_stat(self._stat_asv, f"{total_asvs:,}")
        self._set_stat(self._stat_shannon,
            f"{sum(shannon_vals)/len(shannon_vals):.3f}" if shannon_vals else "—")
        self._set_stat(self._stat_simpson,
            f"{sum(simpson_vals)/len(simpson_vals):.3f}" if simpson_vals else "—")
        self._set_stat(self._stat_genera, str(total_genera) if total_genera else "—")

    # ── Alpha ─────────────────────────────────────────────────────────────────

    def _fetch_alpha(self, run_id: int) -> dict[str, float]:
        if run_id in self._alpha_cache:
            return self._alpha_cache[run_id]
        try:
            rows   = get_alpha_diversities(run_id)
            result = {r["metric"]: float(r["value"]) for r in rows}
        except ServiceError:
            result = {}
        self._alpha_cache[run_id] = result
        return result

    def _refresh_alpha(self) -> None:
        if not self._state or not self._state.lbs:
            self._alpha_canvas.hide()
            self._alpha_placeholder.show()
            return

        bars:   list[tuple[str, float]] = []
        colors: list[str]               = []
        run_colors = self._state.run_colors()

        for label in self._state.run_labels:
            run_id = self._state.lbs.get(label)
            if run_id is None:
                continue
            val = self._fetch_alpha(run_id).get(self._alpha_metric)
            if val is not None:
                bars.append((label, val))
                colors.append(run_colors.get(label, "#6366F1"))

        if not bars:
            self._alpha_canvas.hide()
            self._alpha_placeholder.show()
            return

        ax = self._alpha_ax
        ax.clear()
        labels_ax, values = zip(*bars)
        xs = list(range(len(labels_ax)))
        b  = ax.bar(xs, values, color=colors, width=0.5, zorder=3)
        ax.bar_label(b, fmt="%.3f", padding=3, fontsize=9)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels_ax, fontsize=10)
        ylabel = ("Shannon entropy (bits)"
                  if self._alpha_metric == "shannon"
                  else "Simpson index (0–1)")
        ax.set_ylabel(ylabel, fontsize=9)
        ax.tick_params(axis="y", labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_facecolor("none")
        ax.grid(axis="y", alpha=0.3, zorder=0)
        self._alpha_fig.tight_layout(pad=1.0)
        self._alpha_canvas.draw()
        self._alpha_canvas.show()
        self._alpha_placeholder.hide()

    # ── Beta ──────────────────────────────────────────────────────────────────

    def _fetch_beta_matrix(self, metric: str) -> list[list[float]] | None:
        if metric in self._beta_cache:
            return self._beta_cache[metric]
        if not self._state or not self._state.db_project_id:
            return None
        try:
            flat = get_beta_diversity_matrix(self._state.db_project_id, metric)
        except ServiceError:
            flat = []
        if not flat:
            self._beta_cache[metric] = None
            return None
        labels    = self._state.run_labels
        n         = len(labels)
        mat       = [[0.0] * n for _ in range(n)]
        id_to_idx = {
            self._state.lbs[lbl]: i
            for i, lbl in enumerate(labels)
            if lbl in self._state.lbs
        }
        for row in flat:
            i = id_to_idx.get(row["run_id_1"])
            j = id_to_idx.get(row["run_id_2"])
            if i is not None and j is not None:
                val       = float(row["value"])
                mat[i][j] = val
                mat[j][i] = val
        self._beta_cache[metric] = mat
        return mat

    def _fetch_pcoa_coords(self, metric: str) -> dict[str, tuple[float, float]] | None:
        if metric in self._pcoa_cache:
            return self._pcoa_cache[metric]
        if not self._state or not self._state.db_project_id:
            return None
        try:
            rows = get_pcoa(self._state.db_project_id, metric)
        except ServiceError:
            rows = []
        if not rows:
            self._pcoa_cache[metric] = None
            return None
        id_to_label = {v: k for k, v in self._state.lbs.items()}
        coords = {
            id_to_label[r["run_id"]]: (float(r["pc1"]), float(r["pc2"]))
            for r in rows
            if r["run_id"] in id_to_label
        }
        result = coords if coords else None
        self._pcoa_cache[metric] = result
        return result

    def _refresh_beta(self) -> None:
        lbs_count = len(self._state.lbs) if self._state else 0
        if lbs_count < 2:
            self._pcoa_canvas.hide()
            self._hm_canvas.hide()
            self._pcoa_placeholder.hide()
            self._hm_placeholder.hide()
            self._pcoa_no_unifrac.hide()
            self._hm_no_unifrac.hide()
            self._single_run_notice.show()
            return

        self._single_run_notice.hide()
        metric = self._beta_metric
        matrix = self._fetch_beta_matrix(metric)
        coords = self._fetch_pcoa_coords(metric)

        if matrix is None or coords is None:
            self._pcoa_canvas.hide()
            self._hm_canvas.hide()
            if metric == "unifrac":
                self._pcoa_placeholder.hide()
                self._hm_placeholder.hide()
                self._pcoa_no_unifrac.show()
                self._hm_no_unifrac.show()
            else:
                self._pcoa_placeholder.show()
                self._hm_placeholder.show()
                self._pcoa_no_unifrac.hide()
                self._hm_no_unifrac.hide()
            return

        self._pcoa_placeholder.hide()
        self._hm_placeholder.hide()
        self._pcoa_no_unifrac.hide()
        self._hm_no_unifrac.hide()
        self._render_pcoa(coords, metric)
        self._render_heatmap(matrix)

    def _render_pcoa(self, coords: dict, metric: str) -> None:
        run_colors = self._state.run_colors()
        ax = self._pcoa_ax
        ax.clear()
        for lbl, (x, y) in coords.items():
            color = run_colors.get(lbl, "#6366F1")
            ax.scatter(x, y, c=color, s=130, zorder=3, edgecolors="white", linewidths=0.8)
            ax.annotate(lbl, (x, y), textcoords="offset points", xytext=(7, 4), fontsize=9)
        title = "Bray-Curtis PCoA" if metric == "bray_curtis" else "UniFrac PCoA"
        ax.set_title(title, fontsize=10, pad=6)
        ax.set_xlabel("PC1", fontsize=9)
        ax.set_ylabel("PC2", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_facecolor("none")
        self._pcoa_fig.tight_layout(pad=1.0)
        self._pcoa_canvas.draw()
        self._pcoa_canvas.show()

    def _render_heatmap(self, matrix: list[list[float]]) -> None:
        import numpy as np
        labels = self._state.run_labels
        # Clear the entire figure (removes axes + all colorbar axes) then
        # recreate fresh — colorbar.remove() alone doesn't restore host-axes
        # size and causes the colorbar strip to stack on every metric switch.
        self._hm_fig.clear()
        ax = self._hm_fig.add_subplot(111)
        self._hm_ax = ax
        mat = np.array(matrix)
        im  = ax.imshow(mat, cmap="YlOrRd", vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(labels)))
        ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
        ax.set_yticklabels(labels, fontsize=9)
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, f"{mat[i, j]:.2f}",
                        ha="center", va="center", fontsize=8,
                        color="white" if mat[i, j] > 0.6 else "black")
        self._hm_colorbar = self._hm_fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        ax.set_facecolor("none")
        self._hm_fig.tight_layout(pad=1.0)
        self._hm_canvas.draw()
        self._hm_canvas.show()

    # ── Pill callbacks ────────────────────────────────────────────────────────

    def _on_alpha_metric(self, label: str) -> None:
        self._alpha_metric = "shannon" if "shannon" in label.lower() else "simpson"
        if self._state and self._state.pipeline_complete:
            self._refresh_alpha()

    def _on_beta_metric(self, label: str) -> None:
        self._beta_metric = "bray_curtis" if "bray" in label.lower() else "unifrac"
        if self._state and self._state.pipeline_complete:
            self._refresh_beta()

# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 4 – Taxonomy
# ═════════════════════════════════════════════════════════════════════════════

class TaxonomyPage(QWidget):
    # def __init__(self, parent=None):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state: AppState | None = None
        self._active_run = "R1"
        self._genus_cache: dict[int, list[dict]] = {}
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

        # emma taxonomy
        # ── Row 1: stacked bar (all runs) — shown first so no scrolling needed
        comp_card = card()
        comp_card.layout().addWidget(
            section_title("Genus composition across runs")
        )
        self._stacked = StackedBarWidget(data={}, colors=GENUS_COLORS)
        comp_card.layout().addWidget(self._stacked)
        self._stacked_placeholder = _placeholder(
            "Upload FASTQ files to see composition across all runs."
        )
        comp_card.layout().addWidget(self._stacked_placeholder)
        self._root.addWidget(comp_card)

        # ── Row 2: bar chart  +  legend (per-run) ─────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(12)

        bar_card = card()
        bar_card.layout().addWidget(section_title("Top 10 genera by relative abundance"))
        self._bar = BarChartWidget(data=[], colors=GENUS_COLORS)
        self._bar.setFixedHeight(160)
        bar_card.layout().addWidget(self._bar)
        self._bar_placeholder = _placeholder(
            "Upload FASTQ files to compute taxonomy."
        )
        bar_card.layout().addWidget(self._bar_placeholder)
        cols.addWidget(bar_card, 3)

        tax_card = card()
        tax_card.layout().addWidget(section_title("Genus abundance overview"))
        self._legend_layout = QVBoxLayout()
        self._legend_layout.setSpacing(4)
        tax_card.layout().addLayout(self._legend_layout)
        self._legend_placeholder = _placeholder("No data yet.")
        self._legend_layout.addWidget(self._legend_placeholder)
        cols.addWidget(tax_card, 2)

        self._root.addLayout(cols)

        # ── Row 3: sortable genus table (all genera, current run) ─────────
        genus_tbl_card = card()
        genus_tbl_card.layout().addWidget(
            section_title("Genus abundance table")
        )
        genus_tbl_card.layout().addWidget(
            label_muted(
                "Switch runs with the run button above."
            )
        )
        self._genus_table = GenusTableWidget()
        self._genus_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        genus_tbl_card.layout().addWidget(self._genus_table)
        self._genus_tbl_placeholder = _placeholder(
            "Upload FASTQ files to populate the genus table."
        )
        genus_tbl_card.layout().addWidget(self._genus_tbl_placeholder)
        self._genus_table.hide()
        self._root.addWidget(genus_tbl_card, 1)

        self._root.addStretch()
        # emma taxonomy

        # # Two-column row
        # cols = QHBoxLayout(); cols.setSpacing(12)

        # bar_card = card()
        # bar_card.layout().addWidget(section_title("Top genera — relative abundance"))
        # self._bar = BarChartWidget(data=[], colors=GENUS_COLORS)
        # self._bar.setFixedHeight(160)
        # bar_card.layout().addWidget(self._bar)
        # self._bar_placeholder = _placeholder("Upload FASTQ files to compute taxonomy.")
        # bar_card.layout().addWidget(self._bar_placeholder)
        # cols.addWidget(bar_card, 3)

        # tax_card = card()
        # tax_card.layout().addWidget(section_title("Genus abundance breakdown"))
        # self._legend_layout = QVBoxLayout(); self._legend_layout.setSpacing(4)
        # tax_card.layout().addLayout(self._legend_layout)
        # self._legend_placeholder = _placeholder("No data yet.")
        # self._legend_layout.addWidget(self._legend_placeholder)
        # cols.addWidget(tax_card, 2)
        # self._root.addLayout(cols)

        # # Stacked bar
        # comp_card = card()
        # comp_card.layout().addWidget(section_title("Genus composition — all runs"))
        # self._stacked = StackedBarWidget(data={}, colors=GENUS_COLORS)
        # comp_card.layout().addWidget(self._stacked)
        # self._stacked_placeholder = _placeholder(
        #     "Upload FASTQ files to see composition across all runs.")
        # comp_card.layout().addWidget(self._stacked_placeholder)
        # self._root.addWidget(comp_card)
        # self._root.addStretch()

    def load(self, state: AppState):
        self._state = state

        # # Rebuild run switcher if run labels changed
        # old_active = self._active_run
        # labels = state.run_labels or ["—"]

        # # Reconnect switcher
        # new_sw = PillSwitcher(labels, obj_name="pill")
        # new_sw.on_changed(self._on_run)
        # hdr_lay = self._root.itemAt(0).layout()
        # # Replace old switcher widget
        # old_sw_item = hdr_lay.itemAt(hdr_lay.count() - 1)
        # if old_sw_item and old_sw_item.widget():
        #     old_sw_item.widget().deleteLater()
        # hdr_lay.addWidget(new_sw)
        # self._run_sw = new_sw

        # self._active_run = labels[0] if labels else "R1"
        # self._refresh(self._active_run)

        # # Stacked bar
        # if state.genus_abundances:
        #     self._stacked.set_data(state.genus_abundances)
        #     self._stacked.show()
        #     self._stacked_placeholder.hide()
        # else:
        #     self._stacked.hide()
        #     self._stacked_placeholder.show()

        # emma load
        self._genus_cache.clear()       # invalidate cache on new project load

        if not state.pipeline_complete:
            self._bar.hide()
            self._bar_placeholder.setText("Run the QIIME2 pipeline to compute taxonomy.")
            self._bar_placeholder.show()
            self._genus_table.hide()
            self._genus_tbl_placeholder.setText("Run the QIIME2 pipeline to populate the genus table.")
            self._genus_tbl_placeholder.show()
            self._stacked.hide()
            self._stacked_placeholder.setText("Run the QIIME2 pipeline to see composition.")
            self._stacked_placeholder.show()
            return

        labels = state.run_labels or ["—"]

        # ── Rebuild run switcher ──────────────────────────────────────────
        new_sw = PillSwitcher(labels, obj_name="pill")
        new_sw.on_changed(self._on_run)
        hdr_lay = self._root.itemAt(0).layout()
        old_item = hdr_lay.itemAt(hdr_lay.count() - 1)
        if old_item and old_item.widget():
            old_item.widget().deleteLater()
        hdr_lay.addWidget(new_sw)
        self._run_sw = new_sw

        self._active_run = labels[0] if labels else "R1"
        self._refresh(self._active_run)

        # ── Stacked bar: load all runs at once ────────────────────────────
        self._refresh_stacked()
        # emma load

    def _get_genus_data(self, run_label: str) -> list[dict]:
        """
        Return genus data for run_label using the in-memory cache.
        Returns [] on any error or missing mapping.
        """
        if not self._state:
            return []
        run_id = self._state.lbs.get(run_label)
        if run_id is None:
            return []
        if run_id in self._genus_cache:
            return self._genus_cache[run_id]
        try:
            data = get_genus_data(run_id)
        except ServiceError:
            data = []
        self._genus_cache[run_id] = data
        return data

    def _refresh(self, run_label: str):
        # if not self._state or not self._state.genus_abundances:
        #     self._bar.hide(); self._bar_placeholder.show()
        #     return

        # genera = self._state.genus_abundances.get(run, [])
        # if not genera:
        #     self._bar.hide(); self._bar_placeholder.show()
        #     return

        # self._bar.set_data(genera[:10])
        # self._bar.show(); self._bar_placeholder.hide()
        # self._build_legend(genera)

        # emma refresh
        genera = self._get_genus_data(run_label)

        if not genera:
            self._bar.hide()
            self._bar_placeholder.show()
            self._genus_table.hide()
            self._genus_tbl_placeholder.show()
            return

        # ── Bar chart: top 10 ─────────────────────────────────────────────
        # BarChartWidget expects list[tuple[str, float]]
        top10 = [
            (g["genus"], g["relative_abundance"])
            for g in sorted(genera, key=lambda x: x["relative_abundance"], reverse=True)[:10]
        ]
        self._bar.set_data(top10)
        self._bar.show()
        self._bar_placeholder.hide()

        # ── Legend: top 5 + "Other" ───────────────────────────────────────
        self._build_legend(genera)

        # ── Genus table: all genera ───────────────────────────────────────
        self._genus_table.set_data(genera)
        self._genus_table.show()
        self._genus_tbl_placeholder.hide()
        # emma refresh

    def _refresh_stacked(self) -> None:
        """
        Build the stacked bar from DB data for every run in the project.
        StackedBarWidget expects dict[run_label, list[tuple[genus, abundance]]].
        """
        if not self._state or not self._state.run_labels:
            self._stacked.hide()
            self._stacked_placeholder.show()
            return

        stacked_data: dict[str, list[tuple[str, float]]] = {}
        for label in self._state.run_labels:
            genera = self._get_genus_data(label)
            if genera:
                stacked_data[label] = [
                    (g["genus"], g["relative_abundance"]) for g in genera
                ]

        if stacked_data:
            self._stacked.set_data(stacked_data)
            self._stacked.show()
            self._stacked_placeholder.hide()
        else:
            self._stacked.hide()
            self._stacked_placeholder.show()
    
    def _build_legend(self, genera: list[tuple[str, float]]):
        # _clear(self._legend_layout)
        # top5  = genera[:5]
        # other = sum(p for _, p in genera[5:])
        # for i, (g, v) in enumerate(top5):
        #     row = QHBoxLayout(); row.setSpacing(6)
        #     dot = QLabel("●")
        #     dot.setStyleSheet(f"color:{GENUS_COLORS[i % len(GENUS_COLORS)]}; font-size:11px;")
        #     txt = label_muted(f"{g}   {v:.1f}%")
        #     row.addWidget(dot); row.addWidget(txt); row.addStretch()
        #     self._legend_layout.addLayout(row)
        # if other > 0:
        #     row = QHBoxLayout(); row.setSpacing(6)
        #     dot = QLabel("●"); dot.setStyleSheet("color:#D1D5DB; font-size:11px;")
        #     txt = label_muted(f"Other   {other:.1f}%")
        #     row.addWidget(dot); row.addWidget(txt); row.addStretch()
        #     self._legend_layout.addLayout(row)

        # emma build legend
        _clear(self._legend_layout)
        sorted_genera = sorted(
            genera, key=lambda x: x["relative_abundance"], reverse=True
        )
        top10  = sorted_genera[:10]

        for i, g in enumerate(top10):
            row = QHBoxLayout()
            row.setSpacing(6)
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color:{GENUS_COLORS[i % len(GENUS_COLORS)]}; font-size:11px;"
            )
            txt = label_muted(f"{g['genus']}   {g['relative_abundance']:.1f}%")
            row.addWidget(dot)
            row.addWidget(txt)
            row.addStretch()
            self._legend_layout.addLayout(row)
        # emma build legend

    # def _on_run(self, run: str):
    #     self._active_run = run
    #     self._refresh(run)
    def _on_run(self, run_label: str) -> None:
        self._active_run = run_label
        self._refresh(run_label)


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 5 – ASV Table
# ═════════════════════════════════════════════════════════════════════════════

class AsvTablePage(QWidget):
    # def __init__(self, parent=None):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state: AppState | None = None
        self._active_run = "R1"
        self._build()

    def _build(self):
        # root = QVBoxLayout(self)
        # root.setContentsMargins(28, 24, 28, 24)
        # root.setSpacing(14)

        # hdr = QHBoxLayout()
        # hdr.addWidget(page_title("ASV Table"))
        # self._run_sw = PillSwitcher(["—"], obj_name="pill")
        # hdr.addStretch(); hdr.addWidget(self._run_sw)
        # root.addLayout(hdr)

        # ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        # ctrl.addWidget(label_muted("Sort:"))
        # self._sort_id  = btn_outline("Feature ID ↕")
        # self._sort_cnt = btn_outline("Count ↓")
        # self._sort_id.clicked.connect(lambda: self._table.sortItems(0))
        # self._sort_cnt.clicked.connect(lambda: self._table.sortItems(2))
        # ctrl.addWidget(self._sort_id); ctrl.addWidget(self._sort_cnt)

        # # Summary label
        # self._summary_lbl = QLabel("")
        # self._summary_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_M};")
        # ctrl.addStretch(); ctrl.addWidget(self._summary_lbl)
        # root.addLayout(ctrl)

        # tbl_card = card()
        # root.addWidget(tbl_card, 1)

        # self._table = QTableWidget(0, 4)
        # self._table.setHorizontalHeaderLabels(["Feature ID", "Taxonomy", "Count", "Rel. %"])
        # self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # self._table.setAlternatingRowColors(True)
        # tbl_card.layout().addWidget(self._table)

        # self._placeholder = _placeholder(
        #     "Fetch a project and upload FASTQ files to populate the ASV table.")
        # tbl_card.layout().addWidget(self._placeholder)
        # self._table.hide()
        
        # emma build
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        # Header row: title + run pill switcher
        hdr = QHBoxLayout()
        hdr.addWidget(page_title("ASV Table"))
        self._run_sw = PillSwitcher(["—"], obj_name="pill")
        hdr.addStretch()
        hdr.addWidget(self._run_sw)
        root.addLayout(hdr)

        # Control row: sort buttons + summary label
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        self._summary_lbl = label_muted("")
        ctrl.addStretch()
        ctrl.addWidget(self._summary_lbl)
        root.addLayout(ctrl)

        # Table inside a card
        tbl_card = card()
        root.addWidget(tbl_card, 1)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(
            ["Feature ID", "Taxonomy", "Count"]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        # Count column doesn't need to stretch as wide
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSortIndicatorShown(True)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        tbl_card.layout().addWidget(self._table)

        self._placeholder = _placeholder(
            "Fetch a project and upload FASTQ files to populate the ASV table."
        )
        tbl_card.layout().addWidget(self._placeholder)
        self._table.hide()
        # emma build

    def load(self, state: AppState):
        self._state = state

        if not state.pipeline_complete:
            self._show_placeholder()
            return

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

    def _populate(self, run_label: str):
        # emma populate
        if not self._state:
            self._show_placeholder()
            return
        
        run_id = self._state.lbs.get(run_label)
        if run_id is None:
            self._show_placeholder()

        try:
            rows = get_feature_counts(run_id)
        except ServiceError:
            self._show_placeholder()
            return
        
        if not rows:
            self._show_placeholder()
            return

        # disable sort while filling
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))

        for i, feat in enumerate(rows):
            feature_id = feat.get("feature_id", "")
            taxonomy   = feat.get("taxonomy") or "Unclassified"
            count      = int(feat.get("abundance", 0))

            from PyQt6.QtWidgets import QTableWidgetItem
            id_item  = QTableWidgetItem(feature_id)
            tax_item = QTableWidgetItem(taxonomy)

            cnt_item = NumericSortItem(count, fmt=",")

            self._table.setItem(i, 0, id_item)
            self._table.setItem(i, 1, tax_item)
            self._table.setItem(i, 2, cnt_item)

        self._table.setSortingEnabled(True)
        self._table.sortItems(2, Qt.SortOrder.DescendingOrder) # default sorting

        self._summary_lbl.setText(
            f"{len(rows)} ASVs · {run_label}"
        )
        self._table.show()
        self._placeholder.hide()
        # emma populate

        # if not self._state or not self._state.asv_features:
        #     self._table.hide(); self._placeholder.show()
        #     self._summary_lbl.setText("")
        #     return

        # rows = self._state.asv_features.get(run, [])
        # if not rows:
        #     self._table.hide(); self._placeholder.show()
        #     self._summary_lbl.setText("")
        #     return

        # self._table.setRowCount(len(rows))
        # for r, feat in enumerate(rows):
        #     self._table.setItem(r, 0, QTableWidgetItem(feat["id"]))
        #     self._table.setItem(r, 1, QTableWidgetItem(feat["genus"]))
        #     count_item = QTableWidgetItem()
        #     count_item.setData(Qt.ItemDataRole.DisplayRole, f"{feat['count']:,}")
        #     count_item.setData(Qt.ItemDataRole.UserRole, feat["count"])
        #     self._table.setItem(r, 2, count_item)
        #     self._table.setItem(r, 3, QTableWidgetItem(f"{feat['pct']:.2f}"))

        # self._summary_lbl.setText(
        #     f"{len(rows)} ASVs  ·  {run}  ·  "
        #     f"{sum(f['count'] for f in rows):,} total reads")
        # self._table.show(); self._placeholder.hide()

    def _on_run(self, run_label: str):
        self._active_run = run_label
        self._populate(run_label)

    def _show_placeholder(self) -> None:
        self._table.hide()
        self._placeholder.show()
        self._summary_lbl.setText("")


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 6 – Phylogeny
# ═════════════════════════════════════════════════════════════════════════════

class _TreeNode:
    """Minimal Newick tree node — no skbio dependency, iterative parser."""

    __slots__ = ("name", "length", "parent", "children")

    def __init__(self, name: str = "", length=None):
        self.name     = name
        self.length   = length
        self.parent   = None
        self.children: list = []

    def is_tip(self) -> bool:
        return not self.children

    def tips(self):
        for node in self.postorder():
            if node.is_tip():
                yield node

    def non_tips(self):
        for node in self.postorder():
            if not node.is_tip():
                yield node

    def preorder(self):
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            for c in reversed(node.children):
                stack.append(c)

    def postorder(self):
        stack = [(self, False)]
        while stack:
            node, done = stack.pop()
            if done:
                yield node
            else:
                stack.append((node, True))
                for c in reversed(node.children):
                    stack.append((c, False))

    def shear(self, keep: set) -> "_TreeNode":
        """Prune in-place, keep only tips whose names are in *keep*."""
        def _prune(node) -> bool:
            if node.is_tip():
                return node.name in keep
            node.children = [c for c in node.children if _prune(c)]
            return bool(node.children)
        _prune(self)
        return self

    @classmethod
    def read(cls, f) -> "_TreeNode":
        """Parse Newick from a file-like object (iterative — safe for deep trees)."""
        s = f.read().strip().rstrip(";")
        return cls._parse(s)

    @classmethod
    def _parse(cls, s: str) -> "_TreeNode":
        root    = cls()
        current = root
        i, n    = 0, len(s)

        while i < n:
            ch = s[i]

            if ch == "(":
                child        = cls()
                child.parent = current
                current.children.append(child)
                current = child
                i += 1

            elif ch == ",":
                current = current.parent
                child        = cls()
                child.parent = current
                current.children.append(child)
                current = child
                i += 1

            elif ch == ")":
                current = current.parent
                i += 1
                j = i
                while j < n and s[j] not in ",)(":
                    j += 1
                cls._apply_label(current, s[i:j])
                i = j

            else:
                j = i
                while j < n and s[j] not in ",)(":
                    j += 1
                cls._apply_label(current, s[i:j])
                i = j

        return root

    @staticmethod
    def _apply_label(node, label: str) -> None:
        label = label.strip()
        if not label:
            return
        if ":" in label:
            colon      = label.index(":")
            node.name  = label[:colon].strip().strip("'\"")
            try:
                node.length = float(label[colon + 1:].strip())
            except ValueError:
                node.length = None
        else:
            node.name = label.strip("'\"")

    def to_newick(self) -> str:
        """Serialize tree to a Newick string (iterative — no recursion limit)."""
        buf = []
        # Stack items: (node, next_child_index_to_push; -1 = first visit)
        stk = [(self, -1)]

        while stk:
            node, ci = stk[-1]

            if ci == -1:
                if node.children:
                    buf.append("(")
                    stk[-1] = (node, 1)                   # child[0] pushed next
                    stk.append((node.children[0], -1))
                else:
                    buf.append(node.name or "")
                    if node.length is not None:
                        buf.append(f":{node.length}")
                    stk.pop()
                    if stk and stk[-1][1] < len(stk[-1][0].children):
                        buf.append(",")
            elif ci < len(node.children):
                stk[-1] = (node, ci + 1)
                stk.append((node.children[ci], -1))
            else:
                buf.append(")")
                if node.name:
                    buf.append(node.name)
                if node.length is not None:
                    buf.append(f":{node.length}")
                stk.pop()
                if stk and stk[-1][1] < len(stk[-1][0].children):
                    buf.append(",")

        buf.append(";")
        return "".join(buf)


class PhylogenyPage(QWidget):
    """
    Renders the project's rooted phylogenetic tree (Newick) as a rectangular
    phylogram using matplotlib.  Up to MAX_TIPS tips are shown; larger trees
    are subsampled at regular intervals so the topology is representative.
    """
    MAX_TIPS = 70

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        inner_w = QWidget()
        scroll.setWidget(inner_w)
        root = QVBoxLayout(inner_w)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(20)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Phylogenetic Tree"))
        hdr.addWidget(label_hint("inferred from ASV representative sequences"))
        hdr.addStretch()
        root.addLayout(hdr)

        # Stat cards
        stat_row = QHBoxLayout()
        stat_row.setSpacing(12)
        self._stat_tips   = self._make_stat("—", "Total Tips",      "#6366F1")
        self._stat_nodes  = self._make_stat("—", "Internal Nodes",  "#10B981")
        self._stat_depth  = self._make_stat("—", "Max Branch Depth","#F59E0B")
        for w in (self._stat_tips, self._stat_nodes, self._stat_depth):
            stat_row.addWidget(w)
        stat_row.addStretch()
        root.addLayout(stat_row)

        # Tree card
        tree_card = card()
        root.addWidget(tree_card, 1)

        self._placeholder = QLabel(
            "Run the QIIME2 pipeline to generate the phylogenetic tree.")
        self._placeholder.setObjectName("label_hint")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        tree_card.layout().addWidget(self._placeholder)

        fig_h = max(self.MAX_TIPS * 0.18, 8)
        self._fig = Figure(figsize=(10, fig_h), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._canvas.hide()
        tree_card.layout().addWidget(self._canvas, 1)

        self._note = QLabel("")
        self._note.setObjectName("label_hint")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note.hide()
        tree_card.layout().addWidget(self._note)

    @staticmethod
    def _make_stat(value: str, label: str, accent: str) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        f.setMinimumWidth(140)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(f"font-size:26px;font-weight:700;color:{accent};")
        lbl = QLabel(label)
        lbl.setObjectName("label_hint")
        lay.addWidget(val_lbl)
        lay.addWidget(lbl)
        f._val_lbl = val_lbl
        return f

    @staticmethod
    def _set_stat(frame: QFrame, value: str) -> None:
        frame._val_lbl.setText(value)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, state: AppState):
        self._state = state

        if not state.pipeline_complete:
            self._show_placeholder(
                "Run the QIIME2 pipeline to generate the phylogenetic tree.")
            return

        newick = self._fetch_newick(state)
        if not newick:
            self._show_placeholder("No phylogenetic tree found for this project.")
            return

        self._render(newick)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _show_placeholder(self, msg: str) -> None:
        self._placeholder.setText(msg)
        self._placeholder.show()
        self._canvas.hide()
        self._note.hide()
        for w in (self._stat_tips, self._stat_nodes, self._stat_depth):
            self._set_stat(w, "—")

    @staticmethod
    def _fetch_newick(state: AppState) -> str:
        """Try DB first, then fall back to disk."""
        if state.db_project_id:
            try:
                from src.services.assessment_service import get_tree
                info = get_tree(state.db_project_id)
                nwk = info.get("newick_string", "")
                if nwk:
                    return nwk
            except Exception:
                pass

        # Disk fallback for cases where the pipeline just ran
        from pathlib import Path
        base = Path(__file__).parent.parent / "pipeline" / "data"
        if state.bioproject_id:
            for layout in ("single", "paired"):
                p = base / state.bioproject_id / "reps-tree" / layout / "tree.nwk"
                if p.exists():
                    return p.read_text().strip()
        return ""

    def _render(self, newick: str) -> None:
        import io, re
        from io import StringIO
        from Bio import Phylo

        # ── 1. Fast parse (stats + pruning) ───────────────────────────────────
        try:
            fast_tree = _TreeNode.read(io.StringIO(newick))
        except Exception as exc:
            self._show_placeholder(f"Could not parse tree: {exc}")
            return

        all_tips   = list(fast_tree.tips())
        n_total    = len(all_tips)
        n_internal = sum(1 for _ in fast_tree.non_tips())

        def _root_dist(node):
            d = 0.0
            while node.parent:
                d += node.length or 0.0
                node = node.parent
            return d

        try:
            max_depth = max(_root_dist(t) for t in all_tips)
            self._set_stat(self._stat_depth, f"{max_depth:.4f}")
        except Exception:
            self._set_stat(self._stat_depth, "—")
        self._set_stat(self._stat_tips,  f"{n_total:,}")
        self._set_stat(self._stat_nodes, f"{n_internal:,}")

        # ── 2. Build feature_id → genus map from DB ───────────────────────────
        feature_genus: dict[str, str] = {}
        if self._state:
            try:
                from src.services.assessment_service import (
                    get_project_feature_taxonomy, get_feature_counts,
                )
                from src.pipeline.db_import import clean_genus

                raw: dict[str, str] = {}

                if self._state.lbs:
                    for run_id in self._state.lbs.values():
                        try:
                            for row in get_feature_counts(run_id):
                                fid = row.get("feature_id", "")
                                tax = row.get("taxonomy") or ""
                                if fid and tax:
                                    raw[fid] = tax
                        except Exception:
                            pass

                if not raw and self._state.db_project_id:
                    raw = get_project_feature_taxonomy(self._state.db_project_id)

                for fid, tax in raw.items():
                    g = clean_genus(tax)
                    if g and g != "Unclassified":
                        feature_genus[fid] = g
            except Exception:
                pass

        # ── 3. Prefer ASV tips (MD5 / SHA256 hashes) over reference tips ──────
        _hash = re.compile(r'^[0-9a-fA-F]{32,64}$')
        asv_tips = [t for t in all_tips if _hash.match(t.name or "")]
        note_txt = ""

        if asv_tips:
            candidates = asv_tips
            if len(candidates) > self.MAX_TIPS:
                step       = max(1, len(candidates) // self.MAX_TIPS)
                candidates = candidates[::step]
                note_txt   = (
                    f"Showing {len(candidates)} of {len(asv_tips)} ASV tips "
                    f"({n_total:,} total in reference tree)"
                )
            else:
                note_txt = (
                    f"Showing all {len(candidates)} ASV tips "
                    f"({n_total:,} total in reference tree)"
                )
            keep_names = {t.name for t in candidates}
        else:
            step       = max(1, n_total // self.MAX_TIPS)
            keep_names = {t.name for t in all_tips[::step]}
            note_txt   = f"Displaying {len(keep_names)} of {n_total:,} tips (subsampled)"

        fast_tree.shear(keep_names)

        # ── 4. Rename tip nodes in-place with genus names ─────────────────────
        # Baking names into the tree before to_newick() is more reliable than
        # relying on Bio.Phylo's label_func, which varies across versions.
        _safe = re.compile(r'[^A-Za-z0-9_.\-]')
        genus_seen: dict[str, int] = {}
        for tip in fast_tree.tips():
            raw_name = tip.name or ""
            genus = feature_genus.get(raw_name)
            if genus:
                safe = _safe.sub("_", genus)
                idx  = genus_seen.get(safe, 0)
                genus_seen[safe] = idx + 1
                tip.name = safe if idx == 0 else f"{safe}.{idx}"
            elif raw_name:
                tip.name = raw_name[:10]   # short hash fallback

        # ── 5. Export pruned + relabelled subtree → Bio.Phylo ─────────────────
        pruned_nwk = fast_tree.to_newick()
        try:
            bio_tree = Phylo.read(StringIO(pruned_nwk), "newick")
        except Exception as exc:
            self._show_placeholder(f"Bio.Phylo render error: {exc}")
            return

        # ── 6. Draw ───────────────────────────────────────────────────────────
        n_shown = len(bio_tree.get_terminals())
        self._fig.set_size_inches(10, max(n_shown * 0.22, 6))
        self._fig.clear()
        ax = self._fig.add_subplot(111)

        Phylo.draw(bio_tree, axes=ax, do_show=False)
        ax.set_xlabel("Branch length")
        ax.set_ylabel("")

        self._canvas.draw()
        self._placeholder.hide()
        self._canvas.show()
        if note_txt:
            self._note.setText(note_txt)
            self._note.show()
        else:
            self._note.hide()



# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 7 – Alzheimer Risk
# ═════════════════════════════════════════════════════════════════════════════

class _MriPreprocessWorker(QObject):
    """Runs MRI preprocessing off the main thread."""
    finished = pyqtSignal(object)   # emits np.ndarray
    errored  = pyqtSignal(str)

    def __init__(self, nii_path: str):
        super().__init__()
        self._path = nii_path

    def run(self):
        try:
            from src.services.mri_preprocessing import preprocess_mri
            arr = preprocess_mri(self._path)
            self.finished.emit(arr)
        except Exception as exc:
            self.errored.emit(str(exc))


class AlzheimerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # ── Page header ───────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Alzheimer Risk"))
        hdr.addStretch()
        hdr.addWidget(label_hint("Based on gut-brain axis biomarkers"))
        root.addLayout(hdr)

        # ── Input card: MRI upload + APOE genotype ────────────────────────────
        self._nii_path: str | None = None
        self._mri_thread: QThread | None = None

        input_card = card()
        inp_lay = input_card.layout()
        inp_lay.setSpacing(12)

        # MRI section
        inp_lay.addWidget(section_title("MRI Scan"))

        mri_row = QHBoxLayout()
        browse_btn = btn_outline("Browse .nii file")
        browse_btn.setFixedWidth(150)
        browse_btn.clicked.connect(self._browse_mri)
        mri_row.addWidget(browse_btn)
        self._mri_label = QLabel("No file selected")
        self._mri_label.setObjectName("label_hint")
        mri_row.addWidget(self._mri_label, 1)
        inp_lay.addLayout(mri_row)

        # APOE genotype section
        inp_lay.addWidget(section_title("APOE Genotype"))
        inp_lay.addWidget(label_hint(
            "Enter the number of copies of each allele (0–2). "
            "The three values must sum to exactly 2 (one from each parent)."
        ))

        apoe_row = QHBoxLayout()
        apoe_row.setSpacing(24)
        self._apoe_spins: dict[str, QSpinBox] = {}
        for allele in ("ε2", "ε3", "ε4"):
            col = QVBoxLayout(); col.setSpacing(4)
            col.addWidget(label_muted(f"{allele} alleles"))
            spin = QSpinBox()
            spin.setRange(0, 2)
            spin.setValue(0 if allele == "ε2" else (1 if allele == "ε3" else 1))
            spin.setFixedWidth(64)
            spin.valueChanged.connect(self._validate_apoe)
            self._apoe_spins[allele] = spin
            col.addWidget(spin)
            apoe_row.addLayout(col)
        apoe_row.addStretch()
        inp_lay.addLayout(apoe_row)

        self._apoe_status = QLabel("")
        self._apoe_status.setObjectName("label_hint")
        inp_lay.addWidget(self._apoe_status)
        self._validate_apoe()

        # Run button + status
        run_row = QHBoxLayout()
        self._run_btn = btn_primary("Run Assessment")
        self._run_btn.setStyleSheet(
            "QPushButton { background: #10B981; color: white; border: none; "
            "border-radius: 8px; padding: 9px 20px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: #059669; }"
            "QPushButton:pressed { background: #047857; }"
            "QPushButton:disabled { background: #9CA3AF; }"
        )
        self._run_btn.clicked.connect(self._run_assessment)
        run_row.addStretch()
        run_row.addWidget(self._run_btn)
        inp_lay.addLayout(run_row)

        self._assess_status = QLabel("")
        self._assess_status.setObjectName("label_hint")
        self._assess_status.setWordWrap(True)
        inp_lay.addWidget(self._assess_status)

        root.addWidget(input_card)

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
        self._state: AppState | None = None
        self._render(ALZHEIMER_RISK)

    # ── MRI browse ────────────────────────────────────────────────────────────
    def _browse_mri(self):
        import os
        path, _ = QFileDialog.getOpenFileName(
            self, "Select NIfTI file", "", "NIfTI Files (*.nii *.nii.gz)"
        )
        if path:
            self._nii_path = path
            self._mri_label.setText(os.path.basename(path))
            self._assess_status.setText("")

    # ── APOE validation ───────────────────────────────────────────────────────
    def _validate_apoe(self) -> bool:
        total = sum(s.value() for s in self._apoe_spins.values())
        if total == 2:
            self._apoe_status.setText("✓ Valid genotype")
            self._apoe_status.setStyleSheet("color: #10B981;")
            return True
        self._apoe_status.setText(f"Allele counts sum to {total} — must equal 2")
        self._apoe_status.setStyleSheet("color: #EF4444;")
        return False

    # ── Run assessment ────────────────────────────────────────────────────────
    def _run_assessment(self):
        if not self._validate_apoe():
            return

        self._run_btn.setEnabled(False)

        if self._nii_path:
            self._assess_status.setText("Preprocessing MRI scan…")
            self._mri_thread = QThread(self)
            self._mri_worker = _MriPreprocessWorker(self._nii_path)
            self._mri_worker.moveToThread(self._mri_thread)
            self._mri_thread.started.connect(self._mri_worker.run)
            self._mri_worker.finished.connect(self._on_preprocess_done)
            self._mri_worker.errored.connect(self._on_preprocess_error)
            self._mri_worker.finished.connect(self._mri_thread.quit)
            self._mri_worker.errored.connect(self._mri_thread.quit)
            self._mri_thread.start()
        else:
            self._assess_status.setText("Running assessment (no MRI)…")
            self._run_model(mri_array=None)

    def _on_preprocess_done(self, mri_array):
        print(f"[MRI] shape={mri_array.shape}  dtype={mri_array.dtype}")
        print(f"[MRI] min={mri_array.min():.3f}  max={mri_array.max():.3f}  mean={mri_array.mean():.3f}")
        self._assess_status.setText(
            f"MRI preprocessed — shape {mri_array.shape}. Computing risk…"
        )
        self._run_model(mri_array=mri_array)

    def _on_preprocess_error(self, msg: str):
        if "nibabel" in msg or "scipy" in msg:
            self._assess_status.setText(
                "MRI dependencies missing — run:  pip install nibabel scipy\n"
                "Running assessment without MRI…"
            )
        else:
            self._assess_status.setText(f"MRI error: {msg}  — running without MRI…")
        self._run_model(mri_array=None)

    # ── Model call ────────────────────────────────────────────────────────────
    def _run_model(self, mri_array=None):
        try:
            from src.services.ad_risk_model import (
                predict_from_project, predict_ad_risk,
                get_genus_abundances, get_last_run_genus_abundances,
            )

            apoe = {
                "e2": self._apoe_spins["ε2"].value(),
                "e3": self._apoe_spins["ε3"].value(),
                "e4": self._apoe_spins["ε4"].value(),
            }
            print(f"[APOE] user input: {apoe}")

            # Priority 1: project linked in state → query all runs for that project
            if self._state and self._state.db_project_id:
                genus_abundances = get_genus_abundances(self._state.db_project_id)
                print(f"[Genus] source=DB project  total genera={len(genus_abundances)}")
                print(f"[Genus] {genus_abundances}")
                result = predict_from_project(self._state.db_project_id, apoe, mri_array)

            # Priority 2: in-app analysis cache on state
            elif self._state and self._state.genus_abundances:
                genus_abundances = {}
                run_count = len(self._state.genus_abundances)
                for run_data in self._state.genus_abundances.values():
                    for item in run_data:
                        if isinstance(item, dict):
                            g, v = item["genus"], item["relative_abundance"]
                        else:
                            g, v = item[0], item[1]
                        genus_abundances[g] = genus_abundances.get(g, 0.0) + v / run_count
                print(f"[Genus] source=state cache  total genera={len(genus_abundances)}")
                print(f"[Genus] {genus_abundances}")
                result = predict_ad_risk(genus_abundances, apoe, mri_array)

            # Priority 3: most recent run with genus data in DB
            else:
                genus_abundances = get_last_run_genus_abundances()
                print(f"[Genus] source=last DB run  total genera={len(genus_abundances)}")
                print(f"[Genus] {genus_abundances}")
                result = predict_ad_risk(genus_abundances, apoe, mri_array)

            self._run_btn.setEnabled(True)
            source   = result.get("model_source", "heuristic")
            mri_note = "· MRI included" if mri_array is not None else "· no MRI"
            src_note = "trained model" if source == "trained" else "heuristic (place model files in data/models/)"
            self._assess_status.setText(
                f"Risk: {result['predicted_pct']:.0f}%  "
                f"Confidence: {result['confidence_pct']:.0f}%  "
                f"{mri_note}  ·  {src_note}"
            )
            self._render(result)

        except Exception as exc:
            self._run_btn.setEnabled(True)
            self._assess_status.setText(f"Model error: {exc}")

    def load(self, state: AppState):
        self._state = state
        d = state.risk_result if (state and state.risk_result) else ALZHEIMER_RISK
        self._render(d)

    # ── Render results ────────────────────────────────────────────────────────
    def _modality_bar(self, label: str, pct: float, color: str) -> QWidget:
        """Single modality row with label, gradient bar, and percentage."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(3)
        lay.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setObjectName("label_muted")
        hdr.addWidget(lbl)
        hdr.addStretch()
        pct_lbl = QLabel(f"{pct:.0f}%")
        pct_lbl.setObjectName("label_hint")
        hdr.addWidget(pct_lbl)
        lay.addLayout(hdr)

        stop = max(0.01, min(0.99, pct / 100))
        bar = QFrame()
        bar.setFixedHeight(10)
        bar.setStyleSheet(
            f"QFrame {{ border-radius: 5px; background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {color}, stop:{stop:.3f} {color}, "
            f"stop:{stop:.3f} #E5E7EB, stop:1 #E5E7EB); }}"
        )
        lay.addWidget(bar)
        return w

    def _render(self, d: dict):
        pct   = d.get("predicted_pct", 0)
        conf  = d.get("confidence_pct", 0)
        level = d.get("risk_level", "unknown").capitalize()

        self._pct_lbl.setText(f"{pct:.0f}%")
        self._lvl_lbl.setText(level)
        self._conf_lbl.setText(f"{conf:.0f}%")
        self._meter_widget.set_pct(pct)

        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(12)

        # ── Modality contributions ─────────────────────────────────────────────
        apoe_pct  = d.get("apoe_score",  0.5) * 100
        micro_pct = d.get("micro_score", 0.5) * 100
        mri_score = d.get("mri_score")
        mri_pct   = (mri_score * 100) if mri_score is not None else None

        mod_card = card()
        mod_lay  = mod_card.layout()
        mod_lay.addWidget(section_title("Modality Contributions"))
        mod_lay.addWidget(label_hint(
            "Individual risk contribution from each data source "
            "(higher = more AD-like signal in that modality)"
        ))
        mod_lay.addSpacing(4)
        mod_lay.addWidget(self._modality_bar("APOE Genotype (PRS)",       apoe_pct,  "#6366F1"))
        mod_lay.addWidget(self._modality_bar("Gut Microbiome Dysbiosis",  micro_pct, "#10B981"))
        if mri_pct is not None:
            mod_lay.addWidget(self._modality_bar("MRI Structural Score",  mri_pct,   "#F59E0B"))
        else:
            no_mri = label_hint("MRI: not provided — upload a .nii scan to include structural data")
            no_mri.setWordWrap(True)
            mod_lay.addWidget(no_mri)
        inner_lay.addWidget(mod_card)

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

            arrow     = {"low": "↓", "high": "↑", "normal": "✓"}.get(bm["status"], "")
            style_key = "ok" if bm["status"] == "normal" else bm["status"]
            vl = QLabel(f"{arrow} {bm['value']:.1f}{bm['unit']}")
            vl.setObjectName(f"bm_val_{style_key}")
            lay.addWidget(vl)

            rf = QLabel(f"Ref: {bm['normal']}  ·  {bm['role']}")
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


# ═════════════════════════════════════════════════════════════════════════════
#  PAGE 8 – Gut Microbiome Simulation
# ═════════════════════════════════════════════════════════════════════════════

class SimulationPage(QWidget):
    """
    COMETS-inspired gut microbiome simulation.
    Slider interventions drive a 30-day ODE-like model; results are shown as
    4 matplotlib plots and a QTableWidget of species changes.
    """

    _BUTYRATE = {"Faecalibacterium", "Roseburia", "Blautia", "Eubacterium",
                 "Butyrivibrio", "Anaerostipes", "Subdoligranulum"}
    _PROBIOTIC = {"Bifidobacterium", "Lactobacillus", "Lactococcus"}
    _INFLAM    = {"Fusobacterium", "Escherichia", "Klebsiella", "Enterococcus",
                  "Sutterella"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: AppState | None = None
        self._genus_data: list[dict] = []
        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        inner_w = QWidget()
        scroll.setWidget(inner_w)
        root = QVBoxLayout(inner_w)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.addWidget(page_title("Gut Microbiome Simulation"))
        hdr.addStretch()
        hdr.addWidget(label_hint("COMETS-inspired 30-day dynamic model"))
        root.addLayout(hdr)

        # ── Two-column row: left sliders | right (graphs + table) ─────────────
        row = QHBoxLayout()
        row.setSpacing(14)
        root.addLayout(row)

        # ── Left: slider panel ────────────────────────────────────────────────
        left = card()
        left.setFixedWidth(210)
        left_lay = left.layout()
        left_lay.setSpacing(6)
        left_lay.addWidget(section_title("Interventions"))

        self._sliders: dict[str, QSlider] = {}
        slider_cfg = [
            ("Antibiotic Level", "antibiotic",  0, "#EF4444"),
            ("Probiotic Level",  "probiotic",  30, "#10B981"),
            ("Dietary Fiber",    "fiber",       50, "#6366F1"),
            ("Processed Food",   "processed",   20, "#F59E0B"),
        ]
        for lbl_text, key, default, color in slider_cfg:
            self._sliders[key] = self._add_slider(left_lay, lbl_text, key, default, color)

        left_lay.addSpacing(4)
        run_btn = btn_primary("Run Simulation")
        run_btn.setStyleSheet(
            "QPushButton { background: #10B981; color: white; border: none; "
            "border-radius: 8px; padding: 9px 20px; font-size: 13px; font-weight: 700; }"
            "QPushButton:hover { background: #059669; }"
            "QPushButton:pressed { background: #047857; }"
        )
        run_btn.clicked.connect(self._run_sim)
        left_lay.addWidget(run_btn)

        row.addWidget(left, 0, Qt.AlignmentFlag.AlignTop)

        # ── Right: single card containing graphs grid + table ─────────────────
        right = card()
        right_lay = right.layout()
        right_lay.setSpacing(8)

        # 2 × 2 graphs grid
        graphs_lay = QGridLayout()
        graphs_lay.setSpacing(6)
        graphs_lay.setContentsMargins(0, 0, 0, 0)

        self._figs: list = []
        self._canvases: list = []
        for i in range(4):
            fig = Figure(figsize=(4, 1.5), tight_layout=True)
            canvas = FigureCanvasQTAgg(fig)
            canvas.setFixedHeight(140)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            graphs_lay.addWidget(canvas, i // 2, i % 2)
            self._figs.append(fig)
            self._canvases.append(canvas)

        right_lay.addLayout(graphs_lay)

        # Divider + table header
        right_lay.addWidget(section_title("Species Changes (Initial → Day 30)"))

        # Table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Genus", "Initial %", "Final %", "Δ Change"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setFixedHeight(175)
        right_lay.addWidget(self._table)

        row.addWidget(right, 1, Qt.AlignmentFlag.AlignTop)

        root.addStretch()
        self._draw_placeholders()

    def _add_slider(self, parent_lay, label_text: str, key: str, default: int, accent: str) -> QSlider:
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 6, 0, 2)
        lay.setSpacing(2)

        top = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setObjectName("label_muted")
        val_lbl = QLabel(f"{default}%")
        val_lbl.setFixedWidth(36)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_lbl.setStyleSheet(f"font-weight:600; color:{accent};")
        top.addWidget(lbl, 1)
        top.addWidget(val_lbl)
        lay.addLayout(top)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(default)
        slider.setStyleSheet(
            f"QSlider::handle:horizontal {{ background:{accent}; border-radius:6px; width:12px; height:12px; }}"
            f"QSlider::sub-page:horizontal {{ background:{accent}; border-radius:3px; }}"
        )
        slider.valueChanged.connect(lambda v, vl=val_lbl: vl.setText(f"{v}%"))
        lay.addWidget(slider)

        parent_lay.addWidget(container)
        return slider

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, state: AppState):
        self._state = state
        self._genus_data = []

        if not state:
            return

        from src.services.assessment_service import get_genus_data
        if state.lbs:
            for run_id in state.lbs.values():
                try:
                    data = get_genus_data(run_id)
                    if data:
                        self._genus_data = data
                        break
                except Exception:
                    pass

        if self._genus_data:
            self._run_sim()
        else:
            self._draw_placeholders()

    # ── Simulation ────────────────────────────────────────────────────────────

    def _run_sim(self):
        import numpy as np

        antibiotic = self._sliders["antibiotic"].value() / 100.0
        probiotic  = self._sliders["probiotic"].value()  / 100.0
        fiber      = self._sliders["fiber"].value()      / 100.0
        processed  = self._sliders["processed"].value()  / 100.0

        if not self._genus_data:
            self._draw_placeholders()
            return

        genera  = [d["genus"] for d in self._genus_data]
        init_ab = np.array([d["relative_abundance"] for d in self._genus_data], dtype=float)
        total   = init_ab.sum()
        if total > 0:
            init_ab /= total

        is_butyrate  = np.array([g in self._BUTYRATE for g in genera], dtype=float)
        is_probiotic = np.array([g in self._PROBIOTIC for g in genera], dtype=float)
        is_inflam    = np.array([g in self._INFLAM    for g in genera], dtype=float)

        T = 30
        history = np.zeros((T, len(genera)))
        history[0] = init_ab.copy()

        for t in range(1, T):
            prev = history[t - 1].copy()

            # Antibiotic: broad-spectrum kill, exponentially decaying with time
            antibiotic_kill = antibiotic * np.exp(-0.12 * t) * 0.9
            delta_ab = -antibiotic_kill * prev

            # Probiotic boosts probiotic genera
            delta_ab += probiotic * 0.018 * is_probiotic

            # Fiber feeds butyrate producers
            delta_ab += fiber * 0.014 * is_butyrate

            # Processed food feeds inflammatory genera, starves butyrate producers
            delta_ab += processed * 0.012 * is_inflam
            delta_ab -= processed * 0.010 * is_butyrate

            new_ab = np.clip(prev + delta_ab, 1e-7, None)
            new_ab /= new_ab.sum()
            history[t] = new_ab

        # ── Derived metrics ────────────────────────────────────────────────────
        def _shannon(ab):
            p = ab[ab > 0]
            return float(-np.sum(p * np.log2(p)))

        times         = np.arange(T)
        diversity     = np.array([_shannon(history[t]) for t in range(T)])
        butyrate_lvl  = np.array([(history[t] * is_butyrate).sum() for t in range(T)])
        inflam_lvl    = np.array([(history[t] * is_inflam).sum()   for t in range(T)])
        max_sh        = np.log2(len(genera)) if len(genera) > 1 else 1.0
        ad_risk       = 100.0 * (
            0.35 * np.clip(inflam_lvl    / max(inflam_lvl.max(),   1e-9), 0, 1) +
            0.30 * np.clip(1 - diversity / max_sh,                        0, 1) +
            0.35 * np.clip(1 - butyrate_lvl / max(butyrate_lvl.max(), 1e-9), 0, 1)
        )

        # ── Plot 1: Top genera over time ───────────────────────────────────────
        top_n   = min(6, len(genera))
        top_idx = np.argsort(init_ab)[::-1][:top_n]
        COLORS  = ['#6366F1', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4']

        self._figs[0].clear()
        ax0 = self._figs[0].add_subplot(111)
        for k, i in enumerate(top_idx):
            ax0.plot(times, history[:, i] * 100, label=genera[i],
                     color=COLORS[k % len(COLORS)], linewidth=1.4)
        ax0.set_title("Genus Abundance Over Time", fontsize=8, fontweight='bold')
        ax0.set_xlabel("Day", fontsize=7); ax0.set_ylabel("Rel. Abundance (%)", fontsize=7)
        ax0.tick_params(labelsize=7)
        ax0.legend(fontsize=6, loc='upper right', framealpha=0.7)
        ax0.set_facecolor('#F8FAFC')
        self._canvases[0].draw()

        # ── Plot 2: Alpha diversity ────────────────────────────────────────────
        self._figs[1].clear()
        ax1 = self._figs[1].add_subplot(111)
        ax1.plot(times, diversity, color='#10B981', linewidth=1.6)
        ax1.fill_between(times, diversity, alpha=0.15, color='#10B981')
        ax1.set_title("Alpha Diversity (Shannon)", fontsize=8, fontweight='bold')
        ax1.set_xlabel("Day", fontsize=7); ax1.set_ylabel("Shannon Index", fontsize=7)
        ax1.tick_params(labelsize=7)
        ax1.set_facecolor('#F8FAFC')
        self._canvases[1].draw()

        # ── Plot 3: Metabolite proxies ─────────────────────────────────────────
        self._figs[2].clear()
        ax2 = self._figs[2].add_subplot(111)
        ax2.plot(times, butyrate_lvl * 100, label="Butyrate / SCFA",
                 color='#10B981', linewidth=1.6)
        ax2.plot(times, inflam_lvl * 100, label="LPS / Inflammatory",
                 color='#EF4444', linewidth=1.6, linestyle='--')
        ax2.set_title("Metabolite Proxies", fontsize=8, fontweight='bold')
        ax2.set_xlabel("Day", fontsize=7); ax2.set_ylabel("Relative Level (%)", fontsize=7)
        ax2.tick_params(labelsize=7)
        ax2.legend(fontsize=6, framealpha=0.7)
        ax2.set_facecolor('#F8FAFC')
        self._canvases[2].draw()

        # ── Plot 4: AD risk score over time ───────────────────────────────────
        self._figs[3].clear()
        ax3 = self._figs[3].add_subplot(111)
        ax3.plot(times, ad_risk, color='#EF4444', linewidth=1.6)
        ax3.fill_between(times, ad_risk, alpha=0.10, color='#EF4444')
        ax3.axhline(33, color='#F59E0B', linestyle=':', linewidth=1.0, label='Moderate (33)')
        ax3.axhline(66, color='#EF4444', linestyle=':', linewidth=1.0, label='High (66)')
        ax3.set_ylim(0, 100)
        ax3.set_title("Predicted AD Risk Score", fontsize=8, fontweight='bold')
        ax3.set_xlabel("Day", fontsize=7); ax3.set_ylabel("Risk Score", fontsize=7)
        ax3.tick_params(labelsize=7)
        ax3.legend(fontsize=6, framealpha=0.7)
        ax3.set_facecolor('#F8FAFC')
        self._canvases[3].draw()

        # ── Table: species changes ─────────────────────────────────────────────
        final_ab = history[-1]
        rows = sorted(
            [(genera[i], init_ab[i] * 100, final_ab[i] * 100,
              (final_ab[i] - init_ab[i]) * 100)
             for i in range(len(genera))],
            key=lambda x: abs(x[3]), reverse=True,
        )
        self._table.setRowCount(len(rows))
        for r, (genus, ini, fin, delta) in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(genus))
            self._table.setItem(r, 1, QTableWidgetItem(f"{ini:.3f}"))
            self._table.setItem(r, 2, QTableWidgetItem(f"{fin:.3f}"))
            delta_item = QTableWidgetItem(f"{'+' if delta >= 0 else ''}{delta:.3f}")
            delta_item.setForeground(QColor("#10B981" if delta >= 0 else "#EF4444"))
            self._table.setItem(r, 3, delta_item)

    # ── Placeholder ───────────────────────────────────────────────────────────

    def _draw_placeholders(self):
        titles = [
            "Genus Abundance Over Time",
            "Alpha Diversity (Shannon)",
            "Metabolite Proxies",
            "Predicted AD Risk Score",
        ]
        for i, (fig, canvas) in enumerate(zip(self._figs, self._canvases)):
            fig.clear()
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Load a project to run simulation",
                    ha='center', va='center', transform=ax.transAxes,
                    color='#94A3B8', fontsize=10)
            ax.set_title(titles[i], fontsize=10, fontweight='bold')
            ax.set_facecolor('#F8FAFC')
            canvas.draw()