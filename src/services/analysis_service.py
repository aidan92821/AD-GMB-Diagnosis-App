"""
gui-app/services/analysis_service.py

Computes diversity metrics and taxonomy from fetched NCBI data.

For a real pipeline, these methods would:
  1. Download FASTQ via SRA-toolkit
  2. Run DADA2/QIIME2 denoising
  3. Classify against SILVA/Greengenes database
  4. Output ASV table, taxonomy, phylogenetic tree

For now, they derive realistic-looking metrics directly from the
SRA run metadata (read counts, library layout, etc.) so every
fetched project gets unique, plausible values rather than
identical example data.
"""

from __future__ import annotations

import math
import hashlib
from typing import Optional

from models.app_state import AppState, RunState


# Top 15 human gut genera used for simulated taxonomy
_GUT_GENERA = [
    "Bacteroides", "Prevotella", "Faecalibacterium", "Ruminococcus",
    "Blautia", "Roseburia", "Lachnospiraceae", "Akkermansia",
    "Bifidobacterium", "Lactobacillus", "Clostridium", "Eubacterium",
    "Coprococcus", "Dorea", "Subdoligranulum",
]


def _seed(text: str) -> float:
    """Deterministic pseudo-random float in [0,1] from a string seed."""
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return (h % 10_000) / 10_000.0


def compute_analysis(state: AppState) -> None:
    """
    Populate *state* with diversity metrics and taxonomy estimates
    derived from the run metadata already in *state*.

    This modifies *state* in-place.  Call this after a successful fetch
    and before displaying Diversity / Taxonomy / ASV Table pages.

    In production: replace each section with real QIIME2 API calls.
    """
    if not state.runs:
        return

    _compute_taxonomy(state)
    _compute_alpha_diversity(state)
    _compute_beta_diversity(state)
    _compute_pcoa(state)
    _compute_asv_features(state)
    _compute_phylo_tree(state)

    # Update aggregate counts
    if state.genus_abundances:
        first_run = state.run_labels[0]
        state.genus_count = len(state.genus_abundances[first_run])
        state.asv_count   = sum(
            len(feats) for feats in state.asv_features.values()
        )


def _compute_taxonomy(state: AppState) -> None:
    """
    Derive genus relative abundances for each run.
    Uses the run accession as a seed so each run gets unique but
    reproducible abundances.
    """
    state.genus_abundances = {}

    for run in state.runs.values():
        seed_base = run['run_accession']

        # Generate raw weights seeded by accession
        weights = []
        for i, genus in enumerate(_GUT_GENERA):
            s = _seed(f"{seed_base}_{genus}_{i}")
            # Exponential distribution to mimic realistic microbiome dominance
            w = math.exp(-3.0 * s)
            weights.append(w)

        total = sum(weights)
        pcts  = [round(w / total * 100, 2) for w in weights]

        # Sort descending by abundance
        paired = sorted(zip(_GUT_GENERA, pcts), key=lambda x: -x[1])
        state.genus_abundances[run['label']] = paired

    state.genus_count = len(_GUT_GENERA)


def _compute_alpha_diversity(state: AppState) -> None:
    """
    Estimate Shannon and Simpson diversity indices from abundance profile.
    These are the real diversity formulas applied to the simulated abundances.
    """
    state.alpha_diversity = {}

    for run in state.runs.values():
        genera = state.genus_abundances.get(run['label'], [])
        if not genera:
            continue

        pcts = [p / 100.0 for _, p in genera]
        pcts = [p for p in pcts if p > 0]

        # Shannon entropy: H = -Σ(p * ln(p))
        shannon = -sum(p * math.log(p) for p in pcts)

        # Simpson index: D = 1 - Σ(p²)
        simpson = 1.0 - sum(p * p for p in pcts)

        # Create plausible box-plot whiskers around the point estimate
        # (in reality these come from rarefaction curves across samples)
        s_spread = shannon * 0.12
        state.alpha_diversity[run['label']] = {
            "shannon": (
                round(shannon - 2 * s_spread, 3),
                round(shannon - s_spread,     3),
                round(shannon,                3),
                round(shannon + s_spread,     3),
                round(shannon + 2 * s_spread, 3),
            ),
            "simpson": (
                round(simpson - 0.08, 3),
                round(simpson - 0.04, 3),
                round(simpson,        3),
                round(simpson + 0.04, 3),
                round(simpson + 0.08, 3),
            ),
        }


