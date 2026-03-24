"""
src/pipeline/qiime_preproc.py  —  FIXED VERSION

Bug fixed vs original:
  Module-level call to get_conda_env_path() crashed on import when the
  qiime2 conda environment was not installed, taking down the whole GUI.

Fix:
  All env-dependent constants (env_path, BIN, QIIME, BIOM, env) are now
  computed lazily inside _get_qiime_env(), called only when a pipeline
  function is actually invoked.  The GUI can start and show the Overview
  page even if QIIME2 is not installed.  The user only sees an error when
  they click a button that triggers preprocessing.
"""

import os
from pathlib import Path
import subprocess
import urllib.request

from src.pipeline.environment import get_conda_env_path
from src.pipeline.qc import get_trunc


ENV_NAME = "qiime2-amplicon-2024.10"

# Cached env configuration — populated on first use
_qiime_env_cache: dict | None = None


def _get_qiime_env() -> dict:
    """
    Lazily resolve the QIIME2 conda environment path.

    Returns a dict with keys:
        qiime  – Path to the qiime executable
        biom   – Path to the biom executable
        env    – os.environ copy with PATH and CONDA_PREFIX set

    Raises RuntimeError if the environment is not found.
    This error is caught by the GUI's pipeline worker and shown
    as a user-friendly message rather than crashing the app.
    """
    global _qiime_env_cache
    if _qiime_env_cache is not None:
        return _qiime_env_cache

    env_path = get_conda_env_path(ENV_NAME)
    bin_dir  = env_path / "bin"

    env_vars = os.environ.copy()
    env_vars["PATH"]          = f"{bin_dir}:{env_vars['PATH']}"
    env_vars["CONDA_PREFIX"]  = str(env_path)

    _qiime_env_cache = {
        "qiime": bin_dir / "qiime",
        "biom":  bin_dir / "biom",
        "env":   env_vars,
    }
    return _qiime_env_cache


# ── Pipeline steps ────────────────────────────────────────────────────────────

def import_samples(bioproject: str, lib_layout: str) -> None:
    """Import FASTQ files into a QIIME2 artifact using the manifest."""
    cfg = _get_qiime_env()

    output_dir  = f"data/{bioproject}/qiime/{lib_layout}"
    input_type  = (
        'SampleData[PairedEndSequencesWithQuality]'
        if lib_layout == 'paired'
        else 'SampleData[SequencesWithQuality]'
    )
    input_format = (
        'PairedEndFastqManifestPhred33V2'
        if lib_layout == 'paired'
        else 'SingleEndFastqManifestPhred33V2'
    )

    if os.listdir(f"data/{bioproject}/fastq/{lib_layout}"):
        subprocess.run([
            str(cfg["qiime"]), 'tools', 'import',
            '--type',         input_type,
            '--input-path',   f"{output_dir}/manifest.tsv",
            '--output-path',  f"{output_dir}/demux.qza",
            '--input-format', input_format,
        ], check=True, env=cfg["env"])


def qc(bioproject: str, lib_layout: str) -> dict:
    """
    Run QIIME2 demux summarize and compute truncation positions.
    Returns {'forward': int, 'reverse': int} or {'single': int}.
    """
    cfg    = _get_qiime_env()
    io_dir = f"data/{bioproject}/qiime/{lib_layout}"

    subprocess.run([
        str(cfg["qiime"]), 'demux', 'summarize',
        '--i-data',          f"{io_dir}/demux.qza",
        '--o-visualization', f"{io_dir}/demux.qzv",
    ], check=True, env=cfg["env"])

    return get_trunc(bioproject, lib_layout)


def dada2_denoise(
    bioproject: str,
    lib_layout: str,
    trunc_f: int | None = None,
    trunc_r: int | None = None,
    trunc_s: int | None = None,
) -> None:
    """
    Run DADA2 denoising (paired or single end).

    FIX: added explicit error when neither trunc_f nor trunc_s is provided,
    so silent no-op failures are impossible.
    """
    cfg    = _get_qiime_env()
    io_dir = f"data/{bioproject}/qiime/{lib_layout}"

    cores = str(max((os.cpu_count() or 4) - 4, 1))

    if trunc_f is not None:
        # Paired-end denoising
        if trunc_r is None:
            raise ValueError("trunc_r is required when trunc_f is provided (paired-end)")
        subprocess.run([
            str(cfg["qiime"]), 'dada2', 'denoise-paired',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-trim-left-f',  '17',
            '--p-trim-left-r',  '21',
            '--p-trunc-len-f',  str(trunc_f),
            '--p-trunc-len-r',  str(trunc_r),
            '--p-n-threads',    cores,
            '--o-table',                   f"{io_dir}/table.qza",
            '--o-representative-sequences',f"{io_dir}/rep-seqs.qza",
            '--o-denoising-stats',         f"{io_dir}/stats.qza",
        ], check=True, env=cfg["env"])

    elif trunc_s is not None:
        # Single-end denoising
        subprocess.run([
            str(cfg["qiime"]), 'dada2', 'denoise-single',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-trim-left',   '17',
            '--p-trunc-len',   str(trunc_s),
            '--p-n-threads',   cores,
            '--o-table',                   f"{io_dir}/table.qza",
            '--o-representative-sequences',f"{io_dir}/rep-seqs.qza",
            '--o-denoising-stats',         f"{io_dir}/stats.qza",
        ], check=True, env=cfg["env"])

    else:
        # FIX: was a silent no-op; now raises so the caller knows something is wrong
        raise ValueError(
            "dada2_denoise: must provide either trunc_f (paired) or trunc_s (single). "
            "Both are None — check that get_trunc() returned valid values."
        )


