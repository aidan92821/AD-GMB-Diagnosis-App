"""
tests/test_ncbi_service.py

Unit tests for services/ncbi_service.py.

All tests run 100% offline — NCBI HTTP calls are intercepted and
replaced with realistic XML fixtures so the tests never need a network
connection and always produce the same result.

Run with:
    cd gui-app
    python -m pytest tests/test_ncbi_service.py -v
"""

from __future__ import annotations

import sys
import os
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock, call

# Allow running from gui-app/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.ncbi_service import (
    NcbiService, NcbiFetchError,
    RunRecord, ProjectRecord,
    validate_bioproject, validate_run_accession,
)


# ── XML Fixtures ──────────────────────────────────────────────────────────────

BP_SEARCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>1</Count>
  <IdList><Id>743840</Id></IdList>
</eSearchResult>"""

BP_SUMMARY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSummaryResult>
  <DocumentSummarySet status="OK">
    <DocumentSummary uid="743840">
      <Project_Acc>PRJNA743840</Project_Acc>
      <Project_Title>Human Gut Microbiome Alzheimer Study</Project_Title>
      <Project_Description>16S rRNA amplicon sequencing of gut samples</Project_Description>
      <Organism_Name>Homo sapiens</Organism_Name>
    </DocumentSummary>
  </DocumentSummarySet>
</eSummaryResult>"""

SRA_SEARCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>2</Count>
  <IdList>
    <Id>12345001</Id>
    <Id>12345002</Id>
  </IdList>
</eSearchResult>"""

SRA_FETCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<EXPERIMENT_PACKAGE_SET>
  <EXPERIMENT_PACKAGE>
    <RUN_SET>
      <RUN accession="SRR15638501" total_spots="48200" total_bases="7254100">
        <Pool><Member sample_accession="SAMN20963456"/></Pool>
      </RUN>
    </RUN_SET>
    <EXPERIMENT>
      <LIBRARY_DESCRIPTOR>
        <LIBRARY_LAYOUT><PAIRED/></LIBRARY_LAYOUT>
      </LIBRARY_DESCRIPTOR>
    </EXPERIMENT>
  </EXPERIMENT_PACKAGE>
  <EXPERIMENT_PACKAGE>
    <RUN_SET>
      <RUN accession="SRR15638502" total_spots="51300" total_bases="7695000">
        <Pool><Member sample_accession="SAMN20963457"/></Pool>
      </RUN>
    </RUN_SET>
    <EXPERIMENT>
      <LIBRARY_DESCRIPTOR>
        <LIBRARY_LAYOUT><PAIRED/></LIBRARY_LAYOUT>
      </LIBRARY_DESCRIPTOR>
    </EXPERIMENT>
  </EXPERIMENT_PACKAGE>
</EXPERIMENT_PACKAGE_SET>"""

SRA_FETCH_SINGLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<EXPERIMENT_PACKAGE_SET>
  <EXPERIMENT_PACKAGE>
    <RUN_SET>
      <RUN accession="SRR15638501" total_spots="48200" total_bases="7254100">
        <Pool><Member sample_accession="SAMN20963456"/></Pool>
      </RUN>
    </RUN_SET>
    <EXPERIMENT>
      <LIBRARY_DESCRIPTOR>
        <LIBRARY_LAYOUT><PAIRED/></LIBRARY_LAYOUT>
      </LIBRARY_DESCRIPTOR>
    </EXPERIMENT>
  </EXPERIMENT_PACKAGE>
</EXPERIMENT_PACKAGE_SET>"""

BP_NOT_FOUND_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>0</Count>
  <IdList/>
</eSearchResult>"""

SRA_EMPTY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>0</Count>
  <IdList/>
</eSearchResult>"""

SRA_FETCH_SINGLE_ENDPOINT = """\
<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>1</Count>
  <IdList><Id>12345001</Id></IdList>
