"""
utils/data_loader.py
─────────────────────
Utilities for loading microbiome data files (CSV, TSV, JSON).
"""
from __future__ import annotations
import os, json
from pathlib import Path


def load_file(path: str) -> dict:
    """
    Load a microbiome data file and return a dict with:
      - raw_data   : list[dict] or dict
      - summary    : human-readable summary string
      - taxa       : list of taxon names (if available)

    Supported formats: CSV, TSV, JSON.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in (".csv", ".tsv"):
        return _load_delimited(path, "\t" if suffix == ".tsv" else ",")
    elif suffix == ".json":
        return _load_json(path)
    else:
        # Try CSV as a fallback
        try:
            return _load_delimited(path, ",")
        except Exception:
            return {
                "raw_data": {},
                "summary": f"Unsupported file type: {suffix}",
                "taxa": [],
            }


def _load_delimited(path: Path, sep: str) -> dict:
    import csv
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=sep)
        for row in reader:
            rows.append(row)

    taxa = list(rows[0].keys()) if rows else []
    summary = (
        f"Rows: {len(rows)}\n"
        f"Columns: {len(taxa)}\n"
        f"Columns: {', '.join(taxa[:6])}{'...' if len(taxa) > 6 else ''}"
    )
    return {"raw_data": rows, "summary": summary, "taxa": taxa}


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    taxa = list(data.keys()) if isinstance(data, dict) else []
    summary = f"Keys: {len(taxa)}\nTop keys: {', '.join(taxa[:6])}"
    return {"raw_data": data, "summary": summary, "taxa": taxa}