def classify_taxa(bioproject: str, lib_layout: str) -> None:
    """Classify representative sequences against the SILVA database."""
    cfg             = _get_qiime_env()
    classifier_path = "taxa_classifier/silva-138-99-nb-classifier.qza"
    io_dir          = f"data/{bioproject}/qiime/{lib_layout}"

    subprocess.run([
        str(cfg["qiime"]), 'feature-classifier', 'classify-sklearn',
        '--i-classifier', classifier_path,
        '--i-reads',      f"{io_dir}/rep-seqs.qza",
        '--o-classification', f"{io_dir}/taxonomy.qza",
    ], check=True, env=cfg["env"])


def create_tables(bioproject: str, lib_layout: str) -> None:
    """
    Export QIIME2 artifacts to TSV/FASTA files consumed by the GUI:
      • rep-seqs.fasta      — representative ASV sequences
      • feature-table.tsv   — raw ASV counts per sample
      • taxonomy.tsv        — ASV → taxonomic classification
      • genus-table.tsv     — genus-level relative abundance
    """
    cfg    = _get_qiime_env()
    io_dir = f"data/{bioproject}/qiime/{lib_layout}"

    # Representative sequences (kept for phylogenetic tree building)
    Path(f"data/{bioproject}/reps-tree/{lib_layout}").mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(cfg["qiime"]), 'tools', 'export',
        '--input-path',  f"{io_dir}/rep-seqs.qza",
        '--output-path', f"data/{bioproject}/reps-tree/{lib_layout}",
    ], check=True, env=cfg["env"])

    # Feature table → BIOM → TSV
    subprocess.run([
        str(cfg["qiime"]), 'tools', 'export',
        '--input-path',  f"{io_dir}/table.qza",
        '--output-path', f"{io_dir}/features",
    ], check=True, env=cfg["env"])
    subprocess.run([
        str(cfg["biom"]), 'convert',
        '-i', f"{io_dir}/features/feature-table.biom",
        '-o', f"{io_dir}/feature-table.tsv",
        '--to-tsv',
    ], check=True, env=cfg["env"])

    # Taxonomy map
    subprocess.run([
        str(cfg["qiime"]), 'tools', 'export',
        '--input-path',  f"{io_dir}/taxonomy.qza",
        '--output-path', f"{io_dir}",
    ], check=True, env=cfg["env"])

    # Genus-level relative abundance
    subprocess.run([
        str(cfg["qiime"]), 'taxa', 'collapse',
        '--i-table',    f"{io_dir}/table.qza",
        '--i-taxonomy', f"{io_dir}/taxonomy.qza",
        '--p-level',    '6',  # 6 = genus level in SILVA taxonomy
        '--o-collapsed-table', f"{io_dir}/genus-table.qza",
    ], check=True, env=cfg["env"])
    subprocess.run([
        str(cfg["qiime"]), 'feature-table', 'relative-frequency',
        '--i-table', f"{io_dir}/genus-table.qza",
        '--o-relative-frequency-table', f"{io_dir}/genus-relfreq.qza",
    ], check=True, env=cfg["env"])
    subprocess.run([
        str(cfg["qiime"]), 'tools', 'export',
        '--input-path',  f"{io_dir}/genus-relfreq.qza",
        '--output-path', f"{io_dir}/genus",
    ], check=True, env=cfg["env"])
    subprocess.run([
        str(cfg["biom"]), 'convert',
        '-i', f"{io_dir}/genus/feature-table.biom",
        '-o', f"{io_dir}/genus-table.tsv",
        '--to-tsv',
    ], check=True, env=cfg["env"])


def qiime_preprocess(bioproject: str, lib_layout: str) -> None:
    """
    Full QIIME2 preprocessing pipeline for one library layout.
    Runs: import → QC → DADA2 denoising → taxonomy → table export.
    """
    import_samples(bioproject=bioproject, lib_layout=lib_layout)

    trunc = qc(bioproject=bioproject, lib_layout=lib_layout)

    if lib_layout == 'paired':
        dada2_denoise(
            bioproject=bioproject,
            lib_layout=lib_layout,
            trunc_f=trunc['forward'],
            trunc_r=trunc['reverse'],
        )
    elif lib_layout == 'single':
        dada2_denoise(
            bioproject=bioproject,
            lib_layout=lib_layout,
            trunc_s=trunc['single'],
        )

    classify_taxa(bioproject=bioproject, lib_layout=lib_layout)
    create_tables(bioproject=bioproject, lib_layout=lib_layout)


def download_classifier(classifier_url: str) -> None:
    """Download the SILVA classifier .qza if not already present."""
    output_dir     = Path("taxa_classifier")
    output_dir.mkdir(exist_ok=True)
    classifier_file = output_dir / classifier_url.split("/")[-1]
    print(f"Downloading classifier to {classifier_file} (~1.4 GB) …")
    urllib.request.urlretrieve(classifier_url, classifier_file)
    print("Download complete.")