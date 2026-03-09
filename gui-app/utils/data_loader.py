"""
gui-app/utils/data_loader.py
─────────────────────────────
PURPOSE
───────
Parse a user-uploaded microbiome file into the taxa dict format that
assessment_service expects:  dict[str, float]  with values summing to 1.0.

This module is PARSE-ONLY.  It has NO imports from src.services or src.db.
Calling the service layer is the job of the UI (dashboard_page.py), not the
loader.  Keeping them separate means:
  • data_loader can be unit-tested without a database.
  • The GUI can show parse errors before any DB call is attempted.

SUPPORTED INPUT LAYOUTS
───────────────────────
1. Two-column CSV / TSV   (taxon name | abundance)
       Firmicutes,3500
       Bacteroidetes,4000
   Counts are normalised to proportions automatically.

2. Wide CSV / TSV  (header row = taxon names, data row(s) = abundances)
       Firmicutes,Bacteroidetes,Actinobacteria
       3500,4000,500

3. JSON  –  {"Firmicutes": 0.35, "Bacteroidetes": 0.40, ...}
   Already-proportions or raw counts — both are normalised.

PUBLIC API
──────────
  from utils.data_loader import load_file

  result = load_file("uploads/sample.tsv")
  # result["taxa"]    → dict[str, float]  proportions summing to 1.0  ← pass to service
  # result["summary"] → str               human-readable stats for UI text box
  # result["error"]   → str | None        non-None means parsing failed
  # result["name"]    → str               basename of the file
  # result["size_kb"] → float

HOW THE GUI USES THIS
─────────────────────
  # 1. Parse the file (no DB touch)
  result = load_file(path)
  if result["error"]:
      show_error(result["summary"])
      return

  # 2. Store in DB via service (called from dashboard_page.py, NOT here)
  from src.services.assessment_service import store_microbiome_upload
  mb = store_microbiome_upload(
      project_id=app.current_project_id,
      file_path=path,
      taxa=result["taxa"],          # ← the dict[str, float] this module produces
  )
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path


# ── Public entry point ────────────────────────────────────────────────────────

def load_file(path: str) -> dict:
    """
    Parse *path* and return a result dict.  Never raises — errors are
    captured in result["error"] so the GUI can display them gracefully.

    Return shape:
      {
        "taxa":    dict[str, float],  # proportions, sum == 1.0
        "summary": str,               # multi-line text for the Uploaded Data panel
        "error":   str | None,        # non-None → parsing failed; taxa will be {}
        "name":    str,               # os.path.basename(path)
        "size_kb": float,
      }
    """
    p = Path(path)
    result: dict = {
        "taxa":    {},
        "summary": "",
        "error":   None,
        "name":    p.name,
        "size_kb": round(os.path.getsize(path) / 1024, 1) if p.exists() else 0.0,
    }

    try:
        suffix = p.suffix.lower()

        if suffix == ".json":
            raw = _parse_json(p)
        elif suffix in (".csv", ".tsv", ".txt"):
            sep = "\t" if suffix == ".tsv" else ","
            raw = _parse_delimited(p, sep)
        else:
            # Unknown extension — try comma-separated then tab-separated
            try:
                raw = _parse_delimited(p, ",")
            except Exception:
                raw = _parse_delimited(p, "\t")

        taxa = _normalise(raw)
        result["taxa"]    = taxa
        result["summary"] = _build_summary(taxa, result["name"], result["size_kb"])

    except Exception as exc:
        result["error"]   = str(exc)
        result["summary"] = f"⚠  Failed to parse {p.name}:\n{exc}"

    return result


# ── Format parsers  (all return dict[str, float] of raw values) ──────────────

def _parse_json(path: Path) -> dict[str, float]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(
            "JSON file must be a top-level object mapping taxon names to "
            "abundances, e.g. {\"Firmicutes\": 0.35, \"Bacteroidetes\": 0.40}"
        )
    return {str(k): float(v) for k, v in data.items()}


def _parse_delimited(path: Path, sep: str) -> dict[str, float]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=sep)
        rows = [r for r in reader if any(cell.strip() for cell in r)]

    if not rows:
        raise ValueError("File appears to be empty.")

    # ── Layout 1: two-column  (taxon_name, abundance) ────────────────────────
    # Heuristic: exactly 2 columns AND first cell of first row is not a number.
    if len(rows[0]) == 2 and not _is_number(rows[0][0]):
        parsed: dict[str, float] = {}
        # Common header names to skip
        SKIP = {"taxon", "taxa", "name", "genus", "species", "organism", "feature"}
        for row in rows:
            if len(row) < 2:
                continue
            taxon, val = row[0].strip(), row[1].strip()
            if taxon.lower() in SKIP:
                continue
            if _is_number(val):
                parsed[taxon] = float(val)
        if not parsed:
            raise ValueError(
                "Two-column file contained no numeric abundance values.\n"
                "Expected format:  taxon_name,abundance_count"
            )
        return parsed

    # ── Layout 2: wide format  (header = taxon names, rows = samples) ────────
    header    = [c.strip() for c in rows[0]]
    data_rows = rows[1:]
    if not data_rows:
        raise ValueError(
            "Wide-format file has a header row but no data rows.\n"
            "Expected at least one sample row beneath the taxon-name header."
        )

    # Sum abundances across all sample rows so multi-sample files collapse to one profile.
    totals: dict[str, float] = {}
    for row in data_rows:
        for col, cell in zip(header, row):
            cell = cell.strip()
            if _is_number(cell):
                totals[col] = totals.get(col, 0.0) + float(cell)

    if not totals:
        raise ValueError(
            "Wide-format file contained no numeric abundance values.\n"
            "Check that data rows contain numbers, not strings."
        )
    return totals


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _normalise(raw: dict[str, float]) -> dict[str, float]:
    """
    Convert raw counts or proportions → proportions that sum to 1.0.

    • Drops taxa with zero or negative abundance.
    • Raises ValueError if nothing survives (all-zero file).
    • If values already sum to 1.0 (±0.01) they are kept as-is after
      rounding — no double-normalisation distortion.
    """
    positive = {k: v for k, v in raw.items() if v > 0}
    if not positive:
        raise ValueError(
            "All taxa have zero or negative abundance — nothing to normalise."
        )
    total = sum(positive.values())
    return {k: round(v / total, 8) for k, v in positive.items()}


def _build_summary(taxa: dict[str, float], name: str, size_kb: float) -> str:
    """
    Build the multi-line summary string shown in the 'Uploaded Data' panel.
    Includes file metadata, taxon count, Shannon index, and top-5 taxa.
    """
    if not taxa:
        return f"File: {name}  ({size_kb} KB)\nNo taxa loaded."

    sorted_taxa = sorted(taxa.items(), key=lambda x: x[1], reverse=True)
    top5    = sorted_taxa[:5]
    top_str = "\n".join(f"  {t}: {p * 100:.2f}%" for t, p in top5)
    more    = f"\n  … and {len(taxa) - 5} more" if len(taxa) > 5 else ""

    shannon = -sum(p * math.log(p) for p in taxa.values() if p > 0)

    return (
        f"File:            {name}  ({size_kb} KB)\n"
        f"Taxa detected:   {len(taxa)}\n"
        f"Shannon index:   {shannon:.4f}\n\n"
        f"Top taxa by abundance:\n{top_str}{more}"
    )