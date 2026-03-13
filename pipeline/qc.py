import pandas as pd
import os
import zipfile


# lib_layout = 'paired' or 'single'
# fastqs = list of fastq filenames
def get_min_run_len(bioproject: str, lib_layout: str, fastqs: list[str]) -> int:
    
    lengths = []

    try:
        for fastq in fastqs:
            with open(f"data/{bioproject}/fastq/{lib_layout}/{fastq}", 'r', encoding='utf-8') as f:
                    line = f.readline().split()[2] # or find substr == length might be better
                    length = line.split(sep='=')
                    lengths.append(length[1])
    except FileNotFoundError:
        print(f"Error: The file {fastq} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return min(lengths)


# sns = seven number summary dataframe
# returns first base position where quality drops below threshold
def find_median_drop(sns, quality_threshold: int) -> int:
    
    # transpose to get the percentiles as columns
    sns = sns.T

    # clean up the columns
    sns.columns = sns.iloc[0]
    sns = sns.iloc[1:, :]

    # fix the dtype
    median = sns["50%"].astype(float)

    # find the first position where quality drops below threshold
    pos = median <= quality_threshold
    if pos.any():
        trunc_len = pos.idmax()
    else:
        trunc_len = len(median)

    return trunc_len


# lib_layout = 'paired' or 'single'
# returns a dict of size 0, 1 or 2
# 0 -> something weird happened
# 1 -> single with key: 'single'
# 2 -> paired with keys: 'forward', 'reverse' in that order
def get_trunc(bioproject: str, lib_layout: str):

    QUALITY_THRESHOLD = 25

    input_dir_fastq = f"data/{bioproject}/fastq/{lib_layout}"
    input_dir_qiime = f"data/{bioproject}/qiime/{lib_layout}"

    # organize the fastq types
    files = os.listdir(input_dir_fastq)
    if files:
        # if single, they will all be contained in files list
        forward, reverse = [], []
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
                trunc_forward = min(int(find_median_drop(f_sns, QUALITY_THRESHOLD)) - 17,
                                    int(min_trunc_forward) - 17)
            with z.open(f"{uuid}/data/reverse-seven-number-summaries.tsv") as r:
                r_sns = pd.read_csv(r, sep='\t')
                trunc_reverse = min(int(find_median_drop(r_sns, QUALITY_THRESHOLD)) - 21,
                                    int(min_trunc_reverse) - 21)
            return {'forward': trunc_forward,
                    'reverse': trunc_reverse}
        else:
            with z.open(f"{uuid}/data/forward-seven-number-summaries.tsv") as s:
                s_sns = pd.read_csv(s, sep='\t')
                trunc_single = min(int(find_median_drop(s_sns, QUALITY_THRESHOLD)) - 17,
                                   int(min_trunc_single) - 17)
            return {'single': trunc_single}
    
    return []