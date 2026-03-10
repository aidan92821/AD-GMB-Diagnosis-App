import pandas as pd
import os, sys

# get the minimum run lengths for forward and reverse
EXT_f = '_1.fastq'
EXT_r = '_2.fastq'
fastqs_forward = []
fastqs_reverse = []
lengths_forward = []
lengths_reverse = []

# get fastq files from BioProject
files = os.listdir(f"../../fastq_files/{sys.argv[1]}")
for file in files:
    if EXT_f in file: 
        fastqs_forward.append(file)
    elif EXT_r in file:
        fastqs_reverse.append(file)

for fastq_f, fastq_r in zip(fastqs_forward, fastqs_reverse):
    try:
        with open(f"../../fastq_files/{sys.argv[1]}/{fastq_f}", 'r', encoding='utf-8') as f:
            line = f.readline().split()[2]
            length = line.split(sep='=')
            lengths_forward.append(length[1])
    except FileNotFoundError:
        print(f"Error: The file {fastq_f} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    try:
        with open(f"../../fastq_files/{sys.argv[1]}/{fastq_r}", 'r', encoding='utf-8') as f:
            line = f.readline().split()[2]
            length = line.split(sep='=')
            lengths_reverse.append(length[1])
    except FileNotFoundError:
        print(f"Error: The file {fastq_r} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

min_trunc_f = min(lengths_forward)
min_trunc_r = min(lengths_reverse)

# get qc based trunc length
forward = pd.read_csv("demux_summary/forward-seven-number-summaries.tsv", sep='\t')
reverse = pd.read_csv("demux_summary/reverse-seven-number-summaries.tsv", sep='\t')

# transpose to get the percentiles as columns
forward = forward.T
reverse = reverse.T

# clean up the columns
forward.columns = forward.iloc[0]
forward = forward.iloc[1:, :]
reverse.columns = reverse.iloc[0]
reverse = reverse.iloc[1:, :]

# fix the dtype
median_forward = forward["50%"].astype(float)
median_reverse = reverse["50%"].astype(float)

# acceptable quality threshold lower bound
QUALITY_THRESHOLD = 25

# find the first position where quality drops below threshold
pos = median_forward <= QUALITY_THRESHOLD
if pos.any():
    trunc_len_forward = pos.idmax()
else:
    trunc_len_forward = len(median_forward)

pos = median_reverse <= QUALITY_THRESHOLD
if pos.any():
    trunc_len_reverse = pos.idmax()
else:
    trunc_len_reverse = len(median_reverse)

print(min(int(trunc_len_forward) - 17, int(min_trunc_f) - 17), 
      min(int(trunc_len_reverse) - 21, int(min_trunc_r) - 21))