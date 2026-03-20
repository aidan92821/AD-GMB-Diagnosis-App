"""
GutSeq – MainWindow.

Shell layout:
  ┌─────────────────────────────────────────────────────────┐
  │  Dark sidebar  │  Top bar (project title + badges)      │
  │                ├─────────────────────────────────────────│
  │   nav items    │  QStackedWidget (one page per nav item) │
  │                │  wrapped in a QScrollArea               │
  └─────────────────────────────────────────────────────────┘

Clicking a sidebar item switches the stacked page — nothing else changes.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QScrollArea, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal

from resources.styles import (
    APP_QSS,
    SB_BG, SB_SECTION, WHITE, BG_PAGE, BG_CARD, BORDER,
    TEXT_H, TEXT_M,
)
from models.example_data import PROJECT
from ui.pages import (
    OverviewPage, UploadRunsPage, DiversityPage,
    TaxonomyPage, AsvTablePage, PhylogenyPage, AlzheimerPage,
)
from ui.export_page import ExportPage


# ── Background fetch worker ───────────────────────────────────────────────────

class _FetchWorker(QObject):
    """
    Calls the data service on a background thread so the UI never freezes
    while waiting for an NCBI response.

    Signals
    -------
    finished(dict)  — project data dict on success
    errored(str)    — human-readable error message on failure
    """
    finished = pyqtSignal(object)   # emits the project dict
    errored  = pyqtSignal(str)

    def __init__(self, bioproject: str, run_filter: str, max_runs: int) -> None:
        super().__init__()
        self._bioproject  = bioproject
        self._run_filter  = run_filter or None
        self._max_runs    = max_runs

    def run(self) -> None:
        try:
            from services.ncbi_service import NcbiService, NcbiFetchError

            service = NcbiService()   # reads ENTREZ_EMAIL from ncbi_service.py
            project = service.fetch_project(
                self._bioproject,
                max_runs   = self._max_runs,
                run_filter = self._run_filter,
            )
            self.finished.emit(project.to_dict())

        except Exception as exc:          # noqa: BLE001
            self.errored.emit(str(exc))


# ── Sidebar nav definition ────────────────────────────────────────────────────

NAV = [
    # (section_label, [(display_name, icon)])
    ("ANALYSIS", [
        ("Overview",       "⊞"),
        ("Upload Runs",    "↑"),
        ("Diversity",      "≋"),
        ("Taxonomy",       "⊙"),
        ("ASV Table",      "⋮"),
        ("Phylogeny",      "∿"),
    ]),
    ("INSIGHTS", [
        ("Alzheimer Risk", "♥"),
    ]),
    ("EXPORT", [
        ("Export PDF",     "⬇"),
    ]),
]


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GutSeq — Microbiome Analytics")
        self.resize(1280, 880)
        self.setMinimumSize(900, 600)

        # Apply the stylesheet globally — every widget in the app inherits it
        self.setStyleSheet(APP_QSS)

        self._nav_buttons: list[QPushButton] = []   # flat list in nav order
        self._active_idx  = 0

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root_widget = QWidget()
        root_widget.setStyleSheet(f"background: {BG_PAGE};")
        self.setCentralWidget(root_widget)

        root_row = QHBoxLayout(root_widget)
        root_row.setContentsMargins(0, 0, 0, 0)
        root_row.setSpacing(0)

        # ── Sidebar ──
        sidebar = self._build_sidebar()
        root_row.addWidget(sidebar)

        # ── Right column: top bar + stacked pages ──
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        right.addWidget(self._build_topbar())
        right.addWidget(self._build_content_area(), 1)

        root_row.addLayout(right, 1)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QFrame:
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(180)

        lay = QVBoxLayout(sb)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Logo block
        logo_block = QWidget()
        logo_block.setStyleSheet(f"background: {SB_BG};")
        lb = QVBoxLayout(logo_block)
        lb.setContentsMargins(20, 20, 20, 14)
        lb.setSpacing(2)
        logo = QLabel("GutSeq")
        logo.setObjectName("sb_logo")
        sub  = QLabel("microbiome analytics")
        sub.setObjectName("sb_sub")
        lb.addWidget(logo)
        lb.addWidget(sub)
        lay.addWidget(logo_block)

        # Thin separator
        sep = QFrame()
        sep.setStyleSheet(f"background: #2D3748; max-height: 1px;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        # Nav sections
        nav_widget = QWidget()
        nav_widget.setStyleSheet(f"background: {SB_BG};")
        nav_lay = QVBoxLayout(nav_widget)
        nav_lay.setContentsMargins(0, 8, 0, 0)
        nav_lay.setSpacing(0)

        for section_name, items in NAV:
            sec_lbl = QLabel(section_name)
            sec_lbl.setObjectName("sb_section")
            nav_lay.addWidget(sec_lbl)

            for display, icon in items:
                btn = QPushButton(f"  {icon}   {display}")
                btn.setObjectName("nav_btn")
                btn.setProperty("active", len(self._nav_buttons) == 0)
                idx = len(self._nav_buttons)
                btn.clicked.connect(lambda _, i=idx: self._switch_page(i))
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setFixedHeight(38)
                nav_lay.addWidget(btn)
                self._nav_buttons.append(btn)

        nav_lay.addStretch()
        lay.addWidget(nav_widget, 1)

        # Footer
        footer = QLabel("QIIME2 pipeline · v2024.5")
        footer.setObjectName("sb_footer")
        footer.setStyleSheet(f"background: {SB_BG}; color: {SB_SECTION}; font-size: 10px; padding: 10px 20px;")
        lay.addWidget(footer)

        return sb

    # ── Top bar ───────────────────────────────────────────────────────────────

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(52)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 0, 24, 0)
        lay.setSpacing(10)

        # Title — updated dynamically after a successful fetch
        self._topbar_title = QLabel("AD-GMB Diagnosis ")
        self._topbar_title.setObjectName("topbar_title")
        lay.addWidget(self._topbar_title)
        lay.addStretch()

        # Badges — hidden until a project is fetched
        self._runs_badge = QLabel("")
        self._runs_badge.setObjectName("badge_green")
        self._runs_badge.hide()
        lay.addWidget(self._runs_badge)

        self._warn_badge = QLabel("")
        self._warn_badge.setObjectName("badge_yellow")
        self._warn_badge.hide()
        lay.addWidget(self._warn_badge)

        return bar

    # ── Content area (stacked pages) ─────────────────────────────────────────

    def _build_content_area(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("content_scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Host widget so the scroll area has a background
        host = QWidget()
        host.setObjectName("content_host")
        host.setStyleSheet(f"background: {BG_PAGE};")
        host_lay = QVBoxLayout(host)
        host_lay.setContentsMargins(0, 0, 0, 0)

        # Stacked widget — one page per nav button
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {BG_PAGE};")

        self._overview_page = OverviewPage()
        self._pages = [
            self._overview_page,
            UploadRunsPage(),
            DiversityPage(),
            TaxonomyPage(),
            AsvTablePage(),
            PhylogenyPage(),
            AlzheimerPage(),
            ExportPage(),
        ]
        for page in self._pages:
            self._stack.addWidget(page)

        # ── Wire the fetch signal ──────────────────────────────────────────
        # OverviewPage emits fetch_requested → MainWindow handles the work
        self._overview_page.fetch_requested.connect(self._on_fetch_requested)

        host_lay.addWidget(self._stack)
        scroll.setWidget(host)
        return scroll

    # ── Fetch orchestration ───────────────────────────────────────────────────

    def _on_fetch_requested(
        self, bioproject: str, run_accession: str, max_runs: int
    ) -> None:
        """
        Spawn a background worker for the NCBI fetch.
        The worker emits finished/errored back to the main thread.
        """
        self._fetch_thread = QThread(self)
        self._fetch_worker = _FetchWorker(bioproject, run_accession, max_runs)
        self._fetch_worker.moveToThread(self._fetch_thread)

        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_fetch_complete)
        self._fetch_worker.errored.connect(self._on_fetch_error)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_worker.errored.connect(self._fetch_thread.quit)

        self._fetch_thread.start()

    def _on_fetch_complete(self, project: dict) -> None:
        """Called on the main thread when the worker succeeds."""
        # 1. Hand results back to the Overview page
        self._overview_page.load_project(project)

        # 2. Update the top bar to reflect the loaded project
        self._topbar_title.setText(
            f"{project['bioproject_id']}  —  {project['title']}"
        )
        n_runs = len(project["runs"])
        n_errs = len(project.get("qiime_errors", {}))
        self._runs_badge.setText(f"{n_runs} run{'s' if n_runs != 1 else ''} loaded")
        self._runs_badge.setObjectName("badge_green")
        self._runs_badge.style().unpolish(self._runs_badge)
        self._runs_badge.style().polish(self._runs_badge)
        self._runs_badge.show()

        if n_errs:
            self._warn_badge.setText(
                f"{n_errs} warning{'s' if n_errs > 1 else ''}"
            )
            self._warn_badge.show()
        else:
            self._warn_badge.hide()

    def _on_fetch_error(self, message: str) -> None:
        """Called on the main thread when the worker fails."""
        self._overview_page.show_fetch_error(message)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _switch_page(self, idx: int) -> None:
        """Deactivate old button, activate new, switch stack page."""
        if idx == self._active_idx:
            return

        # Deactivate previous
        old = self._nav_buttons[self._active_idx]
        old.setProperty("active", False)
        old.style().unpolish(old)
        old.style().polish(old)

        # Activate new
        self._active_idx = idx
        new = self._nav_buttons[idx]
        new.setProperty("active", True)
        new.style().unpolish(new)
        new.style().polish(new)

        self._stack.setCurrentIndex(idx)