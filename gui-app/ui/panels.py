# """
# GutSeq — dashboard panel widgets.

# Each class corresponds to one numbered step / section visible in the
# main content area.  Panels receive data through explicit setter methods
# rather than reaching out to services themselves, keeping them pure
# "display" components that are easy to test in isolation.
# """

# from __future__ import annotations

# from pathlib import Path

# from PyQt6.QtWidgets import (
#     QWidget, QFrame, QLabel, QLineEdit, QComboBox,
#     QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
#     QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
#     QSizePolicy, QScrollArea,
# )
# from PyQt6.QtCore import Qt, pyqtSignal
# from PyQt6.QtGui import QColor

# from models.data_models import (
#     ProjectOverview, GenusAbundance, AsvFeature,
#     DiversityMetrics, BetaDiversityMatrix, AlzheimerRiskResult,
#     Biomarker,
# )
# from resources.styles import (
#     TEXT_PRIMARY, TEXT_SECONDARY, TEXT_HINT,
#     PANEL_BG, BORDER, TEAL_MID, TEAL_DARK, TEAL_LIGHT,
#     DANGER_FG, SUCCESS_FG, WARNING_FG,
#     GENUS_COLOURS,
# )
# from ui.widgets import (
#     PanelFrame, StatCard, BannerWidget, RunSwitcher,
#     BarChartWidget, StackedBarWidget, HeatmapWidget, RiskMeterWidget,
#     make_divider, make_section_title, make_hint,
# )


# # ── Step 1 — Fetch data inputs ────────────────────────────────────────────────

# class FetchDataPanel(QWidget):
#     """
#     Presents the BioProject accession input, optional run accession,
#     run-count selector, and Fetch button.

#     Emits *fetch_requested(bioproject, run_accession, max_runs)* when the
#     user clicks Fetch and both inputs pass local validation.
#     """

#     fetch_requested = pyqtSignal(str, str, int)

#     def __init__(self, parent: QWidget | None = None) -> None:
#         super().__init__(parent)
#         self._build_ui()

#     def _build_ui(self) -> None:
#         outer = QVBoxLayout(self)
#         outer.setContentsMargins(0, 0, 0, 0)
#         outer.setSpacing(6)
#         outer.addWidget(make_section_title("Step 1 — Fetch data from NCBI"))

#         card = PanelFrame()
#         outer.addWidget(card)

#         # ── Input row ──
#         row = QHBoxLayout()
#         row.setSpacing(10)

#         # BioProject accession (required)
#         bp_col = QVBoxLayout()
#         bp_label = QLabel("BioProject accession <span style='color:#E24B4A'>*</span>")
#         bp_label.setTextFormat(Qt.TextFormat.RichText)
#         bp_label.setObjectName("muted")
#         self._bp_input = QLineEdit()
#         self._bp_input.setPlaceholderText("e.g. PRJNA123456")
#         self._bp_input.textChanged.connect(self._on_bp_changed)
#         bp_col.addWidget(bp_label)
#         bp_col.addWidget(self._bp_input)
#         row.addLayout(bp_col, 2)

#         # Run accession (optional)
#         run_col = QVBoxLayout()
#         run_label = QLabel("Run accession  <span style='color:#9E9C96; font-size:10px'>(optional — filter to one run)</span>")
#         run_label.setTextFormat(Qt.TextFormat.RichText)
#         run_label.setObjectName("muted")
#         self._run_input = QLineEdit()
#         self._run_input.setPlaceholderText("e.g. SRR987654")
#         self._run_input.textChanged.connect(self._on_run_changed)
#         run_col.addWidget(run_label)
#         run_col.addWidget(self._run_input)
#         row.addLayout(run_col, 2)

#         # Runs-to-fetch dropdown
#         count_col = QVBoxLayout()
#         count_label = QLabel("Runs to fetch")
#         count_label.setObjectName("muted")
#         self._count_combo = QComboBox()
#         for n in range(1, 5):
#             self._count_combo.addItem(str(n), n)
#         self._count_combo.setCurrentIndex(3)   # default = 4
#         count_col.addWidget(count_label)
#         count_col.addWidget(self._count_combo)
#         row.addLayout(count_col, 1)

