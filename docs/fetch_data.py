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

    runs = []
    for sample in summary:
        runs.append(sample["Runs"].split()[1].split(sep='=')[1].strip('\"'))

    print(runs)



# testing
get_runs('emmanicolego@gmail.com', 'PRJNA1028813')