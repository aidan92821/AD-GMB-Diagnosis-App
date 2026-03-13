import os
from pathlib import Path
import subprocess
from environment import get_conda_env_path
from qc import get_trunc


# interact with qiime environment
ENV_NAME = "qiime2-amplicon-2024.10"
env_path = get_conda_env_path(ENV_NAME)
BIN = env_path / "bin"
QIIME = BIN / "qiime"
BIOM = BIN / "biom"

env = os.environ.copy()
env["PATH"] = f"{BIN}:{env['PATH']}"
env["CONDA_PREFIX"] = str(env_path)


# lib_layout = 'paired' or 'single'
def import_samples(bioproject: str, lib_layout: str):
    
    output_dir = f"data/{bioproject}/qiime/{lib_layout}"
    input_type = 'SampleData[PairedEndSequencesWithQuality]' \
                    if lib_layout == 'paired' \
                    else 'SampleData[SequencesWithQuality]'
    input_format = 'PairedEndFastqManifestPhred33V2' \
                    if lib_layout == 'paired' \
                    else 'SingleEndFastqManifestPhred33V2'

    # import runs
    if os.listdir(f"data/{bioproject}/fastq/{lib_layout}"):
        subprocess.run([
            str(QIIME), 'tools', 'import',
            '--type', input_type,
            '--input-path', f"{output_dir}/manifest.tsv",
            '--output-path', f"{output_dir}/demux.qza",
            '--input-format', input_format
        ], check=True, env=env)


# lib_layout = 'paired' or 'single'
# returns a dict of size 0, 1 or 2
# 0 -> something weird happened
# 1 -> single with key: 'single'
# 2 -> paired with keys: 'forward', 'reverse' in that order
def qc(bioproject: str, lib_layout: str):
    
    io_dir = f"data/{bioproject}/qiime/{lib_layout}"

    # calculate summary statistics
    subprocess.run([
        str(QIIME), 'demux', 'summarize',
        '--i-data', f"{io_dir}/demux.qza",
        '--o-visualization', f"{io_dir}/demux.qzv"
    ], check=True, env=env)
    
    # get truncation positions for paired forward, paired reverse, and single
    return get_trunc(bioproject, lib_layout)


# lib_layout = 'paired' or 'single'
def dada2_denoise(bioproject: str, lib_layout: str, trunc_f: int=None, trunc_r: int=None, trunc_s: int=None):
    
    io_dir = f"data/{bioproject}/qiime/{lib_layout}"
    
    # get the number of cores from user's machine
    # and calculate how many to use for the process
    cores = os.cpu_count()
    cores = str(max(cores - 4, 1))

    # paired
    if trunc_f:
        subprocess.run([
            str(QIIME), 'dada2', 'denoise-paired',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-trim-left-f', '17',
            '--p-trim-left-r', '21',
            '--p-trunc-len-f', str(trunc_f),
            '--p-trunc-len-r', str(trunc_r),
            '--p-n-threads', cores,
            '--o-table', f"{io_dir}/table.qza",
            '--o-representative-sequences', f"{io_dir}/rep-seqs.qza",
            '--o-denoising-stats', f"{io_dir}/stats.qza"
        ], check=True, env=env)
    # single
    elif trunc_s:
        subprocess.run([
            str(QIIME), 'dada2', 'denoise-single',
            '--i-demultiplexed-seqs', f"{io_dir}/demux.qza",
            '--p-trim-left', '17',
            '--p-trunc-len', str(trunc_s),
            '--p-n-threads', cores,
            '--o-table', f"{io_dir}/table.qza",
            '--o-representative-sequences', f"{io_dir}/rep-seqs.qza",
            '--o-denoising-stats', f"{io_dir}/stats.qza"
        ], check=True, env=env)


# lib_layout: 'paired' or 'single'
def classify_taxa(bioproject: str, lib_layout: str):
    
    classifier_path = "taxa_classifier/silva-138-99-nb-classifier.qza"
    io_dir = f"data/{bioproject}/qiime/{lib_layout}"

    # call the classifier on the denoised data
    subprocess.run([
        str(QIIME), 'feature-classifier', 'classify-sklearn',
        '--i-classifier', classifier_path,
        '--i-reads', f"{io_dir}/rep-seqs.qza",
        '--o-classification', f"{io_dir}/taxonomy.qza"
    ], check=True, env=env)
    

# lib_layout: 'paired' or 'single'
def create_tables(bioproject: str, lib_layout: str):
    
    io_dir = f"data/{bioproject}/qiime/{lib_layout}"

    # representative sequences (asvs to seqs) (rep-seqs.fasta)
    # this needs to go in a separate directory for conservation
    Path(f"data/{bioproject}/reps-tree/{lib_layout}").mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(QIIME), 'tools', 'export',
        '--input-path', f"{io_dir}/rep-seqs.qza",
        '--output-path', f"data/{bioproject}/reps-tree/{lib_layout}"
    ], check=True, env=env)

    # feature table (asv counts) (feature-table.tsv)
    subprocess.run([
        str(QIIME), 'tools', 'export',
        '--input-path', f"{io_dir}/table.qza",
        '--output-path', f"{io_dir}/features"
    ], check=True, env=env)
    subprocess.run([
        str(BIOM), 'convert',
        '-i', f"{io_dir}/features/feature-table.biom",
        '-o', f"{io_dir}/feature-table.tsv",
        '--to-tsv'
    ], check=True, env=env)

    # asv to taxonomy map table (taxonomy.tsv)
    subprocess.run([
        str(QIIME), 'tools', 'export',
        '--input-path', f"{io_dir}/taxonomy.qza",
        '--output-path', f"{io_dir}"
    ], check=True, env=env)

    # genus relative abundance table (genus-table.tsv)
    # collapse ASV table to genus level abundance
    subprocess.run([
        str(QIIME), 'taxa', 'collapse',
        '--i-table', f"{io_dir}/table.qza",
        '--i-taxonomy', f"{io_dir}/taxonomy.qza",
        '--p-level', str(6), # 6 = genus
        '--o-collapsed-table', f"{io_dir}/genus-table.qza"
    ], check=True, env=env)
    # normalize to get relative abundance
    subprocess.run([
        str(QIIME), 'feature-table', 'relative-frequency',
        '--i-table', f"{io_dir}/genus-table.qza",
        '--o-relative-frequency-table', f"{io_dir}/genus-relfreq.qza"
    ], check=True, env=env)
    # export to BIOM
    subprocess.run([
        str(QIIME), 'tools', 'export',
        '--input-path', f"{io_dir}/genus-relfreq.qza",
        '--output-path', f"{io_dir}/genus"
    ], check=True, env=env)
    # convert to tsv
    subprocess.run([
        str(BIOM), 'convert',
        '-i', f"{io_dir}/genus/feature-table.biom",
        '-o', f"{io_dir}/genus-table.tsv",
        '--to-tsv'
    ], check=True, env=env)