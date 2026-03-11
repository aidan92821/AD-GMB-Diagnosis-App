from Bio import Entrez
import csv
import pandas as pd
from pathlib import Path
import io, os
import sqlite3
import subprocess

# make sure that in the UI, user knows they can only download max 4 runs at a time
# this function downloads one run at a time if the run is specified
# it can download up to 4 runs at a time if no run is specified
# returns two lists of strings: paired end runs and single end runs
def get_runs(bioproject, srr=None, n_runs=1):

    # fetch information about the runs in the bioproject into a csv
    result = subprocess.run(
        f"esearch -db sra -query {bioproject} | efetch -format runinfo",
        shell=True,
        capture_output=True,
        text=True,
        check=True )
    info = pd.read_csv(io.StringIO(result.stdout))

    # only bioproject is specified
    if srr is None:
        # select the first n_runs runs from the dataset
        info = info.head(n_runs)

        # determine which are paired end and which are single
        paired_runs = info.loc[info['LibraryLayout'] == 'PAIRED', 'Run'].tolist()
        single_runs = info.loc[info['LibraryLayout'] == 'SINGLE', 'Run'].tolist()
    # run id is specified
    else: 
        # get the specific run
        row = info.loc[info['Run'] == srr]

        # determine paired or single end
        paired_runs = row.loc[row['LibraryLayout'] == 'PAIRED', 'Run'].tolist()
        single_runs = row.loc[row['LibraryLayout'] == 'SINGLE', 'Run'].tolist()
    
    return paired_runs, single_runs


# the output_dir should have some reference to the bioproject id
def fetch_runs(bioproject, paired_runs, single_runs):

    # create temporary directories for fetching
    # !!! -----> the actual path to run in application needs to be determined
    # !!! -----> the following are temporary paths
    output_dir_fastq = f"data/{bioproject}/fastq"
    Path(f"{output_dir_fastq}/paired").mkdir(parents=True, exist_ok=True)
    Path(f"{output_dir_fastq}/single").mkdir(parents=True, exist_ok=True)
    
    # get the number of cores from user's machine
    # and calculate how many to use for the process
    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    # fetch from NCBI and convert to fastq files -> output_dir
    for run in paired_runs:
        subprocess.run(['fasterq-dump', run, '--split-files', 
                        '--threads', cores, 
                        '--outdir', f"{output_dir_fastq}/paired"],
                       check=True)
    for run in single_runs:
        subprocess.run(['fasterq-dump', run, '--split-files', 
                        '--threads', cores, 
                        '--outdir', f"{output_dir_fastq}/single"],
                       check=True)

# both input_dir should be abs path to data/bioproject/fastq/
def write_manifest(bioproject):

    input_dir = f"data/{bioproject}/fastq"

    # create the temporary qiime directory
    output_dir_qiime = f"data/{bioproject}/qiime"
    Path(f"{output_dir_qiime}").mkdir(exist_ok=True)

    # list the fastq files in the paired end dir
    paired_files = os.listdir(f"{input_dir}/paired")
    # write the paired manifest file for qiime processing
    if paired_files:
        # separate the forward and reverse fastq files
        forward, reverse = [], []
        for file in paired_files:
            if '_1.fastq' in file:
                forward.append(file)
            elif '_2.fastq' in file:
                reverse.append(file)
        
        # open the manifest file for writing
        with open(f"{output_dir_qiime}/manifest_paired.tsv", "w", newline="") as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(['sample-id', 'forward-absolute-filepath', 'reverse-absolute-filepath'])
            for f, r in zip(forward, reverse):
                writer.writerow([f"{f[:-8]}", Path(f"{input_dir}/paired/{f}").resolve(), Path(f"{input_dir}/paired/{r}").resolve()]) # -8 removes _#.fastq chars and keeps srr # only

    # list the fastq files in the single end dir
    single_files = os.listdir(f"{input_dir}/single")
    # write the single manifest file for qiime processing
    if single_files:
        # open the manifest file for writing
        with open(f"{output_dir_qiime}/manifest_single.tsv", "w", newline="") as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(['sample-id', 'absolute-filepath'])
            for s in single_files:
                writer.writerow([f"{s[:-6]}", Path(f"{input_dir}/single/{s}").resolve()]) # -6 removes .fastq chars and keeps srr # only


# testing
print("specifying only BIOPROJECT and n_runs=4")
paired_runs, single_runs = get_runs('PRJNA1334232', n_runs=4)
print(f"paired: {paired_runs}, single: {single_runs}")

print("checking subprocess functionality")
fetch_runs('PRJNA1334232', paired_runs=paired_runs, single_runs=single_runs)

print('checking manifest functionality')
write_manifest('PRJNA1334232')