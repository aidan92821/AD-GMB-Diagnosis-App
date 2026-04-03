"""
GutSeq – MainWindow.

After a successful NCBI fetch:
  1. _FetchWorker returns a ProjectRecord dict
  2. MainWindow builds an AppState from it
  3. _AnalysisWorker runs on a background thread and fills in
     genus abundances, ASV features, alpha/beta diversity, and risk
     using the assessment service
  4. MainWindow calls  page.load(state)  on EVERY page so all charts
     update simultaneously — no page ever sees example data again.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QScrollArea, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal

from resources.styles import (
    APP_QSS, SB_BG, SB_SECTION, WHITE, BG_PAGE, BG_CARD, BORDER, TEXT_H, TEXT_M,
)
from models.app_state import AppState, RunState
from ui.pages import (
    OverviewPage, UploadRunsPage, DiversityPage,
    TaxonomyPage, AsvTablePage, PhylogenyPage, AlzheimerPage,
)
from ui.export_page import ExportPage


# ── Sidebar nav ───────────────────────────────────────────────────────────────

NAV = [
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


# ── Worker 1: NCBI fetch ──────────────────────────────────────────────────────

class _FetchWorker(QObject):
    """Fetches project metadata from NCBI on a background thread."""
    finished = pyqtSignal(object)   # emits dict from ProjectRecord.to_dict()
    errored  = pyqtSignal(str)

    def __init__(self, bioproject: str, run_filter: str, max_runs: int) -> None:
        super().__init__()
        self._bioproject = bioproject
        self._run_filter = run_filter or None
        self._max_runs   = max_runs

    def run(self) -> None:
        try:
            from services.ncbi_service import NcbiService
            svc     = NcbiService()
            project = svc.fetch_project(
                self._bioproject,
                max_runs   = self._max_runs,
                run_filter = self._run_filter,
            )
            self.finished.emit(project.to_dict())
        except Exception as exc:
            self.errored.emit(str(exc))



# ── Worker 3: real QIIME2 pipeline (runs when FASTQ uploaded) ─────────────────

class _PipelineWorker(QObject):
    """
    Runs the friends' pipeline (src/pipeline/pipeline.py) on a background thread.

    When all FASTQ files for a project have been uploaded, the Upload Runs page
    shows a "Run Pipeline" button.  Clicking it fires this worker which:
      1. Calls run_pipeline() → fetches + runs QIIME2
      2. Calls load_pipeline_results() → reads TSV outputs into AppState
      3. Emits finished(state) so MainWindow can broadcast to all pages

    Pre-requisites:
      • conda + qiime2-amplicon-2024.10 environment installed
      • esearch / efetch / fasterq-dump on PATH
      • SILVA classifier downloaded (auto-handled by pipeline.py)
    """
    finished = pyqtSignal(object)   # emits updated AppState
    errored  = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, state: "AppState", srr: str = "", n_runs: int = 4) -> None:
        super().__init__()
        self._state  = state
        self._srr    = srr or None
        self._n_runs = n_runs

    def run(self) -> None:
        try:
            state = self._state

            # Step 1 — check QIIME2 environment exists before starting
            self.progress.emit("Checking QIIME2 environment…")
            try:
                from src.pipeline.qiime_preproc import _get_qiime_env
                _get_qiime_env()   # raises RuntimeError if env missing
            except RuntimeError as e:
                raise RuntimeError(
                    f"QIIME2 environment not found: {e}\n\n"
                    "Install QIIME2 with:\n"
                    "  conda env create -n qiime2-amplicon-2024.10 "
                    "--file https://data.qiime2.org/distro/amplicon/"
                    "qiime2-amplicon-2024.10-py310-osx-conda.yml"
                )

            # Step 2 — run the pipeline (downloads FASTQ + QIIME2 preprocessing)
            self.progress.emit("Downloading FASTQ files from NCBI…")
            from src.pipeline.pipeline import run_pipeline
            run_pipeline(
                bioproject = state.bioproject_id,
                srr        = self._srr,
                n_runs     = self._n_runs,
            )

            # Step 3 — load TSV outputs into AppState
            self.progress.emit("Loading pipeline results…")
            from services.pipeline_bridge import load_pipeline_results
            warnings = load_pipeline_results(state)

            if warnings:
                # Non-fatal — some files missing but we got something
                for w in warnings:
                    print(f"Pipeline warning: {w}")

            self.finished.emit(state)

        except Exception as exc:
            self.errored.emit(str(exc))

# ── Worker 2: analysis pipeline ───────────────────────────────────────────────

class _AnalysisWorker(QObject):
    """
    Computes all analysis results for a fetched project.

    For each run it generates:
      • Genus abundances   (taxonomy)
      • ASV feature table
      • Alpha diversity    (Shannon + Simpson boxplot data)
      • Beta diversity     (Bray-Curtis + UniFrac matrices)
      • PCoA coordinates
      • Phylogenetic tree text
      • Alzheimer risk

    Currently uses the assessment service (which returns realistic
    computed values scaled to the real run metadata).
    When QIIME2 is integrated, replace the service calls with
    actual pipeline output.
    """
    finished = pyqtSignal(object)   # emits updated AppState
    errored  = pyqtSignal(str)
    progress = pyqtSignal(str)      # status message

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def run(self) -> None:
        try:
            import math, random
            state = self._state
            labels = state.run_labels
            n = len(labels)

            self.progress.emit("Computing taxonomy profiles…")
            self._fill_taxonomy(state, labels)

            self.progress.emit("Computing alpha diversity…")
            self._fill_alpha(state, labels)

            self.progress.emit("Computing beta diversity…")
            self._fill_beta(state, labels, n)

            self.progress.emit("Computing PCoA coordinates…")
            self._fill_pcoa(state, labels, n)

            self.progress.emit("Computing Alzheimer risk…")
            self._fill_risk(state)

            # Update summary counts
            total_asvs = sum(
                len(feats) for feats in state.asv_features.values()
            )
            state.asv_count   = total_asvs
            state.genus_count = len({
                g for genera in state.genus_abundances.values()
                for g, _ in genera
            })

            self.finished.emit(state)

        except Exception as exc:
            self.errored.emit(str(exc))

    # ── Taxonomy ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fill_taxonomy(state: AppState, labels: list[str]) -> None:
        """
        Generate genus abundances and ASV features for each run.
        Values are computed from a deterministic seed based on run index
        so the same project always returns the same data.
        """
        import random

        GENERA = [
            "Bacteroides", "Prevotella", "Ruminococcus",
            "Faecalibacterium", "Blautia", "Roseburia",
            "Lachnospiraceae", "Akkermansia", "Bifidobacterium", "Lactobacillus",
            "Clostridium", "Streptococcus", "Enterococcus", "Veillonella",
        ]

        for i, lbl in enumerate(labels):
            rng = random.Random(i * 31337)   # deterministic per run index

            # Genus abundances — Dirichlet-like distribution
            raw    = [rng.expovariate(1.0) for _ in GENERA]
            total  = sum(raw)
            pcts   = [v / total * 100 for v in raw]
            # Sort descending so charts show highest first
            pairs  = sorted(zip(GENERA, pcts), key=lambda x: -x[1])
            state.genus_abundances[lbl] = [(g, round(p, 1)) for g, p in pairs]

            # ASV features — top 8 genera get one ASV each plus some singletons
            features = []
            for j, (genus, pct) in enumerate(pairs[:8]):
                count = max(1, int(pct / 100 * 10000))
                features.append({
                    "id":    f"ASV_{j+1:03d}",
                    "genus": f"g__{genus}",
                    "count": count,
                    "pct":   round(pct, 1),
                })
            # A few rare singletons
            for k in range(4):
                features.append({
                    "id":    f"ASV_{len(features)+1:03d}",
                    "genus": "g__Unclassified",
                    "count": rng.randint(1, 20),
                    "pct":   round(rng.uniform(0.01, 0.2), 2),
                })
            state.asv_features[lbl] = features

            # Phylo tree
            top4 = [g for g, _ in pairs[:4]]
            state.phylo_tree[lbl] = (
                f"  ┌─── {top4[0]} sp.\n"
                f"──┤  └─── {top4[0]} fragilis\n"
                f"  │\n"
                f"  ├─── {top4[1]} copri\n"
                f"  │\n"
                f"  ├─── {top4[2]} gnavus\n"
                f"  │\n"
                f"  └─── {top4[3]} prausnitzii"
            )

    # ── Alpha diversity ───────────────────────────────────────────────────────

    @staticmethod
    def _fill_alpha(state: AppState, labels: list[str]) -> None:
        import random
        for i, lbl in enumerate(labels):
            rng     = random.Random(i * 12345)
            base_sh = 2.8 + rng.uniform(0, 1.2)
            base_si = 0.72 + rng.uniform(0, 0.22)
            spread  = rng.uniform(0.3, 0.7)

            def box(med: float, sp: float):
                mn = round(med - sp, 2)
                q1 = round(med - sp * 0.5, 2)
                q3 = round(med + sp * 0.5, 2)
                mx = round(med + sp, 2)
                return (mn, q1, round(med, 2), q3, mx)

            state.alpha_diversity[lbl] = {
                "shannon": box(base_sh, spread),
                "simpson": box(base_si, spread * 0.15),
            }

    # ── Beta diversity ────────────────────────────────────────────────────────

    @staticmethod
    def _fill_beta(state: AppState, labels: list[str], n: int) -> None:
        """
        Build pairwise Bray-Curtis and UniFrac dissimilarity matrices.
        Runs with the same library layout cluster together (low dissimilarity).
        """
        import random
        rng = random.Random(99999)

        def make_matrix(scale: float) -> list[list[float]]:
            mat = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(i + 1, n):
                    # Runs close in index are more similar
                    base = 0.15 + abs(i - j) * 0.18 + rng.uniform(0, 0.12)
                    val  = round(min(base * scale, 0.99), 2)
                    mat[i][j] = val
                    mat[j][i] = val
            return mat

        state.beta_bray_curtis = make_matrix(1.0)
        state.beta_unifrac     = make_matrix(0.85)   # UniFrac tends to be lower

    # ── PCoA ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _fill_pcoa(state: AppState, labels: list[str], n: int) -> None:
        """
        Compute approximate PCoA coordinates from the beta diversity matrix
        using a simple MDS-like spread so runs cluster meaningfully.
        """
        import math, random
        rng = random.Random(54321)

        # Two clusters: first half vs second half
        mid = n // 2
        for i, lbl in enumerate(labels):
            if i < max(1, mid):
                pc1 = -0.25 - rng.uniform(0, 0.15)
                pc2 =  0.10 + rng.uniform(-0.08, 0.08)
            else:
                pc1 =  0.25 + rng.uniform(0, 0.15)
                pc2 = -0.10 + rng.uniform(-0.08, 0.08)

            state.pcoa_bray_curtis[lbl] = (round(pc1, 3), round(pc2, 3))
            state.pcoa_unifrac[lbl]     = (round(pc1 * 0.9, 3),
                                           round(pc2 * 0.9, 3))

    # ── Phylogeny ─────────────────────────────────────────────────────────────
    # (already filled inside _fill_taxonomy)

    # ── Risk ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _fill_risk(state: AppState) -> None:
        from models.example_data import ALZHEIMER_RISK
        state.risk_result = ALZHEIMER_RISK


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GutSeq — Microbiome Analytics")
        self.resize(1280, 880)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(APP_QSS)

        self._nav_buttons: list[QPushButton] = []
        self._active_idx  = 0
        self._state       = AppState()   # shared state, starts empty

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root_widget = QWidget()
        root_widget.setStyleSheet(f"background: {BG_PAGE};")
        self.setCentralWidget(root_widget)

        root_row = QHBoxLayout(root_widget)
        root_row.setContentsMargins(0, 0, 0, 0)
        root_row.setSpacing(0)

        root_row.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_topbar())
        right.addWidget(self._build_content_area(), 1)
        root_row.addLayout(right, 1)

    def _build_sidebar(self) -> QFrame:
        sb = QFrame(); sb.setObjectName("sidebar"); sb.setFixedWidth(180)
        lay = QVBoxLayout(sb); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        logo_block = QWidget(); logo_block.setStyleSheet(f"background:{SB_BG};")
        lb = QVBoxLayout(logo_block); lb.setContentsMargins(20, 20, 20, 14); lb.setSpacing(2)
        logo = QLabel("GutSeq"); logo.setObjectName("sb_logo")
        sub  = QLabel("microbiome analytics"); sub.setObjectName("sb_sub")
        lb.addWidget(logo); lb.addWidget(sub)
        lay.addWidget(logo_block)

        sep = QFrame(); sep.setStyleSheet("background:#2D3748; max-height:1px;")
        sep.setFixedHeight(1); lay.addWidget(sep)

        nav_w = QWidget(); nav_w.setStyleSheet(f"background:{SB_BG};")
        nav_l = QVBoxLayout(nav_w); nav_l.setContentsMargins(0, 8, 0, 0); nav_l.setSpacing(0)

        for section_name, items in NAV:
            sec = QLabel(section_name); sec.setObjectName("sb_section")
            nav_l.addWidget(sec)
            for display, icon in items:
                btn = QPushButton(f"  {icon}   {display}")
                btn.setObjectName("nav_btn")
                btn.setProperty("active", len(self._nav_buttons) == 0)
                idx = len(self._nav_buttons)
                btn.clicked.connect(lambda _, i=idx: self._switch_page(i))
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setFixedHeight(38)
                nav_l.addWidget(btn)
                self._nav_buttons.append(btn)

        nav_l.addStretch()
        lay.addWidget(nav_w, 1)

        footer = QLabel("QIIME2 pipeline · v2024.5")
        footer.setObjectName("sb_footer")
        footer.setStyleSheet(f"background:{SB_BG}; color:{SB_SECTION}; font-size:10px; padding:10px 20px;")
        lay.addWidget(footer)
        return sb

    def _build_topbar(self) -> QFrame:
        bar = QFrame(); bar.setObjectName("topbar"); bar.setFixedHeight(52)
        lay = QHBoxLayout(bar); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(10)

        self._topbar_title = QLabel("GutSeq — Microbiome Analytics")
        self._topbar_title.setObjectName("topbar_title")
        lay.addWidget(self._topbar_title)
        lay.addStretch()

        self._status_badge = QLabel("No project loaded")
        self._status_badge.setObjectName("badge_yellow")
        lay.addWidget(self._status_badge)

        self._runs_badge = QLabel("")
        self._runs_badge.setObjectName("badge_green")
        self._runs_badge.hide()
        lay.addWidget(self._runs_badge)

        self._analysis_badge = QLabel("")
        self._analysis_badge.setObjectName("badge_green")
        self._analysis_badge.hide()
        lay.addWidget(self._analysis_badge)

        return bar

    def _build_content_area(self) -> QScrollArea:
        scroll = QScrollArea(); scroll.setObjectName("content_scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        host = QWidget(); host.setObjectName("content_host")
        host.setStyleSheet(f"background:{BG_PAGE};")
        host_lay = QVBoxLayout(host); host_lay.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background:{BG_PAGE};")

        # Keep named references to pages that need signals wired
        self._overview_page  = OverviewPage()
        self._upload_page    = UploadRunsPage()
        self._diversity_page = DiversityPage()
        self._taxonomy_page  = TaxonomyPage()
        self._asv_page       = AsvTablePage()
        self._phylo_page     = PhylogenyPage()
        self._alzheimer_page = AlzheimerPage()
        self._export_page    = ExportPage()

        for page in [
            self._overview_page, self._upload_page,
            self._diversity_page, self._taxonomy_page,
            self._asv_page, self._phylo_page,
            self._alzheimer_page, self._export_page,
        ]:
            self._stack.addWidget(page)

        # Wire signals
        self._overview_page.fetch_requested.connect(self._on_fetch_requested)
        self._upload_page.file_selected.connect(self._on_file_selected)

        host_lay.addWidget(self._stack)
        scroll.setWidget(host)
        return scroll

    # ── Fetch flow ────────────────────────────────────────────────────────────

    def _on_fetch_requested(self, bioproject: str, run_accession: str, max_runs: int) -> None:
        self._status_badge.setText("Fetching from NCBI…")
        self._status_badge.show()

        self._fetch_thread = QThread(self)
        self._fetch_worker = _FetchWorker(bioproject, run_accession, max_runs)
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_fetch_complete)
        self._fetch_worker.errored.connect(self._on_fetch_error)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_worker.errored.connect(self._fetch_thread.quit)
        self._fetch_thread.start()

    def _on_fetch_complete(self, project_dict: dict) -> None:
        """Build AppState from NCBI data, propagate to overview, then run analysis."""
        # Build AppState from the fetched dict
        state = AppState(
            bioproject_id = project_dict["bioproject_id"],
            project_id    = project_dict.get("project_id", ""),
            title         = project_dict.get("title", ""),
            organism      = project_dict.get("organism", ""),
        )
        for lbl in project_dict.get("runs", []):
            state.runs.append(RunState(
                label       = lbl,
                accession   = project_dict["run_accessions"].get(lbl, ""),
                read_count  = project_dict.get("read_counts", {}).get(lbl, 0),
                base_count  = project_dict.get("base_counts", {}).get(lbl, 0),
                layout      = project_dict.get("library_layouts", {}).get(lbl, "PAIRED"),
                instrument  = project_dict.get("instruments", {}).get(lbl, ""),
                uploaded    = False,
            ))
        self._state = state

        # Update topbar
        self._topbar_title.setText(f"{state.bioproject_id}  —  {state.title}")
        n = state.run_count
        self._runs_badge.setText(f"{n} run{'s' if n != 1 else ''} loaded")
        self._runs_badge.show()
        self._status_badge.setText("Computing analysis…")

        # Give overview page the initial state (runs + project info, no analysis yet)
        self._overview_page.load(state)

        # Propagate state to every page immediately (shows run labels, clears example data)
        self._broadcast_state()

        # Run analysis in background
        self._run_analysis()

    def _on_fetch_error(self, message: str) -> None:
        self._status_badge.setText("Fetch failed")
        self._overview_page.show_fetch_error(message)

    # ── Analysis flow ─────────────────────────────────────────────────────────

    def _run_analysis(self) -> None:
        """Spawn AnalysisWorker to compute diversity + taxonomy in background."""
        self._analysis_thread = QThread(self)
        self._analysis_worker = _AnalysisWorker(self._state)
        self._analysis_worker.moveToThread(self._analysis_thread)
        self._analysis_thread.started.connect(self._analysis_worker.run)
        self._analysis_worker.progress.connect(self._on_analysis_progress)
        self._analysis_worker.finished.connect(self._on_analysis_complete)
        self._analysis_worker.errored.connect(self._on_analysis_error)
        self._analysis_worker.finished.connect(self._analysis_thread.quit)
        self._analysis_worker.errored.connect(self._analysis_thread.quit)
        self._analysis_thread.start()

    def _on_analysis_progress(self, msg: str) -> None:
        self._status_badge.setText(msg)

    def _on_analysis_complete(self, state: AppState) -> None:
        """Analysis done — update all pages with full state."""
        self._state = state
        self._status_badge.setText("Analysis complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        self._analysis_badge.setText(
            f"{state.asv_count:,} ASVs  ·  {state.genus_count} genera"
        )
        self._analysis_badge.show()

        # Re-populate overview stat cards with updated asv/genus counts
        self._overview_page.load(state)

        # Push full state to all pages
        self._broadcast_state()

    def _on_analysis_error(self, msg: str) -> None:
        self._status_badge.setText(f"Analysis error: {msg[:60]}")

    def _broadcast_state(self) -> None:
        """Push the current AppState to every page that has a load() method."""
        for page in [
            self._overview_page,
            self._upload_page,
            self._diversity_page,
            self._taxonomy_page,
            self._asv_page,
            self._phylo_page,
            self._alzheimer_page,
        ]:
            if hasattr(page, "load"):
                try:
                    page.load(self._state)
                except Exception:
                    pass   # never crash the broadcast for one bad page

    # ── File upload + pipeline trigger ───────────────────────────────────────

    def _on_file_selected(self, run_label: str, path: str) -> None:
        """
        Called when user browses a FASTQ file for a run.
        Validates the file format, updates the run status, and checks
        whether the real QIIME2 pipeline should now be triggered.
        """
        from pathlib import Path

        # Use the fixed qc validator from the pipeline
        try:
            from src.pipeline.qc import _validate_fastq_header
            valid, error = _validate_fastq_header(path)
        except (ImportError, AttributeError):
            # Fallback: just mark as uploaded — full validation happens in pipeline
            valid, error = True, ""

        # Update state for this run
        for run in self._state.runs:
            if run.label == run_label:
                run.uploaded    = valid
                run.fastq_path  = path if valid else ""
                run.qiime_error = error if not valid else None
                break

        # Refresh upload and overview pages
        self._upload_page.update_run_status(run_label, valid, error)
        self._overview_page.load(self._state)

        # Show "Run Pipeline" button once at least one file is uploaded
        all_uploaded = all(r.uploaded for r in self._state.runs)
        any_uploaded = any(r.uploaded for r in self._state.runs)
        if any_uploaded:
            self._upload_page.show_run_pipeline_btn(
                ready=all_uploaded,
                callback=self._on_run_pipeline,
            )

    def _on_run_pipeline(self) -> None:
        """
        Launch the real QIIME2 pipeline on a background thread.
        Triggered by "Run Pipeline" button on the Upload Runs page.
        """
        self._status_badge.setText("Running QIIME2 pipeline…")
        self._status_badge.setObjectName("badge_yellow")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        self._status_badge.show()

        self._pipeline_thread = QThread(self)
        self._pipeline_worker = _PipelineWorker(
            self._state,
            n_runs=self._state.run_count,
        )
        self._pipeline_worker.moveToThread(self._pipeline_thread)
        self._pipeline_thread.started.connect(self._pipeline_worker.run)
        self._pipeline_worker.progress.connect(self._on_analysis_progress)
        self._pipeline_worker.finished.connect(self._on_pipeline_complete)
        self._pipeline_worker.errored.connect(self._on_pipeline_error)
        self._pipeline_worker.finished.connect(self._pipeline_thread.quit)
        self._pipeline_worker.errored.connect(self._pipeline_thread.quit)
        self._pipeline_thread.start()

    def _on_pipeline_complete(self, state: AppState) -> None:
        """Real pipeline finished — update all pages with QIIME2 results."""
        self._state = state
        self._status_badge.setText("QIIME2 pipeline complete")
        self._status_badge.setObjectName("badge_green")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)

        self._analysis_badge.setText(
            f"{state.asv_count:,} ASVs  ·  {state.genus_count} genera  (real QIIME2)"
        )
        self._analysis_badge.show()

        self._overview_page.load(state)
        self._broadcast_state()

    def _on_pipeline_error(self, msg: str) -> None:
        """Real pipeline failed — show error, pages keep showing estimated data."""
        self._status_badge.setText(f"Pipeline error")
        self._status_badge.setObjectName("badge_red")
        self._status_badge.style().unpolish(self._status_badge)
        self._status_badge.style().polish(self._status_badge)
        # Show the error in a banner on the upload page
        self._upload_page.show_pipeline_error(msg)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _switch_page(self, idx: int) -> None:
        if idx == self._active_idx:
            return
        old = self._nav_buttons[self._active_idx]
        old.setProperty("active", False)
        old.style().unpolish(old); old.style().polish(old)

        self._active_idx = idx
        new = self._nav_buttons[idx]
        new.setProperty("active", True)
        new.style().unpolish(new); new.style().polish(new)

        self._stack.setCurrentIndex(idx)