"""
tests/test_ncbi_service.py

Unit tests for services/ncbi_service.py.

All tests run 100% offline — every NCBI HTTP call is intercepted and
replaced with realistic response fixtures.  No network required.

Run:
    cd gui-app
    python -m pytest tests/test_ncbi_service.py -v
"""

from __future__ import annotations

import sys
import os
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 4. Now import using the 'src' prefix
from src.services.ncbi_service import (
    NcbiService, NcbiFetchError,
    RunRecord, ProjectRecord,
    validate_bioproject, validate_run_accession,
    _safe_int,
)


# ── Realistic NCBI response fixtures ─────────────────────────────────────────
 
# Call 1 — esearch SRA → returns internal SRA IDs
SRA_SEARCH_FOUND = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>2</Count>
  <IdList>
    <Id>12345001</Id>
    <Id>12345002</Id>
  </IdList>
</eSearchResult>"""
 
SRA_SEARCH_ONE = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>1</Count>
  <IdList><Id>12345001</Id></IdList>
</eSearchResult>"""
 
SRA_SEARCH_EMPTY = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>0</Count>
  <IdList/>
</eSearchResult>"""
 
# Call 2 — efetch SRA runinfo CSV
RUNINFO_CSV_TWO_RUNS = """\
Run,ReleaseDate,spots,bases,LibraryLayout,LibraryStrategy,Platform,Model,SRAStudy,BioProject,ProjectID,Sample,BioSample,TaxID,ScientificName,SampleName,CenterName
SRR15638501,2021-08-15,48200,7254100,PAIRED,AMPLICON,ILLUMINA,Illumina MiSeq,SRP330000,PRJNA743840,743840,SRS9876543,SAMN20963456,9606,Homo sapiens,Sample_001,UNIVERSITY_X
SRR15638502,2021-08-15,51300,7695000,PAIRED,AMPLICON,ILLUMINA,Illumina MiSeq,SRP330000,PRJNA743840,743840,SRS9876544,SAMN20963457,9606,Homo sapiens,Sample_002,UNIVERSITY_X"""
 
RUNINFO_CSV_SINGLE_END = """\
Run,ReleaseDate,spots,bases,LibraryLayout,LibraryStrategy,Platform,Model,SRAStudy,BioProject,ProjectID,Sample,BioSample,TaxID,ScientificName,SampleName,CenterName
SRR15638503,2021-08-15,35000,5250000,SINGLE,AMPLICON,ILLUMINA,Illumina HiSeq,SRP330000,PRJNA743840,743840,SRS9876545,SAMN20963458,9606,Homo sapiens,Sample_003,UNIVERSITY_X"""
 
RUNINFO_CSV_MIXED = """\
Run,ReleaseDate,spots,bases,LibraryLayout,LibraryStrategy,Platform,Model,SRAStudy,BioProject,ProjectID,Sample,BioSample,TaxID,ScientificName,SampleName,CenterName
SRR15638501,2021-08-15,48200,7254100,PAIRED,AMPLICON,ILLUMINA,Illumina MiSeq,SRP330000,PRJNA743840,743840,SRS9876543,SAMN20963456,9606,Homo sapiens,Sample_001,UNIVERSITY_X
SRR15638503,2021-08-15,35000,5250000,SINGLE,AMPLICON,ILLUMINA,Illumina HiSeq,SRP330000,PRJNA743840,743840,SRS9876545,SAMN20963458,9606,Homo sapiens,Sample_003,UNIVERSITY_X"""
 
RUNINFO_CSV_NO_RUNS = """\
Run,spots,bases
"""
 
# Call 3 — esummary BioProject → XML with title
BP_SUMMARY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSummaryResult>
  <DocumentSummarySet status="OK">
    <DocumentSummary uid="743840">
      <Project_Title>Human Gut Microbiome and Alzheimer Disease Risk</Project_Title>
      <Project_Description>16S rRNA amplicon sequencing of gut samples from 100 subjects</Project_Description>
      <Organism_Name>Homo sapiens</Organism_Name>
    </DocumentSummary>
  </DocumentSummarySet>
</eSummaryResult>"""
 
