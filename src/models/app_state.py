"""
gui-app/models/app_state.py

Central application state shared across all pages.

MainWindow updates this after a successful fetch; all pages
read from it via signals or direct calls.  No page ever
modifies state — only MainWindow writes to it.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RunState:
    """Live state of one sequencing run."""
    label:          str
    accession:      str
    read_count:     int    = 0
    base_count:     int    = 0
    layout:         str    = "PAIRED"
    instrument:     str    = ""
    fastq_path:     str    = ""        # local file path after upload
    uploaded:       bool   = False
    qiime_error:    Optional[str] = None


@dataclass
class AppState:
    """
    Single source of truth for the current project.
    Populated by MainWindow after a successful NCBI fetch.
    """
    # ── Project-level ─────────────────────────────────────────────────────────
    bioproject_id:  str = ""
    project_id:     str = ""           # SRA study ID, e.g. SRP296181
    title:          str = ""
    organism:       str = ""

    # ── Runs ──────────────────────────────────────────────────────────────────
    runs: list[RunState] = field(default_factory=list)

    # ── Analysis results (filled after QIIME2 runs) ───────────────────────────
    asv_count:      int  = 0
    genus_count:    int  = 0

    # Taxonomy per run: run_label → list of (genus, pct)
    genus_abundances:  dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    # ASV table per run: run_label → list of dicts
    asv_features:      dict[str, list[dict]]              = field(default_factory=dict)
    # Phylo tree text per run
    phylo_tree:        dict[str, str]                     = field(default_factory=dict)

    # Alpha diversity: run_label → {"shannon": (min,q1,med,q3,max), "simpson": ...}
    alpha_diversity:   dict[str, dict]                    = field(default_factory=dict)
    # Beta diversity matrices
    beta_bray_curtis:  list[list[float]]                  = field(default_factory=list)
    beta_unifrac:      list[list[float]]                  = field(default_factory=list)
    # PCoA coordinates: run_label → (pc1, pc2)
    pcoa_bray_curtis:  dict[str, tuple[float, float]]     = field(default_factory=dict)
    pcoa_unifrac:      dict[str, tuple[float, float]]     = field(default_factory=dict)

    # ── Risk ──────────────────────────────────────────────────────────────────
    risk_result: Optional[dict] = None

    # ── DB linkage (set when project is saved to database) ────────────────────
    db_project_id: Optional[int] = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def run_labels(self) -> list[str]:
        return [r.label for r in self.runs]

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def uploaded_count(self) -> int:
        return sum(1 for r in self.runs if r.uploaded)

    @property
    def library_layout(self) -> str:
        layouts = {r.layout.upper() for r in self.runs}
        if layouts == {"PAIRED"}:  return "Paired-end"
        if layouts == {"SINGLE"}:  return "Single-end"
        if layouts:                return "Paired + Single"
        return "Unknown"

    @property
    def has_project(self) -> bool:
        return bool(self.bioproject_id)

    @property
    def has_analysis(self) -> bool:
        return bool(self.genus_abundances)

    def run_colors(self) -> dict[str, str]:
        palette = ["#10B981", "#6366F1", "#F59E0B", "#EF4444",
                   "#8B5CF6", "#14B8A6", "#F97316", "#EC4899"]
        return {r.label: palette[i % len(palette)]
                for i, r in enumerate(self.runs)}

    def to_project_dict(self) -> dict:
        """Return the dict shape OverviewPage.load_project() expects."""
        rc = self.run_colors()
        return {
            "bioproject_id":   self.bioproject_id,
            "project_id":      self.project_id,
            "title":           self.title,
            "runs":            self.run_labels,
            "run_accessions":  {r.label: r.accession   for r in self.runs},
            "read_counts":     {r.label: r.read_count  for r in self.runs},
            "uploaded":        {r.label: r.uploaded    for r in self.runs},
            "qiime_errors":    {r.label: r.qiime_error for r in self.runs
                                if r.qiime_error},
            "asv_count":       self.asv_count,
            "genus_count":     self.genus_count,
            "library":         self.library_layout,
        }