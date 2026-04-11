"""
src/pipeline/db_import.py

Parsers for QIIME2 TSV/FASTA output files.
Called by pipeline.py after qiime_preprocess() completes.

Functions
---------
parse_genus_table(genus)
    Parse genus-level collapsed feature table TSV.
    Returns {sample_id: [(genus_name, relative_abundance_pct), ...]}

parse_feat_tax_seqs(tax, seqs)
    Parse taxonomy.tsv + dna-sequences.fasta.
    Returns [{"feature_id", "sequence", "taxonomy"}]

parse_feature_counts(feat)
    Parse raw ASV feature table TSV.
    Returns {feature_id: total_count_across_all_samples}
"""
from __future__ import annotations

import csv
from pathlib import Path


# ── Genus table ───────────────────────────────────────────────────────────────

def parse_genus_table(genus: str) -> dict[str, list[tuple[str, float]]]:
    """
    Parse a QIIME2 genus-level collapsed feature table (TSV).

    Expected format (exported via `qiime tools export` then `biom convert`):
        # Constructed from biom file
        #OTU ID    SRR123    SRR456
        g__Bacteroides    1200.0    3400.0
        g__Prevotella     800.0     200.0

    Returns
    -------
    dict mapping sample_id → [(genus_name, relative_abundance_pct), ...]
    relative abundance is normalised so each sample sums to 100.
    """
    path = Path(genus)
    if not path.exists():
        return {}

    with open(path, newline="") as fh:
        raw = fh.readlines()

    # QIIME2 biom-export format:
    #   "# Constructed from biom file"  — pure comment, skip
    #   "#OTU ID\tSample1\tSample2"     — header row, strip leading '#'
    #   data rows (no leading '#')
    lines = []
    for ln in raw:
        if ln.startswith("# ") or ln.strip() == "#":
            continue           # pure comment line
        if ln.startswith("#"):
            ln = ln[1:]        # strip '#' from header row (e.g. "#OTU ID")
        lines.append(ln)

    if not lines:
        return {}

    reader   = csv.reader(lines, delimiter="\t")
    header   = next(reader)          # ['OTU ID' / 'feature-id', SRR1, SRR2, ...]
    samples  = header[1:]
    raw: dict[str, dict[str, float]] = {s: {} for s in samples}

    for row in reader:
        if not row or not row[0].strip():
            continue
        # Genus label may be full taxonomy string — take last segment
        raw_genus = row[0].strip().split(";")[-1].strip()
        # Strip QIIME2 prefix (g__, d__, etc.)
        genus_name = raw_genus.split("__")[-1].strip() or raw_genus
        if not genus_name or genus_name.lower() in ("unassigned", ""):
            genus_name = "Unclassified"

        for i, sample in enumerate(samples):
            try:
                val = float(row[i + 1]) if i + 1 < len(row) else 0.0
            except ValueError:
                val = 0.0
            if val > 0:
                raw[sample][genus_name] = raw[sample].get(genus_name, 0.0) + val

    result: dict[str, list[tuple[str, float]]] = {}
    for sample, counts in raw.items():
        total = sum(counts.values()) or 1.0
        result[sample] = [
            (g, round(v / total * 100, 4))
            for g, v in sorted(counts.items(), key=lambda x: -x[1])
        ]
    return result


# ── Feature table (raw ASV counts) ───────────────────────────────────────────

def parse_feature_counts(feat: str) -> dict[str, int]:
    """
    Parse a QIIME2 ASV-level feature table TSV (raw counts).

    Expected format:
        # Constructed from biom file
        #OTU ID    SRR123    SRR456
        ASV_001    234       567
        ASV_002    89        12

    Returns
    -------
    {feature_id: total_count_summed_across_all_samples}
    """
    path = Path(feat)
    if not path.exists():
        return {}

    with open(path, newline="") as fh:
        raw = fh.readlines()

    lines = []
    for ln in raw:
        if ln.startswith("# ") or ln.strip() == "#":
            continue
        if ln.startswith("#"):
            ln = ln[1:]
        lines.append(ln)

    if not lines:
        return {}

    reader = csv.reader(lines, delimiter="\t")
    header = next(reader)   # skip header row
    counts: dict[str, int] = {}

    for row in reader:
        if not row or not row[0].strip():
            continue
        feature_id = row[0].strip()
        try:
            total = sum(int(float(v)) for v in row[1:] if v.strip())
        except ValueError:
            total = 0
        counts[feature_id] = total

    return counts


# ── Taxonomy + representative sequences ───────────────────────────────────────

def parse_feat_tax_seqs(tax: str, seqs: str) -> list[dict]:
    """
    Combine QIIME2 taxonomy.tsv and dna-sequences.fasta into one list.

    taxonomy.tsv format:
        Feature ID    Taxon    Confidence
        ASV_001    d__Bacteria; p__Firmicutes; ...; g__Roseburia    0.99

    dna-sequences.fasta format:
        >ASV_001
        GTTTGATAAGTTAGAGGTGAAATCCCG...

    Returns
    -------
    [{"feature_id": str, "sequence": str, "taxonomy": str}, ...]
    """
    # ── Parse taxonomy ────────────────────────────────────────────────────────
    taxonomies: dict[str, str] = {}
    tax_path = Path(tax)
    if tax_path.exists():
        with open(tax_path, newline="") as fh:
            reader = csv.reader(fh, delimiter="\t")
            for row in reader:
                if not row or row[0].startswith("#") or row[0].lower().startswith("feature"):
                    continue
                if len(row) >= 2:
                    taxonomies[row[0].strip()] = row[1].strip()

    # ── Parse FASTA sequences ─────────────────────────────────────────────────
    sequences: dict[str, str] = {}
    seqs_path = Path(seqs)
    if seqs_path.exists():
        current_id:  str | None     = None
        current_seq: list[str]      = []
        with open(seqs_path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(">"):
                    if current_id is not None:
                        sequences[current_id] = "".join(current_seq)
                    current_id  = line[1:].split()[0]   # take id before any description
                    current_seq = []
                elif line:
                    current_seq.append(line)
        if current_id is not None:
            sequences[current_id] = "".join(current_seq)

    # ── Merge ─────────────────────────────────────────────────────────────────
    all_ids = set(taxonomies) | set(sequences)
    return [
        {
            "feature_id": fid,
            "sequence":   sequences.get(fid, ""),
            "taxonomy":   taxonomies.get(fid, ""),
        }
        for fid in sorted(all_ids)
    ]