BP_SUMMARY_EMPTY = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSummaryResult>
  <DocumentSummarySet status="OK"/>
</eSummaryResult>"""
 
 
# ── Helpers ───────────────────────────────────────────────────────────────────
 
def _h(text: str):
    """Return a mock file handle that returns *text* from .read()."""
    handle = MagicMock()
    handle.read.return_value = text
    handle.close.return_value = None
    return handle
 
 
def _make_service() -> NcbiService:
    return NcbiService(email="test@example.com")
 
 
# ── Validation tests ──────────────────────────────────────────────────────────
 
class TestValidateBioproject:
 
    @pytest.mark.parametrize("acc", [
        "PRJNA743840", "PRJEB12345", "PRJDB99999",
        "prjna743840",   # lowercase — should pass (case-insensitive)
        "PRJNA1",        # minimal digits
    ])
    def test_valid_accessions(self, acc):
        ok, msg = validate_bioproject(acc)
        assert ok is True, f"Expected valid for '{acc}' but got: {msg}"
 
    @pytest.mark.parametrize("acc,expected_fragment", [
        ("",          "required"),
        ("GSE201234", "valid"),
        ("PRJNA",     "valid"),     # no digits
        ("SRR123456", "valid"),     # wrong prefix type
    ])
    def test_invalid_accessions(self, acc, expected_fragment):
        ok, msg = validate_bioproject(acc)
        assert ok is False
        assert expected_fragment in msg.lower()
 
    def test_whitespace_trimmed(self):
        ok, _ = validate_bioproject("  PRJNA743840  ")
        assert ok is True
 
 
class TestValidateRunAccession:
 
    def test_empty_is_valid(self):
        ok, msg = validate_run_accession("")
        assert ok is True and msg == ""
 
    @pytest.mark.parametrize("acc", [
        "SRR15638501", "ERR1234567", "DRR000001",
        "srr15638501",   # lowercase
    ])
    def test_valid_accessions(self, acc):
        ok, _ = validate_run_accession(acc)
        assert ok is True
 
    @pytest.mark.parametrize("acc", ["SAMN20963456", "PRJNA743840", "SRR"])
    def test_invalid_accessions(self, acc):
        ok, _ = validate_run_accession(acc)
        assert ok is False
 
    def test_whitespace_trimmed(self):
        ok, _ = validate_run_accession("  SRR15638501  ")
        assert ok is True
 
 
# ── NcbiService construction ──────────────────────────────────────────────────
 
class TestNcbiServiceConstruction:
 
    def test_raises_if_email_not_set(self):
        """Service must raise immediately if email is the placeholder value."""
        with pytest.raises(NcbiFetchError) as exc:
            NcbiService(email="your-email@example.com")
        assert "email" in str(exc.value).lower()
 
    def test_raises_if_email_empty(self):
        with pytest.raises(NcbiFetchError) as exc:
            NcbiService(email="")
        assert "email" in str(exc.value).lower()
 
    def test_valid_email_accepted(self):
        svc = NcbiService(email="researcher@university.edu")
        assert svc is not None
 
 
# ── NcbiService.fetch_project ─────────────────────────────────────────────────
 
class TestFetchProject:
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_happy_path_two_runs(self, mock_summary, mock_efetch, mock_esearch):
        """Full happy-path: 3-call sequence returns populated ProjectRecord."""
        mock_esearch.return_value  = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value   = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value  = _h(BP_SUMMARY_XML)
 
        project = _make_service().fetch_project("PRJNA743840", max_runs=4)
 
        assert isinstance(project, ProjectRecord)
        assert project.bioproject_id == "PRJNA743840"
        assert project.title         == "Human Gut Microbiome and Alzheimer Disease Risk"
        assert project.organism      == "Homo sapiens"
        assert project.run_count     == 2
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_run_labels_r1_r2(self, mock_summary, mock_efetch, mock_esearch):
        """Runs must be assigned sequential labels R1, R2, …"""
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
 
        project = _make_service().fetch_project("PRJNA743840", max_runs=4)
 
        assert [r.label for r in project.runs] == ["R1", "R2"]
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_run_metadata_parsed_correctly(self, mock_summary, mock_efetch, mock_esearch):
        """Read count, base count, accession, layout, platform all parsed."""
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
 
        project = _make_service().fetch_project("PRJNA743840", max_runs=4)
        r1 = project.runs[0]
 
        assert r1.run_accession    == "SRR15638501"
        assert r1.read_count       == 48200
        assert r1.base_count       == 7254100
        assert r1.library_layout   == "PAIRED"
        assert r1.library_strategy == "AMPLICON"
        assert r1.platform         == "ILLUMINA"
        assert r1.instrument       == "Illumina MiSeq"
        assert r1.sample_accession == "SAMN20963456"
        assert r1.organism         == "Homo sapiens"
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_library_layout_paired(self, mock_summary, mock_efetch, mock_esearch):
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
        project = _make_service().fetch_project("PRJNA743840")
        assert project.library_layout == "Paired-end"
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_library_layout_single(self, mock_summary, mock_efetch, mock_esearch):
        mock_esearch.return_value = _h(SRA_SEARCH_ONE)
        mock_efetch.return_value  = _h(RUNINFO_CSV_SINGLE_END)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
        project = _make_service().fetch_project("PRJNA743840")
        assert project.library_layout == "Single-end"
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_library_layout_mixed(self, mock_summary, mock_efetch, mock_esearch):
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_MIXED)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
        project = _make_service().fetch_project("PRJNA743840")
        assert project.library_layout == "Paired + Single"
 
    @patch("Bio.Entrez.esearch")
    def test_not_found_raises_with_helpful_message(self, mock_esearch):
        """Empty SRA search → NcbiFetchError with URL hint."""
        mock_esearch.return_value = _h(SRA_SEARCH_EMPTY)
        with pytest.raises(NcbiFetchError) as exc:
            _make_service().fetch_project("PRJNA999999")
        msg = str(exc.value)
        assert "no sequencing runs" in msg.lower()
        assert "PRJNA999999" in msg
        assert "ncbi.nlm.nih.gov/bioproject" in msg   # URL hint included
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_run_filter_narrows_to_one_run(self, mock_summary, mock_efetch, mock_esearch):
        """run_filter causes SRA to be searched with [Accession] field."""
        mock_esearch.return_value = _h(SRA_SEARCH_ONE)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS[:RUNINFO_CSV_TWO_RUNS.find('\nSRR15638502')])
        mock_summary.return_value = _h(BP_SUMMARY_XML)
 
        _make_service().fetch_project("PRJNA743840", run_filter="SRR15638501")
 
        # Verify the SRA search used [Accession] not [BioProject]
        search_term = mock_esearch.call_args.kwargs.get("term", "")
        assert "SRR15638501" in search_term
        assert "[Accession]" in search_term
 
    @patch("Bio.Entrez.esearch")
    def test_run_filter_not_found_raises(self, mock_esearch):
        mock_esearch.return_value = _h(SRA_SEARCH_EMPTY)
        with pytest.raises(NcbiFetchError) as exc:
            _make_service().fetch_project("PRJNA743840", run_filter="SRR99999999")
        assert "SRR99999999" in str(exc.value)
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_empty_runinfo_csv_raises(self, mock_summary, mock_efetch, mock_esearch):
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_NO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
        with pytest.raises(NcbiFetchError) as exc:
            _make_service().fetch_project("PRJNA743840")
        assert "empty" in str(exc.value).lower()
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_title_falls_back_gracefully(self, mock_summary, mock_efetch, mock_esearch):
        """If esummary returns no DocumentSummary, title defaults to bioproject_id."""
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_EMPTY)
 
        project = _make_service().fetch_project("PRJNA743840")
        # Title must be a non-empty fallback, not an exception
        assert project.title
        assert "PRJNA743840" in project.title or len(project.title) > 0
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_max_runs_respected(self, mock_summary, mock_efetch, mock_esearch):
        """max_runs=1 means only 1 run returned even if CSV has 2."""
        mock_esearch.return_value = _h(SRA_SEARCH_ONE)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
 
        project = _make_service().fetch_project("PRJNA743840", max_runs=1)
        assert project.run_count == 1
 
 
# ── to_dict() contract ────────────────────────────────────────────────────────
 
class TestToDict:
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_all_required_keys_present(self, mock_summary, mock_efetch, mock_esearch):
        """to_dict() must include every key the Overview page reads."""
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
 
        d = _make_service().fetch_project("PRJNA743840").to_dict()
 
        required = [
            "bioproject_id", "project_id", "title", "runs",
            "run_accessions", "read_counts", "uploaded",
            "qiime_errors", "library",
        ]
        for k in required:
            assert k in d, f"Missing key in to_dict(): '{k}'"
 
    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    @patch("Bio.Entrez.esummary")
    def test_values_correct(self, mock_summary, mock_efetch, mock_esearch):
        mock_esearch.return_value = _h(SRA_SEARCH_FOUND)
        mock_efetch.return_value  = _h(RUNINFO_CSV_TWO_RUNS)
        mock_summary.return_value = _h(BP_SUMMARY_XML)
 
        d = _make_service().fetch_project("PRJNA743840").to_dict()
 
        assert d["bioproject_id"]          == "PRJNA743840"
        assert d["runs"]                   == ["R1", "R2"]
        assert d["run_accessions"]["R1"]   == "SRR15638501"
        assert d["read_counts"]["R1"]      == 48200
        assert d["uploaded"]["R1"]         is False
        assert d["library"]                == "Paired-end"
 
 
# ── Retry logic ───────────────────────────────────────────────────────────────
 
class TestRetryLogic:
 
    @patch("Bio.Entrez.esearch")
    @patch("time.sleep")
    def test_retries_three_times_then_raises(self, mock_sleep, mock_esearch):
        from src.services.ncbi_service import _MAX_RETRIES
        mock_esearch.side_effect = ConnectionError("Network unreachable")
 
        with pytest.raises(NcbiFetchError) as exc:
            _make_service()._entrez_call(
                Entrez.esearch, db="sra", term="PRJNA743840[BioProject]"
            )
 
        assert mock_esearch.call_count == _MAX_RETRIES
        assert "connect" in str(exc.value).lower()
 
    @patch("Bio.Entrez.esearch")
    @patch("time.sleep")
    def test_succeeds_on_retry(self, mock_sleep, mock_esearch):
        """First call fails; second succeeds → no exception raised."""
        mock_esearch.side_effect = [
            ConnectionError("Transient failure"),
            _h(SRA_SEARCH_FOUND),
        ]
        result = _make_service()._entrez_call(
            Entrez.esearch, db="sra", term="PRJNA743840[BioProject]"
        )
        assert "<eSearchResult>" in result
        assert mock_esearch.call_count == 2
 
    @patch("Bio.Entrez.esearch")
    @patch("time.sleep")
    def test_403_error_gives_helpful_message(self, mock_sleep, mock_esearch):
        """HTTP 403 should produce a message mentioning email setup."""
        mock_esearch.side_effect = Exception(
            "<url open error Tunnel connection failed: 403 Forbidden>"
        )
        with pytest.raises(NcbiFetchError) as exc:
            _make_service()._entrez_call(
                Entrez.esearch, db="sra", term="test"
            )
        assert "403" in str(exc.value) or "email" in str(exc.value).lower()
 
 
# ── Utilities ─────────────────────────────────────────────────────────────────
 
class TestSafeInt:
    def test_normal(self):      assert _safe_int("48200") == 48200
    def test_empty(self):       assert _safe_int("") == 0
    def test_whitespace(self):  assert _safe_int("  512  ") == 512
    def test_invalid(self):     assert _safe_int("n/a") == 0
    def test_custom_default(self): assert _safe_int("bad", 99) == 99
 
 
# Needed at collection time for patch targets
from Bio import Entrez