'''
Fetch and Preprocess Pipeline
This module is what the GUI interacts with upon user request to fetch and preprocess data.
'''
from db_import import parse_feat_tax_seqs, parse_feature_counts, parse_genus_table
from fetch_data import fetch_ncbi_data
import os
from qiime_preproc import qiime_preprocess, download_classifier
from services import create_project, create_run, ingest_run_data, get_or_create_user, get_project_overview


CLASSIFIER = 'silva-138-99-nb-classifier.qza'
SOURCE = 'https://data.qiime2.org/classifiers/sklearn-1.4.2/silva'

def run_pipeline(bioproject: str, project_id, username: str, project_name: str, srr=None, n_runs=1):

    # get or create user
    user = get_or_create_user(username=username)

    # fetch fastq file(s) from ncbi
    lib_layout = fetch_ncbi_data(bioproject=bioproject,
                                 srr=srr,
                                 n_runs=n_runs)
    
    # download classifier if it does not exist yet
    if CLASSIFIER not in os.listdir('taxa_classifier'):
        download_classifier(classifier_url=f"{SOURCE}/{CLASSIFIER}")

    # paired ends
    if lib_layout['paired']:
        prepocess_parse_import(bioproject=bioproject, project_id=project_id, project_name=project_name, lib_layout='paired')
    
    # single ends
    if lib_layout['single']:
        prepocess_parse_import(bioproject=bioproject, project_id=project_id, project_name=project_name, lib_layout='single')


def prepocess_parse_import(bioproject: str, project_id, project_name: str, lib_layout: str, user: dict):
    
    data_dir = f"data/{bioproject}/"
    
    # preprocess
    qiime_preprocess(bioproject=bioproject,
                    lib_layout=lib_layout)
    
    # parse the data tables for db
    abundances = parse_genus_table(genus=f"{data_dir}/qiime/{lib_layout}/genus-table.tsv")
    feature_seqs = parse_feat_tax_seqs(tax=f"{data_dir}/qiime/{lib_layout}/taxonomy.tsv",
                        seqs=f"{data_dir}/reps-tree/{lib_layout}/dna-sequences.fasta")
    feature_counts = parse_feature_counts(feat=f"{data_dir}/qiime/{lib_layout}/feature-table.tsv")

    # import to database
    # if project does not exist, make one and add runs
    if project_id is None:
        project = create_project(user_id=user['user_id'], name=project_name)
    # otherwise, use existing project to add runs
    else:
        project = get_project_overview(project_id=project_id)
    # add runs and import bulk processed data to database
    for run, row in abundances.items():
        db_run = create_run(project_id=project['project_id'], source='ncbi', srr_accession=run,
                            bio_proj_accession=bioproject, library_layout=lib_layout)
        ingest_run_data(run_id=db_run['run_id'], genus_rows=row, features=feature_seqs, feature_counts=feature_counts)