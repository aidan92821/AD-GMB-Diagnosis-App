'''
Fetch and Preprocess Pipeline
Module GUI interacts with upon user request to fetch and preprocess data.
'''
from fetch_data import fetch_ncbi_data
from qiime_preproc import qiime_preprocess, download_classifier
import os
from pathlib import Path

CLASSIFIER = 'silva-138-99-nb-classifier.qza'
SOURCE = 'https://data.qiime2.org/classifiers/sklearn-1.4.2/silva'

def run_pipeline(project_id, bioproject, srr=None, n_runs=1):

    lib_layout = fetch_ncbi_data(bioproject=bioproject,
                                 srr=srr,
                                 n_runs=n_runs)
    
    # download classifier if it does not exist yet
    
    if CLASSIFIER not in os.listdir('taxa_classifier'):
        download_classifier(classifier_url=f"{SOURCE}/{CLASSIFIER}")

    if lib_layout['paired']:
        qiime_preprocess(bioproject=bioproject,
                        lib_layout='paired')
    
    if lib_layout['single']:
        qiime_preprocess(bioproject=bioproject,
                        lib_layout='single')