'''
Fetch and Preprocess Pipeline
Module GUI interacts with upon user request to fetch and preprocess data.
'''
from fetch_data import fetch_ncbi_data
from qiime_preproc import qiime_preprocess

def run_pipeline(project_id, bioproject, srr=None, n_runs=1):

    lib_layout = fetch_ncbi_data(bioproject=bioproject,
                                 srr=srr,
                                 n_runs=n_runs)
    
    if lib_layout['paired']:
        qiime_preprocess(bioproject=bioproject,
                        lib_layout='paired')
    
    if lib_layout['single']:
        qiime_preprocess(bioproject=bioproject,
                        lib_layout='single')