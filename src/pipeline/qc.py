"""
src/pipeline/qc.py  —  FIXED VERSION

Bugs fixed vs original:
  1. get_min_run_len: return min(lengths) operated on strings → returns int now
  2. find_median_drop: pos.idmax() → pos.idxmax()  (AttributeError crash)
"""

import pandas as pd
import os
import zipfile


# lib_layout = 'paired' or 'single'
# fastqs     = list of fastq filenames
def get_min_run_len(bioproject: str, lib_layout: str, fastqs: list[str]) -> int:
    """
    Read the 'length=N' field from the first header line of each FASTQ
    and return the minimum read length as an INT across all files.

    FIX: lengths were collected as strings; min() on strings gives the
    lexicographically smallest value, not the numerically smallest.
    e.g. min(['251', '75', '200']) == '200' not '75'.
    Fixed by converting each value to int before returning the minimum.
    """
    lengths: list[int] = []

    try:
        for fastq in fastqs:
            with open(f"data/{bioproject}/fastq/{lib_layout}/{fastq}",
                      'r', encoding='utf-8') as f:
                header = f.readline().split()
                # Header format: @SRR26189186.1 1 length=251
                # Grab the 3rd token "length=251" and split on '='
                length_token = header[2]
                length_value = int(length_token.split('=')[1])  # FIX: cast to int
                lengths.append(length_value)

    except FileNotFoundError:
        print(f"Error: The file {fastq} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return min(lengths)   # now compares integers correctly


def find_median_drop(sns: pd.DataFrame, quality_threshold: int) -> int:
    """
    Given a QIIME2 seven-number-summary DataFrame, return the first base
    position where the median quality score drops at or below
    quality_threshold.

    FIX: pos.idmax() → pos.idxmax()
    pandas.Series has .idxmax() (returns index label of max value),
    not .idmax().  Calling idmax() raises AttributeError at runtime.
    """
    # Transpose so rows = base positions, columns = percentile labels
    sns = sns.T

    # Row 0 after transpose is the old column header — promote to column names
    sns.columns = sns.iloc[0]
    sns = sns.iloc[1:, :]

    median = sns["50%"].astype(float)

    # Find positions where median quality is at or below the threshold
    below_threshold = median <= quality_threshold

    if below_threshold.any():
        # FIX: idmax() → idxmax()
        # idxmax() returns the index *label* of the first True value
        trunc_len = below_threshold.idxmax()
    else:
        # All positions are above threshold — use the full read length
        trunc_len = len(median)

    return trunc_len


# lib_layout = 'paired' or 'single'
# Returns a dict:
#   paired → {'forward': int, 'reverse': int}
#   single → {'single': int}
#   error  → {}  (empty dict)
def get_trunc(bioproject: str, lib_layout: str) -> dict:
    """
    Determine safe truncation lengths for DADA2 denoising by:
      1. Finding the minimum read length in each FASTQ file
      2. Finding the first base position where median quality drops below 25
      3. Taking the stricter (smaller) of the two values

    The - 17 / - 21 offsets account for primer trim-left values used in
    dada2_denoise() so the truncation position is consistent.
    """
    QUALITY_THRESHOLD = 25

    input_dir_fastq = f"data/{bioproject}/fastq/{lib_layout}"
    input_dir_qiime = f"data/{bioproject}/qiime/{lib_layout}"

    # Organise files into forward (_1) and reverse (_2) lists
    files = os.listdir(input_dir_fastq)
    forward, reverse = [], []
    if files:
        for file in files:
            if '_1.fastq' in file:
                forward.append(file)
            elif '_2.fastq' in file:
                reverse.append(file)

    # Minimum read lengths per orientation
    if forward:
        min_trunc_forward = get_min_run_len(bioproject, 'paired', forward)
        min_trunc_reverse = get_min_run_len(bioproject, 'paired', reverse)
    else:
        min_trunc_single = get_min_run_len(bioproject, 'single', files)

    # Extract per-position quality statistics from the QIIME2 visualisation
    with zipfile.ZipFile(f"{input_dir_qiime}/demux.qzv") as z:

        # Locate the UUID directory containing the TSV files
        uuid = None
        for name in z.namelist():
            if name.endswith("-seven-number-summaries.tsv"):
                uuid = name.split('/')[0]
                break

        if uuid is None:
            print("Warning: could not locate seven-number-summaries.tsv in demux.qzv")
            return {}

        if forward:
            with z.open(f"{uuid}/data/forward-seven-number-summaries.tsv") as f:
                f_sns = pd.read_csv(f, sep='\t')
                trunc_forward = min(
                    int(find_median_drop(f_sns, QUALITY_THRESHOLD)) - 17,
                    int(min_trunc_forward) - 17
                )
            with z.open(f"{uuid}/data/reverse-seven-number-summaries.tsv") as r:
                r_sns = pd.read_csv(r, sep='\t')
                trunc_reverse = min(
                    int(find_median_drop(r_sns, QUALITY_THRESHOLD)) - 21,
                    int(min_trunc_reverse) - 21
                )
            return {'forward': trunc_forward, 'reverse': trunc_reverse}

        else:
            with z.open(f"{uuid}/data/forward-seven-number-summaries.tsv") as s:
                s_sns = pd.read_csv(s, sep='\t')
                trunc_single = min(
                    int(find_median_drop(s_sns, QUALITY_THRESHOLD)) - 17,
                    int(min_trunc_single) - 17
                )
            return {'single': trunc_single}

    return {}