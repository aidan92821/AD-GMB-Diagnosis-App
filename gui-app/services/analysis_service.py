# """
# GutSeq — service layer.

# All data-fetching and analysis logic lives here, completely separate from
# the UI.  The real NCBI calls are stubbed with realistic mock data so the
# app runs without a network connection; swap in the real Entrez / SRA API
# calls by replacing the methods marked with  # TODO: real API call.
# """

# from __future__ import annotations

# import re
# import gzip
# import math
# from pathlib import Path
# from typing import Optional

# from models.data_models import (
#     ProjectOverview, RunInfo, LibraryLayout,
#     GenusAbundance, AsvFeature,
#     DiversityMetrics, BetaDiversityMatrix,
#     AlzheimerRiskResult, Biomarker, RiskLevel,
# )


# # ── Validation helpers ────────────────────────────────────────────────────────

# BIOPROJECT_RE = re.compile(r"^PRJ[EDN]A\d+$", re.IGNORECASE)
# RUN_ACCESSION_RE = re.compile(r"^[SED]RR\d+$", re.IGNORECASE)


# def validate_bioproject_accession(accession: str) -> tuple[bool, str]:
#     """
#     Return (is_valid, error_message).
#     A valid BioProject accession matches PRJNA / PRJEB / PRJDB + digits.
#     """
#     if not accession.strip():
#         return False, "BioProject accession is required."
#     if not BIOPROJECT_RE.match(accession.strip()):
#         return False, f"'{accession}' does not match expected format (e.g. PRJNA123456)."
#     return True, ""


# def validate_run_accession(accession: str) -> tuple[bool, str]:
#     """
#     Return (is_valid, error_message).
#     A valid Run accession matches SRR / ERR / DRR + digits.
#     Empty string is also valid (field is optional).
#     """
#     if not accession.strip():
#         return True, ""   # optional field — blank is fine
#     if not RUN_ACCESSION_RE.match(accession.strip()):
#         return False, f"'{accession}' does not match expected format (e.g. SRR987654)."
#     return True, ""


# # ── FASTQ format validator ────────────────────────────────────────────────────

# VALID_SEQ_CHARS = set("ACGTNacgtn")
# PHRED_OFFSET    = 33   # Sanger / Illumina 1.8+

# def validate_fastq_file(path: Path) -> tuple[bool, str]:
#     """
#     Peek at the first 40 records of a .fastq or .fastq.gz file and verify
#     the 4-line FASTQ format:
#         Line 1 – @SEQID
#         Line 2 – sequence (A/C/G/T/N only)
#         Line 3 – + (optional second ID)
#         Line 4 – Phred quality string (same length as line 2)

#     Returns (is_valid, error_message).
#     """
#     opener = gzip.open if path.suffix == ".gz" else open

#     try:
#         with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
#             lines = [fh.readline().rstrip("\n") for _ in range(160)]  # 40 records × 4 lines
#     except OSError as exc:
#         return False, f"Cannot open file: {exc}"

#     if not lines[0]:
#         return False, "File appears to be empty."

#     for record_index in range(40):
#         base = record_index * 4
#         if base + 3 >= len(lines):
#             break   # fewer than 40 records is still valid

#         id_line, seq_line, plus_line, qual_line = (
#             lines[base], lines[base + 1], lines[base + 2], lines[base + 3]
#         )

#         if not id_line.startswith("@"):
#             return False, f"Record {record_index + 1}: ID line must start with '@'."

#         invalid_bases = set(seq_line) - VALID_SEQ_CHARS
#         if invalid_bases:
#             return False, (
#                 f"Record {record_index + 1}: invalid sequence characters "
#                 f"{invalid_bases}."
#             )

#         if not plus_line.startswith("+"):
#             return False, f"Record {record_index + 1}: line 3 must start with '+'."

#         if len(qual_line) != len(seq_line):
#             return False, (
#                 f"Record {record_index + 1}: Phred quality length "
#                 f"({len(qual_line)}) ≠ sequence length ({len(seq_line)})."
#             )

#     return True, ""


# # ── NCBI data service ─────────────────────────────────────────────────────────

# class NcbiService:
#     """
#     Handles all communication with NCBI (Entrez / SRA).

#     Currently returns realistic mock data so the app runs offline.
#     To connect to the real API, install Biopython and replace the
#     methods marked with  # TODO: real API call.
#     """

