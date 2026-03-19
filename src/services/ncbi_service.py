"""
gui-app/services/ncbi_service.py

Real NCBI data fetcher using Biopython's Entrez API.

What it does
────────────
1. Validate BioProject / Run accession format
2. Search NCBI BioProject → get project title and internal UID
3. Search NCBI SRA for all runs linked to that BioProject
4. Fetch each run's metadata (accession, read count, library layout)
5. Return a plain Python dict the OverviewPage can display immediately

NCBI API notes
──────────────
• Always set Entrez.email — NCBI will block anonymous requests at scale.
• Entrez.api_key improves rate limit from 3 req/s to 10 req/s.
  Get a free key at: https://www.ncbi.nlm.nih.gov/account/
• All network calls are wrapped in NcbiFetchError so the GUI can show
  a clean message instead of a traceback.

Dependencies
────────────
    pip install biopython
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

# Biopython Entrez — real HTTP calls to eutils.ncbi.nlm.nih.gov
from Bio import Entrez

# ── Config ────────────────────────────────────────────────────────────────────

# Replace with your email — NCBI requires it for API access
ENTREZ_EMAIL   = "tranchung163@gmail.com"

# Optional: add your NCBI API key for 10 req/s instead of 3 req/s
# Get one free at https://www.ncbi.nlm.nih.gov/account/
ENTREZ_API_KEY = ""

# Seconds to wait between retried requests (NCBI rate-limit backoff)
_RETRY_DELAY = 1.0
_MAX_RETRIES  = 3


# ── Exceptions ────────────────────────────────────────────────────────────────

class NcbiFetchError(Exception):
    """
    Raised for any failure during NCBI communication.
    The message is human-readable so the GUI can display it directly.
    """


# ── Input validation ──────────────────────────────────────────────────────────

_BIOPROJECT_RE    = re.compile(r"^PRJ(NA|EA|DA|EB|DB|NB)\d+$", re.IGNORECASE)
_RUN_ACCESSION_RE = re.compile(r"^[SED]RR\d+$",   re.IGNORECASE)


def validate_bioproject(accession: str) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Valid formats: PRJNA123456 / PRJEB123 / PRJDB123.
    """
    if not accession.strip():
        return False, "BioProject accession is required."
    if not _BIOPROJECT_RE.match(accession.strip()):
        return False, (
            f"'{accession}' is not a valid BioProject accession. "
            "Expected format: PRJNA / PRJEB / PRJDB followed by digits "
            "(e.g. PRJNA743840)."
        )
    return True, ""