#         # Fetch button
#         self._fetch_btn = QPushButton("Fetch →")
#         self._fetch_btn.setObjectName("primary")
#         self._fetch_btn.setFixedHeight(32)
#         self._fetch_btn.clicked.connect(self._on_fetch_clicked)
#         row.addWidget(self._fetch_btn, 0, Qt.AlignmentFlag.AlignBottom)

#         card.add_layout(row)

#         # Hint text
#         hint = make_hint(
#             "BioProject (PRJNA…) groups all sequencing runs from one study.  "
#             "Run Accession (SRR…/ERR…) filters to a single file.  "
#             "Fetched runs appear as R1–R4 throughout the dashboard."
#         )
#         card.add_widget(hint)

#         # Validation error banner (hidden until needed)
#         self._error_banner = BannerWidget("", kind="error")
#         self._error_banner.hide()
#         outer.addWidget(self._error_banner)

#     # ── Validation ────────────────────────────────────────────────────────────

#     def _on_bp_changed(self, text: str) -> None:
#         """Live-validate the BioProject field and update its border colour."""
#         from services.analysis_service import validate_bioproject_accession
#         if not text.strip():
#             self._bp_input.setProperty("valid", None)
#         else:
#             ok, _ = validate_bioproject_accession(text)
#             self._bp_input.setProperty("valid", "true" if ok else "false")
#         self._bp_input.style().unpolish(self._bp_input)
#         self._bp_input.style().polish(self._bp_input)

#     def _on_run_changed(self, text: str) -> None:
#         from services.analysis_service import validate_run_accession
#         if not text.strip():
#             self._run_input.setProperty("valid", None)
#         else:
#             ok, _ = validate_run_accession(text)
#             self._run_input.setProperty("valid", "true" if ok else "false")
#         self._run_input.style().unpolish(self._run_input)
#         self._run_input.style().polish(self._run_input)

#     def _on_fetch_clicked(self) -> None:
#         from services.analysis_service import (
#             validate_bioproject_accession, validate_run_accession
#         )
#         bp = self._bp_input.text().strip()
#         run = self._run_input.text().strip()

#         bp_ok, bp_err = validate_bioproject_accession(bp)
#         run_ok, run_err = validate_run_accession(run)

#         if not bp_ok:
#             self._show_error(bp_err)
#             return
#         if not run_ok:
#             self._show_error(run_err)
#             return

#         self._error_banner.hide()
#         max_runs = self._count_combo.currentData()
#         self.fetch_requested.emit(bp, run, max_runs)

#     def _show_error(self, message: str) -> None:
#         # Rebuild banner text (BannerWidget label is static by default)
#         lbl = self._error_banner.findChild(QLabel)
#         if lbl:
#             lbl.setText(message)
#         self._error_banner.show()


# # ── Step 2 — Project overview stats ──────────────────────────────────────────

# class ProjectOverviewPanel(QWidget):
#     """
#     Displays the six top-level stat cards once a project has been fetched.
#     """

#     def __init__(self, parent: QWidget | None = None) -> None:
#         super().__init__(parent)
#         self._build_ui()

#     def _build_ui(self) -> None:
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(8)
#         layout.addWidget(make_section_title("Step 2 — Project overview"))

#         self._grid = QGridLayout()
#         self._grid.setSpacing(8)
#         layout.addLayout(self._grid)

#         # Placeholder until data arrives
#         self._show_placeholder()

#     def _show_placeholder(self) -> None:
#         for i in reversed(range(self._grid.count())):
#             widget = self._grid.itemAt(i).widget()
#             if widget:
#                 widget.deleteLater()

#         placeholder = QLabel("Fetch a BioProject to see summary statistics.")
#         placeholder.setObjectName("hint")
#         self._grid.addWidget(placeholder, 0, 0)

#     def load(self, overview: ProjectOverview) -> None:
#         """Populate the stat cards from a *ProjectOverview* object."""
#         # Clear old widgets
#         for i in reversed(range(self._grid.count())):
#             w = self._grid.itemAt(i).widget()
#             if w:
#                 w.deleteLater()

