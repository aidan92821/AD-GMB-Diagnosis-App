import pandas as pd
import os, sys

# get the minimum run length
EXT = '.fastq'
fastqs = []
lengths = []

# get fastq files from BioProject
files = os.listdir(f"../../fastq_files/{sys.argv[1]}")
for file in files:
    if EXT in file: fastqs.append(file)

for fastq in fastqs:
    try:
        with open(f"../../fastq_files/{sys.argv[1]}/{fastq}", 'r', encoding='utf-8') as f:
            line = f.readline().split()[2]
            length = line.split(sep='=')
            lengths.append(length[1])
    except FileNotFoundError:
        print(f"Error: The file {fastq} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

min_trunc = min(lengths)


# get the qc based trunc length
forward = pd.read_csv("demux_summary/forward-seven-number-summaries.tsv", sep='\t')

# transpose to get the percentiles as columns
forward = forward.T

# clean up the columns
forward.columns = forward.iloc[0]
forward = forward.iloc[1:, :]

# fix the dtype
median = forward["50%"].astype(float)

# acceptable quality threshold lower bound
QUALITY_THRESHOLD = 25

# find the first position where quality drops below threshold
pos = median <= QUALITY_THRESHOLD

if pos.any():
    trunc_len = pos.idmax()
else:
    trunc_len = len(median)

# return the minimum possible trunc length
print(min(int(trunc_len) - 17, int(min_trunc) - 17))