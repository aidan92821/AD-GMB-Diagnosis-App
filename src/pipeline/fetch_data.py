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


    if srr:
        filtered = info.loc[info['Run'] == srr]
        info = filtered if not filtered.empty else info.head(n_runs)
    else:
        info = info.head(n_runs)

    if info.empty:
        raise RuntimeError(
            f"No runs found for BioProject '{bioproject}'"
            + (f" with run accession '{srr}'" if srr else "") + "."
        )


    # determine paired or single end
    paired_runs = info.loc[info['LibraryLayout'] == 'PAIRED', 'Run'].tolist()
    single_runs = info.loc[info['LibraryLayout'] == 'SINGLE', 'Run'].tolist()

    return paired_runs, single_runs


# lib_layout = 'paired' or 'single'
# runs = list of SRR Accessions
def download_runs(runner, bioproject: str, lib_layout: str, runs: list[str], state: AppState) -> AppState:
    
    # create temporary directory for fetching
    APP_DIR = Path(__file__).parent
    SRA_BIN = APP_DIR / "bin" / "sratoolkit" / "bin"
    output_dir_fastq = str((APP_DIR / f"data/{bioproject}/fastq/{lib_layout}").resolve())
    Path(output_dir_fastq).mkdir(parents=True, exist_ok=True)

    # get the number of cores from user's machine
    # and calculate how many to use for the process
    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    # fetch from NCBI and convert to fastq files -> output_dir
    for run in runs:
        subprocess.run(['fasterq-dump', run, '--split-files',
                        '--threads', cores,
                        '--outdir', output_dir_fastq],
                        check=True)


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
                for f, r in zip(forward, reverse):
                    writer.writerow([f"{f[:-8]}",
                                     Path(f"{input_dir}/{f}").resolve(),
                                     Path(f"{input_dir}/{r}").resolve()])
            else:
                # single end
                writer.writerow(['sample-id',
                                 'absolute-filepath'])
                for s in files:
                    writer.writerow([f"{s[:-6]}",
                                     Path(f"{input_dir}/{s}").resolve()])


# clean up the temporary files
# after data tables have been imported to the database, remove them
# the only files needed after importing are rep-seqs.fasta and tree.nwk
def cleanup(bioproject):
    shutil.rmtree(Path("data") / bioproject / "fastq")
    shutil.rmtree(Path("data") / bioproject / "qiime")


'''DEPRECATED'''
def fetch_ncbi_data(email, runner, bioproject: str, state: AppState, srr=None, n_runs=1) -> dict[str: bool]:

    lib_layout = {
        'paired': False,
        'single': False,
    }

    paired_runs, single_runs = get_runs(bioproject=bioproject,
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