#         cards = [
#             StatCard("Project ID",     overview.project_id,
#                      sub=overview.title[:30] + "…" if len(overview.title) > 30 else overview.title),
#             StatCard("Runs",           str(overview.run_count),
#                      sub="  ".join(r.label for r in overview.runs)),
#             StatCard("ASVs",           f"{overview.asv_count:,}",
#                      sub="unique sequences"),
#             StatCard("Genera",         str(overview.genus_count),
#                      sub="bacterial genera"),
#             StatCard("Library",        overview.library_layout.value),
#             StatCard("Upload status",
#                      f"{sum(r.uploaded for r in overview.runs)} / {overview.run_count}",
#                      sub="runs uploaded"),
#         ]
#         for col, card in enumerate(cards):
#             self._grid.addWidget(card, 0, col)


# # ── Step 3 — Genus abundance + taxonomy map ───────────────────────────────────

# class AbundancePanel(QWidget):
#     """
#     Bar chart (top-10 genera) + donut taxonomy map, both with a run switcher.
#     """

#     def __init__(self, run_labels: list[str], parent: QWidget | None = None) -> None:
#         super().__init__(parent)
#         self._run_labels = run_labels
#         self._build_ui()

#     def _build_ui(self) -> None:
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(8)

#         # Header row: title + run switcher
#         header = QHBoxLayout()
#         header.addWidget(make_section_title("Step 3 — Genus abundance & taxonomy"))
#         self._switcher = RunSwitcher(self._run_labels)
#         header.addWidget(self._switcher)
#         layout.addLayout(header)

#         # Two panels side by side
#         row = QHBoxLayout()
#         row.setSpacing(10)

#         # Bar chart panel
#         bar_panel = PanelFrame()
#         bar_panel.add_widget(QLabel("Top 10 genera — relative abundance"))
#         self._bar_chart = BarChartWidget(data=[])
#         self._bar_chart.setFixedHeight(110)
#         bar_panel.add_widget(self._bar_chart)
#         row.addWidget(bar_panel, 1)

#         # Taxonomy donut placeholder (described as text until a custom SVG widget
#         # is added; the stacked-bar widget acts as a readable substitute here)
#         tax_panel = PanelFrame()
#         tax_panel.add_widget(QLabel("ASV → taxonomy map"))
#         self._tax_chart = StackedBarWidget(data={})
#         tax_panel.add_widget(self._tax_chart)
#         hint = make_hint("Inner ring = ASVs · outer ring = genera · width ∝ count")
#         tax_panel.add_widget(hint)
#         row.addWidget(tax_panel, 1)

#         layout.addLayout(row)

#         # Wire switcher → data refresh
#         self._switcher.run_changed.connect(self._refresh_charts)

#     def load(self, abundances_by_run: dict[str, list[GenusAbundance]]) -> None:
#         self._data = abundances_by_run
#         self._refresh_charts(self._switcher.active_run)

#     def _refresh_charts(self, run_label: str) -> None:
#         if not hasattr(self, "_data"):
#             return
#         genera = self._data.get(run_label, [])

#         # Bar chart: (genus_name, abundance)
#         bar_data = [(g.genus, g.relative_abundance) for g in genera]
#         self._bar_chart.update_data(bar_data)

#         # Taxonomy stacked bar: one row per run, segments per genus
#         stacked = {
#             run: [(g.genus, g.relative_abundance) for g in gens]
#             for run, gens in self._data.items()
#         }
#         self._tax_chart.update_data(stacked)


# # ── Step 4 — Upload + diversity ───────────────────────────────────────────────

# class DiversityPanel(QWidget):
#     """
#     Upload zone (FASTQ), alpha diversity boxplots, beta diversity
#     PCoA description + heatmap, and QIIME2 error display.
#     """

#     file_selected = pyqtSignal(str, Path)   # (run_label, path)

#     def __init__(self, run_labels: list[str], parent: QWidget | None = None) -> None:
#         super().__init__(parent)
#         self._run_labels = run_labels
#         self._build_ui()

#     def _build_ui(self) -> None:
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(8)
#         layout.addWidget(make_section_title("Step 4 — Upload run data & diversity analysis"))

