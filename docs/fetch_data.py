from Bio import Entrez
import csv
import pandas as pd
import io, os
import sqlite3
import subprocess

# make sure that in the UI, user knows they can only download max 4 runs at a time
# this function downloads one run at a time if the run is specified
# it can download up to 4 runs at a time if no run is specified
# returns two lists of strings: paired end runs and single end runs
def get_runs(email, bioproject, srr=None, n_runs=1):

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

    # create temporary directories for fetching
    # !!! -----> the actual path to run in application needs to be determined
    # !!! -----> the following are temporary paths
    subprocess.run(f"mkdir -p data/{bioproject}/fastq_files/paired")
    subprocess.run(f"mkdir -p data/{bioproject}/fastq_files/single")
    subprocess.run(f"mkdir -p data/{bioproject}/qiime_files")
    
    return paired_runs, single_runs


# the output_dir should have some reference to the bioproject id
def fetch_runs(paired_runs, single_runs, output_dir):
    
    # get the number of cores from user's machine
    # and calculate how many to use for the process
    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    # fetch from NCBI and convert to fastq files -> output_dir
    for run in paired_runs:
        subprocess.run(f"fasterq-dump {run} --split-files --threads {cores} --outdir {output_dir}/paired",
                       check=True)
    for run in single_runs:
        subprocess.run(f"fasterq-dump {run} --split-files --threads {cores} --outdir {output_dir}/single",
                       check=True)

# both input_dir and output_dir should have some reference to bioproject id
def write_manifest(input_dir, output_dir):

    # list the fastq files in the paired end dir
    paired_files = os.listdir(f"{input_dir}/paired")
    # write the paired manifest file for qiime processing
    if not paired_files:
        # separate the forward and reverse fastq files
        forward, reverse = [], []
        for file in paired_files:
            if '_1.fastq' in file:
                forward.append(file)
            elif '_2.fastq' in file:
                reverse.append(file)
        
        # open the manifest file for writing
        with open(f"{output_dir}/manifest_paired.tsv", "w", newline="") as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(['sample-id', 'forward-absolute-filepath', 'reverse-absolute-filepath'])
            for f, r in zip(forward, reverse):
                writer.writerow([f"{f[:-8]}", f"{input_dir}/paired/{f}", f"{input_dir}/paired/{r}"]) # -8 removes _#.fastq chars and keeps srr # only
            writer.writerow(['\n'])

    # list the fastq files in the single end dir
    single_files = os.listdir(f"{input_dir}/single")
    # write the single manifest file for qiime processing
    if not single_files:
        # open the manifest file for writing
        with open(f"{output_dir}/manifest_single.tsv", "w", newline="") as f:
            writer = csv.writer(f, delimiter='\t')
            writer.writerow(['sample-id', 'absolute-filepath'])
            for s in single_files:
                writer.writerow([f"{s[:-6]}", f"{input_dir}/single/{s}"]) # -6 removes .fastq chars and keeps srr # only
            writer.writerow(['\n'])


# testing
# get_runs('emmanicolego@gmail.com', 'PRJNA1028813')