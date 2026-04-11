"""
tests/test_pipeline.py

Tests for pipeline/pipeline.py and pipeline/db_import.py.

Strategy
--------
• parse_genus_table / parse_feat_tax_seqs / parse_feature_counts
  — pure file-parsing functions. Tested with real temp files (no mocking needed).

• preprocess_parse_import
  — calls qiime_preprocess (QIIME2, heavy) and DB services.
  — qiime_preprocess is mocked so tests run without a QIIME2 install.
  — DB services (create_project, create_run, ingest_run_data) are mocked.
  — Parser functions use real temp TSV/FASTA files so parse logic is verified.

• run_pipeline
  — calls fetch_ncbi_data (network) and preprocess_parse_import.
  — Both mocked to test orchestration logic only.

Run:
    cd AD-GMB-Diagnosis-App
    python -m pytest tests/test_pipeline.py -v
"""

from __future__ import annotations

import os
import sys
import textwrap
import pytest

from pathlib import Path
from unittest.mock import patch, MagicMock, call

# ── sys.path setup ────────────────────────────────────────────────────────────
# Add project root (contains src/) and src/pipeline/ so bare imports work.
_here         = Path(__file__).resolve().parent          # .../tests/
_project_root = _here.parent                             # .../AD-GMB-Diagnosis-App/
_src_dir      = _project_root / "src"
_pipeline_dir = _src_dir / "pipeline"