#         top_row = QHBoxLayout()
#         top_row.setSpacing(10)

#         # Upload zone
#         upload_panel = PanelFrame()
#         upload_panel.add_widget(QLabel("<b>Upload .fastq or .fastq.gz files</b>"))
#         upload_panel.add_widget(make_hint(
#             "Validates 4-line FASTQ format:\n"
#             "@SEQID · ACTG sequence · + · Phred quality scores"
#         ))
#         for label in self._run_labels:
#             btn = QPushButton(f"Browse file for {label}…")
#             btn.clicked.connect(lambda _, lbl=label: self._browse_file(lbl))
#             upload_panel.add_widget(btn)
#         top_row.addWidget(upload_panel, 1)

#         # Alpha diversity panel
#         alpha_panel = PanelFrame()
#         alpha_panel.add_widget(QLabel("Alpha diversity  (Shannon index per run)"))
#         alpha_panel.add_widget(make_hint(
#             "Each box = spread of diversity within one run.\n"
#             "Higher = more species-rich community."
#         ))
#         # Boxplot placeholder label (replaced by a proper custom widget in production)
#         self._alpha_label = QLabel("Load data to see boxplots.")
#         self._alpha_label.setObjectName("hint")
#         alpha_panel.add_widget(self._alpha_label)
#         top_row.addWidget(alpha_panel, 1)

#         layout.addLayout(top_row)

#         # Beta diversity row
#         beta_row = QHBoxLayout()
#         beta_row.setSpacing(10)

#         # PCoA description
#         pcoa_panel = PanelFrame()
#         pcoa_panel.add_widget(QLabel("Beta diversity — PCoA"))
#         pcoa_panel.add_widget(make_hint(
#             "Runs (R1–R4) plotted by community similarity.\n"
#             "Closer together = more similar gut microbiomes.\n"
#             "Each ellipse groups runs with similar profiles."
#         ))
#         self._pcoa_label = QLabel("Load data to see PCoA plot.")
#         self._pcoa_label.setObjectName("hint")
#         pcoa_panel.add_widget(self._pcoa_label)
#         beta_row.addWidget(pcoa_panel, 1)

#         # Heatmap
#         hm_panel = PanelFrame()
#         hm_panel.add_widget(QLabel("Beta diversity — heatmap"))
#         hm_panel.add_widget(make_hint("Pairwise dissimilarity. Darker = more similar."))
#         self._heatmap = HeatmapWidget(labels=[], values=[])
#         hm_panel.add_widget(self._heatmap)
#         beta_row.addWidget(hm_panel, 1)

#         layout.addLayout(beta_row)

#         # QIIME error banner (hidden until an error occurs)
#         self._qiime_banner = BannerWidget("", kind="error")
#         self._qiime_banner.hide()
#         layout.addWidget(self._qiime_banner)

#     # ── Public update methods ─────────────────────────────────────────────────

#     def load_alpha(self, metrics: list[DiversityMetrics]) -> None:
#         """Update the alpha-diversity display."""
#         lines = [
#             f"{m.run_label}:  Shannon = {m.shannon_index:.2f}  |  "
#             f"Simpson = {m.simpson_index:.2f}"
#             for m in metrics
#         ]
#         self._alpha_label.setText("\n".join(lines))

#     def load_beta(self, matrix: BetaDiversityMatrix) -> None:
#         """Update PCoA text and heatmap."""
#         self._heatmap.update_data(matrix.run_labels, matrix.values)
#         # Update PCoA placeholder text with pairwise summary
#         pairs = []
#         n = len(matrix.run_labels)
#         for i in range(n):
#             for j in range(i + 1, n):
#                 val = matrix.values[i][j]
#                 pairs.append(
#                     f"{matrix.run_labels[i]}↔{matrix.run_labels[j]}: {val:.2f}"
#                 )
#         self._pcoa_label.setText(
#             "Bray-Curtis dissimilarity pairs:\n" + "  |  ".join(pairs)
#         )

