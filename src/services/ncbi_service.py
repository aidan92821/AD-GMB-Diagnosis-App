"""
gui-app/services/ncbi_service.py

Real NCBI data fetcher using Biopython's Entrez API.

API strategy (3 calls total)
─────────────────────────────
  Call 1 — esearch(db='sra', term='PRJNA…[BioProject]')
            → gets internal SRA IDs for all runs in the project

  Call 2 — efetch(db='sra', id='…', rettype='runinfo', retmode='text')
            → CSV with per-run details (accession, spots, layout, organism…)
            → also contains the numeric ProjectID we need for the title

  Call 3 — esummary(db='bioproject', id=<numeric_uid>)
            → XML with project title and description

Why this strategy?
  • 'esearch(db=bioproject, term=PRJNA…[Project Accession])' is unreliable —
    the field tag '[Project Accession]' is not consistently indexed and
    returns 0 results for many valid accessions.
  • Going through SRA first is the approach used by QIIME2, SRA-tools,
    and the NCBI EUtils best-practices guide.
  • The runinfo CSV contains the numeric ProjectID in one round-trip,
    avoiding a separate BioProject search step.

Setup
─────
  1. Set ENTREZ_EMAIL to your real email — NCBI blocks anonymous requests.
  2. Optionally set ENTREZ_API_KEY for 10 req/s (free at ncbi.nlm.nih.gov/account).

Install:
  pip install biopython
"""

from __future__ import annotations

import csv
import io
import re
import time
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from Bio import Entrez

# ── Configuration ─────────────────────────────────────────────────────────────

# ⚠ Replace with your actual email — NCBI requires it
ENTREZ_EMAIL   = "tranchung163@gmail.com"

# Optional free API key → 10 requests/sec instead of 3
# Get one at: https://www.ncbi.nlm.nih.gov/account/
ENTREZ_API_KEY = "f8c15c68ee506cfaedc45107e282f583f508"

_MAX_RETRIES = 3
_RETRY_DELAY = 1.5   # seconds (multiplied by attempt number for backoff)
 
 
# ── Exception ─────────────────────────────────────────────────────────────────
 
class NcbiFetchError(Exception):
    """
    Raised for any failure during NCBI communication.
    The message is human-readable so the GUI can show it directly.
    """
 
 
# ── Validation ────────────────────────────────────────────────────────────────
 