#     def fetch_project_overview(
#         self,
#         bioproject_accession: str,
#         max_runs: int = 4,
#         run_accession_filter: Optional[str] = None,
#     ) -> ProjectOverview:
#         """
#         Fetch project metadata and up to *max_runs* run accessions.
#         If *run_accession_filter* is given, only that run is returned.
#         """
#         # TODO: real API call — use Bio.Entrez.esearch + efetch
#         return self._mock_project(bioproject_accession, max_runs, run_accession_filter)

#     # ── Mock data ─────────────────────────────────────────────────────────────

#     def _mock_project(
#         self,
#         project_id: str,
#         max_runs: int,
#         run_filter: Optional[str],
#     ) -> ProjectOverview:
#         all_runs = [
#             RunInfo("SRR001001", "R1", read_count=48_200),
#             RunInfo("SRR001002", "R2", read_count=51_300),
#             RunInfo("SRR001003", "R3", read_count=44_800),
#             RunInfo("SRR001004", "R4", read_count=49_600),
#         ]
#         if run_filter:
#             runs = [r for r in all_runs if r.run_accession == run_filter]
#         else:
#             runs = all_runs[:max_runs]

#         return ProjectOverview(
#             project_id=project_id,
#             title="Human Gut Microbiome Study",
#             runs=runs,
#             asv_count=2_841,
#             genus_count=183,
#             library_layout=LibraryLayout.MIXED,
#         )


# # ── Analysis services ─────────────────────────────────────────────────────────

# class MicrobiomeAnalysisService:
#     """
#     Provides taxonomy, diversity, and risk analysis results.

#     All methods return mock data that mirrors what a real QIIME2 pipeline
#     would produce.  Replace the bodies with calls to your backend or
#     QIIME2 Python API as needed.
#     """

#     # ── Taxonomy ──────────────────────────────────────────────────────────────

#     def get_genus_abundances(self, run_label: str) -> list[GenusAbundance]:
#         """Return top-genus relative abundances for a single run."""
#         # TODO: real call — load feature-table.qza and taxonomy.qza via qiime2 API
#         base = {
#             "R1": [18.3, 12.1, 10.9, 7.4, 5.2, 4.8, 3.6, 2.9, 2.1, 1.8],
#             "R2": [22.1,  9.3, 14.2, 5.0, 6.1, 3.9, 2.8, 3.1, 1.9, 1.5],
#             "R3": [10.4, 20.2,  8.1, 12.3, 4.5, 5.5, 3.2, 2.7, 2.4, 1.6],
#             "R4": [15.0, 15.0, 10.0, 10.0, 5.5, 4.2, 3.8, 3.0, 2.5, 1.9],
#         }
#         genera = [
#             "Bacteroides", "Prevotella", "Ruminococcus", "Faecalibacterium",
#             "Blautia", "Roseburia", "Lachnospiraceae", "Akkermansia",
#             "Bifidobacterium", "Lactobacillus",
#         ]
#         values = base.get(run_label, base["R1"])
#         return [
#             GenusAbundance(genus=g, relative_abundance=v)
#             for g, v in zip(genera, values)
#         ]

#     def get_asv_features(self, run_label: str) -> list[AsvFeature]:
#         """Return ASV feature-count rows for a single run."""
#         # TODO: real call — parse QIIME2 feature-table artifact
#         rows = [
#             AsvFeature("ASV_001", "g__Bacteroides",       4_821, 18.3),
#             AsvFeature("ASV_002", "g__Prevotella",        3_204, 12.1),
#             AsvFeature("ASV_003", "g__Ruminococcus",      2_880, 10.9),
#             AsvFeature("ASV_004", "g__Faecalibacterium",  1_940,  7.4),
#             AsvFeature("ASV_005", "g__Blautia",           1_374,  5.2),
#             AsvFeature("ASV_006", "g__Roseburia",         1_269,  4.8),
#             AsvFeature("ASV_007", "g__Lachnospiraceae",     952,  3.6),
#             AsvFeature("ASV_008", "g__Akkermansia",          769,  2.9),
#         ]
#         return rows

#     # ── Diversity ─────────────────────────────────────────────────────────────