#     def show_qiime_error(self, run_label: str, message: str) -> None:
#         lbl = self._qiime_banner.findChild(QLabel)
#         if lbl:
#             lbl.setText(f"{run_label} — {message}")
#         self._qiime_banner.show()

#     # ── File browser ──────────────────────────────────────────────────────────

#     def _browse_file(self, run_label: str) -> None:
#         path_str, _ = QFileDialog.getOpenFileName(
#             self,
#             f"Select FASTQ file for {run_label}",
#             "",
#             "FASTQ files (*.fastq *.fastq.gz);;All files (*)",
#         )
#         if path_str:
#             self.file_selected.emit(run_label, Path(path_str))


# # ── Step 5 — Taxonomy tables + phylogeny ─────────────────────────────────────

# class TaxonomyPanel(QWidget):
#     """
#     ASV feature-count table, genus abundance table (filterable + sortable),
#     genus composition stacked bar chart, and a text-based phylogenetic tree.
#     """

#     def __init__(self, run_labels: list[str], parent: QWidget | None = None) -> None:
#         super().__init__(parent)
#         self._run_labels = run_labels
#         self._build_ui()

#     def _build_ui(self) -> None:
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(8)

#         # Header with run switcher
#         header = QHBoxLayout()
#         header.addWidget(make_section_title("Step 5 — Taxonomy tables & phylogeny"))
#         self._switcher = RunSwitcher(self._run_labels)
#         self._switcher.run_changed.connect(self._on_run_changed)
#         header.addWidget(self._switcher)
#         layout.addLayout(header)

#         # Top row: ASV table + genus table + composition bar
#         top_row = QHBoxLayout()
#         top_row.setSpacing(10)

#         # ASV feature counts table
#         asv_panel = PanelFrame()
#         asv_panel.add_widget(QLabel("ASV feature counts"))
#         self._asv_table = self._build_asv_table()
#         asv_panel.add_widget(self._asv_table)
#         top_row.addWidget(asv_panel, 2)

#         # Genus abundance table
#         genus_panel = PanelFrame()
#         genus_panel.add_widget(QLabel("Genus abundance table"))
#         self._genus_table = self._build_genus_table()
#         genus_panel.add_widget(self._genus_table)
#         top_row.addWidget(genus_panel, 1)

#         # Composition stacked bar
#         comp_panel = PanelFrame()
#         comp_panel.add_widget(QLabel("Genus composition — all runs"))
#         self._comp_bar = StackedBarWidget(data={})
#         comp_panel.add_widget(self._comp_bar)
#         top_row.addWidget(comp_panel, 1)

#         layout.addLayout(top_row)

#         # Phylogenetic tree (text representation)
#         tree_panel = PanelFrame()
#         tree_panel.add_widget(QLabel("Phylogenetic tree  (IQ-TREE · tree.nwk)"))
#         tree_panel.add_widget(make_hint(
#             "Switch runs with the pill buttons above to see each run's tree."
#         ))
#         self._tree_label = QLabel(self._placeholder_tree())
#         self._tree_label.setFont(
#             self._tree_label.font()
#         )
#         self._tree_label.setStyleSheet(
#             f"font-family: monospace; font-size: 11px; color: {TEXT_SECONDARY};"
#         )
#         tree_panel.add_widget(self._tree_label)
#         layout.addWidget(tree_panel)

#     @staticmethod
#     def _build_asv_table() -> QTableWidget:
#         tbl = QTableWidget(0, 4)
#         tbl.setHorizontalHeaderLabels(["Feature ID", "Taxonomy", "Count", "Rel. %"])
#         tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
#         tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
#         tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
#         tbl.setAlternatingRowColors(True)
#         tbl.setFixedHeight(160)
#         return tbl

#     @staticmethod
#     def _build_genus_table() -> QTableWidget:
#         tbl = QTableWidget(0, 2)
#         tbl.setHorizontalHeaderLabels(["Genus", "Rel. %"])
#         tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
#         tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
#         tbl.setAlternatingRowColors(True)
#         tbl.setFixedHeight(160)
#         return tbl