# NCBI BioProject accession formats:
#   PRJNA…  (NIH/NCBI)
#   PRJEB…  (EBI/European)
#   PRJDB…  (DDBJ/Japan)
_BIOPROJECT_RE    = re.compile(r"^PRJ(NA|EA|DA|EB|DB|NB)\d+$", re.IGNORECASE)
_RUN_ACCESSION_RE = re.compile(r"^[SED]RR\d+$",                 re.IGNORECASE)
 
 
def validate_bioproject(accession: str) -> tuple[bool, str]:
    """
    Return (is_valid, error_message).
    Valid formats: PRJNA123456 / PRJEB12345 / PRJDB99999.
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
    Return (is_valid, error_message).
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
    run_accession:    str          # SRR / ERR / DRR accession
    label:            str          # short UI label: "R1", "R2", …
    read_count:       int  = 0     # total spots (read pairs)
    base_count:       int  = 0     # total bases sequenced
    library_layout:   str  = "PAIRED"     # "PAIRED" or "SINGLE"
    library_strategy: str  = ""    # e.g. "AMPLICON", "WGS"
    platform:         str  = ""    # e.g. "ILLUMINA"
    instrument:       str  = ""    # e.g. "Illumina MiSeq"
    sample_accession: str  = ""    # BioSample accession
    organism:         str  = ""    # scientific name
    uploaded:         bool = False
    qiime_error:      Optional[str] = None
 
 
@dataclass
class ProjectRecord:
    """All metadata fetched for one BioProject."""
    bioproject_id:    str                          # e.g. "PRJNA743840"
    project_uid:      str          = ""            # NCBI numeric UID
    sra_study_id:     str          = ""            # e.g. "SRP330000"
    title:            str          = ""
    description:      str          = ""
    organism:         str          = ""
    runs:             list[RunRecord] = field(default_factory=list)
    asv_count:        int          = 0
    genus_count:      int          = 0
 
    @property
    def run_count(self) -> int:
        return len(self.runs)
 
    @property
    def library_layout(self) -> str:
        """
        Summarise library layout across all runs.
        Returns 'Paired-end', 'Single-end', or 'Paired + Single'.
        """
        layouts = {r.library_layout.upper() for r in self.runs}
        if layouts == {"PAIRED"}:
            return "Paired-end"
        if layouts == {"SINGLE"}:
            return "Single-end"
        if layouts:
            return "Paired + Single"
        return "Unknown"
 
    def to_dict(self) -> dict:
        """
        Convert to the plain dict the Overview page expects.
        Keys match the shape of models/example_data.PROJECT.
        """
        return {
            "bioproject_id":   self.bioproject_id,
            "project_id":      self.sra_study_id or self.project_uid,
            "title":           self.title or self.bioproject_id,
            "description":     self.description,
            "organism":        self.organism,
            "runs":            [r.label for r in self.runs],
            "run_accessions":  {r.label: r.run_accession    for r in self.runs},
            "read_counts":     {r.label: r.read_count       for r in self.runs},
            "base_counts":     {r.label: r.base_count       for r in self.runs},
            "library_layouts": {r.label: r.library_layout   for r in self.runs},
            "instruments":     {r.label: r.instrument       for r in self.runs},
            "platforms":       {r.label: r.platform         for r in self.runs},
            "uploaded":        {r.label: r.uploaded         for r in self.runs},
            "qiime_errors":    {
                r.label: r.qiime_error
                for r in self.runs if r.qiime_error
            },
            "asv_count":       self.asv_count,
            "genus_count":     self.genus_count,
            "library":         self.library_layout,
        }
 
 
# ── NCBI service ──────────────────────────────────────────────────────────────
 
class NcbiService:
    """
    Fetches BioProject + SRA run metadata from NCBI Entrez.
 
    Example
    -------
        service = NcbiService(email="you@example.com")
        project = service.fetch_project("PRJNA743840", max_runs=4)
        print(project.title)
        for run in project.runs:
            print(run.run_accession, run.read_count)
    """
 
    def __init__(
        self,
        email:   str = ENTREZ_EMAIL,
        api_key: str = ENTREZ_API_KEY,
    ) -> None:
        if not email or email == "your-email@example.com":
            raise NcbiFetchError(
                "NCBI requires a valid email address for API access. "
                "Open gui-app/services/ncbi_service.py and set ENTREZ_EMAIL "
                "to your real email address."
            )
        Entrez.email   = email
        Entrez.api_key = api_key or None
 
    # ── Public API ────────────────────────────────────────────────────────────
 
    def fetch_project(
        self,
        bioproject_accession: str,
        max_runs:             int           = 4,
        run_filter:           Optional[str] = None,
    ) -> ProjectRecord:
        """
        Fetch all metadata for a BioProject and its sequencing runs.
 
        Parameters
        ----------
        bioproject_accession
            NCBI BioProject accession, e.g. "PRJNA743840".
        max_runs
            Maximum number of runs to return (1–10).
            Ignored when run_filter is provided.
        run_filter
            If given, return only this run accession (e.g. "SRR15638501").
 
        Returns
        -------
        ProjectRecord
 
        Raises
        ------
        NcbiFetchError  — connection failure, accession not found, or parse error.
        """
        bp = bioproject_accession.strip().upper()
 
        # ── Pre-flight: verify NCBI is reachable before any API calls ─────
        ok, err = check_connectivity()
        if not ok:
            raise NcbiFetchError(err)
 
        # ── Call 1: find SRA run IDs ──────────────────────────────────────
        if run_filter:
            query   = f"{run_filter.strip().upper()}[Accession]"
            retmax  = 1
        else:
            query   = f"{bp}[BioProject]"
            retmax  = max_runs
 
        sra_ids = self._sra_search(query, retmax)
 
        if not sra_ids:
            if run_filter:
                raise NcbiFetchError(
                    f"Run accession '{run_filter}' was not found in NCBI SRA. "
                    "Check that the accession is correct and the data is public."
                )
            raise NcbiFetchError(
                f"No sequencing runs found for BioProject '{bp}'. "
                "Possible reasons:\n"
                "  • The accession does not exist in NCBI\n"
                "  • The data has not been released publicly yet\n"
                "  • The BioProject has no linked SRA experiments\n"
                f"You can verify at: https://www.ncbi.nlm.nih.gov/bioproject/{bp}"
            )
 
        # ── Call 2: fetch run metadata as CSV ─────────────────────────────
        runs, project_uid, sra_study_id, organism = self._fetch_runinfo_csv(
            sra_ids, max_runs
        )
 
        # ── Call 3: fetch project title from BioProject db ────────────────
        title, description = "", ""
        if project_uid:
            title, description = self._fetch_project_title(project_uid)
 
        # Fallback title
        if not title:
            title = f"{bp} — {len(runs)} run(s)"
 
        return ProjectRecord(
            bioproject_id = bp,
            project_uid   = project_uid,
            sra_study_id  = sra_study_id,
            title         = title,
            description   = description,
            organism      = organism,
            runs          = runs,
        )
 
    # ── Call 1: SRA esearch ───────────────────────────────────────────────────
 
    def _sra_search(self, query: str, retmax: int) -> list[str]:
        """
        Search NCBI SRA and return a list of internal SRA IDs.
        Returns an empty list when nothing is found.
        """
        xml = self._entrez_call(
            Entrez.esearch,
            db="sra",
            term=query,
            retmax=retmax,
            usehistory="y",
        )
        root = ET.fromstring(xml)
        return [el.text.strip() for el in root.findall(".//Id") if el.text]
 
    # ── Call 2: SRA efetch runinfo CSV ────────────────────────────────────────
 
    def _fetch_runinfo_csv(
        self,
        sra_ids: list[str],
        max_runs: int,
    ) -> tuple[list[RunRecord], str, str, str]:
        """
        Fetch run metadata as a CSV from NCBI SRA efetch.
 
        Returns
        -------
        (runs, project_uid, sra_study_id, organism)
        """
        ids_csv = ",".join(sra_ids[:max_runs])
        csv_text = self._entrez_call(
            Entrez.efetch,
            db="sra",
            id=ids_csv,
            rettype="runinfo",
            retmode="text",
        )
 
        # Parse CSV — NCBI runinfo has a well-known column layout
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        rows   = [r for r in reader if r.get("Run", "").startswith(("SRR", "ERR", "DRR"))]
 
        if not rows:
            raise NcbiFetchError(
                "NCBI returned an empty runinfo table. "
                "The runs may still be processing or the data may be restricted."
            )
 
        runs: list[RunRecord] = []
        for idx, row in enumerate(rows[:max_runs], start=1):
            layout = row.get("LibraryLayout", "").upper()
            if layout not in {"PAIRED", "SINGLE"}:
                layout = "PAIRED"   # safe default for 16S studies
 
            runs.append(RunRecord(
                run_accession    = row.get("Run", ""),
                label            = f"R{idx}",
                read_count       = _safe_int(row.get("spots", "0")),
                base_count       = _safe_int(row.get("bases", "0")),
                library_layout   = layout,
                library_strategy = row.get("LibraryStrategy", ""),
                platform         = row.get("Platform", ""),
                instrument       = row.get("Model", ""),
                sample_accession = row.get("BioSample", ""),
                organism         = row.get("ScientificName", ""),
            ))
 
        # Project-level fields come from the first row
        first       = rows[0]
        project_uid = first.get("ProjectID", "").strip()
        sra_study   = first.get("SRAStudy", "").strip()
        organism    = first.get("ScientificName", "").strip()
 
        return runs, project_uid, sra_study, organism
 
    # ── Call 3: BioProject esummary ───────────────────────────────────────────
 
    def _fetch_project_title(self, project_uid: str) -> tuple[str, str]:
        """
        Fetch the project title and description using the numeric UID.
        Returns ("", "") on any failure (title is non-critical).
        """
        try:
            xml  = self._entrez_call(
                Entrez.esummary,
                db="bioproject",
                id=project_uid,
            )
            root = ET.fromstring(xml)
            doc  = root.find(".//DocumentSummary")
            if doc is None:
                return "", ""
            title = (
                doc.findtext("Project_Title", "")
                or doc.findtext("Title", "")
            ).strip()
            description = (
                doc.findtext("Project_Description", "")
                or doc.findtext("Description", "")
            ).strip()
            return title, description
        except Exception:
            # Title is cosmetic — don't fail the whole fetch for it
            return "", ""
 
    # ── Entrez call with retry ────────────────────────────────────────────────
 
    def _entrez_call(self, func, **kwargs) -> str:
        """
        Call a Biopython Entrez function with automatic retry on network error.
        Returns the response as a decoded string.
        Raises NcbiFetchError after _MAX_RETRIES failed attempts.
        """
        last_error: Exception | None = None
 
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                handle   = func(**kwargs)
                raw      = handle.read()
                handle.close()
 
                # Biopython may return bytes or str
                text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
 
                # Check for NCBI application-level error in the XML body
                if "<ERROR>" in text or "<error>" in text:
                    try:
                        root = ET.fromstring(text)
                        err  = (root.findtext("ERROR") or root.findtext("error") or "").strip()
                        if err:
                            raise NcbiFetchError(f"NCBI returned an error: {err}")
                    except NcbiFetchError:
                        raise
                    except ET.ParseError:
                        pass   # not XML — ignore
 
                return text
 
            except NcbiFetchError:
                raise   # our own errors — don't retry
 
            except Exception as exc:
                last_error = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY * attempt)
 
        # All retries exhausted
        detail = str(last_error)
 
        # Translate common low-level errors into helpful messages
        if "403" in detail or "Forbidden" in detail:
            msg = (
                "NCBI blocked the connection (HTTP 403). "
                "This usually means:\n"
                "  • No email address set in ncbi_service.py (ENTREZ_EMAIL)\n"
                "  • Too many requests — wait 30 seconds and try again\n"
                "  • Your IP has been rate-limited by NCBI"
            )
        elif "SSL" in detail or "certificate" in detail.lower():
            msg = (
                "SSL certificate error connecting to NCBI. "
                "Check your internet connection and proxy settings."
            )
        elif "timed out" in detail.lower() or "timeout" in detail.lower():
            msg = (
                f"NCBI request timed out after {_MAX_RETRIES} attempts. "
                "NCBI may be under heavy load. Please try again in a few minutes."
            )
        elif any(f"[Errno {n}]" in detail or f"[Errno {n}]" in detail
                  or (hasattr(last_error, 'args') and
                      last_error.args and last_error.args[0] in _DNS_ERRNOS)
                  for n in _DNS_ERRNOS):
            msg = (
                "DNS lookup failed — your computer cannot resolve "
                "'eutils.ncbi.nlm.nih.gov'.\n"
                "Check your internet connection or VPN settings.\n"
                f"Run  check_connectivity()  for a detailed diagnosis."
            )
        elif "nodename" in detail.lower() or "not known" in detail.lower() or "name resolution" in detail.lower():
            msg = (
                "DNS lookup failed — your computer cannot resolve "
                "'eutils.ncbi.nlm.nih.gov'.\n\n"
                "Most likely causes:\n"
                "  • No internet connection\n"
                "  • VPN or firewall blocking NCBI\n"
                "  • DNS server not responding\n\n"
                "Try: curl https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            )
        else:
            msg = (
                f"Could not connect to NCBI after {_MAX_RETRIES} attempts. "
                f"Check your internet connection.\nDetail: {detail}"
            )
 
        raise NcbiFetchError(msg)
 
 
# ── Utilities ─────────────────────────────────────────────────────────────────
 
def _safe_int(value: str, default: int = 0) -> int:
    """Convert a string to int, returning *default* on any failure."""
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default
 
 
# ── DNS / connectivity pre-flight ─────────────────────────────────────────────
 
# DNS error numbers that mean "hostname not found"
_DNS_ERRNOS = {
    8,       # macOS:   nodename nor servname provided, or not known
    -2,      # Linux:   Name or service not known
    -3,      # Linux:   Temporary failure in name resolution
    11001,   # Windows: No such host is known
    11004,   # Windows: The requested name is valid but no data was found
}
 
_NCBI_HOST = "eutils.ncbi.nlm.nih.gov"
 
 
def check_connectivity() -> tuple[bool, str]:
    """
    Quick pre-flight DNS + TCP check against NCBI before sending any API calls.
 
    Returns
    -------
    (reachable: bool, error_message: str)
    error_message is empty string when reachable is True.
 
    This runs in ~1 second and gives a precise diagnosis instead of the
    generic 'Could not connect after 3 attempts' message that appears after
    a 5-second wait.
    """
    try:
        # Step 1 – DNS: can we resolve the hostname at all?
        socket.getaddrinfo(_NCBI_HOST, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        errno_code = e.args[0] if e.args else 0
 
        if errno_code in _DNS_ERRNOS:
            return False, (
                f"DNS lookup failed for '{_NCBI_HOST}' (error {errno_code}).\n\n"
                "Your computer cannot resolve the NCBI hostname. "
                "Common causes and fixes:\n\n"
                "  1. No internet connection\n"
                "     → Check Wi-Fi / Ethernet is connected.\n\n"
                "  2. Corporate VPN or firewall blocking NCBI\n"
                "     → Disconnect VPN and try again, or ask your IT team\n"
                "       to allow outbound HTTPS to eutils.ncbi.nlm.nih.gov\n\n"
                "  3. DNS server not responding\n"
                "     → Try switching to Google DNS (8.8.8.8) or\n"
                "       Cloudflare DNS (1.1.1.1) in your network settings.\n\n"
                "  4. System /etc/hosts blocking the domain\n"
                "     → Check that eutils.ncbi.nlm.nih.gov is not redirected\n"
                "       to 127.0.0.1 or 0.0.0.0 in your hosts file.\n\n"
                f"You can test manually by running in your terminal:\n"
                f"    curl https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            )
        return False, (
            f"Network error resolving NCBI hostname: {e}\n"
            "Check your internet connection."
        )
 
    except OSError as e:
        return False, f"Network error: {e}"
 
    try:
        # Step 2 – TCP: can we open a connection on port 443?
        conn = socket.create_connection((_NCBI_HOST, 443), timeout=5)
        conn.close()
    except (socket.timeout, OSError) as e:
        return False, (
            f"Could not open a TCP connection to {_NCBI_HOST}:443.\n"
            "NCBI may be temporarily unreachable, or a firewall is blocking "
            "outbound HTTPS. Try again in a minute."
        )
 
    return True, ""