def validate_run_accession(accession: str) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Empty string is valid — the field is optional.
    """
    if not accession.strip():
        return True, ""
    if not _RUN_ACCESSION_RE.match(accession.strip()):
        return False, (
            f"'{accession}' is not a valid Run accession. "
            "Expected format: SRR / ERR / DRR followed by digits "
            "(e.g. SRR15638501)."
        )
    return True, ""


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class RunRecord:
    """Metadata for one sequencing run from NCBI SRA."""
    run_accession: str          # e.g. "SRR15638501"
    label:         str          # short UI label: "R1", "R2", …
    read_count:    int   = 0    # total spots (read pairs) in the run
    base_count:    int   = 0    # total bases sequenced
    library_layout: str = "PAIRED"   # "PAIRED" or "SINGLE"
    sample_accession: str = ""  # e.g. "SAMN20963456"
    uploaded:      bool  = False
    qiime_error:   Optional[str] = None


@dataclass
class ProjectRecord:
    """All metadata fetched for one BioProject."""
    bioproject_id:  str                          # NCBI accession  PRJNA…
    project_id:     str          = ""            # NCBI internal UID
    title:          str          = ""
    description:    str          = ""
    organism:       str          = ""
    runs:           list[RunRecord] = field(default_factory=list)
    asv_count:      int          = 0             # filled by pipeline later
    genus_count:    int          = 0             # filled by pipeline later

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def library_layout(self) -> str:
        """
        Summarise library layout across all runs:
        'Paired-end', 'Single-end', or 'Paired + Single'.
        """
        layouts = {r.library_layout for r in self.runs}
        if layouts == {"PAIRED"}:
            return "Paired-end"
        if layouts == {"SINGLE"}:
            return "Single-end"
        return "Paired + Single"

    def to_dict(self) -> dict:
        """
        Convert to the plain dict format the Overview page expects.
        Keys match models/example_data.PROJECT so no GUI code changes
        are needed.
        """
        return {
            "bioproject_id":  self.bioproject_id,
            "project_id":     self.project_id,
            "title":          self.title,
            "description":    self.description,
            "organism":       self.organism,
            "runs":           [r.label for r in self.runs],
            "run_accessions": {r.label: r.run_accession for r in self.runs},
            "read_counts":    {r.label: r.read_count    for r in self.runs},
            "base_counts":    {r.label: r.base_count    for r in self.runs},
            "library_layouts":{r.label: r.library_layout for r in self.runs},
            "uploaded":       {r.label: r.uploaded      for r in self.runs},
            "qiime_errors":   {
                r.label: r.qiime_error
                for r in self.runs
                if r.qiime_error
            },
            "asv_count":      self.asv_count,
            "genus_count":    self.genus_count,
            "library":        self.library_layout,
        }


# ── NCBI service ──────────────────────────────────────────────────────────────

class NcbiService:
    """
    Fetches BioProject and SRA run metadata from NCBI Entrez.

    Typical usage
    ─────────────
        service = NcbiService(email="you@example.com")
        project = service.fetch_project("PRJNA743840", max_runs=4)
        print(project.title)          # "Human gut microbiome…"
        print(project.runs[0].run_accession)   # "SRR15638501"

    All network failures are converted to NcbiFetchError with a
    user-readable message.
    """

    def __init__(
        self,
        email:   str = ENTREZ_EMAIL,
        api_key: str = ENTREZ_API_KEY,
    ) -> None:
        Entrez.email   = email
        Entrez.api_key = api_key or None
        self._email    = email

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_project(
        self,
        bioproject_accession: str,
        max_runs:             int            = 4,
        run_filter:           Optional[str]  = None,
    ) -> ProjectRecord:
        """
        Fetch everything needed to populate the Overview page.

        Parameters
        ──────────
        bioproject_accession
            NCBI BioProject accession, e.g. "PRJNA743840".
        max_runs
            Maximum number of runs to return (1–10).
            Ignored when run_filter is given.
        run_filter
            If provided, return ONLY this run accession (SRR…).

        Returns
        ───────
        ProjectRecord  — all project metadata plus a list of RunRecords.

        Raises
        ──────
        NcbiFetchError  — for any network, parsing, or "not found" error.
        """
        bp = bioproject_accession.strip().upper()

        # Step 1: resolve BioProject accession → internal NCBI UID + title
        uid, title, description, organism = self._fetch_bioproject_summary(bp)

        # Step 2: find SRA run IDs linked to this BioProject
        if run_filter:
            sra_ids = self._search_sra(f"{run_filter}[Accession]", retmax=1)
        else:
            sra_ids = self._search_sra(
                f"{bp}[BioProject]", retmax=max_runs
            )

        if not sra_ids:
            raise NcbiFetchError(
                f"No sequencing runs found for {bp}. "
                "Make sure the accession is correct and the data is public."
            )

        # Step 3: fetch run metadata from SRA
        runs = self._fetch_run_records(sra_ids, max_runs)

        return ProjectRecord(
            bioproject_id = bp,
            project_id    = uid,
            title         = title,
            description   = description,
            organism      = organism,
            runs          = runs,
        )

    def fetch_single_run(self, run_accession: str) -> RunRecord:
        """
        Fetch metadata for a single run by its SRR/ERR/DRR accession.
        Useful for validating a run accession before full project fetch.
        """
        sra_ids = self._search_sra(
            f"{run_accession.strip().upper()}[Accession]", retmax=1
        )
        if not sra_ids:
            raise NcbiFetchError(
                f"Run '{run_accession}' was not found in NCBI SRA. "
                "Check the accession and try again."
            )
        runs = self._fetch_run_records(sra_ids, max_runs=1)
        return runs[0]

    # ── Step 1: BioProject summary ────────────────────────────────────────────

    def _fetch_bioproject_summary(
        self, accession: str
    ) -> tuple[str, str, str, str]:
        """
        Returns (uid, title, description, organism) for a BioProject accession.
        Raises NcbiFetchError if not found or network fails.
        """
        # Search BioProject database for the accession
        search_xml = self._entrez_call(
            Entrez.esearch,
            db="bioproject",
            term=f"{accession}[Project Accession]",
            retmax=1,
        )
        root    = ET.fromstring(search_xml)
        id_list = root.findall(".//Id")

        if not id_list:
            raise NcbiFetchError(
                f"BioProject '{accession}' was not found in NCBI. "
                "Check the accession format and make sure the study is public."
            )

        uid = id_list[0].text.strip()

        # Fetch the project summary by UID
        summary_xml = self._entrez_call(
            Entrez.esummary,
            db="bioproject",
            id=uid,
        )
        root = ET.fromstring(summary_xml)
        doc  = root.find(".//DocumentSummary")

        if doc is None:
            # Fallback: return minimal info
            return uid, accession, "", ""

        title       = doc.findtext("Project_Title",       "").strip()
        description = doc.findtext("Project_Description", "").strip()
        organism    = doc.findtext("Organism_Name",        "").strip()

        # Use accession as title fallback
        if not title:
            title = accession

        return uid, title, description, organism

    # ── Step 2: SRA search ────────────────────────────────────────────────────

    def _search_sra(self, query: str, retmax: int) -> list[str]:
        """
        Search NCBI SRA and return a list of internal SRA IDs.
        Returns an empty list if nothing is found.
        """
        xml = self._entrez_call(
            Entrez.esearch,
            db="sra",
            term=query,
            retmax=retmax,
        )
        root = ET.fromstring(xml)
        return [el.text.strip() for el in root.findall(".//Id") if el.text]

    # ── Step 3: SRA run metadata ──────────────────────────────────────────────

    def _fetch_run_records(
        self, sra_ids: list[str], max_runs: int
    ) -> list[RunRecord]:
        """
        Fetch full run metadata for a list of SRA internal IDs.
        Returns up to max_runs RunRecord objects.
        """
        # Fetch in one batch call (NCBI allows up to 200 IDs per efetch)
        ids_csv = ",".join(sra_ids[:max_runs])
        xml = self._entrez_call(
            Entrez.efetch,
            db="sra",
            id=ids_csv,
            rettype="runinfo",
            retmode="xml",
        )

        runs: list[RunRecord] = []
        root = ET.fromstring(xml)

        for idx, pkg in enumerate(
            root.findall(".//EXPERIMENT_PACKAGE"), start=1
        ):
            run_el = pkg.find(".//RUN")
            if run_el is None:
                continue

            run_acc   = run_el.get("accession", "").strip()
            spots     = int(run_el.get("total_spots", "0") or "0")
            bases     = int(run_el.get("total_bases", "0") or "0")

            # Library layout
            layout_el = pkg.find(".//LIBRARY_LAYOUT")
            if layout_el is not None and layout_el.find("PAIRED") is not None:
                layout = "PAIRED"
            else:
                layout = "SINGLE"

            # Sample accession
            member    = pkg.find(".//Pool/Member")
            sample_acc = member.get("sample_accession", "") if member is not None else ""

            if run_acc:
                runs.append(RunRecord(
                    run_accession    = run_acc,
                    label            = f"R{idx}",
                    read_count       = spots,
                    base_count       = bases,
                    library_layout   = layout,
                    sample_accession = sample_acc,
                ))

        if not runs:
            raise NcbiFetchError(
                "Could not parse run metadata from NCBI SRA response. "
                "The data format may have changed — please file a bug report."
            )

        return runs

    # ── Entrez call wrapper ───────────────────────────────────────────────────

    def _entrez_call(self, func, **kwargs) -> str:
        """
        Call a Biopython Entrez function with automatic retry on failure.
        Returns the raw XML string.
        Raises NcbiFetchError on persistent failure.
        """
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                handle = func(**kwargs)
                xml    = handle.read()
                handle.close()

                # Biopython may return bytes or str depending on version
                if isinstance(xml, bytes):
                    xml = xml.decode("utf-8", errors="replace")

                # Check for NCBI error response embedded in XML
                if "<ERROR>" in xml:
                    root = ET.fromstring(xml)
                    err  = root.findtext("ERROR", "Unknown NCBI error")
                    raise NcbiFetchError(f"NCBI returned an error: {err}")

                return xml

            except NcbiFetchError:
                raise   # don't retry our own errors

            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY * attempt)   # exponential-ish backoff

        raise NcbiFetchError(
            f"Could not connect to NCBI after {_MAX_RETRIES} attempts. "
            f"Check your internet connection. Detail: {last_error}"
        )