#     @staticmethod
#     def _placeholder_tree() -> str:
#         return (
#             "  ┌── Bacteroides fragilis\n"
#             "──┤  └── Bacteroides thetaiotaomicron\n"
#             "  │\n"
#             "  ├── Prevotella copri\n"
#             "  │  └── Prevotella melaninogenica\n"
#             "  │\n"
#             "  └── Ruminococcus gnavus\n"
#             "     └── Faecalibacterium prausnitzii"
#         )

#     # ── Public update methods ─────────────────────────────────────────────────

#     def load(
#         self,
#         asv_features_by_run: dict[str, list[AsvFeature]],
#         abundances_by_run: dict[str, list[GenusAbundance]],
#     ) -> None:
#         self._asv_data = asv_features_by_run
#         self._abundance_data = abundances_by_run

#         # Populate composition chart from all runs
#         stacked = {
#             run: [(g.genus, g.relative_abundance) for g in gens]
#             for run, gens in abundances_by_run.items()
#         }
#         self._comp_bar.update_data(stacked)

#         # Show first run by default
#         self._on_run_changed(self._switcher.active_run)

#     def _on_run_changed(self, run_label: str) -> None:
#         if hasattr(self, "_asv_data"):
#             self._populate_asv_table(self._asv_data.get(run_label, []))
#         if hasattr(self, "_abundance_data"):
#             self._populate_genus_table(self._abundance_data.get(run_label, []))

#     def _populate_asv_table(self, features: list[AsvFeature]) -> None:
#         self._asv_table.setRowCount(len(features))
#         for row, feat in enumerate(features):
#             self._asv_table.setItem(row, 0, QTableWidgetItem(feat.feature_id))
#             self._asv_table.setItem(row, 1, QTableWidgetItem(feat.taxonomy))
#             self._asv_table.setItem(row, 2, QTableWidgetItem(f"{feat.count:,}"))
#             self._asv_table.setItem(row, 3, QTableWidgetItem(f"{feat.relative_abundance:.1f}"))

#     def _populate_genus_table(self, genera: list[GenusAbundance]) -> None:
#         self._genus_table.setRowCount(len(genera))
#         for row, g in enumerate(genera):
#             self._genus_table.setItem(row, 0, QTableWidgetItem(g.genus))
#             self._genus_table.setItem(row, 1, QTableWidgetItem(f"{g.relative_abundance:.1f}"))


# # ── Step 6 — Alzheimer risk prediction ───────────────────────────────────────

# class AlzheimerRiskPanel(QWidget):
#     """
#     Displays predicted Alzheimer's disease risk percentage, confidence,
#     risk-level spectrum bar, and a grid of key biomarker cards.
#     """

#     def __init__(self, parent: QWidget | None = None) -> None:
#         super().__init__(parent)
#         self._build_ui()

#     def _build_ui(self) -> None:
#         layout = QVBoxLayout(self)
#         layout.setContentsMargins(0, 0, 0, 0)
#         layout.setSpacing(8)

#         header = QHBoxLayout()
#         header.addWidget(make_section_title("Step 6 — Alzheimer's disease risk prediction"))
#         header.addWidget(make_hint("Based on gut-brain axis biomarkers · research-grade only"))
#         layout.addLayout(header)

#         card = PanelFrame()
#         layout.addWidget(card)

#         # ── Top risk summary row ──
#         summary_row = QHBoxLayout()
#         summary_row.setSpacing(20)

#         # Big risk percentage
#         self._risk_pct_label = QLabel("—")
#         self._risk_pct_label.setStyleSheet(
#             "font-size: 36px; font-weight: 700; color: #D85A30;"
#         )
#         pct_col = QVBoxLayout()
#         pct_col.addWidget(QLabel("Predicted risk"))
#         pct_col.addWidget(self._risk_pct_label)
#         self._risk_level_label = QLabel("")
#         self._risk_level_label.setObjectName("hint")
#         pct_col.addWidget(self._risk_level_label)
#         summary_row.addLayout(pct_col)