</eSearchResult>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_handle(xml_str: str):
    """Return a file-like object that yields the given XML string."""
    handle = MagicMock()
    handle.read.return_value = xml_str
    handle.close.return_value = None
    return handle


# ── Validation tests ──────────────────────────────────────────────────────────

class TestValidateBioproject:

    def test_valid_prjna(self):
        ok, msg = validate_bioproject("PRJNA743840")
        assert ok is True
        assert msg == ""

    def test_valid_prjeb(self):
        ok, msg = validate_bioproject("PRJEB12345")
        assert ok is True

    def test_valid_prjdb(self):
        ok, msg = validate_bioproject("PRJDB99999")
        assert ok is True

    def test_case_insensitive(self):
        ok, _ = validate_bioproject("prjna743840")
        assert ok is True

    def test_empty_string(self):
        ok, msg = validate_bioproject("")
        assert ok is False
        assert "required" in msg.lower()

    def test_invalid_prefix(self):
        ok, msg = validate_bioproject("GSE201234")
        assert ok is False
        assert "valid" in msg.lower()

    def test_missing_digits(self):
        ok, msg = validate_bioproject("PRJNA")
        assert ok is False

    def test_whitespace_stripped(self):
        ok, _ = validate_bioproject("  PRJNA743840  ")
        assert ok is True


class TestValidateRunAccession:

    def test_empty_is_valid(self):
        """Run accession field is optional — empty string must pass."""
        ok, msg = validate_run_accession("")
        assert ok is True
        assert msg == ""

    def test_valid_srr(self):
        ok, _ = validate_run_accession("SRR15638501")
        assert ok is True

    def test_valid_err(self):
        ok, _ = validate_run_accession("ERR1234567")
        assert ok is True

    def test_valid_drr(self):
        ok, _ = validate_run_accession("DRR000001")
        assert ok is True

    def test_invalid_format(self):
        ok, msg = validate_run_accession("SAMN20963456")
        assert ok is False
        assert "valid" in msg.lower()

    def test_whitespace_stripped(self):
        ok, _ = validate_run_accession("  SRR15638501  ")
        assert ok is True


# ── NcbiService fetch tests ───────────────────────────────────────────────────

