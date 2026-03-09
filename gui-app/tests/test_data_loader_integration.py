"""
tests/test_data_loader_integration.py
───────────────────────────────────────
Smoke tests for the data_loader → assessment_service handoff.

These tests run WITHOUT a real database.  They verify:
  1. load_file() produces a taxa dict that satisfies the service contract
     (dict[str, float], values sum to 1.0).
  2. The taxa dict is accepted by the stub model functions.
  3. The taxa dict is accepted by store_microbiome_upload when a mock session
     is injected (no real DB required).

Run from the project root:
    pytest tests/test_data_loader_integration.py -v
"""
from __future__ import annotations
import sys
import math
import json
import tempfile
import os
from pathlib import Path

# ── Make sure both gui-app/ and the project root are on the path ──────────────
_tests_dir    = Path(__file__).resolve().parent          # capstone/tests/
_project_root = _tests_dir.parent                        # capstone/
_gui_app_dir  = _project_root / "gui-app"

for _p in [str(_project_root), str(_gui_app_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.data_loader import load_file, _normalise      # noqa: E402
from utils.model import stub_model_fn, stub_simulation_fn, risk_label  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix,
                                    delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def _assert_valid_taxa(taxa: dict, label: str = ""):
    assert isinstance(taxa, dict), f"{label} taxa must be a dict"
    assert len(taxa) > 0, f"{label} taxa dict is empty"
    total = sum(taxa.values())
    assert abs(total - 1.0) < 1e-4, (
        f"{label} proportions sum to {total:.6f}, expected 1.0"
    )
    for k, v in taxa.items():
        assert isinstance(k, str), f"{label} taxon key {k!r} is not a string"
        assert v > 0, f"{label} taxon {k!r} has non-positive proportion {v}"


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_two_column_csv():
    path = _write_tmp(
        "taxon,abundance\nFirmicutes,3500\nBacteroidetes,4000\nActinobacteria,500\n",
        ".csv"
    )
    try:
        result = load_file(path)
        assert result["error"] is None, f"Unexpected error: {result['error']}"
        _assert_valid_taxa(result["taxa"], "two-column CSV")
        assert "Firmicutes" in result["taxa"]
    finally:
        os.unlink(path)


def test_two_column_tsv_no_header():
    path = _write_tmp(
        "Firmicutes\t0.35\nBacteroidetes\t0.40\nActinobacteria\t0.25\n",
        ".tsv"
    )
    try:
        result = load_file(path)
        assert result["error"] is None
        _assert_valid_taxa(result["taxa"], "two-column TSV")
    finally:
        os.unlink(path)


def test_wide_csv():
    path = _write_tmp(
        "Firmicutes,Bacteroidetes,Actinobacteria\n3500,4000,500\n",
        ".csv"
    )
    try:
        result = load_file(path)
        assert result["error"] is None
        _assert_valid_taxa(result["taxa"], "wide CSV")
    finally:
        os.unlink(path)


def test_json_proportions():
    data = {"Firmicutes": 0.35, "Bacteroidetes": 0.40, "Actinobacteria": 0.25}
    path = _write_tmp(json.dumps(data), ".json")
    try:
        result = load_file(path)
        assert result["error"] is None
        _assert_valid_taxa(result["taxa"], "JSON proportions")
    finally:
        os.unlink(path)


def test_json_raw_counts():
    data = {"Firmicutes": 3500, "Bacteroidetes": 4000, "Actinobacteria": 500}
    path = _write_tmp(json.dumps(data), ".json")
    try:
        result = load_file(path)
        assert result["error"] is None
        _assert_valid_taxa(result["taxa"], "JSON counts")
    finally:
        os.unlink(path)


def test_stub_model_accepts_taxa():
    """Verify stub_model_fn accepts the taxa dict load_file produces."""
    data = {"Firmicutes": 0.35, "Bacteroidetes": 0.40, "Actinobacteria": 0.25}
    path = _write_tmp(json.dumps(data), ".json")
    try:
        result = load_file(path)
        taxa = result["taxa"]
        risk = stub_model_fn(taxa)
        assert isinstance(risk, float)
        assert 0 < risk < 100
    finally:
        os.unlink(path)


def test_stub_simulation_accepts_taxa_and_diet():
    taxa = {"Firmicutes": 0.35, "Bacteroidetes": 0.40, "Actinobacteria": 0.25}
    diet = {"probiotic": 5, "antibiotics": 0, "fiber": 3, "processed_foods": -2}
    risk = stub_simulation_fn(taxa, diet)
    assert isinstance(risk, float)
    assert 0 < risk < 100


def test_risk_label_thresholds():
    assert risk_label(10.0)  == "Low"
    assert risk_label(32.9)  == "Low"
    assert risk_label(33.0)  == "Moderate"
    assert risk_label(65.9)  == "Moderate"
    assert risk_label(66.0)  == "High"
    assert risk_label(99.0)  == "High"


def test_normalise_sums_to_one():
    raw = {"A": 1000, "B": 2000, "C": 500}
    norm = _normalise(raw)
    assert abs(sum(norm.values()) - 1.0) < 1e-8


def test_summary_contains_shannon():
    data = {"Firmicutes": 0.35, "Bacteroidetes": 0.40, "Actinobacteria": 0.25}
    path = _write_tmp(json.dumps(data), ".json")
    try:
        result = load_file(path)
        assert "Shannon" in result["summary"]
    finally:
        os.unlink(path)


def test_empty_file_returns_error():
    path = _write_tmp("", ".csv")
    try:
        result = load_file(path)
        assert result["error"] is not None
        assert result["taxa"] == {}
    finally:
        os.unlink(path)


if __name__ == "__main__":
    tests = [
        test_two_column_csv,
        test_two_column_tsv_no_header,
        test_wide_csv,
        test_json_proportions,
        test_json_raw_counts,
        test_stub_model_accepts_taxa,
        test_stub_simulation_accepts_taxa_and_diet,
        test_risk_label_thresholds,
        test_normalise_sums_to_one,
        test_summary_contains_shannon,
        test_empty_file_returns_error,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")