#         # Risk meter bar
#         meter_col = QVBoxLayout()
#         meter_col.addWidget(QLabel("Risk spectrum — gut-brain axis score"))
#         self._risk_meter = RiskMeterWidget(risk_pct=0.0)
#         meter_col.addWidget(self._risk_meter)
#         spectrum_row = QHBoxLayout()
#         for txt in ("Low", "Moderate", "Elevated", "High"):
#             lbl = QLabel(txt)
#             lbl.setObjectName("hint")
#             lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
#             spectrum_row.addWidget(lbl)
#         meter_col.addLayout(spectrum_row)
#         summary_row.addLayout(meter_col, 1)

#         # Confidence score
#         self._conf_label = QLabel("—")
#         self._conf_label.setStyleSheet("font-size: 22px; font-weight: 600;")
#         conf_col = QVBoxLayout()
#         conf_col.addWidget(QLabel("Confidence"))
#         conf_col.addWidget(self._conf_label)
#         conf_col.addWidget(make_hint("model certainty"))
#         summary_row.addLayout(conf_col)

#         card.add_layout(summary_row)
#         card.add_widget(make_divider())

#         # ── Biomarker grid ──
#         card.add_widget(make_hint("Key biomarkers driving this prediction:"))
#         self._biomarker_grid = QGridLayout()
#         self._biomarker_grid.setSpacing(8)
#         card.add_layout(self._biomarker_grid)

#         # ── Disclaimer ──
#         card.add_widget(make_divider())
#         self._disclaimer = make_hint(
#             "⚠  This prediction is a research-grade estimate based on published "
#             "gut-brain axis literature. It is NOT a clinical diagnosis. "
#             "Consult a physician for clinical assessment."
#         )
#         card.add_widget(self._disclaimer)

#         # Show placeholder until data is loaded
#         self._show_placeholder()

#     def _show_placeholder(self) -> None:
#         lbl = QLabel("Fetch a project and upload runs to see risk prediction.")
#         lbl.setObjectName("hint")
#         self._biomarker_grid.addWidget(lbl, 0, 0)

#     def load(self, result: AlzheimerRiskResult) -> None:
#         """Populate the panel with an *AlzheimerRiskResult*."""
#         self._risk_pct_label.setText(f"{result.predicted_risk_pct:.0f}%")
#         self._risk_level_label.setText(result.risk_level.value)
#         self._risk_meter.set_risk(result.predicted_risk_pct)
#         self._conf_label.setText(f"{result.confidence_pct:.0f}%")

#         # Clear old biomarker cards
#         for i in reversed(range(self._biomarker_grid.count())):
#             w = self._biomarker_grid.itemAt(i).widget()
#             if w:
#                 w.deleteLater()

#         # Rebuild biomarker grid (3 columns)
#         for idx, bm in enumerate(result.biomarkers):
#             card = self._make_biomarker_card(bm)
#             row, col = divmod(idx, 3)
#             self._biomarker_grid.addWidget(card, row, col)

#         self._disclaimer.setText(result.disclaimer)

#     @staticmethod
#     def _make_biomarker_card(bm: Biomarker) -> QFrame:
#         """Build one small card for a single biomarker."""
#         card = QFrame()
#         card.setObjectName("panel")
#         layout = QVBoxLayout(card)
#         layout.setContentsMargins(10, 8, 10, 8)
#         layout.setSpacing(2)

#         name_lbl = QLabel(bm.name)
#         name_lbl.setObjectName("muted")
#         name_lbl.setWordWrap(True)
#         layout.addWidget(name_lbl)

#         # Colour value label by status
#         colour = {
#             "low":    DANGER_FG,
#             "high":   DANGER_FG,
#             "normal": SUCCESS_FG,
#         }.get(bm.status, TEXT_PRIMARY)

#         arrow = {"low": "↓", "high": "↑", "normal": "✓"}.get(bm.status, "")
#         val_lbl = QLabel(f"{arrow} {bm.observed_value:.1f}{bm.unit}")
#         val_lbl.setStyleSheet(
#             f"font-size: 14px; font-weight: 600; color: {colour};"
#         )
#         layout.addWidget(val_lbl)

#         ref_lbl = QLabel(f"Normal: {bm.normal_range} · {bm.description}")
#         ref_lbl.setObjectName("hint")
#         ref_lbl.setWordWrap(True)
#         layout.addWidget(ref_lbl)

#         return card