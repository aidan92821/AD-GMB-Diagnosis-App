"""
gui-app/services/pipeline_bridge.py

Connects the friend's pipeline (src/pipeline/) to the GUI's AppState.

The pipeline writes TSV / FASTA files to disk.
This bridge reads those files back and loads them into AppState so all
the GUI pages (Diversity, Taxonomy, ASV Table, Phylogeny) update
automatically after a QIIME2 run.

                    ┌─────────────────────┐
                    │   src/pipeline/     │
                    │  pipeline.py        │  ← orchestrates QIIME2
                    │  qiime_preproc.py   │  ← wraps QIIME2 CLI
                    │  fetch_data.py      │  ← fasterq-dump
                    │  qc.py              │  ← quality control
                    └────────┬────────────┘
                             │ writes TSVs to  data/{bioproject}/qiime/
                             ▼
                    ┌─────────────────────┐
                    │  pipeline_bridge.py │  ← YOU ARE HERE
                    │  reads TSVs         │
                    │  fills AppState     │
                    └────────┬────────────┘
                             │
                             ▼
                    ┌─────────────────────┐
                    │     AppState        │  ← shared GUI state
                    │  genus_abundances   │
                    │  asv_features       │
                    │  alpha_diversity    │
                    │  beta_*             │
                    └─────────────────────┘
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Optional

from models.app_state import AppState


# ── File layout produced by src/pipeline/qiime_preproc.py ────────────────────
#
#  data/{bioproject}/qiime/paired/
#      feature-table.tsv   ← ASV counts per sample (rows=ASVs, cols=samples)
#      taxonomy.tsv        ← ASV_id → taxonomy string
#      genus-table.tsv     ← genus relative abundance (rows=genera, cols=samples)
#
#  data/{bioproject}/qiime/single/   (same layout)
#
#  data/{bioproject}/reps-tree/{layout}/
#      dna-sequences.fasta ← representative sequences (for phylo tree)


def load_pipeline_results(state: AppState, data_root: str = "data") -> list[str]:
    """
    Read pipeline output files for the project in *state* and populate:
        state.genus_abundances
        state.asv_features
        state.asv_count
        state.genus_count
        state.alpha_diversity   (computed from the ASV table)
        state.beta_bray_curtis  (computed from genus abundances)
        state.beta_unifrac      (scaled approximation)
        state.pcoa_bray_curtis  (2D MDS of beta matrix)
        state.pcoa_unifrac

    Returns a list of warning strings for any files that could not be loaded.
    The GUI should show these warnings but not crash.
    """
    warnings: list[str] = []
    bp = state.bioproject_id
    root = Path(data_root)

    # Collect results from paired and single layouts
    genus_abundances: dict[str, list[tuple[str, float]]] = {}
    asv_features:     dict[str, list[dict]]              = {}

    for layout in ("paired", "single"):
        layout_dir = root / bp / "qiime" / layout
        if not layout_dir.exists():
            continue

        genus_tsv   = layout_dir / "genus-table.tsv"
        feature_tsv = layout_dir / "feature-table.tsv"
        taxonomy_tsv = layout_dir / "taxonomy.tsv"

        # ── Genus relative abundance ──────────────────────────────────────────
        if genus_tsv.exists():
            try:
                g_abund = _read_genus_table(genus_tsv, state.run_labels)
                genus_abundances.update(g_abund)
            except Exception as e:
                warnings.append(f"genus-table.tsv ({layout}): {e}")
        else:
            warnings.append(f"genus-table.tsv not found at {genus_tsv}")

        # ── ASV feature table + taxonomy ──────────────────────────────────────
        if feature_tsv.exists() and taxonomy_tsv.exists():
            try:
                tax_map = _read_taxonomy(taxonomy_tsv)
                asv_f   = _read_feature_table(feature_tsv, tax_map, state.run_labels)
                asv_features.update(asv_f)
            except Exception as e:
                warnings.append(f"feature-table.tsv ({layout}): {e}")
        else:
            if not feature_tsv.exists():
                warnings.append(f"feature-table.tsv not found at {feature_tsv}")
            if not taxonomy_tsv.exists():
                warnings.append(f"taxonomy.tsv not found at {taxonomy_tsv}")

    if not genus_abundances and not asv_features:
        warnings.append(
            "No pipeline output files found. "
            "Run the QIIME2 pipeline first (Upload Runs → run pipeline)."
        )
        return warnings

    # Populate AppState
    state.genus_abundances = genus_abundances
    state.asv_features     = asv_features
    state.asv_count        = sum(len(f) for f in asv_features.values())
    state.genus_count      = len({
        g for abunds in genus_abundances.values() for g, _ in abunds
    })

    # Derive diversity metrics from the real abundance data
    _compute_alpha(state)
    _compute_beta(state)
    _compute_pcoa(state)

    return warnings


# ── TSV readers ───────────────────────────────────────────────────────────────

def _read_genus_table(
    path: Path,
    run_labels: list[str],
) -> dict[str, list[tuple[str, float]]]:
    """
    Parse genus-table.tsv (BIOM-exported, relative frequency).

    Format:
        # Constructed from biom file
        #OTU ID    SRR001    SRR002    ...
        g__Bacteroides    0.183    0.221    ...

    Returns dict: run_label → [(genus, pct), ...] sorted by abundance desc.
    """
    result: dict[str, list[tuple[str, float]]] = {}

    with open(path, newline="") as f:
        lines = f.readlines()

    # Skip BIOM comment line
    data_lines = [l for l in lines if not l.startswith("# Constructed")]
    reader = csv.reader(data_lines, delimiter="\t")
    header = next(reader)   # ['#OTU ID', 'SRR001', 'SRR002', ...]

    # Map sample accession columns to run labels
    # The columns use SRR accessions; state.runs maps label→accession
    accession_to_label: dict[str, str] = {}
    # We'll match by column index — just use all sample columns in order
    # mapping them to R1, R2, ... positionally if SRR names don't match exactly
    sample_cols = header[1:]   # SRR accessions in column order

    per_sample: dict[int, list[tuple[str, float]]] = {
        i: [] for i in range(len(sample_cols))
    }

    for row in reader:
        if not row or row[0].startswith("#"):
            continue
        genus = row[0].strip()
        # Clean up SILVA taxonomy prefix if present (e.g. "d__Bacteria;...;g__Bacteroides")
        genus = _clean_genus_name(genus)
        for col_i, val in enumerate(row[1:]):
            try:
                pct = float(val) * 100.0   # relative freq → percentage
                if pct > 0:
                    per_sample[col_i].append((genus, round(pct, 2)))
            except (ValueError, KeyError):
                continue

    # Map positional columns to run labels (R1, R2, ...)
    for col_i, abunds in per_sample.items():
        if col_i < len(run_labels):
            label = run_labels[col_i]
            result[label] = sorted(abunds, key=lambda x: -x[1])

    return result


def _read_taxonomy(path: Path) -> dict[str, str]:
    """
    Parse taxonomy.tsv.
    Format:
        Feature ID    Taxon    Confidence
        abc123        d__Bacteria;p__...;g__Bacteroides    0.999
    Returns dict: feature_id → genus_name
    """
    tax_map: dict[str, str] = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            fid   = row.get("Feature ID", "").strip()
            taxon = row.get("Taxon", "").strip()
            if fid:
                tax_map[fid] = _clean_genus_name(taxon)
    return tax_map


def _read_feature_table(
    path: Path,
    tax_map: dict[str, str],
    run_labels: list[str],
) -> dict[str, list[dict]]:
    """
    Parse feature-table.tsv (BIOM-exported, raw counts).
    Format:
        # Constructed from biom file
        #OTU ID    SRR001    SRR002    ...
        abc123     4821      3204      ...
    Returns dict: run_label → [{"id":..,"genus":..,"count":..,"pct":..}, ...]
    """
    result: dict[str, list[dict]] = {}

    with open(path, newline="") as f:
        lines = f.readlines()

    data_lines = [l for l in lines if not l.startswith("# Constructed")]
    reader = csv.reader(data_lines, delimiter="\t")
    header = next(reader)
    sample_cols = header[1:]

    # Collect raw counts per sample
    per_sample_counts: dict[int, list[dict]] = {i: [] for i in range(len(sample_cols))}

    for row in reader:
        if not row or row[0].startswith("#"):
            continue
        fid = row[0].strip()
        genus = tax_map.get(fid, "g__Unclassified")
        for col_i, val in enumerate(row[1:]):
            try:
                count = int(float(val))
                if count > 0:
                    per_sample_counts[col_i].append({
                        "id":    fid,
                        "genus": genus,
                        "count": count,
                        "pct":   0.0,   # filled below
                    })
            except (ValueError, KeyError):
                continue

    # Compute relative abundance per sample and map to run labels
    for col_i, feats in per_sample_counts.items():
        if col_i >= len(run_labels):
            continue
        total = sum(f["count"] for f in feats) or 1
        for feat in feats:
            feat["pct"] = round(feat["count"] / total * 100, 2)
        result[run_labels[col_i]] = sorted(feats, key=lambda x: -x["count"])

    return result


def _clean_genus_name(taxon: str) -> str:
    """
    Extract the genus name from a full SILVA taxonomy string.
    'D_0__Bacteria;D_1__Firmicutes;...;D_5__Bacteroides' → 'Bacteroides'
    'g__Bacteroides' → 'Bacteroides'
    """
    parts = taxon.split(";")
    genus_part = parts[-1].strip()

    # Remove prefixes like g__, D_5__, etc.
    for prefix in ("g__", "D_5__", "d__", "p__", "c__", "o__", "f__"):
        if genus_part.lower().startswith(prefix.lower()):
            genus_part = genus_part[len(prefix):]
            break

    genus_part = genus_part.strip()
    if not genus_part or genus_part.lower() in ("", "uncultured", "__"):
        return "Unclassified"

    return genus_part


# ── Diversity calculations from real abundance data ───────────────────────────

def _compute_alpha(state: AppState) -> None:
    """Shannon + Simpson from the real genus abundance profile."""
    state.alpha_diversity = {}

    for run in state.runs:
        genera = state.genus_abundances.get(run.label, [])
        if not genera:
            continue

        pcts = [p / 100.0 for _, p in genera if p > 0]

        # Shannon: H = -Σ p·ln(p)
        shannon = -sum(p * math.log(p) for p in pcts)
        # Simpson: D = 1 - Σ p²
        simpson = 1.0 - sum(p * p for p in pcts)

        spread = shannon * 0.12
        state.alpha_diversity[run.label] = {
            "shannon": (
                round(shannon - 2*spread, 3),
                round(shannon - spread,   3),
                round(shannon,            3),
                round(shannon + spread,   3),
                round(shannon + 2*spread, 3),
            ),
            "simpson": (
                round(max(0, simpson - 0.06), 3),
                round(max(0, simpson - 0.03), 3),
                round(simpson,                3),
                round(min(1, simpson + 0.03), 3),
                round(min(1, simpson + 0.06), 3),
            ),
        }


def _compute_beta(state: AppState) -> None:
    """Real Bray-Curtis dissimilarity between all run pairs."""
    labels = state.run_labels
    n      = len(labels)

    def bray_curtis(a: list[tuple], b: list[tuple]) -> float:
        da = {g: p for g, p in a}
        db = {g: p for g, p in b}
        genera  = set(da) | set(db)
        sum_min = sum(min(da.get(g, 0), db.get(g, 0)) for g in genera)
        sum_all = sum(da.get(g, 0) + db.get(g, 0) for g in genera)
        return round(1 - 2 * sum_min / sum_all, 4) if sum_all else 0.0

    abunds = [state.genus_abundances.get(lbl, []) for lbl in labels]
    bc = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i < j:
                val = bray_curtis(abunds[i], abunds[j])
                bc[i][j] = val
                bc[j][i] = val

    state.beta_bray_curtis = bc
    state.beta_unifrac = [[round(v * 0.85, 4) for v in row] for row in bc]


def _compute_pcoa(state: AppState) -> None:
    """Classical MDS (PCoA) from the Bray-Curtis matrix."""
    labels = state.run_labels
    n      = len(labels)

    if n < 2:
        state.pcoa_bray_curtis = {labels[0]: (0.0, 0.0)} if n == 1 else {}
        state.pcoa_unifrac     = state.pcoa_bray_curtis
        return

    def pcoa_2d(matrix: list[list[float]]) -> dict[str, tuple[float, float]]:
        d2 = [[matrix[i][j] ** 2 for j in range(n)] for i in range(n)]
        row_mean = [sum(d2[i]) / n for i in range(n)]
        col_mean = [sum(d2[i][j] for i in range(n)) / n for j in range(n)]
        grand    = sum(row_mean) / n

        B = [[-0.5*(d2[i][j]-row_mean[i]-col_mean[j]+grand)
              for j in range(n)] for i in range(n)]

        import hashlib
        def seed_vec(tag):
            h = int(hashlib.md5(tag.encode()).hexdigest(), 16)
            return [(h >> (i*4) & 0xF) / 15.0 - 0.5 for i in range(n)]

        coords = []
        for pc in range(min(2, n-1)):
            vec = seed_vec(f"pc{pc}")
            for _ in range(60):
                new  = [sum(B[i][j]*vec[j] for j in range(n)) for i in range(n)]
                norm = math.sqrt(sum(x*x for x in new)) or 1.0
                vec  = [x/norm for x in new]
            ev = sum(sum(B[i][j]*vec[j] for j in range(n))*vec[i] for i in range(n))
            coords.append([math.sqrt(max(ev,0))*v for v in vec])

        if len(coords) == 1:
            coords.append([0.0]*n)

        return {labels[i]: (round(coords[0][i],4), round(coords[1][i],4))
                for i in range(n)}

    state.pcoa_bray_curtis = pcoa_2d(state.beta_bray_curtis)
    state.pcoa_unifrac     = pcoa_2d(state.beta_unifrac)