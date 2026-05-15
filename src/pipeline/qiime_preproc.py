from __future__ import annotations
import os
from pathlib import Path
from src.pipeline.qc import get_trunc
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qiime2_runner import QiimeRunner
    from src.models.app_state import AppState


REF_PHYLO_DB = "sepp-refs-silva-128.qza"
REF_PHYLO_DB_DIR = "ref_phylo_db"
REF_PHYLO_LINK = "https://data.qiime2.org/2023.5/common/sepp-refs-silva-128.qza"

SILVA_CLASSIFIER = "silva-138-99-nb-classifier.qza"
SILVA_CLASSIFIER_DIR = "taxa_classifier"
SILVA_CLASSIFIER_LINK = "https://data.qiime2.org/classifiers/sklearn-1.4.2/silva/silva-138-99-nb-classifier.qza"


# lib_layout = 'paired' or 'single'
def import_samples(runner: QiimeRunner, bioproject: str, lib_layout: str, state: AppState, callback=None):

    APP_DIR = Path(__file__).parent
    fastq_list = []
    input_dir = ""
    if state.local_paths['paired'] or state.local_paths['single']:
        # local runs uploaded
        fastq_list = state.local_paths[lib_layout]
        output_dir = str((APP_DIR / f"data/LOCAL_PROJECT/qiime/{lib_layout}").resolve())
    else:
        # runs downloaded from NCBI
        input_dir = str((APP_DIR / f"data/{bioproject}/fastq/{lib_layout}").resolve())
        output_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    demux_path = Path(output_dir) / "demux.qza"
    if demux_path.exists():
        return

    input_type = 'SampleData[PairedEndSequencesWithQuality]' \
                 if lib_layout == 'paired' \
                 else 'SampleData[SequencesWithQuality]'
    input_format = 'PairedEndFastqManifestPhred33V2' \
                   if lib_layout == 'paired' \
                   else 'SingleEndFastqManifestPhred33V2'

    # import runs
    if fastq_list or os.listdir(input_dir):
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
def qc(runner: QiimeRunner, bioproject: str, lib_layout: str, state: AppState, callback=None):

    APP_DIR = Path(__file__).parent
    if state.local_paths['paired'] or state.local_paths['single']:
        io_dir = str((APP_DIR / f"data/LOCAL_PROJECT/qiime/{lib_layout}").resolve())
    else:
        io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # calculate summary statistics (skip if already done)
    qzv_path = Path(io_dir) / "demux.qzv"
    if not qzv_path.exists():
        runner.run([
            'qiime', 'demux', 'summarize',
            '--i-data', f"{io_dir}/demux.qza",
            '--o-visualization', f"{io_dir}/demux.qzv"
        ], callback=callback)

    # get truncation positions for paired forward, paired reverse, and single
    return get_trunc(bioproject, lib_layout, state)


