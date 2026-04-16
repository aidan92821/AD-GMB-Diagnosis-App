import os
from pathlib import Path
from src.pipeline.qc import get_trunc
import urllib.request


# lib_layout = 'paired' or 'single'
def import_samples(runner, bioproject: str, lib_layout: str):
    
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
        ])


# lib_layout = 'paired' or 'single'
# returns a dict of size 0, 1 or 2
# 0 -> something weird happened
# 1 -> single with key: 'single'
# 2 -> paired with keys: 'forward', 'reverse' in that order
def qc(runner, bioproject: str, lib_layout: str):
    
    APP_DIR = Path(__file__).parent
    io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # calculate summary statistics
    runner.run([
        'qiime', 'demux', 'summarize',
        '--i-data', f"{io_dir}/demux.qza",
        '--o-visualization', f"{io_dir}/demux.qzv"
    ])

    # get truncation positions for paired forward, paired reverse, and single
    return get_trunc(bioproject, lib_layout)


# lib_layout = 'paired' or 'single'
def dada2_denoise(runner, bioproject: str, lib_layout: str, trunc_f: int=None, trunc_r: int=None, trunc_s: int=None):
    
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
        ])

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
        ])


'''
classifier: silva-138-99-nb-classifier.qza
source: https://data.qiime2.org/classifiers/sklearn-1.4.2/silva/silva-138-99-nb-classifier.qza
'''
# lib_layout: 'paired' or 'single'
def classify_taxa(runner, bioproject: str, lib_layout: str):
    
    APP_DIR = Path(__file__).parent
    classifier_path = str((APP_DIR / "taxa_classifier/silva-138-99-nb-classifier.qza").resolve())
    io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # call the classifier on the denoised data
    runner.run([
        'qiime', 'feature-classifier', 'classify-sklearn',
        '--i-classifier', classifier_path,
        '--i-reads', f"{io_dir}/rep-seqs.qza",
        '--o-classification', f"{io_dir}/taxonomy.qza"
    ])
    

# lib_layout: 'paired' or 'single'
def create_tables(runner, bioproject: str, lib_layout: str):
    
    APP_DIR = Path(__file__).parent
    io_dir = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())
    reps_tree_dir = str((APP_DIR / f"data/{bioproject}/reps-tree/{lib_layout}").resolve())

    # representative sequences (asvs to seqs) (rep-seqs.fasta)
    # this needs to go in a separate directory for conservation
    Path(reps_tree_dir).mkdir(parents=True, exist_ok=True)
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/rep-seqs.qza",
        '--output-path', reps_tree_dir
    ])

    # feature table (asv counts) (feature-table.tsv)
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/table.qza",
        '--output-path', f"{io_dir}/features"
    ])
    runner.run([
        'biom', 'convert',
        '-i', f"{io_dir}/features/feature-table.biom",
        '-o', f"{io_dir}/feature-table.tsv",
        '--to-tsv'
    ])

    # asv to taxonomy map table (taxonomy.tsv)
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/taxonomy.qza",
        '--output-path', f"{io_dir}"
    ])

    # genus relative abundance table (genus-table.tsv)
    # collapse ASV table to genus level abundance
    runner.run([
        'qiime', 'taxa', 'collapse',
        '--i-table', f"{io_dir}/table.qza",
        '--i-taxonomy', f"{io_dir}/taxonomy.qza",
        '--p-level', str(6), # 6 = genus
        '--o-collapsed-table', f"{io_dir}/genus-table.qza"
    ])
    
    # normalize to get relative abundance
    runner.run([
        'qiime', 'feature-table', 'relative-frequency',
        '--i-table', f"{io_dir}/genus-table.qza",
        '--o-relative-frequency-table', f"{io_dir}/genus-relfreq.qza"
    ])
    
    # export to BIOM
    runner.run([
        'qiime', 'tools', 'export',
        '--input-path', f"{io_dir}/genus-relfreq.qza",
        '--output-path', f"{io_dir}/genus"
    ])
    
    # convert to tsv
    runner.run([
        'biom', 'convert',
        '-i', f"{io_dir}/genus/feature-table.biom",
        '-o', f"{io_dir}/genus-table.tsv",
        '--to-tsv'
    ])


def qiime_preprocess(runner, bioproject: str, lib_layout: str):
    
    print('importing samples')
    import_samples(runner,
                   bioproject=bioproject,
                   lib_layout=lib_layout)

    print('doing qc')
    trunc = qc(runner,
               bioproject=bioproject, 
               lib_layout=lib_layout)

    print('denoising')
    if lib_layout == 'paired':
        dada2_denoise(runner,
                      bioproject=bioproject,
                      lib_layout=lib_layout,
                      trunc_f=trunc['forward'],
                      trunc_r=trunc['reverse'])
    elif lib_layout == 'single':
        dada2_denoise(runner,
                      bioproject=bioproject,
                      lib_layout=lib_layout,
                      trunc_s=trunc['single'])

    print('classifying taxa')
    classify_taxa(runner,
                  bioproject=bioproject,
                  lib_layout=lib_layout)

    print('creating tables')
    create_tables(runner,
                  bioproject=bioproject,
                  lib_layout=lib_layout)
    

def download_classifier(classifier_url: str):

    output_dir = Path("taxa_classifier").resolve()
    output_dir.mkdir(exist_ok=True)

    classifier_file = output_dir / classifier_url.split("/")[-1]

    urllib.request.urlretrieve(classifier_url, classifier_file)
