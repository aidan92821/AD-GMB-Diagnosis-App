from __future__ import annotations
import os
from pathlib import Path
from src.pipeline.qc import get_trunc
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qiime2_runner import QiimeRunner


REF_PHYLO_DB = "sepp-refs-silva-128.qza"
REF_PHYLO_DB_DIR = "ref_phylo_db"
REF_PHYLO_LINK = "https://data.qiime2.org/2023.5/common/sepp-refs-silva-128.qza"


# lib_layout = 'paired' or 'single'
def import_samples(runner: QiimeRunner, bioproject: str, lib_layout: str, callback=None):

    APP_DIR = Path(__file__).parent
    input_dir = str((APP_DIR / f"data/{bioproject}/fastq/{lib_layout}").resolve())
    output_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    input_type = 'SampleData[PairedEndSequencesWithQuality]' \
                 if lib_layout == 'paired' \
                 else 'SampleData[SequencesWithQuality]'
    input_format = 'PairedEndFastqManifestPhred33V2' \
                   if lib_layout == 'paired' \
                   else 'SingleEndFastqManifestPhred33V2'

    # import runs
    if os.listdir(input_dir):
        runner.run([
            'qiime', 'tools', 'import',
            '--type', input_type,
            '--input-path', f"{output_dir}/manifest.tsv",
            '--output-path', f"{output_dir}/demux.qza",
            '--input-format', input_format
        ], callback=callback)


# lib_layout = 'paired' or 'single'
# returns a dict of size 0, 1 or 2
# 0 -> something weird happened
# 1 -> single with key: 'single'
# 2 -> paired with keys: 'forward', 'reverse' in that order
def qc(runner: QiimeRunner, bioproject: str, lib_layout: str, callback=None):

    APP_DIR = Path(__file__).parent
    io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # calculate summary statistics
    runner.run([
        'qiime', 'demux', 'summarize',
        '--i-data', f"{io_dir}/demux.qza",
        '--o-visualization', f"{io_dir}/demux.qzv"
    ], callback=callback)

    # get truncation positions for paired forward, paired reverse, and single
    return get_trunc(bioproject, lib_layout)


# lib_layout = 'paired' or 'single'
def dada2_denoise(runner: QiimeRunner, bioproject: str, lib_layout: str, trunc_f: int=None, trunc_r: int=None, trunc_s: int=None, callback=None):

    APP_DIR = Path(__file__).parent
    io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # get the number of cores from user's machine
    # and calculate how many to use for the process
    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    # paired
    if trunc_f:
        runner.run([
            'qiime', 'dada2', 'denoise-paired',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-trim-left-f', '17',
            '--p-trim-left-r', '21',
            '--p-trunc-len-f', str(trunc_f),
            '--p-trunc-len-r', str(trunc_r),
            '--p-n-threads', cores,
            '--o-table', f"{io_dir}/table.qza",
            '--o-representative-sequences', f"{io_dir}/rep-seqs.qza",
            '--o-denoising-stats', f"{io_dir}/stats.qza"
        ], callback=callback)

    # single
    elif trunc_s:
        runner.run([
            'qiime', 'dada2', 'denoise-single',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-trim-left', '17',
            '--p-trunc-len', str(trunc_s),
            '--p-n-threads', cores,
            '--o-table', f"{io_dir}/table.qza",
            '--o-representative-sequences', f"{io_dir}/rep-seqs.qza",
            '--o-denoising-stats', f"{io_dir}/stats.qza"
        ], callback=callback)


'''
classifier: silva-138-99-nb-classifier.qza
source: https://data.qiime2.org/classifiers/sklearn-1.4.2/silva/silva-138-99-nb-classifier.qza
'''
# lib_layout: 'paired' or 'single'
def classify_taxa(runner: QiimeRunner, bioproject: str, lib_layout: str, callback=None):

    APP_DIR = Path(__file__).parent
    classifier_path = str((APP_DIR / "taxa_classifier/silva-138-99-nb-classifier.qza").resolve())
    io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # call the classifier on the denoised data
    runner.run([
        'qiime', 'feature-classifier', 'classify-sklearn',
        '--i-classifier', classifier_path,
        '--i-reads', f"{io_dir}/rep-seqs.qza",
        '--o-classification', f"{io_dir}/taxonomy.qza"
    ], callback=callback)
    

def infer_phylogeny(runner: QiimeRunner, bioproject: str, lib_layout: str, callback=None) -> str:

    APP_DIR = Path(__file__).parent
    ref_phylo_db_dir_path = str((APP_DIR / REF_PHYLO_DB_DIR).resolve())
    reps_tree_dir = str((APP_DIR / f"data/{bioproject}/reps-tree/{lib_layout}").resolve())

    # get the number of cores from user's machine
    # and calculate how many to use for the process
    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    try:
        runner.run([
            'qiime', 'fragment-insertion', 'sepp',
            '--i-representative-sequences', f"{reps_tree_dir}/rep-seqs.qza",
            '--i-reference-database', f"{ref_phylo_db_dir_path}/{REF_PHYLO_DB}",
            '--o-tree', f"{reps_tree_dir}/insertion-tree.qza",
            '--o-placements', f"{reps_tree_dir}/insertion-placements.qza",
            '--p-threads', cores
        ])

        # produce the newick string from the inferred tree
        runner.run([
            'qiime', 'tools', 'export',
            '--input-path', f"{reps_tree_dir}/insertion-tree.qza",
            "--output-path", reps_tree_dir
        ])
    except Exception as e:
        if callback:
            callback(f"** tree error: {e}")

    # clean up the intermediate files
    runner.rm([f"{reps_tree_dir}/insertion-tree.qza",
               f"{reps_tree_dir}/insertion-placements.qza",
               f"{reps_tree_dir}/rep-seqs.qza"])
    
    return f"{reps_tree_dir}/tree.nwk"