# lib_layout = 'paired' or 'single'
def dada2_denoise(runner: QiimeRunner, bioproject: str, lib_layout: str, state: AppState, trunc_f: int=None, trunc_r: int=None, trunc_s: int=None, callback=None):

    APP_DIR = Path(__file__).parent
    if state.local_paths['paired'] or state.local_paths['single']:
        io_dir = (APP_DIR / f"data/LOCAL_PROJECT/qiime/{lib_layout}").resolve()
    else:
        io_dir = Path(APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve()

    if (io_dir / "table.qza").exists():
        return

    io_dir = str(io_dir)

    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    # paired
    if trunc_f:
        # For paired-end, use deblur on forward reads only (as per deblur docs)
        runner.run([
            'qiime', 'deblur', 'denoise-16S',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-left-trim-len', '0',
            '--p-trim-length', str(trunc_f),
            '--p-jobs-to-start', cores,
            '--o-table', f"{io_dir}/table.qza",
            '--o-representative-sequences', f"{io_dir}/rep-seqs.qza",
            '--o-stats', f"{io_dir}/stats.qza"
        ], callback=callback)

    # single
    elif trunc_s:
        runner.run([
            'qiime', 'deblur', 'denoise-16S',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-left-trim-len', '0',
            '--p-trim-length', str(trunc_s),
            '--p-jobs-to-start', cores,
            '--o-table', f"{io_dir}/table.qza",
            '--o-representative-sequences', f"{io_dir}/rep-seqs.qza",
            '--o-stats', f"{io_dir}/stats.qza"
        ], callback=callback)


'''
classifier: silva-138-99-nb-classifier.qza
source: https://data.qiime2.org/classifiers/sklearn-1.4.2/silva/silva-138-99-nb-classifier.qza
'''
# lib_layout: 'paired' or 'single'
def classify_taxa(runner: QiimeRunner, bioproject: str, lib_layout: str, state: AppState, callback=None):

    APP_DIR = Path(__file__).parent
    classifier_path = str((APP_DIR / "taxa_classifier/silva-138-99-nb-classifier.qza").resolve())
    if state.local_paths['paired'] or state.local_paths['single']:
        io_dir = str((APP_DIR / f"data/LOCAL_PROJECT/qiime/{lib_layout}").resolve())
    else:
        io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # call the classifier on the denoised data
    runner.run([
        'qiime', 'feature-classifier', 'classify-sklearn',
        '--i-classifier', classifier_path,
        '--i-reads', f"{io_dir}/rep-seqs.qza",
        '--o-classification', f"{io_dir}/taxonomy.qza"
    ], callback=callback)
    

def infer_phylogeny(runner: QiimeRunner, bioproject: str, lib_layout: str, state: AppState, callback=None) -> str:
    """
    Build a rooted phylogenetic tree from representative sequences using
    MAFFT + FastTree2 (no reference DB download required).
    Returns the Newick string, or '' on failure.
    Skips inference if tree.nwk already exists.
    """
    APP_DIR = Path(__file__).parent
    if state.local_paths['paired'] or state.local_paths['single']:
        reps_tree_dir = (APP_DIR / f"data/LOCAL_PROJECT/reps-tree/{lib_layout}").resolve()
    else:
        reps_tree_dir = (APP_DIR / f"data/{bioproject}/reps-tree/{lib_layout}").resolve()
    nwk_file = reps_tree_dir / "tree.nwk"

    if nwk_file.exists():
        if callback:
            callback(f"[{lib_layout}] tree.nwk already exists — skipping phylogeny inference.")
        return nwk_file.read_text().strip()

    s = str(reps_tree_dir)
    cores = str(max(os.cpu_count() - 4, 1))

    try:
        runner.run([
            'qiime', 'phylogeny', 'align-to-tree-mafft-fasttree',
            '--i-sequences',        f"{s}/rep-seqs.qza",
            '--o-alignment',        f"{s}/aligned-rep-seqs.qza",
            '--o-masked-alignment', f"{s}/masked-aligned-rep-seqs.qza",
            '--o-tree',             f"{s}/unrooted-tree.qza",
            '--o-rooted-tree',      f"{s}/rooted-tree.qza",
            '--p-n-threads',        cores,
        ], callback=callback)

        runner.run([
            'qiime', 'tools', 'export',
            '--input-path',  f"{s}/rooted-tree.qza",
            '--output-path', s,
        ], callback=callback)
    except Exception as e:
        if callback:
            callback(f"[{lib_layout}] Phylogeny inference failed: {e}")
        return ""

    # clean up intermediate QZA files
    for fname in ("aligned-rep-seqs.qza", "masked-aligned-rep-seqs.qza",
                  "unrooted-tree.qza", "rooted-tree.qza"):
        (reps_tree_dir / fname).unlink(missing_ok=True)

    return nwk_file.read_text().strip() if nwk_file.exists() else ""


# lib_layout: 'paired' or 'single'
def create_tables(runner: QiimeRunner, bioproject: str, lib_layout: str, state: AppState, has_taxonomy: bool = True, callback=None):

    APP_DIR = Path(__file__).parent
    if state.local_paths['paired'] or state.local_paths['single']:
        io_dir = str((APP_DIR / f"data/LOCAL_PROJECT/qiime/{lib_layout}").resolve())
        reps_tree_dir = str((APP_DIR / f"data/LOCAL_PROJECT/reps-tree/{lib_layout}").resolve())
    else:
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
    if has_taxonomy:
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
    # Always regenerate — stale FASTA from a prior cleanup causes FK violations in feature_count
    fasta_path = Path(reps_tree_dir) / "dna-sequences.fasta"
    fasta_path.unlink(missing_ok=True)
    rep_seqs_src = (
        f"{io_dir}/rep-seqs.qza"
        if Path(f"{io_dir}/rep-seqs.qza").exists()
        else f"{reps_tree_dir}/rep-seqs.qza"
    )
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', rep_seqs_src,
        '--output-path', reps_tree_dir
    ], callback=callback)

    # move rep-seqs.qza to a persistent folder for phylogeny inference (idempotent)
    if Path(f"{io_dir}/rep-seqs.qza").exists():
        runner.mv(file=f"{io_dir}/rep-seqs.qza", dir=reps_tree_dir)