class TestNcbiServiceFetchProject:

    def _make_service(self) -> NcbiService:
        return NcbiService(email="test@example.com")

    def _patch_entrez(self, responses: list[str]):
        """
        Context manager that patches Entrez so calls return XML strings
        from *responses* in order.
        """
        handles = [_mock_handle(xml) for xml in responses]
        # esearch → esummary → esearch(sra) → efetch
        from Bio import Entrez as E
        return patch.multiple(
            "Bio.Entrez",
            esearch=MagicMock(side_effect=handles[:2]),
            esummary=MagicMock(return_value=handles[1]),
            efetch=MagicMock(return_value=handles[-1]),
        )

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.esummary")
    @patch("Bio.Entrez.efetch")
    def test_full_fetch_returns_project(self, mock_efetch, mock_esummary, mock_esearch):
        """Happy path: fetch project with 2 runs."""
        mock_esearch.side_effect = [
            _mock_handle(BP_SEARCH_XML),    # BioProject search
            _mock_handle(SRA_SEARCH_XML),   # SRA run search
        ]
        mock_esummary.return_value = _mock_handle(BP_SUMMARY_XML)
        mock_efetch.return_value   = _mock_handle(SRA_FETCH_XML)

        service = self._make_service()
        project = service.fetch_project("PRJNA743840", max_runs=2)

        assert isinstance(project, ProjectRecord)
        assert project.bioproject_id == "PRJNA743840"
        assert project.title == "Human Gut Microbiome Alzheimer Study"
        assert project.organism == "Homo sapiens"
        assert project.run_count == 2

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.esummary")
    @patch("Bio.Entrez.efetch")
    def test_run_labels_assigned_correctly(self, mock_efetch, mock_esummary, mock_esearch):
        """Runs must be labelled R1, R2, … in order."""
        mock_esearch.side_effect = [
            _mock_handle(BP_SEARCH_XML),
            _mock_handle(SRA_SEARCH_XML),
        ]
        mock_esummary.return_value = _mock_handle(BP_SUMMARY_XML)
        mock_efetch.return_value   = _mock_handle(SRA_FETCH_XML)

        project = self._make_service().fetch_project("PRJNA743840", max_runs=4)
        labels  = [r.label for r in project.runs]
        assert labels == ["R1", "R2"]

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.esummary")
    @patch("Bio.Entrez.efetch")
    def test_run_accessions_parsed(self, mock_efetch, mock_esummary, mock_esearch):
        """Run accessions and read counts must be parsed from SRA XML."""
        mock_esearch.side_effect = [
            _mock_handle(BP_SEARCH_XML),
            _mock_handle(SRA_SEARCH_XML),
        ]
        mock_esummary.return_value = _mock_handle(BP_SUMMARY_XML)
        mock_efetch.return_value   = _mock_handle(SRA_FETCH_XML)

        project = self._make_service().fetch_project("PRJNA743840", max_runs=4)
        r1 = project.runs[0]

        assert r1.run_accession   == "SRR15638501"
        assert r1.read_count      == 48200
        assert r1.base_count      == 7254100
        assert r1.library_layout  == "PAIRED"
        assert r1.sample_accession == "SAMN20963456"

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.esummary")
    @patch("Bio.Entrez.efetch")
    def test_library_layout_summary(self, mock_efetch, mock_esummary, mock_esearch):
        """library_layout property returns 'Paired-end' when all runs are PAIRED."""
        mock_esearch.side_effect = [
            _mock_handle(BP_SEARCH_XML),
            _mock_handle(SRA_SEARCH_XML),
        ]
        mock_esummary.return_value = _mock_handle(BP_SUMMARY_XML)
        mock_efetch.return_value   = _mock_handle(SRA_FETCH_XML)

        project = self._make_service().fetch_project("PRJNA743840", max_runs=4)
        assert project.library_layout == "Paired-end"

    @patch("Bio.Entrez.esearch")
    def test_bioproject_not_found_raises(self, mock_esearch):
        """NcbiFetchError raised when BioProject accession not found."""
        mock_esearch.return_value = _mock_handle(BP_NOT_FOUND_XML)

        service = self._make_service()
        with pytest.raises(NcbiFetchError) as exc_info:
            service.fetch_project("PRJNA999999")

        assert "not found" in str(exc_info.value).lower()

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.esummary")
    def test_no_runs_raises(self, mock_esummary, mock_esearch):
        """NcbiFetchError raised when no SRA runs linked to BioProject."""
        mock_esearch.side_effect = [
            _mock_handle(BP_SEARCH_XML),
            _mock_handle(SRA_EMPTY_XML),
        ]
        mock_esummary.return_value = _mock_handle(BP_SUMMARY_XML)

        service = self._make_service()
        with pytest.raises(NcbiFetchError) as exc_info:
            service.fetch_project("PRJNA743840", max_runs=4)

        assert "no sequencing runs" in str(exc_info.value).lower()

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.esummary")
    @patch("Bio.Entrez.efetch")
    def test_run_filter_applied(self, mock_efetch, mock_esummary, mock_esearch):
        """When run_filter given, SRA is searched for that specific accession."""
        mock_esearch.side_effect = [
            _mock_handle(BP_SEARCH_XML),
            _mock_handle(SRA_FETCH_SINGLE_ENDPOINT),   # single run search
        ]
        mock_esummary.return_value  = _mock_handle(BP_SUMMARY_XML)
        mock_efetch.return_value    = _mock_handle(SRA_FETCH_SINGLE_XML)

        project = self._make_service().fetch_project(
            "PRJNA743840", run_filter="SRR15638501"
        )
        assert project.run_count == 1
        assert project.runs[0].run_accession == "SRR15638501"

        # Verify the SRA search query contained the run accession
        second_search_call = mock_esearch.call_args_list[1]
        assert "SRR15638501" in second_search_call.kwargs.get("term", "")

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.esummary")
    @patch("Bio.Entrez.efetch")
    def test_to_dict_structure(self, mock_efetch, mock_esummary, mock_esearch):
        """to_dict() must produce all keys the Overview page expects."""
        mock_esearch.side_effect = [
            _mock_handle(BP_SEARCH_XML),
            _mock_handle(SRA_SEARCH_XML),
        ]
        mock_esummary.return_value = _mock_handle(BP_SUMMARY_XML)
        mock_efetch.return_value   = _mock_handle(SRA_FETCH_XML)

        project = self._make_service().fetch_project("PRJNA743840", max_runs=4)
        d = project.to_dict()

        required_keys = [
            "bioproject_id", "project_id", "title", "runs",
            "run_accessions", "read_counts", "uploaded",
            "qiime_errors", "library",
        ]
        for key in required_keys:
            assert key in d, f"Missing key in to_dict(): '{key}'"

        assert d["bioproject_id"]     == "PRJNA743840"
        assert d["runs"]              == ["R1", "R2"]
        assert d["run_accessions"]["R1"] == "SRR15638501"
        assert d["read_counts"]["R1"]    == 48200
        assert d["uploaded"]["R1"]       is False


