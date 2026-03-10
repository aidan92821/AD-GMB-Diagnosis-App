from Bio import Entrez
import os
import sqlite3
import subprocess

# make sure that in the UI, user knows they can only download max 4 runs at a time
# this function downloads one run at a time if the run is specified
# it can download up to 4 runs at a time if no run is specified
def get_runs(email, bioproject, srr=None, n_runs=1):
    
    Entrez.email = email
    
    # only bioproject is specified, get first n_runs runs
    if srr is None:
        handle = Entrez.esearch(
            db='sra',
            term=bioproject,
            retmax=n_runs
        )
        record = Entrez.read(handle)
        ids = record['IdList']
        handle = Entrez.esummary(db="sra", id=",".join(ids))
    # srr run was specified
    else:
        handle = Entrez.esummary(db='sra', id=srr)

    summary = Entrez.read(handle)

    # get list of runs or singular run
    runs = []
    for sample in summary:
        runs.append(sample["Runs"].split()[1].split(sep='=')[1].strip('\"'))

    # create temporary directories for fetching
    # !!! -----> the actual path to run in application needs to be determined
    # !!! -----> the following are temporary paths
    subprocess.run(['mkdir', '-p', 
                    f"data/{bioproject}/fastq_files"])
    subprocess.run(['mkdir', '-p', 
                    f"data/{bioproject}/qiime_files"])

    

# the output_dir should have some reference to the bioproject id
def fetch_runs(runs, output_dir):
    
    # get the number of cores from user's machine
    # and calculate how many to use for the process
    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    # fetch from NCBI and convert to fastq files -> output_dir
    for run in runs:
        subprocess.run(['fasterq-dump', run, 
                        '--split-files', 
                        '--threads', cores,
                        '--outdir', output_dir,],
                        check=True)

# both input_dir and output_dir should have some reference to bioproject id
def write_manifest(input_dir, output_dir):
    pass

# pass the fastq data to the database and clear the temporary directories
def fastq_to_db(input_dir):
    pass

# testing
# get_runs('emmanicolego@gmail.com', 'PRJNA1028813')