def qiime_preprocess(runner: QiimeRunner, bioproject: str, lib_layout: str, state: AppState, callback=None):

    def _log(msg: str):
        print(msg)
        if callback:
            callback(msg)

    APP_DIR = Path(__file__).parent

    # ensure SILVA classifier is present
    silva_path = (APP_DIR / SILVA_CLASSIFIER_DIR / SILVA_CLASSIFIER).resolve()
    if not silva_path.exists():
        _log("Downloading SILVA classifier (this may take a while)…")
        get_silva_classifier()

    _log(f"[{lib_layout}] Importing samples…")
    import_samples(runner, bioproject=bioproject, lib_layout=lib_layout, state=state, callback=callback)

    _log(f"[{lib_layout}] Running QC / demux summary…")
    trunc = qc(runner, bioproject=bioproject, lib_layout=lib_layout, state=state, callback=callback)

    _log(f"[{lib_layout}] Denoising…")
    if lib_layout == 'paired':
        dada2_denoise(runner, bioproject=bioproject, lib_layout=lib_layout,
                      trunc_f=trunc['forward'], trunc_r=trunc['reverse'], 
                      state=state, callback=callback)
    elif lib_layout == 'single':
        dada2_denoise(runner, bioproject=bioproject, lib_layout=lib_layout,
                      trunc_s=trunc['single'], state=state, callback=callback)

    if state.local_paths['paired'] or state.local_paths['single']:
        io_dir = APP_DIR / f"data/LOCAL_PROJECT/qiime/{lib_layout}"
        reps_tree_dir = APP_DIR / f"data/LOCAL_PROJECT/reps-tree/{lib_layout}"
    else:
        io_dir = APP_DIR / f"data/{bioproject}/qiime/{lib_layout}"
        reps_tree_dir = APP_DIR / f"data/{bioproject}/reps-tree/{lib_layout}"

    # If denoising did not produce table.qza, nothing left to do
    if not (io_dir / "table.qza").exists():
        _log(f"[{lib_layout}] Denoising did not produce output — skipping remaining steps. "
             "Check that the run contains 16S amplicon data.")
        return

    # Taxonomy — skip if already done (rep-seqs.qza may have been moved on a re-run)
    _log(f"[{lib_layout}] Classifying taxa…")
    if (io_dir / "taxonomy.qza").exists():
        _log(f"[{lib_layout}] Taxonomy already classified — skipping.")
        has_taxonomy = True
    elif not (io_dir / "rep-seqs.qza").exists() and (reps_tree_dir / "rep-seqs.qza").exists():
        _log(f"[{lib_layout}] rep-seqs.qza already moved to reps-tree — skipping taxonomy re-run.")
        has_taxonomy = False
    else:
        try:
            classify_taxa(runner, bioproject=bioproject, lib_layout=lib_layout, state=state, callback=callback)
            has_taxonomy = True
        except Exception as e:
            _log(f"[{lib_layout}] Taxonomy classification failed: {e}")
            _log(f"[{lib_layout}] ** WARNING: Taxonomy assignment skipped. Genus-level analysis will not be available. **")
            has_taxonomy = False

    # Create output tables — skip if already done
    _log(f"[{lib_layout}] Creating output tables…")
    if (io_dir / "feature-table.tsv").exists():
        _log(f"[{lib_layout}] Output tables already exist — skipping.")
    else:
        create_tables(runner, bioproject=bioproject, lib_layout=lib_layout,
                      has_taxonomy=has_taxonomy, state=state, callback=callback)

    _log(f"[{lib_layout}] Preprocessing complete.")
    

def download_classifier(classifier_url: str):

    APP_DIR = Path(__file__).parent
    output_dir = (APP_DIR / "taxa_classifier").resolve()
    output_dir.mkdir(exist_ok=True)

    classifier_file = output_dir / classifier_url.split("/")[-1]

    urllib.request.urlretrieve(classifier_url, classifier_file)


def get_silva_classifier():

    APP_DIR = Path(__file__).parent
    classifier_dir = (APP_DIR / SILVA_CLASSIFIER_DIR).resolve()
    classifier_dir.mkdir(parents=True, exist_ok=True)
    classifier_path = classifier_dir / SILVA_CLASSIFIER

    urllib.request.urlretrieve(SILVA_CLASSIFIER_LINK, classifier_path)


def get_ref_phylo_db():

    APP_DIR = Path(__file__).parent
    ref_phylo_db_dir_path = (APP_DIR / REF_PHYLO_DB_DIR).resolve()
    ref_phylo_db_dir_path.mkdir(parents=True, exist_ok=True)
    ref_phylo_db_path = ref_phylo_db_dir_path / REF_PHYLO_DB

    urllib.request.urlretrieve(REF_PHYLO_LINK, ref_phylo_db_path)
    