#     def get_alpha_diversity(self, runs: list[RunInfo]) -> list[DiversityMetrics]:
#         """Return Shannon / Simpson alpha-diversity metrics per run."""
#         # TODO: real call — compute from QIIME2 alpha-diversity artifact
#         mock = {
#             "R1": DiversityMetrics("R1", 3.42, 0.87, (2.8, 3.1, 3.4, 3.7, 4.1),
#                                                       (0.78, 0.83, 0.87, 0.91, 0.95)),
#             "R2": DiversityMetrics("R2", 3.71, 0.91, (3.1, 3.4, 3.7, 4.0, 4.4),
#                                                       (0.84, 0.88, 0.91, 0.94, 0.97)),
#             "R3": DiversityMetrics("R3", 3.18, 0.82, (2.5, 2.9, 3.2, 3.5, 3.8),
#                                                       (0.72, 0.78, 0.82, 0.86, 0.90)),
#             "R4": DiversityMetrics("R4", 3.55, 0.89, (2.9, 3.2, 3.5, 3.8, 4.2),
#                                                       (0.81, 0.85, 0.89, 0.92, 0.96)),
#         }
#         return [mock[r.label] for r in runs if r.label in mock]

#     def get_beta_diversity(self, runs: list[RunInfo]) -> BetaDiversityMatrix:
#         """Return Bray-Curtis pairwise dissimilarity matrix."""
#         # TODO: real call — compute from QIIME2 beta-diversity artifact
#         labels = [r.label for r in runs]
#         n = len(labels)
#         # Symmetric matrix: diagonal = 0, off-diagonal = mock dissimilarity
#         mock_values = [
#             [0.00, 0.18, 0.64, 0.71],
#             [0.18, 0.00, 0.60, 0.67],
#             [0.64, 0.60, 0.00, 0.22],
#             [0.71, 0.67, 0.22, 0.00],
#         ]
#         values = [mock_values[i][:n] for i in range(n)]
#         return BetaDiversityMatrix(run_labels=labels, values=values)

#     # ── Alzheimer risk ────────────────────────────────────────────────────────

#     def predict_alzheimer_risk(self, run_label: str) -> AlzheimerRiskResult:
#         """
#         Estimate Alzheimer's disease risk from gut microbiome composition.

#         The model is based on published gut-brain axis literature:
#         low butyrate producers, low Akkermansia, and high Proteobacteria
#         are associated with neuroinflammation and AD risk.

#         TODO: replace with a trained classifier (e.g. scikit-learn or ONNX).
#         """
#         biomarkers = [
#             Biomarker(
#                 name="Faecalibacterium prausnitzii",
#                 observed_value=2.1, unit="%",
#                 normal_range=">8%",
#                 description="Anti-inflammatory; butyrate producer",
#                 is_depleted=True,
#             ),
#             Biomarker(
#                 name="Akkermansia muciniphila",
#                 observed_value=0.3, unit="%",
#                 normal_range=">1%",
#                 description="Gut barrier integrity; neuroprotective",
#                 is_depleted=True,
#             ),
#             Biomarker(
#                 name="Proteobacteria (phylum)",
#                 observed_value=24.0, unit="%",
#                 normal_range="<5%",
#                 description="Pro-inflammatory; dysbiosis marker",
#                 is_elevated=True,
#             ),
#             Biomarker(
#                 name="Butyrate producers",
#                 observed_value=8.4, unit="%",
#                 normal_range=">20%",
#                 description="Neuroprotective short-chain fatty acids",
#                 is_depleted=True,
#             ),
#             Biomarker(
#                 name="Bacteroides / Firmicutes ratio",
#                 observed_value=3.2, unit="×",
#                 normal_range="~1×",
#                 description="Gut dysbiosis marker",
#                 is_elevated=True,
#             ),
#             Biomarker(
#                 name="Lactobacillus spp.",
#                 observed_value=4.8, unit="%",
#                 normal_range="2–6%",
#                 description="Beneficial probiotic genus",
#             ),
#         ]

#         # Simple weighted score: each depleted/elevated marker adds weight
#         risk_pct = self._compute_risk_score(biomarkers)

#         if risk_pct < 30:
#             level = RiskLevel.LOW
#         elif risk_pct < 50:
#             level = RiskLevel.MODERATE
#         elif risk_pct < 70:
#             level = RiskLevel.ELEVATED
#         else:
#             level = RiskLevel.HIGH

#         return AlzheimerRiskResult(
#             predicted_risk_pct=risk_pct,
#             confidence_pct=81.0,
#             risk_level=level,
#             biomarkers=biomarkers,
#         )

#     @staticmethod
#     def _compute_risk_score(biomarkers: list[Biomarker]) -> float:
#         """
#         Naïve linear risk score.
#         Each abnormal biomarker contributes a fixed weight.
#         Replace with a trained model for production use.
#         """
#         weights = {"depleted": 15.0, "elevated": 12.0, "normal": 0.0}
#         base_score = 10.0   # baseline population risk
#         score = base_score + sum(weights[b.status] for b in biomarkers)
#         return min(score, 100.0)