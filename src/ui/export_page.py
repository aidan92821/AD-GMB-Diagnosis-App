"""
Axis – Export page.

Layout:
  ┌─────────────────────────────────────────────────────┐
  │  Scrollable content area                            │
  │    • Page header                                    │
  │    • Section checkboxes (2-column grid)             │
  │    • Output file path + Browse button               │
  ├─────────────────────────────────────────────────────┤
  │  STICKY BOTTOM ACTION BAR  (never scrolls away)     │
  │    [  ⬇  Export PDF  ]   ████░░░  67%   Saving…   │
  └─────────────────────────────────────────────────────┘

The sticky bottom bar means the Export button is ALWAYS visible
regardless of scroll position.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QCheckBox,
    QFileDialog, QProgressBar,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QPushButton,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject

from models.app_state import AppState
from resources.styles import (
    BG_PAGE, BG_CARD, BORDER,
    TEXT_H, TEXT_M, TEXT_HINT,
    ACCENT, SUCCESS_FG, DANGER_FG,
)

_CARD  = f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:10px;"
_BAR   = f"background:{BG_CARD}; border-top:2px solid {BORDER};"


# ── Background PDF worker ─────────────────────────────────────────────────────

class _PdfWorker(QObject):
    """
    Runs pdf_exporter.build_report() off the main thread.
    Signals:
        progress(int)  – 0..100
        finished(str)  – absolute path of saved file
        errored(str)   – human-readable error message
    """
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    errored  = pyqtSignal(str)

    def __init__(self, output_path: str, sections: list[str], state) -> None:
        super().__init__()
        self._path     = output_path
        self._sections = sections
        self._state    = state

    def run(self) -> None:
        try:
            self.progress.emit(5)
            from services.pdf_exporter import build_report
            self.progress.emit(25)
            result = build_report(self._path, sections=self._sections, state=self._state)
            self.progress.emit(100)
            self.finished.emit(str(result))
        except Exception as exc:          # noqa: BLE001
            self.errored.emit(str(exc))


# ── Section checkbox widget ───────────────────────────────────────────────────
 
class _SectionCheck(QWidget):
    """Single checkbox row:  ☑  Title  /  subtitle."""
 
    def __init__(self, key: str, title: str, desc: str) -> None:
        super().__init__()
        self.key = key
 
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(10)
 
        self._cb = QCheckBox()
        self._cb.setChecked(True)
        self._cb.setStyleSheet(f"""
            QCheckBox::indicator {{
                width:17px; height:17px;
                border:1.5px solid {BORDER};
                border-radius:4px; background:white;
            }}
            QCheckBox::indicator:checked {{
                background:{TEXT_H}; border-color:{TEXT_H};
            }}
            QCheckBox::indicator:hover {{ border-color:{ACCENT}; }}
        """)
        lay.addWidget(self._cb, 0, Qt.AlignmentFlag.AlignTop)
 
        col = QVBoxLayout(); col.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet(f"font-size:13px;font-weight:600;color:{TEXT_H};")
        d = QLabel(desc)
        d.setStyleSheet(f"font-size:11px;color:{TEXT_HINT};")
        col.addWidget(t); col.addWidget(d)
        lay.addLayout(col, 1)
 
    @property
    def is_checked(self) -> bool:
        return self._cb.isChecked()
 
    def set_checked(self, v: bool) -> None:
        self._cb.setChecked(v)


# ── Export page ───────────────────────────────────────────────────────────────

class ExportPage(QWidget):

    _SECTIONS = [
        ("cover",      "Cover page",           "Project title, metadata summary"),
        ("overview",   "Project overview",     "Stat cards: runs, ASVs, genera, library"),
        ("taxonomy",   "Taxonomy",             "Bar charts, pie charts, stacked bars per run"),
        ("diversity",  "Diversity",            "Alpha boxplots · beta heatmap · PCoA scatter"),
        ("asv",        "ASV feature table",    "Full ASV counts and relative abundance"),
        ("phylogeny",  "Phylogenetic tree",    "IQ-TREE rendered tree with tip/node stats"),
        ("alzheimer",  "Alzheimer risk",       "Biomarker grid and gut-brain axis risk score"),
        ("simulation", "Gut simulation",       "30-day ODE model: abundance, diversity, AD risk"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _PdfWorker | None = None
        self._checks: list[_SectionCheck] = []
        self._saved_path: str = ""
        self._state: AppState | None = None
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scrollable top area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea{{background:{BG_PAGE};border:none;}}")

        body = QWidget()
        body.setStyleSheet(f"background:{BG_PAGE};")
        blay = QVBoxLayout(body)
        blay.setContentsMargins(28, 24, 28, 20)
        blay.setSpacing(16)

        # Header
        title = QLabel("Export Report")
        title.setStyleSheet(f"font-size:20px;font-weight:700;color:{TEXT_H};")
        blay.addWidget(title)

        self._sub_lbl = QLabel("Generate a complete PDF report for the current project. "
                               "Deselect any sections you don't need.")
        self._sub_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._sub_lbl.setWordWrap(True)
        self._sub_lbl.setStyleSheet(f"font-size:13px;color:{TEXT_M};")
        blay.addWidget(self._sub_lbl)

        # Section selector card
        blay.addWidget(self._build_sections_card())

        # Output file card
        blay.addWidget(self._build_output_card())

        blay.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── Sticky bottom action bar ──
        root.addWidget(self._build_action_bar())

    # ── Cards ─────────────────────────────────────────────────────────────────

    def _build_sections_card(self) -> QFrame:
        card = QFrame(); card.setStyleSheet(_CARD)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        # Header row
        hdr = QHBoxLayout()
        t = QLabel("Include in report")
        t.setStyleSheet(f"font-size:14px;font-weight:700;color:{TEXT_H};")
        hdr.addWidget(t)
        hdr.addStretch()

        for label, state in [("Select all", True), ("Deselect all", False)]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"QPushButton{{background:transparent;border:1px solid {BORDER};"
                f"border-radius:5px;padding:4px 10px;font-size:11px;color:{TEXT_M};}}"
                f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
            )
            btn.clicked.connect(lambda _, s=state: self._toggle_all(s))
            hdr.addWidget(btn)
        lay.addLayout(hdr)

        # Divider
        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background:{BORDER};max-height:1px;")
        lay.addWidget(div)

        # 2-column grid
        grid = QGridLayout(); grid.setSpacing(4)
        for i, (key, title, desc) in enumerate(self._SECTIONS):
            chk = _SectionCheck(key, title, desc)
            self._checks.append(chk)
            grid.addWidget(chk, i // 2, i % 2)
        if len(self._SECTIONS) % 2:
            grid.addWidget(QWidget(), len(self._SECTIONS) // 2, 1)
        lay.addLayout(grid)
        return card

    def _build_output_card(self) -> QFrame:
        card = QFrame(); card.setStyleSheet(_CARD)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        t = QLabel("Output file")
        t.setStyleSheet(f"font-size:14px;font-weight:700;color:{TEXT_H};")
        lay.addWidget(t)

        s = QLabel("Choose where to save the PDF on your computer.")
        s.setStyleSheet(f"font-size:12px;color:{TEXT_M};")
        lay.addWidget(s)

        row = QHBoxLayout(); row.setSpacing(8)

        self._path_input = QLineEdit(
            str(Path.home() / "Desktop" / "gutseq_report.pdf")
        )
        self._path_input.setStyleSheet(
            f"background:white;border:1.5px solid {BORDER};"
            "border-radius:6px;padding:8px 10px;font-size:13px;"
            f"color:{TEXT_H};"
        )
        row.addWidget(self._path_input, 1)

        browse = QPushButton("Browse…")
        browse.setStyleSheet(
            f"QPushButton{{background:white;border:1.5px solid {BORDER};"
            "border-radius:6px;padding:8px 16px;font-size:12px;"
            f"color:{TEXT_M};}}"
            f"QPushButton:hover{{border-color:{ACCENT};color:{ACCENT};}}"
        )
        browse.clicked.connect(self._browse_output)
        row.addWidget(browse)

        lay.addLayout(row)

        hint = QLabel(
            "The file will be saved to this exact path.  "
            "After export a link appears to open the folder directly."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size:11px;color:{TEXT_HINT};")
        lay.addWidget(hint)
        return card

    def _build_action_bar(self) -> QFrame:
        """
        Fixed-height bar pinned to the bottom of the page.
        Contains the Export button, progress bar, and status text.
        This is ALWAYS visible — it does not scroll.
        """
        bar = QFrame()
        bar.setStyleSheet(_BAR)
        bar.setFixedHeight(70)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(28, 12, 28, 12)
        lay.setSpacing(16)

        # ── Export button ──
        self._export_btn = QPushButton("  ⬇   Export PDF")
        self._export_btn.setFixedHeight(46)
        self._export_btn.setMinimumWidth(160)
        self._export_btn.setStyleSheet(
            f"QPushButton{{"
            f"  background:{TEXT_H};color:white;"
            "  border:none;border-radius:8px;"
            "  font-size:14px;font-weight:700;"
            "  padding:0 24px;"
            "}}"
            "QPushButton:hover{"
            "  background:#1F2937;"
            "}"
            "QPushButton:pressed{"
            "  background:#374151;"
            "}"
            "QPushButton:disabled{"
            "  background:#9CA3AF;"
            "}"
        )
        self._export_btn.clicked.connect(self._on_export)
        lay.addWidget(self._export_btn)

        # ── Progress + status column ──
        prog_col = QVBoxLayout()
        prog_col.setSpacing(4)

        self._status_lbl = QLabel("Ready to export")
        self._status_lbl.setStyleSheet(f"font-size:12px;color:{TEXT_M};")
        prog_col.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar{{background:{BG_PAGE};border:1px solid {BORDER};"
            "border-radius:3px;}}"
            f"QProgressBar::chunk{{background:{ACCENT};border-radius:3px;}}"
        )
        prog_col.addWidget(self._progress)
        lay.addLayout(prog_col, 1)

        # ── "Open folder" button — hidden until export succeeds ──
        self._open_btn = QPushButton("Open folder")
        self._open_btn.setFixedHeight(36)
        self._open_btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:1.5px solid {ACCENT};"
            f"border-radius:6px;font-size:12px;color:{ACCENT};padding:0 14px;}}"
            f"QPushButton:hover{{background:{ACCENT};color:white;}}"
        )
        self._open_btn.clicked.connect(self._open_file_location)
        self._open_btn.hide()
        lay.addWidget(self._open_btn)

        return bar

    # ── State ─────────────────────────────────────────────────────────────────

    def load(self, state: "AppState") -> None:
        self._state = state
        if state and state.has_project:
            self._sub_lbl.setText(
                f"Generate a complete PDF report for  "
                f"<b>{state.bioproject_id}</b>"
                f"{'  ·  ' + state.title if state.title else ''}.  "
                "Deselect any sections you don't need."
            )

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _toggle_all(self, state: bool) -> None:
        for c in self._checks:
            c.set_checked(state)

    def _browse_output(self) -> None:
        current = self._path_input.text().strip() or str(Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF Report", current,
            "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self._path_input.setText(path)

    def _on_export(self) -> None:
        """Validate then start the background PDF generation worker."""
        output = self._path_input.text().strip()
        if not output:
            self._set_status("⚠  Please specify a file path.", ok=False)
            return

        selected = [c.key for c in self._checks if c.is_checked]
        if not selected:
            self._set_status("⚠  Select at least one section.", ok=False)
            return

        # Ensure the destination directory exists
        try:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._set_status(f"⚠  Cannot create directory: {e}", ok=False)
            return

        # Lock UI while generating
        self._export_btn.setEnabled(False)
        self._export_btn.setText("  Generating…")
        self._open_btn.hide()
        self._progress.setValue(0)
        self._set_status("Building report…", ok=None)

        # Background thread
        self._thread = QThread(self)
        self._worker = _PdfWorker(output, selected, self._state)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.errored.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.errored.connect(self._thread.quit)

        self._thread.start()

    def _on_progress(self, pct: int) -> None:
        self._progress.setValue(pct)
        self._set_status(f"Generating report… {pct}%", ok=None)

    def _on_done(self, path: str) -> None:
        self._saved_path = path
        self._export_btn.setEnabled(True)
        self._export_btn.setText("  ⬇   Export PDF")
        self._progress.setValue(100)
        self._set_status(f"✓  Saved to {path}", ok=True)
        self._open_btn.show()

    def _on_error(self, message: str) -> None:
        self._export_btn.setEnabled(True)
        self._export_btn.setText("  ⬇   Export PDF")
        self._progress.setValue(0)
        self._set_status(f"✗  Export failed: {message}", ok=False)

    def _set_status(self, msg: str, ok: bool | None) -> None:
        color = {True: SUCCESS_FG, False: DANGER_FG}.get(ok, TEXT_M)
        self._status_lbl.setStyleSheet(f"font-size:12px;color:{color};")
        self._status_lbl.setText(msg)

    def _open_file_location(self) -> None:
        """Open the containing folder in the OS file manager."""
        if not self._saved_path:
            return
        folder = str(Path(self._saved_path).parent)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", self._saved_path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])