# Only add project root and src/ — NOT src/pipeline/.
# Adding src/pipeline/ would make Python resolve `pipeline` to pipeline.py
# (a file) instead of the pipeline/ directory package.
for p in [str(_project_root), str(_src_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Import the modules under test
from pipeline.db_import import (
    parse_genus_table,
    parse_feat_tax_seqs,
    parse_feature_counts,
)

# pipeline.pipeline uses bare imports (from db_import import ..., from qiime_preproc import ...)
# that only work when src/pipeline/ is on sys.path.  Pre-patch those bare names
# so the module loads without QIIME2 or the real services wired up.
import unittest.mock as _mock

_bare_mocks = {
    "qiime_preproc": _mock.MagicMock(),
    "fetch_data":    _mock.MagicMock(),
    # Patch the bare `services` name AND the package so both resolve
    "services":      _mock.MagicMock(),
    # db_import is real — we test its behaviour via parse_* directly
    "db_import":     sys.modules.get("pipeline.db_import", _mock.MagicMock()),
}
with _mock.patch.dict("sys.modules", _bare_mocks):
    # Temporarily add pipeline dir so bare imports inside pipeline.py resolve
    if str(_pipeline_dir) not in sys.path:
        sys.path.insert(0, str(_pipeline_dir))
    import importlib
    import pipeline.pipeline as _pipeline_mod
    importlib.reload(_pipeline_mod)
    sys.path.remove(str(_pipeline_dir))

preprocess_parse_import = _pipeline_mod.preprocess_parse_import
run_pipeline            = _pipeline_mod.run_pipeline


# ═══════════════════════════════════════════════════════════════════════════════
#  Fixtures — realistic QIIME2 output file content
# ═══════════════════════════════════════════════════════════════════════════════

GENUS_TABLE_TSV = textwrap.dedent("""\
    # Constructed from biom file
    #OTU ID\tSRR001\tSRR002
    g__Bacteroides\t1200.0\t800.0
    g__Prevotella\t600.0\t1400.0
    g__Faecalibacterium\t900.0\t300.0
    g__Unassigned\t300.0\t500.0
""")

FEATURE_TABLE_TSV = textwrap.dedent("""\
    # Constructed from biom file
    #OTU ID\tSRR001\tSRR002
    ASV_001\t234\t567
    ASV_002\t89\t12
    ASV_003\t450\t230
""")

TAXONOMY_TSV = textwrap.dedent("""\
    Feature ID\tTaxon\tConfidence
    ASV_001\td__Bacteria;p__Firmicutes;c__Clostridia;o__Lachnospirales;f__Lachnospiraceae;g__Roseburia\t0.99
    ASV_002\td__Bacteria;p__Bacteroidota;c__Bacteroidia;o__Bacteroidales;f__Bacteroidaceae;g__Bacteroides\t0.97
    ASV_003\td__Bacteria;p__Firmicutes;c__Clostridia;o__Oscillospirales;f__Ruminococcaceae;g__Faecalibacterium\t0.98
""")

FASTA_SEQS = textwrap.dedent("""\
    >ASV_001
    GTTTGATAAGTTAGAGGTGAAATCCCGAGATTTGGCCGTGAAACGCTTTCGC
    >ASV_002
    GTTTGATCCTGTAGAGGTGAAATCCCGAGATTTGGCCGTGAAACGCTTTCGC
    >ASV_003
    GTTTGATAAGCTAGAGGTGAAATCCCGAGATTTGGCCGTGAAACGCTTTCGC
""")


@pytest.fixture
def tmp_qiime_dir(tmp_path: Path) -> dict:
    """
    Create a realistic QIIME2 output directory tree under tmp_path.
    Returns a dict with paths to each file.
    """
    bioproject = "PRJTEST001"
    layout     = "single"
    qiime_dir  = tmp_path / "data" / bioproject / "qiime" / layout
    tree_dir   = tmp_path / "data" / bioproject / "reps-tree" / layout
    qiime_dir.mkdir(parents=True)
    tree_dir.mkdir(parents=True)

    genus_tsv   = qiime_dir / "genus-table.tsv"
    feature_tsv = qiime_dir / "feature-table.tsv"
    taxonomy_tsv = qiime_dir / "taxonomy.tsv"
    fasta_file  = tree_dir / "dna-sequences.fasta"

    genus_tsv.write_text(GENUS_TABLE_TSV)
    feature_tsv.write_text(FEATURE_TABLE_TSV)
    taxonomy_tsv.write_text(TAXONOMY_TSV)
    fasta_file.write_text(FASTA_SEQS)

    return {
        "root":        tmp_path,
        "bioproject":  bioproject,
        "layout":      layout,
        "genus_tsv":   str(genus_tsv),
        "feature_tsv": str(feature_tsv),
        "taxonomy_tsv": str(taxonomy_tsv),
        "fasta":       str(fasta_file),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  1. parse_genus_table
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseGenusTable:

    def test_returns_both_samples(self, tmp_qiime_dir):
        result = parse_genus_table(tmp_qiime_dir["genus_tsv"])
        assert "SRR001" in result
        assert "SRR002" in result

    def test_genera_normalised_to_100_pct(self, tmp_qiime_dir):
        result = parse_genus_table(tmp_qiime_dir["genus_tsv"])
        for sample, genera in result.items():
            total = sum(pct for _, pct in genera)
            assert abs(total - 100.0) < 0.01, (
                f"{sample}: abundances sum to {total:.2f}%, expected ~100%"
            )

    def test_correct_genus_names(self, tmp_qiime_dir):
        result = parse_genus_table(tmp_qiime_dir["genus_tsv"])
        names_srr001 = {g for g, _ in result["SRR001"]}
        assert "Bacteroides"    in names_srr001
        assert "Prevotella"     in names_srr001
        assert "Faecalibacterium" in names_srr001

    def test_sorted_by_descending_abundance(self, tmp_qiime_dir):
        result = parse_genus_table(tmp_qiime_dir["genus_tsv"])
        for sample, genera in result.items():
            pcts = [pct for _, pct in genera]
            assert pcts == sorted(pcts, reverse=True), (
                f"{sample}: genera not sorted by descending abundance"
            )

    def test_unassigned_mapped_to_unclassified(self, tmp_qiime_dir):
        result = parse_genus_table(tmp_qiime_dir["genus_tsv"])
        # "Unassigned" in the TSV should become "Unclassified"
        for sample, genera in result.items():
            names = {g for g, _ in genera}
            assert "Unassigned" not in names

    def test_missing_file_returns_empty(self, tmp_path):
        result = parse_genus_table(str(tmp_path / "nonexistent.tsv"))
        assert result == {}

    def test_relative_abundances_match_raw_counts(self, tmp_qiime_dir):
        # SRR001 raw: Bacteroides=1200, Prevotella=600, Faecalibacterium=900, Unassigned=300
        # total = 3000  →  Bacteroides = 40%, Prevotella = 20%, Faecalibacterium = 30%
        result = parse_genus_table(tmp_qiime_dir["genus_tsv"])
        srr001 = dict(result["SRR001"])
        assert abs(srr001.get("Bacteroides", 0) - 40.0) < 0.1
        assert abs(srr001.get("Prevotella",  0) - 20.0) < 0.1
        assert abs(srr001.get("Faecalibacterium", 0) - 30.0) < 0.1


# ═══════════════════════════════════════════════════════════════════════════════
#  2. parse_feature_counts
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseFeatureCounts:

    def test_returns_dict(self, tmp_qiime_dir):
        result = parse_feature_counts(tmp_qiime_dir["feature_tsv"])
        assert isinstance(result, dict)

    def test_all_asvs_present(self, tmp_qiime_dir):
        result = parse_feature_counts(tmp_qiime_dir["feature_tsv"])
        assert "ASV_001" in result
        assert "ASV_002" in result
        assert "ASV_003" in result

    def test_counts_summed_across_samples(self, tmp_qiime_dir):
        # ASV_001: 234 + 567 = 801
        # ASV_002: 89  + 12  = 101
        # ASV_003: 450 + 230 = 680
        result = parse_feature_counts(tmp_qiime_dir["feature_tsv"])
        assert result["ASV_001"] == 801
        assert result["ASV_002"] == 101
        assert result["ASV_003"] == 680

    def test_missing_file_returns_empty(self, tmp_path):
        result = parse_feature_counts(str(tmp_path / "nonexistent.tsv"))
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════════
#  3. parse_feat_tax_seqs
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseFeatTaxSeqs:

    def test_returns_list_of_dicts(self, tmp_qiime_dir):
        result = parse_feat_tax_seqs(
            tax  = tmp_qiime_dir["taxonomy_tsv"],
            seqs = tmp_qiime_dir["fasta"],
        )
        assert isinstance(result, list)
        assert len(result) == 3

    def test_each_entry_has_required_keys(self, tmp_qiime_dir):
        result = parse_feat_tax_seqs(
            tax  = tmp_qiime_dir["taxonomy_tsv"],
            seqs = tmp_qiime_dir["fasta"],
        )
        for entry in result:
            assert "feature_id" in entry
            assert "sequence"   in entry
            assert "taxonomy"   in entry

    def test_taxonomy_parsed_correctly(self, tmp_qiime_dir):
        result = parse_feat_tax_seqs(
            tax  = tmp_qiime_dir["taxonomy_tsv"],
            seqs = tmp_qiime_dir["fasta"],
        )
        by_id = {e["feature_id"]: e for e in result}
        assert "Roseburia" in by_id["ASV_001"]["taxonomy"]
        assert "Bacteroides" in by_id["ASV_002"]["taxonomy"]

    def test_sequences_parsed_correctly(self, tmp_qiime_dir):
        result = parse_feat_tax_seqs(
            tax  = tmp_qiime_dir["taxonomy_tsv"],
            seqs = tmp_qiime_dir["fasta"],
        )
        by_id = {e["feature_id"]: e for e in result}
        assert by_id["ASV_001"]["sequence"].startswith("GTTTGATAAGTTAGAGG")
        assert len(by_id["ASV_001"]["sequence"]) > 10

    def test_missing_taxonomy_file(self, tmp_qiime_dir, tmp_path):
        # Should still return sequences with empty taxonomy strings
        result = parse_feat_tax_seqs(
            tax  = str(tmp_path / "nonexistent.tsv"),
            seqs = tmp_qiime_dir["fasta"],
        )
        assert len(result) == 3
        for entry in result:
            assert entry["taxonomy"] == ""
            assert len(entry["sequence"]) > 0

    def test_missing_fasta_file(self, tmp_qiime_dir, tmp_path):
        # Should still return taxonomy with empty sequence strings
        result = parse_feat_tax_seqs(
            tax  = tmp_qiime_dir["taxonomy_tsv"],
            seqs = str(tmp_path / "nonexistent.fasta"),
        )
        assert len(result) == 3
        for entry in result:
            assert entry["sequence"] == ""
            assert len(entry["taxonomy"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  4. preprocess_parse_import
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreprocessParseImport:
    """
    Tests for preprocess_parse_import().

    qiime_preprocess is mocked (no QIIME2 install needed).
    DB service calls (create_project, create_run, ingest_run_data) are mocked.
    Parser functions use real temp files — parse logic IS exercised.
    """

    def _make_user(self) -> dict:
        return {"user_id": 1, "username": "testuser"}

    def _make_project(self, project_id=42) -> dict:
        return {"project_id": project_id, "name": "Test Project"}

    def _make_run(self, run_id=10) -> dict:
        return {"run_id": run_id}

    def test_calls_qiime_preprocess(self, tmp_qiime_dir, monkeypatch):
        """qiime_preprocess must be called once with the correct args."""
        mock_qiime = MagicMock()
        monkeypatch.setattr(_pipeline_mod, "qiime_preprocess", mock_qiime)
        monkeypatch.setattr(_pipeline_mod, "create_project",   MagicMock(return_value=self._make_project()))
        monkeypatch.setattr(_pipeline_mod, "create_run",       MagicMock(return_value=self._make_run()))
        monkeypatch.setattr(_pipeline_mod, "ingest_run_data",  MagicMock())

        monkeypatch.chdir(tmp_qiime_dir["root"])
        preprocess_parse_import(
            bioproject   = tmp_qiime_dir["bioproject"],
            project_id   = None,
            project_name = "Test Project",
            lib_layout   = tmp_qiime_dir["layout"],
            user         = self._make_user(),
        )

        mock_qiime.assert_called_once_with(
            bioproject = tmp_qiime_dir["bioproject"],
            lib_layout = tmp_qiime_dir["layout"],
        )

    def test_creates_new_project_when_project_id_is_none(self, tmp_qiime_dir, monkeypatch):
        """When project_id=None, create_project must be called."""
        mock_create_project = MagicMock(return_value=self._make_project())
        mock_get_project    = MagicMock()

        monkeypatch.setattr(_pipeline_mod, "qiime_preprocess", MagicMock())
        monkeypatch.setattr(_pipeline_mod, "create_project",   mock_create_project)
        monkeypatch.setattr(_pipeline_mod, "get_project_overview", mock_get_project)
        monkeypatch.setattr(_pipeline_mod, "create_run",       MagicMock(return_value=self._make_run()))
        monkeypatch.setattr(_pipeline_mod, "ingest_run_data",  MagicMock())

        monkeypatch.chdir(tmp_qiime_dir["root"])
        preprocess_parse_import(
            bioproject   = tmp_qiime_dir["bioproject"],
            project_id   = None,
            project_name = "Test Project",
            lib_layout   = tmp_qiime_dir["layout"],
            user         = self._make_user(),
        )

        mock_create_project.assert_called_once_with(
            user_id = 1,
            name    = "Test Project",
        )
        mock_get_project.assert_not_called()

    def test_uses_existing_project_when_project_id_provided(self, tmp_qiime_dir, monkeypatch):
        """When project_id is given, get_project_overview must be called instead."""
        mock_create_project = MagicMock()
        mock_get_project    = MagicMock(return_value=self._make_project(project_id=99))

        monkeypatch.setattr(_pipeline_mod, "qiime_preprocess",     MagicMock())
        monkeypatch.setattr(_pipeline_mod, "create_project",       mock_create_project)
        monkeypatch.setattr(_pipeline_mod, "get_project_overview",  mock_get_project)
        monkeypatch.setattr(_pipeline_mod, "create_run",           MagicMock(return_value=self._make_run()))
        monkeypatch.setattr(_pipeline_mod, "ingest_run_data",      MagicMock())

        monkeypatch.chdir(tmp_qiime_dir["root"])
        preprocess_parse_import(
            bioproject   = tmp_qiime_dir["bioproject"],
            project_id   = 99,
            project_name = "Test Project",
            lib_layout   = tmp_qiime_dir["layout"],
            user         = self._make_user(),
        )

        mock_get_project.assert_called_once_with(project_id=99)
        mock_create_project.assert_not_called()

    def test_creates_run_and_ingests_data_for_each_sample(self, tmp_qiime_dir, monkeypatch):
        """create_run + ingest_run_data must be called once per SRR sample."""
        mock_create_run   = MagicMock(side_effect=[self._make_run(10), self._make_run(11)])
        mock_ingest       = MagicMock()

        monkeypatch.setattr(_pipeline_mod, "qiime_preprocess", MagicMock())
        monkeypatch.setattr(_pipeline_mod, "create_project",   MagicMock(return_value=self._make_project()))
        monkeypatch.setattr(_pipeline_mod, "create_run",       mock_create_run)
        monkeypatch.setattr(_pipeline_mod, "ingest_run_data",  mock_ingest)

        monkeypatch.chdir(tmp_qiime_dir["root"])
        preprocess_parse_import(
            bioproject   = tmp_qiime_dir["bioproject"],
            project_id   = None,
            project_name = "Test Project",
            lib_layout   = tmp_qiime_dir["layout"],
            user         = self._make_user(),
        )

        # genus-table.tsv has SRR001 and SRR002 → 2 runs created
        assert mock_create_run.call_count == 2
        assert mock_ingest.call_count == 2

    def test_ingest_called_with_correct_run_id(self, tmp_qiime_dir, monkeypatch):
        """ingest_run_data must receive the run_id returned by create_run."""
        mock_create_run = MagicMock(return_value={"run_id": 77})
        mock_ingest     = MagicMock()

        monkeypatch.setattr(_pipeline_mod, "qiime_preprocess", MagicMock())
        monkeypatch.setattr(_pipeline_mod, "create_project",   MagicMock(return_value=self._make_project()))
        monkeypatch.setattr(_pipeline_mod, "create_run",       mock_create_run)
        monkeypatch.setattr(_pipeline_mod, "ingest_run_data",  mock_ingest)

        monkeypatch.chdir(tmp_qiime_dir["root"])
        preprocess_parse_import(
            bioproject   = tmp_qiime_dir["bioproject"],
            project_id   = None,
            project_name = "Test Project",
            lib_layout   = tmp_qiime_dir["layout"],
            user         = self._make_user(),
        )

        for c in mock_ingest.call_args_list:
            assert c.kwargs["run_id"] == 77


# ═══════════════════════════════════════════════════════════════════════════════
#  5. run_pipeline  (orchestration only — no real network/QIIME2)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunPipeline:
    """
    Tests for run_pipeline().

    fetch_ncbi_data and preprocess_parse_import are both mocked.
    get_or_create_user and download_classifier are also mocked.
    Only the orchestration logic is verified.
    """

    _fake_user = {"user_id": 1, "username": "tester"}

    def _patch_all(self, monkeypatch, lib_layout: dict):
        monkeypatch.setattr(_pipeline_mod, "fetch_ncbi_data",        MagicMock(return_value=lib_layout))
        monkeypatch.setattr(_pipeline_mod, "get_or_create_user",     MagicMock(return_value=self._fake_user))
        monkeypatch.setattr(_pipeline_mod, "download_classifier",    MagicMock())
        # Patch os.listdir to pretend classifier already exists
        monkeypatch.setattr(_pipeline_mod.os, "listdir",
                            MagicMock(return_value=["silva-138-99-nb-classifier.qza"]))

    def test_calls_fetch_ncbi_data(self, monkeypatch):
        mock_fetch = MagicMock(return_value={"paired": False, "single": False})
        monkeypatch.setattr(_pipeline_mod, "fetch_ncbi_data",    mock_fetch)
        monkeypatch.setattr(_pipeline_mod, "get_or_create_user", MagicMock(return_value=self._fake_user))
        monkeypatch.setattr(_pipeline_mod.os, "listdir",
                            MagicMock(return_value=["silva-138-99-nb-classifier.qza"]))

        run_pipeline("PRJNA001", None, "tester", "Test", srr="SRR001", n_runs=1)

        mock_fetch.assert_called_once_with(bioproject="PRJNA001", srr="SRR001", n_runs=1)

    def test_paired_layout_calls_preprocess(self, monkeypatch):
        mock_preprocess = MagicMock()
        self._patch_all(monkeypatch, {"paired": True, "single": False})
        monkeypatch.setattr(_pipeline_mod, "preprocess_parse_import", mock_preprocess)

        run_pipeline("PRJNA001", None, "tester", "Test")

        mock_preprocess.assert_called_once()
        kw = mock_preprocess.call_args.kwargs
        assert kw["bioproject"]   == "PRJNA001"
        assert kw["project_id"]   is None
        assert kw["project_name"] == "Test"
        assert kw["lib_layout"]   == "paired"
        assert kw["user"]         == self._fake_user

    def test_single_layout_calls_preprocess(self, monkeypatch):
        mock_preprocess = MagicMock()
        self._patch_all(monkeypatch, {"paired": False, "single": True})
        monkeypatch.setattr(_pipeline_mod, "preprocess_parse_import", mock_preprocess)

        run_pipeline("PRJNA001", None, "tester", "Test")

        mock_preprocess.assert_called_once()
        kw = mock_preprocess.call_args.kwargs
        assert kw["bioproject"]   == "PRJNA001"
        assert kw["project_id"]   is None
        assert kw["project_name"] == "Test"
        assert kw["lib_layout"]   == "single"
        assert kw["user"]         == self._fake_user

    def test_both_layouts_calls_preprocess_twice(self, monkeypatch):
        mock_preprocess = MagicMock()
        self._patch_all(monkeypatch, {"paired": True, "single": True})
        monkeypatch.setattr(_pipeline_mod, "preprocess_parse_import", mock_preprocess)

        run_pipeline("PRJNA001", None, "tester", "Test")

        assert mock_preprocess.call_count == 2

    def test_no_layouts_does_not_call_preprocess(self, monkeypatch):
        mock_preprocess = MagicMock()
        self._patch_all(monkeypatch, {"paired": False, "single": False})
        monkeypatch.setattr(_pipeline_mod, "preprocess_parse_import", mock_preprocess)

        run_pipeline("PRJNA001", None, "tester", "Test")

        mock_preprocess.assert_not_called()

    def test_downloads_classifier_when_missing(self, monkeypatch):
        mock_download = MagicMock()
        monkeypatch.setattr(_pipeline_mod, "fetch_ncbi_data",    MagicMock(return_value={"paired": False, "single": False}))
        monkeypatch.setattr(_pipeline_mod, "get_or_create_user", MagicMock(return_value=self._fake_user))
        monkeypatch.setattr(_pipeline_mod, "download_classifier", mock_download)
        # Pretend classifier is NOT in the directory
        monkeypatch.setattr(_pipeline_mod.os, "listdir", MagicMock(return_value=[]))

        run_pipeline("PRJNA001", None, "tester", "Test")

        mock_download.assert_called_once()
        url = mock_download.call_args.kwargs.get("classifier_url") or mock_download.call_args.args[0]
        assert "silva-138-99-nb-classifier.qza" in url

    def test_skips_classifier_download_when_present(self, monkeypatch):
        mock_download = MagicMock()
        monkeypatch.setattr(_pipeline_mod, "fetch_ncbi_data",    MagicMock(return_value={"paired": False, "single": False}))
        monkeypatch.setattr(_pipeline_mod, "get_or_create_user", MagicMock(return_value=self._fake_user))
        monkeypatch.setattr(_pipeline_mod, "download_classifier", mock_download)
        # Classifier already present
        monkeypatch.setattr(_pipeline_mod.os, "listdir",
                            MagicMock(return_value=["silva-138-99-nb-classifier.qza"]))

        run_pipeline("PRJNA001", None, "tester", "Test")

        mock_download.assert_not_called()
