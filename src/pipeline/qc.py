import pandas as pd
from pathlib import Path
import os
import zipfile


# lib_layout = 'paired' or 'single'
# fastqs = list of fastq filenames
def get_min_run_len(bioproject: str, lib_layout: str, fastqs: list[str]) -> int:
    
    print('get min run length')
    APP_DIR = Path(__file__).parent
    input_dir = str((APP_DIR / f"data/{bioproject}/fastq/{lib_layout}").resolve())
    
    lengths = []

    try:
        for fastq in fastqs:
            with open(f"{input_dir}/{fastq}", 'r', encoding='utf-8') as f:
                f.readline()           # skip header (@...)
                seq = f.readline().strip()  # actual sequence
                if seq:
                    lengths.append(len(seq))
    except Exception as e:
            print(f"An error occurred reading {fastq}: {e}")

    return min(lengths) if lengths else 0


# sns = seven number summary dataframe
# returns first base position where quality drops below threshold
def find_median_drop(sns, quality_threshold: int) -> int:
    
    print('find median drop')
    # convert to DataFrame if a file-like object was passed
    if not isinstance(sns, pd.DataFrame):
        sns = pd.read_csv(sns, sep='\t', index_col=0)
    else:
        # if the first column is the percentile label, use it as the index
        if sns.columns[0] == 'Unnamed: 0' or sns.columns[0].startswith('Unnamed'):
            sns = sns.set_index(sns.columns[0])
        else:
            sns = sns.set_index(sns.columns[0])

    if "50%" not in sns.index:
        raise ValueError("Missing 50% row in quality summary")

    median = sns.loc["50%"].astype(float)
    pos = median <= quality_threshold
    if pos.any():
        trunc_len = int(pos.idxmax())
    else:
        trunc_len = len(median)

    return trunc_len


# lib_layout = 'paired' or 'single'
# returns a dict of size 0, 1 or 2
# 0 -> something weird happened
# 1 -> single with key: 'single'
# 2 -> paired with keys: 'forward', 'reverse' in that order
def get_trunc(bioproject: str, lib_layout: str):

    print("get trunc")
    QUALITY_THRESHOLD = 25

    APP_DIR = Path(__file__).parent
    input_dir_fastq = str((APP_DIR / f"data/{bioproject}/fastq/{lib_layout}").resolve())
    input_dir_qiime = str((APP_DIR / f"data/{bioproject}/qiime/{lib_layout}").resolve())

    # organize the fastq types (ignore non-.fastq files like .sra)
    files = [f for f in os.listdir(input_dir_fastq) if f.endswith('.fastq')]
    forward, reverse = [], []
    if files:
        # if single, they will all be contained in files list
        for file in files:
            if '_1.fastq' in file:
                forward.append(file)
            elif '_2.fastq' in file:
                reverse.append(file)

    # find the smallest run length
    if forward:
        min_trunc_forward = get_min_run_len(bioproject, 'paired', forward)
        min_trunc_reverse = get_min_run_len(bioproject, 'paired', reverse)
    else:
        min_trunc_single = get_min_run_len(bioproject, 'single', files)

    # find first base position where median read quality drops below the threshold
    with zipfile.ZipFile(f"{input_dir_qiime}/demux.qzv") as z:
        for name in z.namelist():
            if name.endswith("-seven-number-summaries.tsv"):
                uuid = name.split(sep='/')[0]
        if forward:
            with z.open(f"{uuid}/data/forward-seven-number-summaries.tsv") as f:
                f_sns = pd.read_csv(f, sep='\t')
                med_drop_f = int(find_median_drop(f_sns, QUALITY_THRESHOLD))
                if (med_drop_f <= 17) or (min_trunc_forward / med_drop_f >= 2):
                    trunc_forward = int(min_trunc_forward) - 17
                else:
                    trunc_forward = min(med_drop_f - 17,
                                        int(min_trunc_forward) - 17)
            with z.open(f"{uuid}/data/reverse-seven-number-summaries.tsv") as r:
                r_sns = pd.read_csv(r, sep='\t')
                med_drop_r = int(find_median_drop(r_sns, QUALITY_THRESHOLD))
                if (med_drop_r <= 21) or (min_trunc_reverse / med_drop_r >= 2):
                    trunc_reverse = int(min_trunc_reverse) - 21
                else:
                    trunc_reverse = min(med_drop_r - 21,
                                        int(min_trunc_reverse) - 21)
            return {'forward': trunc_forward,
                    'reverse': trunc_reverse}
        else:
            with z.open(f"{uuid}/data/forward-seven-number-summaries.tsv") as s:
                s_sns = pd.read_csv(s, sep='\t')
                med_drop_s = int(find_median_drop(s_sns, QUALITY_THRESHOLD))
                if (med_drop_s <= 17) or (min_trunc_single / med_drop_s >= 2):
                    trunc_single = int(min_trunc_single) - 17
                else:
                    trunc_single = min(med_drop_s - 17,
                                        int(min_trunc_single) - 17)
            return {'single': trunc_single}
    
    return []
