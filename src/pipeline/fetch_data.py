from __future__ import annotations
import csv
import pandas as pd
from pathlib import Path
from typing import TYPE_CHECKING
import os
import shutil

if TYPE_CHECKING:
    from models.app_state import AppState

# make sure that in the UI, user knows they can only download max 4 runs at a time
# this function downloads one run at a time if the run is specified
# it can download up to 4 runs at a time if no run is specified
# returns two lists of strings: paired end runs and single end runs (SRR Accessions)
def fetch_runs(email, runner, bioproject: str, srr=None, n_runs=1) -> tuple[list[str], list[str], dict]:

    env = os.environ.copy()
    env.update({
        "EMAIL": email
    })

    # fetch information about the runs in the bioproject into a csv
    esearch = runner.es_run([
        "esearch", 
        "-db", "sra",
        "-query", bioproject
    ], env=env)
    result = runner.ef_run([
        "efetch",
        "-format", "runinfo"
    ], es_process=esearch, env=env)
    
    
    info = pd.read_csv(result)

    if info.empty:
        raise ValueError(f"No run info returned from NCBI for bioproject '{bioproject}'. "
                         "Check that the accession is valid and your email is set.")

    # only bioproject is specified
    if srr is None or info.loc[info['Run'] == srr].empty:
        # select the first n_runs runs from the dataset if srr is None
        # or select the first run from the dataset if srr not associated with this bioproject
        # (n_runs will == 1 if srr is supplied to GUI)
        info = info.head(n_runs)
    # run id is specified
    else:
        # get the specific run
        info = info.loc[info['Run'] == srr]

    if info.empty:
        raise ValueError(f"No matching runs found for bioproject '{bioproject}'"
                         + (f" / SRR '{srr}'" if srr else "") + ".")

    # determine paired or single end
    paired_runs = info.loc[info['LibraryLayout'] == 'PAIRED', 'Run'].tolist()
    single_runs = info.loc[info['LibraryLayout'] == 'SINGLE', 'Run'].tolist()

    # get the run record (using a dict instead of RunRecord class)
    runs: list[dict] = []
    for i, (_, row) in enumerate(info.iterrows(), start=1):
        layout = str(row.get("LibraryLayout", "")).upper()
        if layout not in {"PAIRED", "SINGLE"}:
            layout = "PAIRED"

        runs.append({
            'run_accession'    : row.get("Run", ""),
            'label'            : f"R{i}",
            'read_count'       : int(row.get("spots", 0)),
            'base_count'       : int(row.get("bases", 0)),
            'library_layout'   : layout,
            'library_strategy' : row.get("LibraryStrategy", ""),
            'platform'         : row.get("Platform", ""),
            'instrument'       : row.get("Model", ""),
            'sample_accession' : row.get("BioSample", ""),
            'organism'         : row.get("ScientificName", ""),
            'uploaded'         : False,
            'qiime_error'      : ""
        })

    # get project meta data
    first       = info.iloc[0]
    project_uid = str(first.get("ProjectID", "")).strip()
    sra_study   = str(first.get("SRAStudy", "")).strip()
    organism    = str(first.get("ScientificName", "")).strip()

    # get the project record (using a dict instead of ProjectRecord class)
    project = {
        'bioproject_id' : bioproject,
        'project_uid'   : project_uid,
        'sra_study_id'  : sra_study,
        'title'         : f"{bioproject}",
        'description'   : "",
        'organism'      : organism,
        'runs'          : runs,
    }

    return single_runs, paired_runs, project


