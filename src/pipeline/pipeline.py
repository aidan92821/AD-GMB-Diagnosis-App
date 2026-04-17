'''
Fetch and Preprocess Pipeline
This module is what the GUI interacts with upon user request to fetch and preprocess data.
'''
from db_import import parse_feat_tax_seqs, parse_feature_counts, parse_genus_table
from fetch_data import fetch_ncbi_data
import os
from qiime_preproc import qiime_preprocess, download_classifier
from services.assessment_service import create_project, create_run, ingest_run_data, get_or_create_user, get_project_overview
from qiime2_runner import QiimeRunner

# get email from user -> db -> retrieve from db to use as argument here
def run_fetch(bioproject: str, email: str, srr: str=None, n_runs=1):

    CLASSIFIER = 'silva-138-99-nb-classifier.qza'
    SOURCE = 'https://data.qiime2.org/classifiers/sklearn-1.4.2/silva'

    # ensures exact environment is used
    runner = QiimeRunner()

    # fetch fastq file(s) from ncbi
    lib_layout = fetch_ncbi_data(email,
                                 runner,
                                 bioproject=bioproject,
                                 srr=srr,
                                 n_runs=n_runs)

    # download classifier if it does not exist yet
    if CLASSIFIER not in os.listdir('taxa_classifier'):
        download_classifier(classifier_url=f"{SOURCE}/{CLASSIFIER}")

    return lib_layout # to _on_fetch_request() in main_window.py


def preprocess_parse_import(runner: QiimeRunner, bioproject: str, lib_layout: str, user: dict, project_id, project_name: str=None) -> None:

    data_dir = f"data/{bioproject}/"

    # preprocess with qiime2
    qiime_preprocess(runner,
                     bioproject=bioproject,
                     lib_layout=lib_layout)

    # parse the data tables for db
    abundances = parse_genus_table(genus=f"{data_dir}/qiime/{lib_layout}/genus-table.tsv")
    feature_seqs = parse_feat_tax_seqs(tax=f"{data_dir}/qiime/{lib_layout}/taxonomy.tsv",
                        seqs=f"{data_dir}/reps-tree/{lib_layout}/dna-sequences.fasta")
    feature_counts = parse_feature_counts(feat=f"{data_dir}/qiime/{lib_layout}/feature-table.tsv")

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
