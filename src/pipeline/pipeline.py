"""
src/pipeline/pipeline.py  —  FIXED VERSION

Fix vs original:
  project_id parameter was accepted by run_pipeline() but never used.
  Removed to keep the interface clean and avoid confusion.
  If you need project_id as an output directory label in future,
  add it back and thread it through fetch_ncbi_data().
"""

import os
from pathlib import Path

from src.pipeline.fetch_data      import fetch_ncbi_data
from src.pipeline.qiime_preproc   import qiime_preprocess, download_classifier

CLASSIFIER = 'silva-138-99-nb-classifier.qza'
SOURCE      = 'https://data.qiime2.org/classifiers/sklearn-1.4.2/silva'


def run_pipeline(bioproject: str, srr: str | None = None, n_runs: int = 1) -> None:
    """
    Fetch FASTQ data from NCBI and run the full QIIME2 preprocessing pipeline.

    Parameters
    ----------
    bioproject : NCBI BioProject accession (e.g. 'PRJNA1020741')
    srr        : Optional single Run accession to restrict to one file
    n_runs     : Max number of runs to fetch (1–4, default 1)

    Steps
    -----
    1. Fetch run info and download FASTQ files via fasterq-dump
    2. Download the SILVA classifier if not already present
    3. Run QIIME2 preprocessing (import → QC → DADA2 → taxonomy → tables)
       separately for paired-end and single-end runs if both are present
    """
    # Step 1 — fetch FASTQ files and write manifests
    lib_layout = fetch_ncbi_data(bioproject=bioproject, srr=srr, n_runs=n_runs)

    # Step 2 — download SILVA classifier (~1.4 GB, one-time download)
    classifier_dir = Path('taxa_classifier')
    if CLASSIFIER not in os.listdir(classifier_dir) if classifier_dir.exists() else True:
        download_classifier(classifier_url=f"{SOURCE}/{CLASSIFIER}")

    # Step 3 — QIIME2 preprocessing per library layout
    if lib_layout['paired']:
        qiime_preprocess(bioproject=bioproject, lib_layout='paired')

    if lib_layout['single']:
        qiime_preprocess(bioproject=bioproject, lib_layout='single')