# lib_layout = 'paired' or 'single'
# runs = list of SRR Accessions
def download_runs(runner, bioproject: str, lib_layout: str, runs: list[str], state: AppState) -> AppState:

    APP_DIR = Path(__file__).parent
    SRA_BIN = APP_DIR / "bin" / "sratoolkit" / "bin"
    output_dir = Path(APP_DIR / f"data/{bioproject}/fastq/{lib_layout}").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cores = str(max(os.cpu_count() - 4, 1))

    for run in runs:
        # Skip download if files already present on disk
        already_paired  = (output_dir / f"{run}_1.fastq").exists()
        already_single  = (output_dir / f"{run}.fastq").exists()
        if already_paired or already_single:
            continue

        runner.fq_run([
            str(SRA_BIN / "fasterq-dump"), run, "--split-files",
            "--threads", cores,
            "--outdir", str(output_dir),
        ])

    return state


# lib_layout = 'paired' or 'single'
def write_manifest(bioproject: str, lib_layout: str, state: AppState) -> None:
    
    APP_DIR = Path(__file__).parent
    input_dir = str((APP_DIR / f"data/{bioproject}/fastq/{lib_layout}").resolve())
    output_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())
    
    # # create the temporary qiime directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # organize fastq types
    files = os.listdir(input_dir)
    if files:
        # if single, they will all be contained in files list
        forward, reverse = [], []
        for file in files:
            if '_1.fastq' in file:
                forward.append(file)
            elif '_2.fastq' in file:
                reverse.append(file)
        
        # open the manifest file for writing
        with open(f"{output_dir}/manifest.tsv", "w", newline="") as m:
            writer = csv.writer(m, delimiter='\t')
            if forward:
                # paired end
                writer.writerow(['sample-id',
                                 'forward-absolute-filepath',
                                 'reverse-absolute-filepath'])
                for f, r in zip(sorted(forward), sorted(reverse)):
                    srr = f[:-8]   # strip _1.fastq (8 chars)
                    if srr not in state.runs:
                        continue   # skip leftover files from previous fetches
                    state.runs[srr]['uploaded'] = True
                    writer.writerow([srr,
                                     str(Path(f"{input_dir}/{f}").resolve()),
                                     str(Path(f"{input_dir}/{r}").resolve())])
            else:
                # single end
                writer.writerow(['sample-id', 'absolute-filepath'])
                for s in files:
                    srr = s[:-6]   # strip .fastq (6 chars)
                    if srr not in state.runs:
                        continue   # skip leftover files from previous fetches
                    state.runs[srr]['uploaded'] = True
                    writer.writerow([srr,
                                     str(Path(f"{input_dir}/{s}").resolve())])


# clean up the temporary files
# after data tables have been imported to the database, remove them
# the only files needed after importing are rep-seqs.fasta and tree.nwk
def cleanup(bioproject: str):
    APP_DIR = Path(__file__).parent # pipeline/
    FASTQ_DIR = (APP_DIR / f"data/{bioproject}/fastq")
    QIIME_DIR = (APP_DIR / f"data/{bioproject}/qiime")
    
    shutil.rmtree(FASTQ_DIR, ignore_errors=True)
    shutil.rmtree(QIIME_DIR, ignore_errors=True)


'''DEPRECATED'''
def fetch_ncbi_data(email, runner, bioproject: str, state: AppState, srr=None, n_runs=1) -> dict[str: bool]:

    lib_layout = {
        'paired': False,
        'single': False,
    }

    paired_runs, single_runs, project = fetch_runs(email,
                                                   runner,
                                                   bioproject=bioproject,
                                                   srr=srr,
                                                   n_runs=n_runs)
    
    if paired_runs:
        state = download_runs(runner,
                              bioproject=bioproject,
                              lib_layout='paired',
                              runs=paired_runs,
                              state=state)
        write_manifest(bioproject=bioproject,
                       lib_layout='paired',
                       state=state)
        lib_layout['paired'] = True
    
    if single_runs:
        state = download_runs(runner,
                              bioproject=bioproject,
                              lib_layout='single',
                              runs=single_runs,
                              state=state)
        write_manifest(bioproject=bioproject,
                       lib_layout='single',
                       state=state)
        lib_layout['single'] = True
        
    return lib_layout