# lib_layout: 'paired' or 'single'
def create_tables(runner: QiimeRunner, bioproject: str, lib_layout: str, callback=None):

    APP_DIR = Path(__file__).parent
    io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())
    reps_tree_dir = str((APP_DIR / f"data/{bioproject}/reps-tree/{lib_layout}").resolve())
    Path(reps_tree_dir).mkdir(parents=True, exist_ok=True)

    # feature table (asv counts) (feature-table.tsv)
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/table.qza",
        '--output-path', f"{io_dir}/features"
    ], callback=callback)
    runner.run([
        'biom', 'convert',
        '-i', f"{io_dir}/features/feature-table.biom",
        '-o', f"{io_dir}/feature-table.tsv",
        '--to-tsv'
    ], callback=callback)

    # asv to taxonomy map table (taxonomy.tsv)
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/taxonomy.qza",
        '--output-path', f"{io_dir}"
    ], callback=callback)

    # genus relative abundance table (genus-table.tsv)
    # collapse ASV table to genus level abundance
    runner.run([
        'qiime', 'taxa', 'collapse',
        '--i-table', f"{io_dir}/table.qza",
        '--i-taxonomy', f"{io_dir}/taxonomy.qza",
        '--p-level', str(6), # 6 = genus
        '--o-collapsed-table', f"{io_dir}/genus-table.qza"
    ], callback=callback)

    # normalize to get relative abundance
    runner.run([
        'qiime', 'feature-table', 'relative-frequency',
        '--i-table', f"{io_dir}/genus-table.qza",
        '--o-relative-frequency-table', f"{io_dir}/genus-relfreq.qza"
    ], callback=callback)

    # export to BIOM
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/genus-relfreq.qza",
        '--output-path', f"{io_dir}/genus"
    ], callback=callback)

    # convert to tsv
    runner.run([
        'biom', 'convert',
        '-i', f"{io_dir}/genus/feature-table.biom",
        '-o', f"{io_dir}/genus-table.tsv",
        '--to-tsv'
    ], callback=callback)

    # export representative sequences to FASTA (dna-sequences.fasta)
    # must happen before the .qza is moved, while it still lives in io_dir
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/rep-seqs.qza",
        '--output-path', reps_tree_dir
    ], callback=callback)

    # move rep-seqs.qza to a persistent folder for phylogeny inference
    runner.mv(file=f"{io_dir}/rep-seqs.qza", dir=reps_tree_dir)


def qiime_preprocess(runner: QiimeRunner, bioproject: str, lib_layout: str, callback=None):

    def _log(msg: str):
        print(msg)
        if callback:
            callback(msg)

    APP_DIR = Path(__file__).parent
    ref_phylo_db_dir_path = str((APP_DIR / REF_PHYLO_DB_DIR).resolve())
    os.makedirs(ref_phylo_db_dir_path, exist_ok=True)

    if REF_PHYLO_DB not in os.listdir(ref_phylo_db_dir_path):
        _log(f"Getting reference phylogeny database...")
        get_ref_phylo_db()

    _log(f"[{lib_layout}] Importing samples…")
    import_samples(runner, bioproject=bioproject, lib_layout=lib_layout, callback=callback)

    _log(f"[{lib_layout}] Running QC / demux summary…")
    trunc = qc(runner, bioproject=bioproject, lib_layout=lib_layout, callback=callback)

    _log(f"[{lib_layout}] DADA2 denoising…")
    if lib_layout == 'paired':
        dada2_denoise(runner, bioproject=bioproject, lib_layout=lib_layout,
                      trunc_f=trunc['forward'], trunc_r=trunc['reverse'], callback=callback)
    elif lib_layout == 'single':
        dada2_denoise(runner, bioproject=bioproject, lib_layout=lib_layout,
                      trunc_s=trunc['single'], callback=callback)

    _log(f"[{lib_layout}] Classifying taxa…")
    classify_taxa(runner, bioproject=bioproject, lib_layout=lib_layout, callback=callback)

    _log(f"[{lib_layout}] Creating output tables…")
    create_tables(runner, bioproject=bioproject, lib_layout=lib_layout, callback=callback)

    _log(f"[{lib_layout}] Inferring phylogeny…")
    infer_phylogeny(runner, bioproject=bioproject, lib_layout=lib_layout, callback=callback)

    _log(f"[{lib_layout}] Preprocessing complete.")
    

def download_classifier(classifier_url: str):

    output_dir = Path("taxa_classifier").resolve()
    output_dir.mkdir(exist_ok=True)

    classifier_file = output_dir / classifier_url.split("/")[-1]

    urllib.request.urlretrieve(classifier_url, classifier_file)


def get_ref_phylo_db():

    APP_DIR = Path(__file__).parent
    ref_phylo_db_dir_path = (APP_DIR / REF_PHYLO_DB_DIR).resolve()
    ref_phylo_db_dir_path.mkdir(parents=True, exist_ok=True)
    ref_phylo_db_path = ref_phylo_db_dir_path / REF_PHYLO_DB

    urllib.request.urlretrieve(REF_PHYLO_LINK, ref_phylo_db_path)
    