def _compute_beta_diversity(state: AppState) -> None:
    """
    Compute Bray-Curtis dissimilarity between all pairs of runs.
    Real formula: BC(i,j) = 1 - 2*Σmin(p_i, p_j) / (Σp_i + Σp_j)
    """
    labels = state.run_labels
    n      = len(labels)

    def bray_curtis(a: list[tuple], b: list[tuple]) -> float:
        a_dict = {g: p for g, p in a}
        b_dict = {g: p for g, p in b}
        genera  = set(a_dict) | set(b_dict)
        sum_min = sum(min(a_dict.get(g, 0), b_dict.get(g, 0)) for g in genera)
        sum_all = sum(a_dict.get(g, 0) + b_dict.get(g, 0) for g in genera)
        return round(1 - 2 * sum_min / sum_all, 4) if sum_all else 0.0

    # Build n×n matrix
    abunds = [state.genus_abundances.get(lbl, []) for lbl in labels]
    bc_mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                bc_mat[i][j] = 0.0
            elif i < j:
                val = bray_curtis(abunds[i], abunds[j])
                bc_mat[i][j] = val
                bc_mat[j][i] = val

    state.beta_bray_curtis = bc_mat

    # UniFrac: scale Bray-Curtis by a small phylogenetic factor
    state.beta_unifrac = [
        [round(v * 0.85, 4) for v in row]
        for row in bc_mat
    ]


def _compute_pcoa(state: AppState) -> None:
    """
    Simple 2-D PCoA from the Bray-Curtis matrix using classical MDS.
    For n <= 4 runs we can do this analytically without scipy.
    """
    labels = state.run_labels
    n      = len(labels)

    if n < 2:
        state.pcoa_bray_curtis = {labels[0]: (0.0, 0.0)} if n == 1 else {}
        state.pcoa_unifrac      = state.pcoa_bray_curtis
        return

    def pcoa_2d(matrix: list[list[float]]) -> dict[str, tuple[float, float]]:
        """Classical MDS — double-centering then power iteration for 2 PCs."""
        # Double-centering: B = -0.5 * H * D² * H  where H = I - (1/n)11'
        d2 = [[matrix[i][j] ** 2 for j in range(n)] for i in range(n)]
        row_mean = [sum(d2[i]) / n for i in range(n)]
        col_mean = [sum(d2[i][j] for i in range(n)) / n for j in range(n)]
        grand    = sum(row_mean) / n

        B = [
            [-0.5 * (d2[i][j] - row_mean[i] - col_mean[j] + grand)
             for j in range(n)]
            for i in range(n)
        ]

        # Power iteration for first 2 eigenvectors
        coords = []
        for pc in range(min(2, n - 1)):
            vec = [_seed(f"pc{pc}_{i}") - 0.5 for i in range(n)]
            for _ in range(50):
                new = [sum(B[i][j] * vec[j] for j in range(n)) for i in range(n)]
                norm = math.sqrt(sum(x * x for x in new)) or 1.0
                vec  = [x / norm for x in new]
            eigenval = sum(sum(B[i][j] * vec[j] for j in range(n)) * vec[i]
                          for i in range(n))
            score = [math.sqrt(max(eigenval, 0)) * v for v in vec]
            coords.append(score)

        if len(coords) == 1:
            coords.append([0.0] * n)

        return {labels[i]: (round(coords[0][i], 4), round(coords[1][i], 4))
                for i in range(n)}

    state.pcoa_bray_curtis = pcoa_2d(state.beta_bray_curtis)
    state.pcoa_unifrac      = pcoa_2d(state.beta_unifrac)


def _compute_asv_features(state: AppState) -> None:
    """Generate a plausible ASV feature table for each run."""
    state.asv_features = {}

    for run in state.runs.values():
        genera = state.genus_abundances.get(run['label'], [])
        total_reads = run.get('read_count') or 10_000
        features = []
        asv_idx  = 1
        srr = run['run_accession']

        for genus, pct in genera:
            # Each genus gets 1-3 ASVs
            n_asvs = 1 + int(_seed(f"{srr}_{genus}_n") * 2)
            remaining_pct = pct
            for k in range(n_asvs):
                if k == n_asvs - 1:
                    asv_pct = remaining_pct
                else:
                    frac    = 0.4 + _seed(f"{srr}_{genus}_{k}") * 0.4
                    asv_pct = round(remaining_pct * frac, 2)
                    remaining_pct -= asv_pct

                count = int(total_reads * asv_pct / 100)
                if count < 1:
                    continue

                features.append({
                    "id":    f"ASV_{asv_idx:04d}",
                    "genus": f"g__{genus}",
                    "count": count,
                    "pct":   round(asv_pct, 2),
                })
                asv_idx += 1

        # Sort by count descending
        features.sort(key=lambda x: -x["count"])
        state.asv_features[run['label']] = features

    state.asv_count = sum(len(f) for f in state.asv_features.values())


def _compute_phylo_tree(state: AppState) -> None:
    """Generate a text phylogenetic tree for display."""
    state.phylo_tree = {}
    for run in state.runs.values():
        genera = [g for g, _ in state.genus_abundances.get(run['label'], [])[:6]]
        if not genera:
            state.phylo_tree[run['label']] = "(no data)"
            continue
        lines = []
        for i, g in enumerate(genera):
            if i == 0:
                lines.append(f"  ┌─── {g}")
                lines.append( "──┤")
            elif i == len(genera) - 1:
                lines.append(f"  └─── {g}")
            else:
                lines.append(f"  ├─── {g}")
        state.phylo_tree[run['label']] = "\n".join(lines)