class TestNcbiServiceFetchSingleRun:

    @patch("Bio.Entrez.esearch")
    @patch("Bio.Entrez.efetch")
    def test_fetch_single_run(self, mock_efetch, mock_esearch):
        """fetch_single_run returns a RunRecord for a valid SRR accession."""
        mock_esearch.return_value = _mock_handle(SRA_FETCH_SINGLE_ENDPOINT)
        mock_efetch.return_value  = _mock_handle(SRA_FETCH_SINGLE_XML)

        service = NcbiService(email="test@example.com")
        run     = service.fetch_single_run("SRR15638501")

        assert isinstance(run, RunRecord)
        assert run.run_accession  == "SRR15638501"
        assert run.read_count     == 48200
        assert run.library_layout == "PAIRED"

    @patch("Bio.Entrez.esearch")
    def test_fetch_single_run_not_found(self, mock_esearch):
        """NcbiFetchError raised for unknown run accession."""
        mock_esearch.return_value = _mock_handle(SRA_EMPTY_XML)

        service = NcbiService(email="test@example.com")
        with pytest.raises(NcbiFetchError) as exc_info:
            service.fetch_single_run("SRR99999999")

        assert "not found" in str(exc_info.value).lower()


class TestRetryLogic:

    @patch("Bio.Entrez.esearch")
    @patch("time.sleep")
    def test_retries_on_network_error(self, mock_sleep, mock_esearch):
        """_entrez_call retries up to _MAX_RETRIES times on network failure."""
        from services.ncbi_service import _MAX_RETRIES

        mock_esearch.side_effect = ConnectionError("Network unreachable")

        service = NcbiService(email="test@example.com")
        with pytest.raises(NcbiFetchError) as exc_info:
            service._entrez_call(Entrez.esearch, db="bioproject", term="PRJNA1")

        assert "connect" in str(exc_info.value).lower()
        # Should have been called _MAX_RETRIES times
        assert mock_esearch.call_count == _MAX_RETRIES

    @patch("Bio.Entrez.esearch")
    @patch("time.sleep")
    def test_succeeds_on_second_attempt(self, mock_sleep, mock_esearch):
        """If the first call fails but the second succeeds, no error is raised."""
        mock_esearch.side_effect = [
            ConnectionError("Temporary failure"),
            _mock_handle(BP_SEARCH_XML),
        ]

        service = NcbiService(email="test@example.com")
        result  = service._entrez_call(
            Entrez.esearch, db="bioproject", term="PRJNA743840"
        )
        assert "<eSearchResult>" in result
        assert mock_esearch.call_count == 2


# Import Entrez at test collection time (needed for patch targets)
from Bio import Entrez